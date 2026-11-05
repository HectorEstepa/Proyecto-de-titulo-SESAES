import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models.usuario import Usuario
from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminPermiso,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")

    Usuario.__table__.create(engine)
    AccesoAdministrativo.__table__.create(engine)
    AccesoAdminPermiso.__table__.create(engine)

    with Session(engine) as session:
        yield session


def _crear_usuario_admin(db: Session, correo: str) -> Usuario:
    usuario = Usuario(
        correo=correo,
        password="hash",
        rol="admin",
        nombre="Admin SA9",
        activo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def _crear_acceso(db: Session, usuario_id: int) -> AccesoAdministrativo:
    acceso = AccesoAdministrativo(
        usuario_id=usuario_id,
        perfil="administrador_general",
        tipo_alcance="institucional",
    )
    db.add(acceso)
    db.commit()
    db.refresh(acceso)
    return acceso


def test_persistir_permiso_admin_explicito(db):
    usuario = _crear_usuario_admin(db, "admin1@utem.cl")
    acceso = _crear_acceso(db, usuario.id)

    registro = AccesoAdminPermiso(
        acceso_admin_id=acceso.id,
        permiso="usuarios.ver",
    )

    db.add(registro)
    db.commit()
    db.refresh(registro)

    assert registro.id is not None
    assert registro.permiso == "usuarios.ver"


def test_no_existen_permisos_automaticos_al_crear_acceso(db):
    usuario = _crear_usuario_admin(db, "admin2@utem.cl")
    acceso = _crear_acceso(db, usuario.id)

    total = (
        db.query(AccesoAdminPermiso)
        .filter(AccesoAdminPermiso.acceso_admin_id == acceso.id)
        .count()
    )

    assert total == 0


def test_no_permite_permiso_duplicado_en_mismo_acceso(db):
    usuario = _crear_usuario_admin(db, "admin3@utem.cl")
    acceso = _crear_acceso(db, usuario.id)

    db.add(
        AccesoAdminPermiso(
            acceso_admin_id=acceso.id,
            permiso="agenda.ver",
        )
    )
    db.commit()

    db.add(
        AccesoAdminPermiso(
            acceso_admin_id=acceso.id,
            permiso="agenda.ver",
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


@pytest.mark.parametrize(
    "permiso",
    [
        "roles.gestionar",
        "auditoria.ver",
        "configuracion.gestionar",
        "reportes.cgr.exportar",
        "ficha.ver_asignada",
        "atenciones.registrar",
        "sistema.control_total",
    ],
)
def test_bd_rechaza_permiso_no_delegable(db, permiso):
    usuario = _crear_usuario_admin(
        db,
        f"admin-{permiso.replace('.', '-')}@utem.cl",
    )
    acceso = _crear_acceso(db, usuario.id)

    db.add(
        AccesoAdminPermiso(
            acceso_admin_id=acceso.id,
            permiso=permiso,
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_mismo_permiso_puede_existir_en_accesos_distintos(db):
    usuario1 = _crear_usuario_admin(db, "admin4@utem.cl")
    acceso1 = _crear_acceso(db, usuario1.id)

    usuario2 = _crear_usuario_admin(db, "admin5@utem.cl")
    acceso2 = _crear_acceso(db, usuario2.id)

    db.add_all(
        [
            AccesoAdminPermiso(
                acceso_admin_id=acceso1.id,
                permiso="reportes.ver",
            ),
            AccesoAdminPermiso(
                acceso_admin_id=acceso2.id,
                permiso="reportes.ver",
            ),
        ]
    )

    db.commit()

    assert db.query(AccesoAdminPermiso).count() == 2
