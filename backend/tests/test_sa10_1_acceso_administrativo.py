import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminEspecialidad,
    AccesoAdminPermiso,
)
from app.models.usuario import Usuario
from app.rbac.admin_access import (
    PerfilAccesoAdmin,
    TipoAlcanceAdmin,
)
from app.rbac.admin_authorization import (
    obtener_acceso_administrativo_efectivo,
)
from app.rbac.permissions import (
    Permission,
    ROLE_DEFAULT_PERMISSIONS,
)
from app.rbac.roles import Role
from app.routers.usuarios import (
    obtener_mi_acceso_administrativo,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:"
    )

    Usuario.__table__.create(engine)
    AccesoAdministrativo.__table__.create(engine)
    AccesoAdminEspecialidad.__table__.create(engine)
    AccesoAdminPermiso.__table__.create(engine)

    with Session(engine) as session:
        yield session


def _crear_usuario(
    db,
    *,
    correo,
    rol="admin",
    activo=True,
):
    usuario = Usuario(
        correo=correo,
        password="hash-sa10",
        rol=rol,
        nombre="Usuario SA-10.1",
        activo=activo,
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return usuario


def _crear_acceso(
    db,
    usuario,
    *,
    perfil="administrador_general",
    tipo_alcance="institucional",
    especialidades=(),
    permisos=(),
):
    acceso = AccesoAdministrativo(
        usuario_id=usuario.id,
        perfil=perfil,
        tipo_alcance=tipo_alcance,
    )

    db.add(acceso)
    db.flush()

    for nombre in especialidades:
        visible = " ".join(
            nombre.split()
        )

        db.add(
            AccesoAdminEspecialidad(
                acceso_admin_id=acceso.id,
                especialidad=nombre,
                especialidad_normalizada=(
                    visible.casefold()
                ),
            )
        )

    for permiso in permisos:
        valor = (
            permiso.value
            if isinstance(permiso, Permission)
            else permiso
        )

        db.add(
            AccesoAdminPermiso(
                acceso_admin_id=acceso.id,
                permiso=valor,
            )
        )

    db.commit()
    db.refresh(acceso)

    return acceso


def test_admin_expone_solo_permisos_persistidos_y_especialidades_visibles(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="admin-contexto-sa10@utem.cl",
    )

    _crear_acceso(
        db,
        usuario,
        perfil="administrador_especialidad",
        tipo_alcance="especialidades",
        especialidades=[
            "  Nutrición  ",
            "Medicina   General",
        ],
        permisos=[
            Permission.AGENDA_VER,
            Permission.PROFESIONALES_VER,
        ],
    )

    acceso = obtener_acceso_administrativo_efectivo(
        db,
        {
            "id": usuario.id,
            "rol": "admin",
        },
    )

    assert acceso is not None
    assert acceso.rol is Role.ADMIN

    assert (
        acceso.perfil
        is PerfilAccesoAdmin.ADMINISTRADOR_ESPECIALIDAD
    )

    assert (
        acceso.tipo_alcance
        is TipoAlcanceAdmin.ESPECIALIDADES
    )

    assert {
        e.nombre
        for e in acceso.especialidades
    } == {
        "Nutrición",
        "Medicina General",
    }

    assert acceso.permisos == frozenset(
        {
            Permission.AGENDA_VER,
            Permission.PROFESIONALES_VER,
        }
    )


def test_permiso_persistido_fuera_del_techo_del_perfil_no_se_expone(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="secretaria-contexto-sa10@utem.cl",
    )

    _crear_acceso(
        db,
        usuario,
        perfil="secretaria_general",
        tipo_alcance="institucional",
        permisos=[
            Permission.AGENDA_VER,
            Permission.PROFESIONALES_GESTIONAR,
        ],
    )

    acceso = obtener_acceso_administrativo_efectivo(
        db,
        {
            "id": usuario.id,
            "rol": "admin",
        },
    )

    assert acceso is not None

    assert acceso.permisos == frozenset(
        {
            Permission.AGENDA_VER,
        }
    )


def test_admin_con_configuracion_valida_y_cero_permisos_devuelve_contexto_vacio(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="admin-cero-sa10@utem.cl",
    )

    _crear_acceso(
        db,
        usuario,
    )

    acceso = obtener_acceso_administrativo_efectivo(
        db,
        {
            "id": usuario.id,
            "rol": "admin",
        },
    )

    assert acceso is not None
    assert acceso.permisos == frozenset()


def test_admin_sin_configuracion_no_tiene_contexto(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="admin-sin-config-sa10@utem.cl",
    )

    assert (
        obtener_acceso_administrativo_efectivo(
            db,
            {
                "id": usuario.id,
                "rol": "admin",
            },
        )
        is None
    )


def test_admin_config_especialidad_sin_especialidades_falla_cerrado(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="admin-config-invalida-sa10@utem.cl",
    )

    # La BD permite que no existan filas hijas, pero la regla
    # de dominio SA-8 exige al menos una especialidad.
    _crear_acceso(
        db,
        usuario,
        perfil="administrador_especialidad",
        tipo_alcance="especialidades",
    )

    assert (
        obtener_acceso_administrativo_efectivo(
            db,
            {
                "id": usuario.id,
                "rol": "admin",
            },
        )
        is None
    )


def test_admin_inactivo_no_tiene_contexto(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="admin-inactivo-sa10@utem.cl",
        activo=False,
    )

    _crear_acceso(
        db,
        usuario,
        permisos=[
            Permission.AGENDA_VER,
        ],
    )

    assert (
        obtener_acceso_administrativo_efectivo(
            db,
            {
                "id": usuario.id,
                "rol": "admin",
            },
        )
        is None
    )


def test_superadmin_no_depende_de_acceso_administrativo(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="super-contexto-sa10@utem.cl",
        rol="superadmin",
    )

    # Deliberadamente pasamos un rol viejo en current_user:
    # el resolver debe usar el Usuario ACTUAL de BD.
    acceso = obtener_acceso_administrativo_efectivo(
        db,
        {
            "id": usuario.id,
            "rol": "admin",
        },
    )

    assert acceso is not None
    assert acceso.rol is Role.SUPERADMIN
    assert acceso.perfil is None

    assert (
        acceso.tipo_alcance
        is TipoAlcanceAdmin.INSTITUCIONAL
    )

    assert acceso.especialidades == ()

    assert (
        acceso.permisos
        == ROLE_DEFAULT_PERMISSIONS[
            Role.SUPERADMIN
        ]
    )

    assert (
        Permission.FICHA_VER_ASIGNADA
        not in acceso.permisos
    )


def test_endpoint_admin_devuelve_response_determinista(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="admin-endpoint-sa10@utem.cl",
    )

    _crear_acceso(
        db,
        usuario,
        perfil="administrador_especialidad",
        tipo_alcance="especialidades",
        especialidades=[
            "Nutrición",
        ],
        permisos=[
            Permission.PROFESIONALES_VER,
            Permission.AGENDA_VER,
        ],
    )

    respuesta = obtener_mi_acceso_administrativo(
        db=db,
        current_user={
            "id": usuario.id,
            "rol": "admin",
        },
    )

    assert respuesta == {
        "rol": "admin",
        "perfil": "administrador_especialidad",
        "permisos": [
            "agenda.ver",
            "profesionales.ver",
        ],
        "alcance": {
            "tipo": "especialidades",
            "especialidades": [
                "Nutrición",
            ],
        },
    }


def test_endpoint_admin_sin_configuracion_responde_403(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="admin-endpoint-sin-config-sa10@utem.cl",
    )

    with pytest.raises(HTTPException) as exc:
        obtener_mi_acceso_administrativo(
            db=db,
            current_user={
                "id": usuario.id,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403


def test_endpoint_superadmin_es_institucional(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="super-endpoint-sa10@utem.cl",
        rol="superadmin",
    )

    respuesta = obtener_mi_acceso_administrativo(
        db=db,
        current_user={
            "id": usuario.id,
            "rol": "superadmin",
        },
    )

    assert respuesta["rol"] == "superadmin"
    assert respuesta["perfil"] is None

    assert respuesta["alcance"] == {
        "tipo": "institucional",
        "especialidades": [],
    }

    assert set(
        respuesta["permisos"]
    ) == {
        permiso.value
        for permiso in ROLE_DEFAULT_PERMISSIONS[
            Role.SUPERADMIN
        ]
    }


def test_endpoint_rechaza_rol_no_administrativo(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="prof-endpoint-sa10@utem.cl",
        rol="profesional",
    )

    with pytest.raises(HTTPException) as exc:
        obtener_mi_acceso_administrativo(
            db=db,
            current_user={
                "id": usuario.id,
                "rol": "profesional",
            },
        )

    assert exc.value.status_code == 403


def test_superadmin_degradado_a_admin_usa_rol_y_contexto_actual_de_bd(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="super-degradado-admin-sa10@utem.cl",
        rol="admin",
    )

    _crear_acceso(
        db,
        usuario,
        perfil="administrador_general",
        tipo_alcance="institucional",
        permisos=[
            Permission.AGENDA_VER,
        ],
    )

    # La sesion entregada al helper afirma un rol viejo.
    # La fila Usuario actual de BD debe prevalecer.
    acceso = obtener_acceso_administrativo_efectivo(
        db,
        {
            "id": usuario.id,
            "rol": "superadmin",
        },
    )

    assert acceso is not None
    assert acceso.rol is Role.ADMIN
    assert (
        acceso.perfil
        is PerfilAccesoAdmin.ADMINISTRADOR_GENERAL
    )
    assert acceso.permisos == frozenset(
        {
            Permission.AGENDA_VER,
        }
    )


@pytest.mark.parametrize(
    "rol_actual",
    [
        "profesional",
        "estudiante",
    ],
)
def test_sesion_admin_vieja_no_sobrevive_cambio_a_rol_no_administrativo(
    db,
    rol_actual,
):
    usuario = _crear_usuario(
        db,
        correo=f"{rol_actual}-desde-admin-sa10@utem.cl",
        rol=rol_actual,
    )

    acceso = obtener_acceso_administrativo_efectivo(
        db,
        {
            "id": usuario.id,
            "rol": "superadmin",
        },
    )

    assert acceso is None


def test_endpoint_admin_valido_con_cero_permisos_devuelve_lista_vacia(
    db,
):
    usuario = _crear_usuario(
        db,
        correo="admin-endpoint-cero-sa10@utem.cl",
    )

    _crear_acceso(
        db,
        usuario,
        perfil="administrador_general",
        tipo_alcance="institucional",
    )

    respuesta = obtener_mi_acceso_administrativo(
        db=db,
        current_user={
            "id": usuario.id,
            "rol": "admin",
        },
    )

    assert respuesta == {
        "rol": "admin",
        "perfil": "administrador_general",
        "permisos": [],
        "alcance": {
            "tipo": "institucional",
            "especialidades": [],
        },
    }
