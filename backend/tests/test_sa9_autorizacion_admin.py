import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminEspecialidad,
    AccesoAdminPermiso,
)
from app.models.usuario import Usuario
from app.rbac.admin_authorization import (
    especialidad_en_alcance_admin,
    obtener_contexto_admin,
    tiene_permiso_admin,
    tiene_permiso_admin_en_especialidad,
    tiene_permiso_efectivo,
)
from app.rbac.permissions import Permission


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")

    Usuario.__table__.create(engine)
    AccesoAdministrativo.__table__.create(engine)
    AccesoAdminEspecialidad.__table__.create(engine)
    AccesoAdminPermiso.__table__.create(engine)

    with Session(engine) as session:
        yield session


def _usuario(
    db,
    *,
    correo,
    rol="admin",
    activo=True,
):
    usuario = Usuario(
        correo=correo,
        password="hash",
        rol=rol,
        nombre="Usuario SA9.3",
        activo=activo,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def _acceso(
    db,
    usuario,
    *,
    perfil="administrador_general",
    tipo_alcance="institucional",
    especialidades=(),
    permisos=(),
    normalizadas_override=None,
):
    acceso = AccesoAdministrativo(
        usuario_id=usuario.id,
        perfil=perfil,
        tipo_alcance=tipo_alcance,
    )
    db.add(acceso)
    db.flush()

    overrides = normalizadas_override or {}

    for especialidad in especialidades:
        db.add(
            AccesoAdminEspecialidad(
                acceso_admin_id=acceso.id,
                especialidad=especialidad,
                especialidad_normalizada=overrides.get(
                    especialidad,
                    especialidad.strip().casefold(),
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


def test_admin_con_permiso_persistido_y_permitido_pasa(db):
    usuario = _usuario(
        db,
        correo="admin1@utem.cl",
    )
    _acceso(
        db,
        usuario,
        permisos=[Permission.USUARIOS_VER],
    )

    assert tiene_permiso_admin(
        db,
        usuario.id,
        Permission.USUARIOS_VER,
    )


def test_admin_sin_configuracion_falla_cerrado(db):
    usuario = _usuario(
        db,
        correo="admin2@utem.cl",
    )

    assert not tiene_permiso_admin(
        db,
        usuario.id,
        Permission.USUARIOS_VER,
    )


def test_admin_sin_permiso_persistido_falla_cerrado(db):
    usuario = _usuario(
        db,
        correo="admin3@utem.cl",
    )
    _acceso(db, usuario)

    assert not tiene_permiso_admin(
        db,
        usuario.id,
        Permission.USUARIOS_VER,
    )


def test_permiso_persistido_fuera_del_techo_del_perfil_no_autoriza(db):
    usuario = _usuario(
        db,
        correo="secretaria1@utem.cl",
    )
    _acceso(
        db,
        usuario,
        perfil="secretaria_general",
        tipo_alcance="institucional",
        # La BD permite este permiso porque es delegable en general,
        # pero el perfil secretaria NO permite gestion profesional.
        permisos=[Permission.PROFESIONALES_GESTIONAR],
    )

    assert not tiene_permiso_admin(
        db,
        usuario.id,
        Permission.PROFESIONALES_GESTIONAR,
    )


def test_admin_inactivo_falla_cerrado_aunque_tenga_permiso(db):
    usuario = _usuario(
        db,
        correo="admin4@utem.cl",
        activo=False,
    )
    _acceso(
        db,
        usuario,
        permisos=[Permission.AGENDA_VER],
    )

    assert not tiene_permiso_admin(
        db,
        usuario.id,
        Permission.AGENDA_VER,
    )


def test_rol_no_admin_no_puede_usar_configuracion_dormida(db):
    usuario = _usuario(
        db,
        correo="prof1@utem.cl",
        rol="profesional",
    )
    _acceso(
        db,
        usuario,
        permisos=[Permission.AGENDA_VER],
    )

    assert not tiene_permiso_admin(
        db,
        usuario.id,
        Permission.AGENDA_VER,
    )


def test_perfil_especialidad_sin_especialidades_falla_cerrado(db):
    usuario = _usuario(
        db,
        correo="admin5@utem.cl",
    )
    _acceso(
        db,
        usuario,
        perfil="administrador_especialidad",
        tipo_alcance="especialidades",
        permisos=[Permission.AGENDA_VER],
    )

    assert obtener_contexto_admin(db, usuario.id) is None
    assert not tiene_permiso_admin(
        db,
        usuario.id,
        Permission.AGENDA_VER,
    )


def test_perfil_institucional_con_especialidades_residuales_falla_cerrado(db):
    usuario = _usuario(
        db,
        correo="admin6@utem.cl",
    )
    _acceso(
        db,
        usuario,
        perfil="administrador_general",
        tipo_alcance="institucional",
        especialidades=["Nutricion"],
        permisos=[Permission.AGENDA_VER],
    )

    assert obtener_contexto_admin(db, usuario.id) is None


def test_especialidad_limitada_normaliza_unicode_mayusculas_y_espacios(db):
    usuario = _usuario(
        db,
        correo="admin7@utem.cl",
    )
    _acceso(
        db,
        usuario,
        perfil="administrador_especialidad",
        tipo_alcance="especialidades",
        especialidades=["  Nutrici?n  "],
        permisos=[Permission.AGENDA_VER],
    )

    assert especialidad_en_alcance_admin(
        db,
        usuario.id,
        "NUTRICI?N",
    )

    assert not especialidad_en_alcance_admin(
        db,
        usuario.id,
        "Odontolog?a",
    )


def test_no_confia_en_normalizada_almacenada_para_ampliar_alcance(db):
    usuario = _usuario(
        db,
        correo="admin8@utem.cl",
    )
    _acceso(
        db,
        usuario,
        perfil="administrador_especialidad",
        tipo_alcance="especialidades",
        especialidades=["Nutrici?n"],
        permisos=[Permission.AGENDA_VER],
        normalizadas_override={
            "Nutrici?n": "odontolog?a",
        },
    )

    assert especialidad_en_alcance_admin(
        db,
        usuario.id,
        "Nutrici?n",
    )

    assert not especialidad_en_alcance_admin(
        db,
        usuario.id,
        "Odontolog?a",
    )


def test_alcance_institucional_cubre_especialidad_valida(db):
    usuario = _usuario(
        db,
        correo="admin9@utem.cl",
    )
    _acceso(
        db,
        usuario,
        permisos=[Permission.AGENDA_VER],
    )

    assert especialidad_en_alcance_admin(
        db,
        usuario.id,
        "Medicina General",
    )


@pytest.mark.parametrize(
    "especialidad",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_especialidad_invalida_falla_cerrado(
    db,
    especialidad,
):
    usuario = _usuario(
        db,
        correo=f"admin-invalid-{repr(especialidad)}@utem.cl",
    )
    _acceso(
        db,
        usuario,
        permisos=[Permission.AGENDA_VER],
    )

    assert not especialidad_en_alcance_admin(
        db,
        usuario.id,
        especialidad,
    )


def test_permiso_y_alcance_deben_cumplirse_juntos(db):
    usuario = _usuario(
        db,
        correo="admin10@utem.cl",
    )
    _acceso(
        db,
        usuario,
        perfil="administrador_especialidad",
        tipo_alcance="especialidades",
        especialidades=["Odontolog?a"],
        permisos=[Permission.AGENDA_VER],
    )

    assert tiene_permiso_admin_en_especialidad(
        db,
        usuario.id,
        Permission.AGENDA_VER,
        "odontolog?a",
    )

    assert not tiene_permiso_admin_en_especialidad(
        db,
        usuario.id,
        Permission.AGENDA_VER,
        "Nutrici?n",
    )

    assert not tiene_permiso_admin_en_especialidad(
        db,
        usuario.id,
        Permission.USUARIOS_VER,
        "Odontolog?a",
    )


def test_resolver_usa_rol_actual_bd_no_rol_del_payload(db):
    usuario = _usuario(
        db,
        correo="super1@utem.cl",
        rol="superadmin",
    )

    current_user_viejo = {
        "id": usuario.id,
        "rol": "admin",
    }

    assert tiene_permiso_efectivo(
        db,
        current_user_viejo,
        Permission.ROLES_GESTIONAR,
    )


def test_payload_superadmin_no_salva_admin_sin_configuracion(db):
    usuario = _usuario(
        db,
        correo="admin11@utem.cl",
        rol="admin",
    )

    current_user_viejo = {
        "id": usuario.id,
        "rol": "superadmin",
    }

    assert not tiene_permiso_efectivo(
        db,
        current_user_viejo,
        Permission.ROLES_GESTIONAR,
    )

    assert not tiene_permiso_efectivo(
        db,
        current_user_viejo,
        Permission.AGENDA_VER,
    )


def test_superadmin_no_recibe_permiso_clinico(db):
    usuario = _usuario(
        db,
        correo="super2@utem.cl",
        rol="superadmin",
    )

    assert not tiene_permiso_efectivo(
        db,
        {"id": usuario.id, "rol": "superadmin"},
        Permission.FICHA_VER_ASIGNADA,
    )


def test_profesional_conserva_capacidad_rbac_de_rol(db):
    usuario = _usuario(
        db,
        correo="prof2@utem.cl",
        rol="profesional",
    )

    assert tiene_permiso_efectivo(
        db,
        {"id": usuario.id, "rol": "profesional"},
        Permission.FICHA_VER_ASIGNADA,
    )


@pytest.mark.parametrize(
    "current_user",
    [
        None,
        {},
        {"id": None},
        {"id": "1"},
        {"id": True},
    ],
)
def test_current_user_malformado_falla_cerrado(
    db,
    current_user,
):
    assert not tiene_permiso_efectivo(
        db,
        current_user,
        Permission.AGENDA_VER,
    )


def test_permiso_desconocido_falla_cerrado(db):
    usuario = _usuario(
        db,
        correo="admin12@utem.cl",
    )
    _acceso(
        db,
        usuario,
        permisos=[Permission.AGENDA_VER],
    )

    assert not tiene_permiso_admin(
        db,
        usuario.id,
        "sistema.control_total",
    )

    assert not tiene_permiso_efectivo(
        db,
        {"id": usuario.id, "rol": "admin"},
        "sistema.control_total",
    )
