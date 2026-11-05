"""
Tests SA-3 — Gobernanza ADMIN/SUPERADMIN.

Mismo patrón que test_auditoria.py / test_usuarios_me.py: SQLite en
memoria creada solo con las tablas necesarias (Usuario, Auditoria) a
partir del Base declarativo real del proyecto, sin TestClient/httpx.
Los endpoints de gobernanza (app/routers/usuarios.py) se llaman
directamente como funciones Python, pasando `db` y `current_user` como
lo haría FastAPI tras resolver las dependencias.
"""

import inspect

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auditoria import registrar_evento_auditoria
from app.auth_dependencies import get_current_user
from app.database import Base
from app.models.auditoria import Auditoria
from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminEspecialidad,
    AccesoAdminPermiso,
)
from app.models.usuario import Usuario
from app.rbac.dependencies import require_permission
from app.rbac.permissions import Permission, has_permission
from app.rbac.roles import Role
from app.routers.usuarios import (
    _bloquear_cuentas_administrativas,
    actualizar_estado_administrador,
    actualizar_rol_administrador,
    crear_administrador,
    listar_administradores,
)
from app.schemas import (
    UsuarioAdministrativoCreate,
    UsuarioAdministrativoEstadoUpdate,
    UsuarioAdministrativoRolUpdate,
)
from app.security import create_access_token, hash_password, verify_password

PASSWORD_VALIDA = "Password123!"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Usuario.__table__,
            Auditoria.__table__,
            AccesoAdministrativo.__table__,
            AccesoAdminEspecialidad.__table__,
            AccesoAdminPermiso.__table__,
        ],
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _crear_usuario(db, *, correo, rol, activo=True, nombre=None, password=PASSWORD_VALIDA):
    usuario = Usuario(
        correo=correo,
        password=hash_password(password),
        rol=rol,
        nombre=nombre,
        activo=activo,
        debe_cambiar_password=False,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def _current_user_de(usuario: Usuario) -> dict:
    return {"id": usuario.id, "rol": usuario.rol, "correo": usuario.correo}


# ══════════════════════════════════════
# 1-2. ROLES_GESTIONAR por rol
# ══════════════════════════════════════

def test_superadmin_tiene_roles_gestionar():
    assert has_permission(Role.SUPERADMIN, Permission.ROLES_GESTIONAR) is True


def test_admin_no_tiene_roles_gestionar():
    assert has_permission(Role.ADMIN, Permission.ROLES_GESTIONAR) is False


# ══════════════════════════════════════
# 3-6. Crear ADMIN/SUPERADMIN por gobernanza
# ══════════════════════════════════════

def test_crear_admin_por_gobernanza_funciona(db_session):
    superadmin = _crear_usuario(db_session, correo="super@utem.cl", rol="superadmin")

    datos = UsuarioAdministrativoCreate(correo="nuevo-admin@utem.cl", password=PASSWORD_VALIDA, rol="admin")
    resultado = crear_administrador(datos, db_session, _current_user_de(superadmin))

    assert resultado.rol == "admin"
    assert resultado.correo == "nuevo-admin@utem.cl"
    assert resultado.activo is True


def test_crear_superadmin_por_gobernanza_funciona(db_session):
    superadmin = _crear_usuario(db_session, correo="super2@utem.cl", rol="superadmin")

    datos = UsuarioAdministrativoCreate(correo="nuevo-super@utem.cl", password=PASSWORD_VALIDA, rol="superadmin")
    resultado = crear_administrador(datos, db_session, _current_user_de(superadmin))

    assert resultado.rol == "superadmin"


def test_password_se_guarda_hasheada_nunca_plaintext(db_session):
    superadmin = _crear_usuario(db_session, correo="super3@utem.cl", rol="superadmin")

    datos = UsuarioAdministrativoCreate(correo="hash-check@utem.cl", password=PASSWORD_VALIDA, rol="admin")
    crear_administrador(datos, db_session, _current_user_de(superadmin))

    guardado = db_session.query(Usuario).filter(Usuario.correo == "hash-check@utem.cl").first()
    assert guardado.password != PASSWORD_VALIDA
    assert verify_password(PASSWORD_VALIDA, guardado.password) is True


def test_debe_cambiar_password_false_en_cuenta_nueva(db_session):
    superadmin = _crear_usuario(db_session, correo="super4@utem.cl", rol="superadmin")

    datos = UsuarioAdministrativoCreate(correo="flag-check@utem.cl", password=PASSWORD_VALIDA, rol="admin")
    crear_administrador(datos, db_session, _current_user_de(superadmin))

    guardado = db_session.query(Usuario).filter(Usuario.correo == "flag-check@utem.cl").first()
    assert guardado.debe_cambiar_password is False


# ══════════════════════════════════════
# 7-9. Duplicados / validación de schema
# ══════════════════════════════════════

def test_correo_duplicado_devuelve_409(db_session):
    superadmin = _crear_usuario(db_session, correo="super5@utem.cl", rol="superadmin")
    datos = UsuarioAdministrativoCreate(correo="Duplicado@Utem.cl", password=PASSWORD_VALIDA, rol="admin")
    crear_administrador(datos, db_session, _current_user_de(superadmin))

    datos_repetido = UsuarioAdministrativoCreate(correo="duplicado@utem.cl", password=PASSWORD_VALIDA, rol="admin")
    with pytest.raises(HTTPException) as exc_info:
        crear_administrador(datos_repetido, db_session, _current_user_de(superadmin))

    assert exc_info.value.status_code == 409
    assert db_session.query(Usuario).filter(Usuario.correo == "duplicado@utem.cl").count() == 1


def test_rol_invalido_en_schema_es_rechazado():
    with pytest.raises(ValidationError):
        UsuarioAdministrativoCreate(correo="x@utem.cl", password=PASSWORD_VALIDA, rol="estudiante")


@pytest.mark.parametrize("campo,valor", [
    ("activo", True),
    ("password_hash", "algo"),
    ("permisos", ["roles.gestionar"]),
    ("debe_cambiar_password", True),
])
def test_extra_fields_no_se_aceptan_en_create(campo, valor):
    with pytest.raises(ValidationError):
        UsuarioAdministrativoCreate(**{
            "correo": "x@utem.cl", "password": PASSWORD_VALIDA, "rol": "admin", campo: valor,
        })


def test_extra_fields_no_se_aceptan_en_estado_update():
    with pytest.raises(ValidationError):
        UsuarioAdministrativoEstadoUpdate(activo=True, rol="superadmin")


def test_extra_fields_no_se_aceptan_en_rol_update():
    with pytest.raises(ValidationError):
        UsuarioAdministrativoRolUpdate(rol="admin", activo=True)


# ══════════════════════════════════════
# Correo vacío / solo espacios -> 422 fail-closed
# ══════════════════════════════════════

def test_correo_vacio_es_rechazado_con_422(db_session):
    superadmin = _crear_usuario(db_session, correo="super-correo-vacio@utem.cl", rol="superadmin")

    datos = UsuarioAdministrativoCreate(correo="", password=PASSWORD_VALIDA, rol="admin")
    with pytest.raises(HTTPException) as exc_info:
        crear_administrador(datos, db_session, _current_user_de(superadmin))

    assert exc_info.value.status_code == 422
    assert db_session.query(Usuario).count() == 1  # solo el superadmin de setup


def test_correo_solo_espacios_es_rechazado_con_422(db_session):
    superadmin = _crear_usuario(db_session, correo="super-correo-espacios@utem.cl", rol="superadmin")

    datos = UsuarioAdministrativoCreate(correo="     ", password=PASSWORD_VALIDA, rol="admin")
    with pytest.raises(HTTPException) as exc_info:
        crear_administrador(datos, db_session, _current_user_de(superadmin))

    assert exc_info.value.status_code == 422
    assert db_session.query(Usuario).count() == 1  # solo el superadmin de setup


# ══════════════════════════════════════
# 10. ADMIN no puede usar la dependency
# ══════════════════════════════════════


# SA-6.1 - Correo institucional obligatorio

def test_correo_institucional_se_normaliza_a_minusculas(db_session):
    superadmin = _crear_usuario(
        db_session,
        correo="super-correo-normaliza@utem.cl",
        rol="superadmin",
    )

    datos = UsuarioAdministrativoCreate(
        correo="  Nueva.Cuenta@UTEM.CL  ",
        password=PASSWORD_VALIDA,
        rol="admin",
    )

    resultado = crear_administrador(
        datos,
        db_session,
        _current_user_de(superadmin),
    )

    assert resultado.correo == "nueva.cuenta@utem.cl"


@pytest.mark.parametrize(
    "correo_invalido",
    [
        "usuario@gmail.com",
        "usuario@test.local",
        "usuario@utem.cl.evil.com",
        "usuario@sub.utem.cl",
        "usuario@@utem.cl",
    ],
)
def test_correo_no_institucional_es_rechazado_con_422(
    db_session,
    correo_invalido,
):
    superadmin = _crear_usuario(
        db_session,
        correo="super-correo-institucional@utem.cl",
        rol="superadmin",
    )

    datos = UsuarioAdministrativoCreate(
        correo=correo_invalido,
        password=PASSWORD_VALIDA,
        rol="admin",
    )

    with pytest.raises(HTTPException) as exc_info:
        crear_administrador(
            datos,
            db_session,
            _current_user_de(superadmin),
        )

    assert exc_info.value.status_code == 422
    assert "@utem.cl" in str(exc_info.value.detail)
    assert db_session.query(Usuario).count() == 1


def test_admin_no_puede_usar_dependency_roles_gestionar():
    dependencia = require_permission(Permission.ROLES_GESTIONAR)
    admin_dict = {"id": 1, "rol": "admin", "correo": "admin@utem.cl"}

    with pytest.raises(HTTPException) as exc_info:
        dependencia(current_user=admin_dict)

    assert exc_info.value.status_code == 403


# ══════════════════════════════════════
# 11-12. IDOR: target estudiante/profesional -> 404
# ══════════════════════════════════════

def test_target_estudiante_no_se_puede_convertir(db_session):
    superadmin = _crear_usuario(db_session, correo="super6@utem.cl", rol="superadmin")
    estudiante = _crear_usuario(db_session, correo="estudiante1@utem.cl", rol="estudiante")

    with pytest.raises(HTTPException) as exc_info:
        actualizar_rol_administrador(
            estudiante.id, UsuarioAdministrativoRolUpdate(rol="admin"), db_session, _current_user_de(superadmin)
        )
    assert exc_info.value.status_code == 404

    guardado = db_session.query(Usuario).filter(Usuario.id == estudiante.id).first()
    assert guardado.rol == "estudiante"


def test_target_profesional_no_se_puede_convertir(db_session):
    superadmin = _crear_usuario(db_session, correo="super7@utem.cl", rol="superadmin")
    profesional = _crear_usuario(db_session, correo="profesional1@utem.cl", rol="profesional")

    with pytest.raises(HTTPException) as exc_info:
        actualizar_estado_administrador(
            profesional.id, UsuarioAdministrativoEstadoUpdate(activo=False), db_session, _current_user_de(superadmin)
        )
    assert exc_info.value.status_code == 404

    guardado = db_session.query(Usuario).filter(Usuario.id == profesional.id).first()
    assert guardado.activo is True


# ══════════════════════════════════════
# 13-14. Activar / desactivar ADMIN
# ══════════════════════════════════════

def test_activar_admin_funciona(db_session):
    superadmin = _crear_usuario(db_session, correo="super8@utem.cl", rol="superadmin")
    admin = _crear_usuario(db_session, correo="admin-inactivo@utem.cl", rol="admin", activo=False)

    resultado = actualizar_estado_administrador(
        admin.id, UsuarioAdministrativoEstadoUpdate(activo=True), db_session, _current_user_de(superadmin)
    )
    assert resultado.activo is True


def test_desactivar_admin_funciona(db_session):
    superadmin = _crear_usuario(db_session, correo="super9@utem.cl", rol="superadmin")
    admin = _crear_usuario(db_session, correo="admin-activo@utem.cl", rol="admin", activo=True)

    resultado = actualizar_estado_administrador(
        admin.id, UsuarioAdministrativoEstadoUpdate(activo=False), db_session, _current_user_de(superadmin)
    )
    assert resultado.activo is False


# ══════════════════════════════════════
# 15-18. Última protección SUPERADMIN (estado y rol)
# ══════════════════════════════════════

def test_unico_superadmin_activo_no_puede_desactivarse(db_session):
    superadmin = _crear_usuario(db_session, correo="unico1@utem.cl", rol="superadmin")

    with pytest.raises(HTTPException) as exc_info:
        actualizar_estado_administrador(
            superadmin.id, UsuarioAdministrativoEstadoUpdate(activo=False), db_session, _current_user_de(superadmin)
        )
    assert exc_info.value.status_code == 409

    guardado = db_session.query(Usuario).filter(Usuario.id == superadmin.id).first()
    assert guardado.activo is True


def test_con_dos_superadmin_activos_uno_puede_desactivarse(db_session):
    superadmin_a = _crear_usuario(db_session, correo="doble1@utem.cl", rol="superadmin")
    superadmin_b = _crear_usuario(db_session, correo="doble2@utem.cl", rol="superadmin")

    resultado = actualizar_estado_administrador(
        superadmin_b.id, UsuarioAdministrativoEstadoUpdate(activo=False), db_session, _current_user_de(superadmin_a)
    )
    assert resultado.activo is False


def test_ultimo_superadmin_activo_no_puede_cambiar_rol_a_admin(db_session):
    superadmin = _crear_usuario(db_session, correo="unico2@utem.cl", rol="superadmin")

    with pytest.raises(HTTPException) as exc_info:
        actualizar_rol_administrador(
            superadmin.id, UsuarioAdministrativoRolUpdate(rol="admin"), db_session, _current_user_de(superadmin)
        )
    assert exc_info.value.status_code == 409

    guardado = db_session.query(Usuario).filter(Usuario.id == superadmin.id).first()
    assert guardado.rol == "superadmin"


def test_con_dos_activos_uno_puede_cambiar_superadmin_a_admin(db_session):
    superadmin_a = _crear_usuario(db_session, correo="doble3@utem.cl", rol="superadmin")
    superadmin_b = _crear_usuario(db_session, correo="doble4@utem.cl", rol="superadmin")

    resultado = actualizar_rol_administrador(
        superadmin_b.id, UsuarioAdministrativoRolUpdate(rol="admin"), db_session, _current_user_de(superadmin_a)
    )
    assert resultado.rol == "admin"


def test_superadmin_inactivo_puede_cambiar_a_admin_sin_bloqueo(db_session):
    # Un SUPERADMIN ya inactivo no reduce el número de SUPERADMIN
    # activos al cambiar de rol, así que no debe bloquearse.
    superadmin_activo = _crear_usuario(db_session, correo="activo-guard@utem.cl", rol="superadmin")
    superadmin_inactivo = _crear_usuario(db_session, correo="inactivo-cambia@utem.cl", rol="superadmin", activo=False)

    resultado = actualizar_rol_administrador(
        superadmin_inactivo.id, UsuarioAdministrativoRolUpdate(rol="admin"), db_session, _current_user_de(superadmin_activo)
    )
    assert resultado.rol == "admin"
    assert resultado.activo is False


# ══════════════════════════════════════
# 19-20. ADMIN -> SUPERADMIN, reactivar
# ══════════════════════════════════════

def test_admin_a_superadmin_ejecutado_por_superadmin_funciona(db_session):
    superadmin = _crear_usuario(db_session, correo="ejecutor@utem.cl", rol="superadmin")
    admin = _crear_usuario(db_session, correo="ascenso@utem.cl", rol="admin", nombre="Ascendido")

    resultado = actualizar_rol_administrador(
        admin.id, UsuarioAdministrativoRolUpdate(rol="superadmin"), db_session, _current_user_de(superadmin)
    )
    assert resultado.rol == "superadmin"


def test_admin_a_superadmin_elimina_acceso_administrativo_previo(db_session):
    superadmin = _crear_usuario(
        db_session,
        correo="ejecutor-limpieza@utem.cl",
        rol="superadmin",
    )
    admin = _crear_usuario(
        db_session,
        correo="ascenso-limpieza@utem.cl",
        rol="admin",
    )

    acceso = AccesoAdministrativo(
        usuario_id=admin.id,
        perfil="secretaria_especialidad",
        tipo_alcance="especialidades",
    )
    db_session.add(acceso)
    db_session.flush()
    db_session.add(
        AccesoAdminEspecialidad(
            acceso_admin_id=acceso.id,
            especialidad="Odontología",
            especialidad_normalizada="odontología",
        )
    )
    db_session.add(
        AccesoAdminPermiso(
            acceso_admin_id=acceso.id,
            permiso="agenda.ver",
        )
    )
    db_session.commit()

    actualizar_rol_administrador(
        admin.id,
        UsuarioAdministrativoRolUpdate(rol="superadmin"),
        db_session,
        _current_user_de(superadmin),
    )

    assert (
        db_session.query(AccesoAdministrativo)
        .filter(AccesoAdministrativo.usuario_id == admin.id)
        .count()
        == 0
    )
    assert db_session.query(AccesoAdminEspecialidad).count() == 0
    assert db_session.query(AccesoAdminPermiso).count() == 0


def test_superadmin_a_admin_no_reactiva_acceso_administrativo_residual(db_session):
    ejecutor = _crear_usuario(
        db_session,
        correo="ejecutor-degradacion@utem.cl",
        rol="superadmin",
    )
    target = _crear_usuario(
        db_session,
        correo="target-degradacion@utem.cl",
        rol="superadmin",
    )

    # Simula una fila residual heredada de una versión anterior.
    acceso = AccesoAdministrativo(
        usuario_id=target.id,
        perfil="administrador_general",
        tipo_alcance="institucional",
    )
    db_session.add(acceso)
    db_session.flush()
    db_session.add(
        AccesoAdminPermiso(
            acceso_admin_id=acceso.id,
            permiso="agenda.gestionar",
        )
    )
    db_session.commit()

    resultado = actualizar_rol_administrador(
        target.id,
        UsuarioAdministrativoRolUpdate(rol="admin"),
        db_session,
        _current_user_de(ejecutor),
    )

    assert resultado.rol == "admin"
    assert (
        db_session.query(AccesoAdministrativo)
        .filter(AccesoAdministrativo.usuario_id == target.id)
        .count()
        == 0
    )
    assert db_session.query(AccesoAdminPermiso).count() == 0


def test_reactivar_conserva_rol_e_historial(db_session):
    superadmin = _crear_usuario(db_session, correo="reactivador@utem.cl", rol="superadmin")
    admin = _crear_usuario(db_session, correo="reactivado@utem.cl", rol="admin", nombre="Nombre Original", activo=False)

    resultado = actualizar_estado_administrador(
        admin.id, UsuarioAdministrativoEstadoUpdate(activo=True), db_session, _current_user_de(superadmin)
    )
    assert resultado.activo is True
    assert resultado.rol == "admin"
    assert resultado.nombre == "Nombre Original"


# ══════════════════════════════════════
# 21-24. JWT viejo / get_current_user fail-closed
# ══════════════════════════════════════

def test_jwt_de_usuario_desactivado_queda_bloqueado(db_session):
    usuario = _crear_usuario(db_session, correo="se-desactiva@utem.cl", rol="admin")
    token = create_access_token({"id": usuario.id, "rol": "admin", "correo": usuario.correo})
    credenciales = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    # El JWT funciona mientras la cuenta está activa.
    assert get_current_user(credentials=credenciales, db=db_session)["id"] == usuario.id

    usuario.activo = False
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credenciales, db=db_session)
    assert exc_info.value.status_code == 401


def test_jwt_viejo_despues_de_superadmin_a_admin_usa_rol_db_actual(db_session):
    superadmin = _crear_usuario(db_session, correo="degradado@utem.cl", rol="superadmin")
    otro_superadmin = _crear_usuario(db_session, correo="otro-super@utem.cl", rol="superadmin")

    token_viejo = create_access_token({"id": superadmin.id, "rol": "superadmin", "correo": superadmin.correo})
    credenciales = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_viejo)

    actualizar_rol_administrador(
        superadmin.id, UsuarioAdministrativoRolUpdate(rol="admin"), db_session, _current_user_de(otro_superadmin)
    )

    current_user = get_current_user(credentials=credenciales, db=db_session)
    assert current_user["rol"] == "admin"


def test_usuario_inexistente_referido_por_jwt_queda_bloqueado(db_session):
    token = create_access_token({"id": 987654, "rol": "admin", "correo": "fantasma@utem.cl"})
    credenciales = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credenciales, db=db_session)
    assert exc_info.value.status_code == 401


def test_rol_db_invalido_falla_cerrado(db_session):
    usuario = _crear_usuario(db_session, correo="rol-raro@utem.cl", rol="admin")
    # Simula un dato legado/corrupto directamente en BD (nunca ocurre a
    # través del schema, que restringe rol a admin|superadmin).
    usuario.rol = "rol-que-no-existe"
    db_session.commit()

    token = create_access_token({"id": usuario.id, "rol": "admin", "correo": usuario.correo})
    credenciales = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credenciales, db=db_session)
    assert exc_info.value.status_code == 401


# ══════════════════════════════════════
# 25. SUPERADMIN sin acceso clínico
# ══════════════════════════════════════

def test_superadmin_no_obtiene_permiso_clinico():
    assert has_permission({"rol": "superadmin"}, Permission.FICHA_VER_ASIGNADA) is False
    assert has_permission({"rol": "superadmin"}, Permission.FICHA_EDITAR_ASIGNADA) is False
    assert has_permission({"rol": "superadmin"}, Permission.ATENCIONES_REGISTRAR) is False
    assert has_permission({"rol": "superadmin"}, Permission.ATENCIONES_VER_ASIGNADAS) is False


# ══════════════════════════════════════
# 26-28. Auditoría de gobernanza
# ══════════════════════════════════════

def test_operaciones_exitosas_generan_auditoria_correcta(db_session):
    superadmin = _crear_usuario(db_session, correo="auditor@utem.cl", rol="superadmin")

    datos = UsuarioAdministrativoCreate(correo="auditado@utem.cl", password=PASSWORD_VALIDA, rol="admin")
    nuevo = crear_administrador(datos, db_session, _current_user_de(superadmin))

    evento = (
        db_session.query(Auditoria)
        .filter(Auditoria.entidad_id == nuevo.id, Auditoria.entidad == "usuario")
        .first()
    )
    assert evento is not None
    assert evento.usuario_id == superadmin.id
    assert evento.actor_rol == "superadmin"
    assert evento.resultado == "exito"


def test_proteccion_ultimo_superadmin_genera_evento_denegado_seguro(db_session):
    superadmin = _crear_usuario(db_session, correo="unico3@utem.cl", rol="superadmin")

    with pytest.raises(HTTPException):
        actualizar_estado_administrador(
            superadmin.id, UsuarioAdministrativoEstadoUpdate(activo=False), db_session, _current_user_de(superadmin)
        )

    evento = (
        db_session.query(Auditoria)
        .filter(Auditoria.entidad_id == superadmin.id, Auditoria.resultado == "denegado")
        .first()
    )
    assert evento is not None
    assert evento.detalle == "proteccion_ultimo_superadmin"


def test_password_ni_token_aparecen_en_auditoria(db_session):
    superadmin = _crear_usuario(db_session, correo="sin-secretos@utem.cl", rol="superadmin")

    datos = UsuarioAdministrativoCreate(correo="sin-secretos-target@utem.cl", password=PASSWORD_VALIDA, rol="admin")
    crear_administrador(datos, db_session, _current_user_de(superadmin))

    columnas = {c.name for c in Auditoria.__table__.columns}
    assert "password" not in columnas
    assert "token" not in columnas

    eventos = db_session.query(Auditoria).all()
    for evento in eventos:
        detalle = evento.detalle or ""
        assert PASSWORD_VALIDA not in detalle


# ══════════════════════════════════════
# 29. El helper de bloqueo usa FOR UPDATE
# ══════════════════════════════════════

def test_helper_de_bloqueo_usa_for_update():
    codigo = inspect.getsource(_bloquear_cuentas_administrativas)
    assert "with_for_update()" in codigo


def test_helper_de_bloqueo_devuelve_solo_cuentas_administrativas(db_session):
    _crear_usuario(db_session, correo="estudiante-fuera@utem.cl", rol="estudiante")
    _crear_usuario(db_session, correo="profesional-fuera@utem.cl", rol="profesional")
    admin = _crear_usuario(db_session, correo="admin-dentro@utem.cl", rol="admin")
    superadmin = _crear_usuario(db_session, correo="super-dentro@utem.cl", rol="superadmin")

    cuentas = _bloquear_cuentas_administrativas(db_session)
    ids = {u.id for u in cuentas}

    assert admin.id in ids
    assert superadmin.id in ids
    assert len(ids) == 2


# ══════════════════════════════════════
# Extra: listar_administradores
# ══════════════════════════════════════

def test_listar_administradores_incluye_solo_admin_superadmin(db_session):
    superadmin = _crear_usuario(db_session, correo="listador@utem.cl", rol="superadmin")
    _crear_usuario(db_session, correo="admin-en-lista@utem.cl", rol="admin")
    _crear_usuario(db_session, correo="estudiante-no-en-lista@utem.cl", rol="estudiante")

    resultado = listar_administradores(db_session, _current_user_de(superadmin))
    correos = {u.correo for u in resultado}

    assert "listador@utem.cl" in correos
    assert "admin-en-lista@utem.cl" in correos
    assert "estudiante-no-en-lista@utem.cl" not in correos
