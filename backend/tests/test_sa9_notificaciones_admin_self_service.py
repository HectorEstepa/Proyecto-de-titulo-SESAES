import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Registrar todos los modelos/relaciones antes de create_all().
import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.auth_dependencies import get_current_user
from app.database import Base
from app.models.notificacion import Notificacion
from app.models.usuario import Usuario
from app.routers import admin


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={
            "check_same_thread": False
        },
    )

    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _usuario(
    *,
    id,
    correo,
    rol,
):
    return Usuario(
        id=id,
        correo=correo,
        password="hash-no-relevante",
        rol=rol,
        nombre=f"Usuario {id}",
        activo=True,
    )


def test_admin_notificaciones_depende_solo_de_usuario_autenticado():
    parametro = inspect.signature(
        admin.get_notificaciones_admin
    ).parameters["current_user"]

    assert parametro.default.dependency is get_current_user


def test_admin_notificaciones_no_exige_permiso_administrativo():
    source = inspect.getsource(
        admin.get_notificaciones_admin
    )

    assert "require_permission(" not in source
    assert "require_effective_permission(" not in source

    assert "Permission.USUARIOS_GESTIONAR" not in source
    assert "Permission.USUARIOS_VER" not in source

    assert 'current_user["id"]' in source

    assert (
        "Notificacion.usuario_id == usuario_id"
        in source
    )


def test_admin_solo_recibe_sus_propias_notificaciones(
    db_session,
):
    usuario_admin = _usuario(
        id=101,
        correo="admin-self@utem.cl",
        rol="admin",
    )

    otro_usuario = _usuario(
        id=202,
        correo="otro@utem.cl",
        rol="admin",
    )

    db_session.add_all([
        usuario_admin,
        otro_usuario,
    ])

    db_session.flush()

    propia_1 = Notificacion(
        usuario_id=101,
        mensaje="Propia uno",
        tipo="info",
        leida=False,
    )

    ajena = Notificacion(
        usuario_id=202,
        mensaje="Ajena",
        tipo="advertencia",
        leida=False,
    )

    propia_2 = Notificacion(
        usuario_id=101,
        mensaje="Propia dos",
        tipo="info",
        leida=True,
    )

    db_session.add_all([
        propia_1,
        ajena,
        propia_2,
    ])

    db_session.commit()

    resultado = admin.get_notificaciones_admin(
        db=db_session,
        current_user={
            "id": 101,
            "rol": "admin",
            "correo": "admin-self@utem.cl",
        },
    )

    mensajes = {
        fila["mensaje"]
        for fila in resultado
    }

    assert mensajes == {
        "Propia uno",
        "Propia dos",
    }

    assert "Ajena" not in mensajes


def test_superadmin_tampoco_recibe_notificaciones_ajenas(
    db_session,
):
    superadmin = _usuario(
        id=301,
        correo="super-self@utem.cl",
        rol="superadmin",
    )

    otro = _usuario(
        id=302,
        correo="otro-super@utem.cl",
        rol="admin",
    )

    db_session.add_all([
        superadmin,
        otro,
    ])

    db_session.flush()

    propia = Notificacion(
        usuario_id=301,
        mensaje="Solo m?a",
        tipo="info",
        leida=False,
    )

    ajena = Notificacion(
        usuario_id=302,
        mensaje="No visible",
        tipo="info",
        leida=False,
    )

    db_session.add_all([
        propia,
        ajena,
    ])

    db_session.commit()

    resultado = admin.get_notificaciones_admin(
        db=db_session,
        current_user={
            "id": 301,
            "rol": "superadmin",
            "correo": "super-self@utem.cl",
        },
    )

    assert [
        fila["mensaje"]
        for fila in resultado
    ] == [
        "Solo m?a"
    ]


def test_endpoint_no_resuelve_scope_administrativo():
    source = inspect.getsource(
        admin.get_notificaciones_admin
    )

    assert (
        "obtener_alcance_administrativo_efectivo"
        not in source
    )

    assert (
        "especialidad_permitida_por_alcance"
        not in source
    )
