from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminEspecialidad,
    AccesoAdminPermiso,
)
from app.models.usuario import Usuario
from app.schemas import (
    AccesoAdministrativoEfectivoOut,
    AccesoAdministrativoGestionOut,
    AccesoAdministrativoGestionUpdate,
    CatalogoAccesoAdministrativoOut,
    UsuarioAdministrativoCreate,
    UsuarioAdministrativoEstadoUpdate,
    UsuarioAdministrativoOut,
    UsuarioAdministrativoRolUpdate,
    UsuarioMeOut,
    UsuarioMeUpdate,
)
from app.auth_dependencies import get_current_user, verificar_rol
from app.auditoria import registrar_evento_auditoria
from app.bootstrap_superadmin import _password_cumple_politica_existente
from app.rbac.admin_access import (
    PERFILES_INSTITUCIONALES,
    PerfilAccesoAdmin,
    TipoAlcanceAdmin,
    permisos_permitidos_para_perfil,
    validar_configuracion_acceso_admin,
    validar_permisos_para_perfil,
)
from app.rbac.admin_authorization import (
    obtener_acceso_administrativo_efectivo,
)
from app.rbac.dependencies import require_permission
from app.rbac.permissions import Permission
from app.rbac.roles import Role
from app.security import hash_password

router = APIRouter(
    prefix="/usuarios",
    tags=["usuarios"],
)

_ROLES_ADMINISTRATIVOS = (Role.ADMIN.value, Role.SUPERADMIN.value)


def _obtener_usuario_actual(db: Session, current_user: dict) -> Usuario:
    """
    Carga el registro completo de Usuario correspondiente a
    current_user["id"].

    Mi Perfil nunca acepta un usuario_id del cliente: la identidad
    siempre sale del token verificado (current_user), nunca del body
    o de la URL. Esto garantiza que un ADMIN/SUPERADMIN solo pueda
    leer/editar su propio registro (aislamiento entre usuarios).

    Si el id del token no corresponde a ningún Usuario existente
    (cuenta eliminada, inconsistencia de datos, etc.), falla seguro
    con 404 en vez de devolver un perfil vacío o de otro usuario.
    """
    usuario = db.query(Usuario).filter(Usuario.id == current_user["id"]).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@router.get("/me", response_model=UsuarioMeOut)
def obtener_mi_perfil(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Perfil propio del Usuario autenticado (SA-1.2).

    Reemplaza a ConfiguracionCentro como fuente de identidad para
    "Mi Perfil": ADMIN y SUPERADMIN obtienen aquí su propio
    nombre/correo/telefono/foto_url/rol/activo, nunca datos de otro
    usuario ni del centro. `UsuarioMeOut` no declara `password`, así
    que nunca se expone el hash en la respuesta.
    """
    verificar_rol(current_user, roles_permitidos=["admin", "superadmin"])
    return _obtener_usuario_actual(db, current_user)


@router.patch("/me", response_model=UsuarioMeOut)
def actualizar_mi_perfil(
    datos: UsuarioMeUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Actualiza el perfil propio del Usuario autenticado (SA-1.2).

    Único endpoint de Mi Perfil para nombre/foto_url/telefono. Opera
    exclusivamente sobre current_user["id"]. `UsuarioMeUpdate` tiene
    extra="forbid": rol, activo, permisos, password,
    debe_cambiar_password, usuario_id y correo no son campos válidos
    del schema, así que enviarlos hace que la petición completa sea
    rechazada con 422 antes de llegar a este cuerpo — nunca se aceptan
    y se ignoran en silencio.
    """
    verificar_rol(current_user, roles_permitidos=["admin", "superadmin"])
    usuario = _obtener_usuario_actual(db, current_user)

    if datos.nombre is not None:
        usuario.nombre = datos.nombre

    if datos.foto_url is not None:
        usuario.foto_url = datos.foto_url

    if datos.telefono is not None:
        usuario.telefono = datos.telefono

    db.commit()
    db.refresh(usuario)

    return usuario


@router.get(
    "/me/acceso-administrativo",
    response_model=AccesoAdministrativoEfectivoOut,
)
def obtener_mi_acceso_administrativo(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Entrega al propio ADMIN/SUPERADMIN su contexto administrativo
    efectivo actual para representar correctamente la UX.

    No reemplaza la autorizacion server-side de ningun endpoint.
    Un ADMIN sin configuracion valida falla cerrado con 403.
    """
    verificar_rol(
        current_user,
        roles_permitidos=[
            Role.ADMIN.value,
            Role.SUPERADMIN.value,
        ],
    )

    acceso = obtener_acceso_administrativo_efectivo(
        db,
        current_user,
    )

    if acceso is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Acceso administrativo no configurado "
                "o invalido."
            ),
        )

    return {
        "rol": acceso.rol.value,
        "perfil": (
            acceso.perfil.value
            if acceso.perfil is not None
            else None
        ),
        "permisos": sorted(
            permiso.value
            for permiso in acceso.permisos
        ),
        "alcance": {
            "tipo": acceso.tipo_alcance.value,
            "especialidades": sorted(
                especialidad.nombre
                for especialidad in acceso.especialidades
            ),
        },
    }


# ══════════════════════════════════════════════════════════════════
# GOBERNANZA ADMIN/SUPERADMIN (SA-3)
# ══════════════════════════════════════════════════════════════════
#
# Todos los endpoints de esta sección exigen Permission.ROLES_GESTIONAR
# (Depends(require_permission(...))): SUPERADMIN lo tiene por defecto,
# ADMIN no (ver ROLE_DEFAULT_PERMISSIONS) — así que ADMIN recibe 403 en
# todos ellos sin ninguna comprobación adicional en este archivo.
#
# "Target" siempre significa: un Usuario cuyo rol ACTUAL en BD ya es
# "admin" o "superadmin". Nunca se acepta estudiante/profesional como
# destino de estas rutas (ver _bloquear_cuentas_administrativas: filtra
# por rol desde el inicio, así que un usuario_id de estudiante/
# profesional simplemente no aparece entre las filas bloqueadas y
# termina devolviendo 404 genérico, sin revelar si ese id existe con
# otro rol).


def _bloquear_cuentas_administrativas(db: Session) -> List[Usuario]:
    """
    SELECT ... FOR UPDATE de todas las cuentas admin/superadmin,
    ordenadas por id, para las operaciones de estado/rol.

    Diseño elegido (serializar todo cambio administrativo) en vez de
    bloquear fila por fila: son operaciones de baja frecuencia y esto
    evita cualquier ventana entre "contar SUPERADMIN activos" y
    "decidir si la operación reduce ese conteo a 0" — la regla del
    último SUPERADMIN se evalúa siempre sobre datos ya bloqueados, no
    sobre un count() suelto que otra transacción concurrente podría
    volver obsoleto entre la lectura y la escritura.

    En PostgreSQL (producción) esto adquiere locks de fila reales.
    En SQLite (tests) with_for_update() es un no-op de SQLAlchemy, pero
    el camino de código productivo es exactamente el mismo — la
    concurrencia real de PostgreSQL queda fuera del alcance verificable
    acá (documentado para SA-6/7 en el pedido original).
    """
    return (
        db.query(Usuario)
        .filter(Usuario.rol.in_(_ROLES_ADMINISTRATIVOS))
        .order_by(Usuario.id)
        .with_for_update()
        .all()
    )


def _contar_superadmin_activos(cuentas_bloqueadas: List[Usuario]) -> int:
    return sum(
        1
        for u in cuentas_bloqueadas
        if u.rol == Role.SUPERADMIN.value and u.activo is True
    )


def _obtener_target_administrativo(cuentas_bloqueadas: List[Usuario], usuario_id: int) -> Usuario:
    target = next((u for u in cuentas_bloqueadas if u.id == usuario_id), None)
    if target is None:
        # 404 genérico: no distingue entre "no existe", "es estudiante"
        # o "es profesional" — ninguno de esos casos es un target válido
        # de gobernanza y no hace falta revelar cuál es cuál.
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return target


def _registrar_error_best_effort(db: Session, current_user: dict, accion: str, detalle: str) -> None:
    """
    Best-effort: tras un rollback ya hecho por el caller, intenta dejar
    un evento resultado="error" en una transacción separada. Si eso
    también falla, se hace rollback de nuevo y NO se oculta ni se
    reemplaza la excepción original (el caller siempre hace `raise`
    después de llamar a esto).
    """
    try:
        registrar_evento_auditoria(db, current_user, accion, resultado="error", detalle=detalle)
        db.commit()
    except Exception:
        db.rollback()


def _registrar_denegado_best_effort(
    db: Session,
    current_user: dict,
    accion: str,
    *,
    entidad_id: int | None = None,
    detalle: str,
) -> None:
    """
    Registra un intento denegado sin reemplazar el HTTPException del
    caller si la auditoría secundaria falla.
    """
    try:
        registrar_evento_auditoria(
            db,
            current_user,
            accion,
            resultado="denegado",
            entidad="usuario" if entidad_id is not None else None,
            entidad_id=entidad_id,
            detalle=detalle,
        )
        db.commit()
    except Exception:
        db.rollback()


def _obtener_target_admin_para_acceso(
    db: Session,
    usuario_id: int,
    *,
    bloquear: bool = False,
) -> Usuario:
    """
    Devuelve una cuenta administrativa existente y exige que su rol
    ACTUAL sea ADMIN. SUPERADMIN no usa AccesoAdministrativo.
    """
    query = db.query(Usuario).filter(Usuario.id == usuario_id)

    if bloquear:
        query = query.with_for_update()

    target = query.first()

    if target is None or target.rol not in _ROLES_ADMINISTRATIVOS:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if target.rol != Role.ADMIN.value:
        raise HTTPException(
            status_code=409,
            detail="La configuración de acceso administrativo solo aplica a cuentas ADMIN.",
        )

    return target


def _obtener_acceso_persistido(
    db: Session,
    usuario_id: int,
) -> AccesoAdministrativo | None:
    return (
        db.query(AccesoAdministrativo)
        .filter(AccesoAdministrativo.usuario_id == usuario_id)
        .first()
    )


def _eliminar_acceso_administrativo_persistido(
    db: Session,
    usuario_id: int,
) -> bool:
    """
    Elimina configuración y relaciones delegables de una cuenta ADMIN.

    Se borran hijos explícitamente para no depender del soporte de
    ON DELETE CASCADE del motor de pruebas.
    """
    acceso = _obtener_acceso_persistido(db, usuario_id)

    if acceso is None:
        return False

    (
        db.query(AccesoAdminPermiso)
        .filter(AccesoAdminPermiso.acceso_admin_id == acceso.id)
        .delete(synchronize_session=False)
    )
    (
        db.query(AccesoAdminEspecialidad)
        .filter(AccesoAdminEspecialidad.acceso_admin_id == acceso.id)
        .delete(synchronize_session=False)
    )
    db.delete(acceso)
    db.flush()

    return True


def _serializar_acceso_administrativo_gestion(
    db: Session,
    usuario_id: int,
) -> dict:
    acceso = _obtener_acceso_persistido(db, usuario_id)

    if acceso is None:
        return {
            "usuario_id": usuario_id,
            "configurado": False,
            "perfil": None,
            "permisos": [],
            "alcance": {
                "tipo": None,
                "especialidades": [],
            },
        }

    especialidades = (
        db.query(AccesoAdminEspecialidad)
        .filter(AccesoAdminEspecialidad.acceso_admin_id == acceso.id)
        .order_by(AccesoAdminEspecialidad.especialidad_normalizada)
        .all()
    )
    permisos = (
        db.query(AccesoAdminPermiso)
        .filter(AccesoAdminPermiso.acceso_admin_id == acceso.id)
        .order_by(AccesoAdminPermiso.permiso)
        .all()
    )

    try:
        perfil, tipo_alcance, especialidades_validadas = (
            validar_configuracion_acceso_admin(
                rol_usuario=Role.ADMIN.value,
                perfil=acceso.perfil,
                tipo_alcance=acceso.tipo_alcance,
                especialidades=[
                    fila.especialidad
                    for fila in especialidades
                ],
            )
        )
        permisos_validados = validar_permisos_para_perfil(
            perfil=perfil,
            permisos=[
                fila.permiso
                for fila in permisos
            ],
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "La configuración administrativa persistida es inválida "
                "y debe reemplazarse."
            ),
        ) from exc

    return {
        "usuario_id": usuario_id,
        "configurado": True,
        "perfil": perfil.value,
        "permisos": sorted(
            permiso.value
            for permiso in permisos_validados
        ),
        "alcance": {
            "tipo": tipo_alcance.value,
            "especialidades": sorted(
                especialidad.nombre
                for especialidad in especialidades_validadas
            ),
        },
    }


@router.get("/administradores", response_model=List[UsuarioAdministrativoOut])
def listar_administradores(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(Permission.ROLES_GESTIONAR)),
):
    """Lista todas las cuentas ADMIN/SUPERADMIN. Solo SUPERADMIN llega
    hasta acá (ROLES_GESTIONAR)."""
    return (
        db.query(Usuario)
        .filter(Usuario.rol.in_(_ROLES_ADMINISTRATIVOS))
        .order_by(Usuario.id)
        .all()
    )


@router.get(
    "/administradores/catalogo-acceso",
    response_model=CatalogoAccesoAdministrativoOut,
)
def obtener_catalogo_acceso_administrativo(
    current_user: dict = Depends(
        require_permission(Permission.ROLES_GESTIONAR)
    ),
):
    """
    Catálogo server-side para construir la UI de perfiles/permisos.

    No concede nada: expone únicamente el techo delegable definido en
    app.rbac.admin_access. Las especialidades no forman parte de este
    catálogo porque aún no existe un catálogo institucional único en el
    modelo actual.
    """
    perfiles = []

    for perfil in PerfilAccesoAdmin:
        tipo_alcance = (
            TipoAlcanceAdmin.INSTITUCIONAL
            if perfil in PERFILES_INSTITUCIONALES
            else TipoAlcanceAdmin.ESPECIALIDADES
        )

        perfiles.append(
            {
                "perfil": perfil.value,
                "tipo_alcance": tipo_alcance.value,
                "permisos_permitidos": sorted(
                    permiso.value
                    for permiso in permisos_permitidos_para_perfil(perfil)
                ),
            }
        )

    return {
        "perfiles": perfiles,
    }


@router.get(
    "/administradores/{usuario_id}/acceso-administrativo",
    response_model=AccesoAdministrativoGestionOut,
)
def obtener_acceso_administrativo_de_admin(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission(Permission.ROLES_GESTIONAR)
    ),
):
    """
    Lee la configuración persistida de una cuenta ADMIN.

    Una cuenta ADMIN sin configuración devuelve `configurado=false`
    en vez de inventar permisos o defaults. SUPERADMIN no usa estas
    tablas y por eso no es un target válido de este endpoint.
    """
    _obtener_target_admin_para_acceso(
        db,
        usuario_id,
        bloquear=False,
    )

    return _serializar_acceso_administrativo_gestion(
        db,
        usuario_id,
    )


@router.put(
    "/administradores/{usuario_id}/acceso-administrativo",
    response_model=AccesoAdministrativoGestionOut,
)
def reemplazar_acceso_administrativo_de_admin(
    usuario_id: int,
    datos: AccesoAdministrativoGestionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission(Permission.ROLES_GESTIONAR)
    ),
):
    """
    Reemplaza de forma completa y transaccional perfil + permisos +
    alcance de una cuenta ADMIN.

    El target se bloquea antes de validar/persistir para impedir que un
    cambio concurrente de rol deje permisos ADMIN asociados a una cuenta
    que ya pasó a SUPERADMIN.
    """
    try:
        target = _obtener_target_admin_para_acceso(
            db,
            usuario_id,
            bloquear=True,
        )
    except HTTPException as exc:
        if exc.status_code == 409:
            _registrar_denegado_best_effort(
                db,
                current_user,
                "Intentó configurar acceso administrativo en target inválido",
                entidad_id=usuario_id,
                detalle="target_no_es_admin",
            )
        raise

    try:
        perfil, tipo_alcance, especialidades = (
            validar_configuracion_acceso_admin(
                rol_usuario=target.rol,
                perfil=datos.perfil,
                tipo_alcance=datos.alcance.tipo,
                especialidades=datos.alcance.especialidades,
            )
        )
        permisos = validar_permisos_para_perfil(
            perfil=perfil,
            permisos=datos.permisos,
        )
    except (TypeError, ValueError) as exc:
        db.rollback()
        _registrar_denegado_best_effort(
            db,
            current_user,
            "Intentó guardar acceso administrativo inválido",
            entidad_id=target.id,
            detalle="configuracion_acceso_invalida",
        )
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    try:
        acceso = _obtener_acceso_persistido(
            db,
            target.id,
        )

        if acceso is None:
            acceso = AccesoAdministrativo(
                usuario_id=target.id,
                perfil=perfil.value,
                tipo_alcance=tipo_alcance.value,
            )
            db.add(acceso)
            db.flush()
        else:
            acceso.perfil = perfil.value
            acceso.tipo_alcance = tipo_alcance.value

            (
                db.query(AccesoAdminPermiso)
                .filter(
                    AccesoAdminPermiso.acceso_admin_id
                    == acceso.id
                )
                .delete(synchronize_session=False)
            )
            (
                db.query(AccesoAdminEspecialidad)
                .filter(
                    AccesoAdminEspecialidad.acceso_admin_id
                    == acceso.id
                )
                .delete(synchronize_session=False)
            )
            db.flush()

        for especialidad in especialidades:
            db.add(
                AccesoAdminEspecialidad(
                    acceso_admin_id=acceso.id,
                    especialidad=especialidad.nombre,
                    especialidad_normalizada=(
                        especialidad.normalizada
                    ),
                )
            )

        for permiso in sorted(
            permisos,
            key=lambda item: item.value,
        ):
            db.add(
                AccesoAdminPermiso(
                    acceso_admin_id=acceso.id,
                    permiso=permiso.value,
                )
            )

        registrar_evento_auditoria(
            db,
            current_user,
            "Configuró acceso administrativo",
            resultado="exito",
            entidad="usuario",
            entidad_id=target.id,
            detalle=(
                f"perfil={perfil.value}; "
                f"alcance={tipo_alcance.value}; "
                f"permisos={len(permisos)}; "
                f"especialidades={len(especialidades)}"
            ),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        _registrar_error_best_effort(
            db,
            current_user,
            "Error al configurar acceso administrativo",
            "integridad_acceso_administrativo",
        )
        raise HTTPException(
            status_code=409,
            detail="No fue posible guardar la configuración administrativa.",
        )
    except SQLAlchemyError:
        db.rollback()
        _registrar_error_best_effort(
            db,
            current_user,
            "Error al configurar acceso administrativo",
            "error_bd_configurar_acceso_administrativo",
        )
        raise

    return _serializar_acceso_administrativo_gestion(
        db,
        target.id,
    )


@router.post("/administradores", response_model=UsuarioAdministrativoOut, status_code=201)
def crear_administrador(
    datos: UsuarioAdministrativoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(Permission.ROLES_GESTIONAR)),
):
    """
    Crea una cuenta ADMIN o SUPERADMIN nueva.

    Nace siempre activo=True, debe_cambiar_password=False (mismo
    comportamiento que bootstrap_superadmin: no existe hoy ningún flujo
    de "primer acceso" administrativo que resuelva esa bandera si se
    dejara en True).
    """
    if not _password_cumple_politica_existente(datos.password):
        raise HTTPException(
            status_code=422,
            detail="La contraseña no cumple la política de seguridad requerida "
            "(mínimo 8 caracteres, con mayúscula, minúscula, número y "
            "carácter especial, sin espacios).",
        )

    correo_normalizado = datos.correo.strip().lower()

    if not correo_normalizado:
        raise HTTPException(
            status_code=422,
            detail="El correo no puede estar vacío.",
        )

    # Comprobación case-insensitive ANTES de insertar. No sustituye la
    # protección real (el índice UNIQUE de PostgreSQL sobre
    # ix_usuario_correo): existe una carrera concurrente posible entre
    # este SELECT y el INSERT, por eso también se captura IntegrityError
    # más abajo.
    # SA-6.1 - Las cuentas administrativas deben usar el dominio
    # institucional que tambien exige el login. El backend es la autoridad.
    partes_correo = correo_normalizado.split("@")
    if (
        len(partes_correo) != 2
        or not partes_correo[0]
        or partes_correo[1] != "utem.cl"
        or any(caracter.isspace() for caracter in correo_normalizado)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "El correo de una cuenta administrativa debe ser "
                "institucional y terminar exactamente en @utem.cl."
            ),
        )

    duplicado = (
        db.query(Usuario)
        .filter(func.lower(Usuario.correo) == correo_normalizado)
        .first()
    )
    if duplicado is not None:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo.")

    nuevo = Usuario(
        correo=correo_normalizado,
        password=hash_password(datos.password),
        rol=datos.rol,
        nombre=datos.nombre,
        telefono=datos.telefono,
        activo=True,
        debe_cambiar_password=False,
    )

    try:
        db.add(nuevo)
        db.flush()  # asigna nuevo.id sin cerrar la transacción
        registrar_evento_auditoria(
            db,
            current_user,
            "Creó cuenta administrativa",
            resultado="exito",
            entidad="usuario",
            entidad_id=nuevo.id,
            detalle=f"rol={datos.rol}",
        )
        db.commit()
    except IntegrityError:
        # Carrera concurrente real: el índice UNIQUE de PostgreSQL es la
        # protección final. No se revela detalle interno del motor.
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo.")
    except SQLAlchemyError:
        db.rollback()
        _registrar_error_best_effort(
            db, current_user, "Error al crear cuenta administrativa", "error_bd_crear_administrador"
        )
        raise

    db.refresh(nuevo)
    return nuevo


@router.patch("/administradores/{usuario_id}/estado", response_model=UsuarioAdministrativoOut)
def actualizar_estado_administrador(
    usuario_id: int,
    datos: UsuarioAdministrativoEstadoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(Permission.ROLES_GESTIONAR)),
):
    """
    Activa/desactiva una cuenta ADMIN/SUPERADMIN.

    Regla del último SUPERADMIN: nunca se permite que el sistema pase
    de >=1 SUPERADMIN activo a 0. Solo aplica al desactivar un
    SUPERADMIN que hoy está activo; reactivar siempre está permitido.
    """
    cuentas = _bloquear_cuentas_administrativas(db)
    target = _obtener_target_administrativo(cuentas, usuario_id)

    estado_anterior = target.activo
    va_a_desactivar_superadmin = (
        target.rol == Role.SUPERADMIN.value
        and estado_anterior is True
        and datos.activo is False
    )

    if va_a_desactivar_superadmin and _contar_superadmin_activos(cuentas) <= 1:
        try:
            registrar_evento_auditoria(
                db,
                current_user,
                "Intentó desactivar al último SUPERADMIN activo",
                resultado="denegado",
                entidad="usuario",
                entidad_id=target.id,
                detalle="proteccion_ultimo_superadmin",
            )
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(status_code=409, detail="No es posible desactivar al último SUPERADMIN activo.")

    target.activo = datos.activo

    try:
        registrar_evento_auditoria(
            db,
            current_user,
            "Cambió estado de cuenta administrativa",
            resultado="exito",
            entidad="usuario",
            entidad_id=target.id,
            detalle=(
                f"estado_anterior={'activo' if estado_anterior else 'inactivo'}; "
                f"estado_nuevo={'activo' if datos.activo else 'inactivo'}"
            ),
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        _registrar_error_best_effort(
            db, current_user, "Error al cambiar estado de cuenta administrativa", "error_bd_cambiar_estado"
        )
        raise

    db.refresh(target)
    return target


@router.patch("/administradores/{usuario_id}/rol", response_model=UsuarioAdministrativoOut)
def actualizar_rol_administrador(
    usuario_id: int,
    datos: UsuarioAdministrativoRolUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(Permission.ROLES_GESTIONAR)),
):
    """
    Cambia el rol de una cuenta administrativa entre "admin" y
    "superadmin".

    Regla del último SUPERADMIN: si el target es el único SUPERADMIN
    activo, degradarlo a ADMIN queda bloqueado (409), igual que
    desactivarlo. Si el target ya estaba inactivo, cambiar su rol NO
    reduce el número de SUPERADMIN activos y no se bloquea por esta
    regla.
    """
    cuentas = _bloquear_cuentas_administrativas(db)
    target = _obtener_target_administrativo(cuentas, usuario_id)

    rol_anterior = target.rol
    rol_nuevo = datos.rol

    va_a_degradar_superadmin = (
        target.rol == Role.SUPERADMIN.value
        and target.activo is True
        and rol_nuevo == Role.ADMIN.value
    )

    if va_a_degradar_superadmin and _contar_superadmin_activos(cuentas) <= 1:
        try:
            registrar_evento_auditoria(
                db,
                current_user,
                "Intentó degradar al último SUPERADMIN activo",
                resultado="denegado",
                entidad="usuario",
                entidad_id=target.id,
                detalle="proteccion_ultimo_superadmin",
            )
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(status_code=409, detail="No es posible degradar al último SUPERADMIN activo.")

    try:
        acceso_reiniciado = False

        if rol_nuevo != rol_anterior:
            acceso_reiniciado = _eliminar_acceso_administrativo_persistido(
                db,
                target.id,
            )

        target.rol = rol_nuevo

        registrar_evento_auditoria(
            db,
            current_user,
            "Cambió rol de cuenta administrativa",
            resultado="exito",
            entidad="usuario",
            entidad_id=target.id,
            detalle=(
                f"rol_anterior={rol_anterior}; "
                f"rol_nuevo={rol_nuevo}; "
                f"acceso_admin_reiniciado={'si' if acceso_reiniciado else 'no'}"
            ),
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        _registrar_error_best_effort(
            db, current_user, "Error al cambiar rol de cuenta administrativa", "error_bd_cambiar_rol"
        )
        raise

    db.refresh(target)
    return target
