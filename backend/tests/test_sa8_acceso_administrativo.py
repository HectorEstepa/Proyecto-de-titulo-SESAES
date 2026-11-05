import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.usuario import Usuario
from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminEspecialidad,
)
from app.rbac.admin_access import (
    PerfilAccesoAdmin,
    TipoAlcanceAdmin,
    normalizar_especialidad,
    validar_configuracion_acceso_admin,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")

    Usuario.__table__.create(bind=engine)
    AccesoAdministrativo.__table__.create(bind=engine)
    AccesoAdminEspecialidad.__table__.create(bind=engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _usuario_admin(db, correo="admin-sa8@utem.cl"):
    usuario = Usuario(
        correo=correo,
        password="hash-prueba",
        rol="admin",
        activo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def test_catalogo_perfiles_sa8():
    assert {p.value for p in PerfilAccesoAdmin} == {
        "administrador_general",
        "administrador_especialidad",
        "secretaria_general",
        "secretaria_especialidad",
    }


def test_catalogo_tipos_alcance_sa8():
    assert {a.value for a in TipoAlcanceAdmin} == {
        "institucional",
        "especialidades",
    }


@pytest.mark.parametrize(
    "perfil",
    [
        "administrador_general",
        "secretaria_general",
    ],
)
def test_perfiles_generales_solo_institucional(perfil):
    perfil_out, alcance, especialidades = validar_configuracion_acceso_admin(
        rol_usuario="admin",
        perfil=perfil,
        tipo_alcance="institucional",
        especialidades=[],
    )

    assert perfil_out.value == perfil
    assert alcance is TipoAlcanceAdmin.INSTITUCIONAL
    assert especialidades == ()


@pytest.mark.parametrize(
    "perfil",
    [
        "administrador_especialidad",
        "secretaria_especialidad",
    ],
)
def test_perfiles_especialidad_requieren_especialidades(perfil):
    perfil_out, alcance, especialidades = validar_configuracion_acceso_admin(
        rol_usuario="admin",
        perfil=perfil,
        tipo_alcance="especialidades",
        especialidades=[" Medicina   General ", "Psicologia"],
    )

    assert perfil_out.value == perfil
    assert alcance is TipoAlcanceAdmin.ESPECIALIDADES
    assert [e.nombre for e in especialidades] == [
        "Medicina General",
        "Psicologia",
    ]


@pytest.mark.parametrize("rol", ["superadmin", "profesional", "estudiante", "", None])
def test_solo_admin_puede_tener_configuracion(rol):
    with pytest.raises(ValueError):
        validar_configuracion_acceso_admin(
            rol_usuario=rol,
            perfil="administrador_general",
            tipo_alcance="institucional",
            especialidades=[],
        )


def test_general_no_puede_declarar_especialidades():
    with pytest.raises(ValueError):
        validar_configuracion_acceso_admin(
            rol_usuario="admin",
            perfil="administrador_general",
            tipo_alcance="institucional",
            especialidades=["Medicina General"],
        )


def test_perfil_especialidad_no_puede_ser_institucional():
    with pytest.raises(ValueError):
        validar_configuracion_acceso_admin(
            rol_usuario="admin",
            perfil="administrador_especialidad",
            tipo_alcance="institucional",
            especialidades=["Medicina General"],
        )


def test_perfil_especialidad_requiere_al_menos_una():
    with pytest.raises(ValueError):
        validar_configuracion_acceso_admin(
            rol_usuario="admin",
            perfil="administrador_especialidad",
            tipo_alcance="especialidades",
            especialidades=[],
        )


def test_especialidades_duplicadas_fallan_tras_normalizar():
    with pytest.raises(ValueError):
        validar_configuracion_acceso_admin(
            rol_usuario="admin",
            perfil="secretaria_especialidad",
            tipo_alcance="especialidades",
            especialidades=[
                "Psicologia",
                "  PSICOLOGIA  ",
            ],
        )


def test_normalizacion_conserva_nombre_y_genera_clave_casefold():
    valor = normalizar_especialidad("  Medicina    General  ")

    assert valor.nombre == "Medicina General"
    assert valor.normalizada == "medicina general"


def test_usuario_solo_puede_tener_un_acceso_administrativo(db):
    usuario = _usuario_admin(db)

    db.add(
        AccesoAdministrativo(
            usuario_id=usuario.id,
            perfil="administrador_general",
            tipo_alcance="institucional",
        )
    )
    db.commit()

    db.add(
        AccesoAdministrativo(
            usuario_id=usuario.id,
            perfil="secretaria_general",
            tipo_alcance="institucional",
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_db_rechaza_combinacion_perfil_alcance_invalida(db):
    usuario = _usuario_admin(db)

    db.add(
        AccesoAdministrativo(
            usuario_id=usuario.id,
            perfil="administrador_general",
            tipo_alcance="especialidades",
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_db_rechaza_especialidad_normalizada_duplicada(db):
    usuario = _usuario_admin(db)

    acceso = AccesoAdministrativo(
        usuario_id=usuario.id,
        perfil="administrador_especialidad",
        tipo_alcance="especialidades",
    )
    db.add(acceso)
    db.commit()
    db.refresh(acceso)

    db.add(
        AccesoAdminEspecialidad(
            acceso_admin_id=acceso.id,
            especialidad="Psicologia",
            especialidad_normalizada="psicologia",
        )
    )
    db.commit()

    db.add(
        AccesoAdminEspecialidad(
            acceso_admin_id=acceso.id,
            especialidad="PSICOLOGIA",
            especialidad_normalizada="psicologia",
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()
