import inspect

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Registrar modelos/relaciones antes de create_all.
import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.cita import Cita
from app.models.correo_log import CorreoLog
from app.models.profesional import Profesional
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import correos as m


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


def _alcance_limitado(*especialidades):
    return AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset(
            normalizar_especialidad(e).normalizada
            for e in especialidades
        ),
    )


def _alcance_institucional():
    return AlcanceAdministrativoEfectivo(
        institucional=True,
        especialidades_normalizadas=frozenset(),
    )


def _cargar_datos(db):
    nutricion = Profesional(
        id=10,
        nombre="Nutricionista",
        especialidad="Nutrici?n",
    )

    odontologia = Profesional(
        id=20,
        nombre="Odont?loga",
        especialidad="Odontolog?a",
    )

    db.add_all([
        nutricion,
        odontologia,
    ])

    db.flush()

    cita_nutricion = Cita(
        id=100,
        profesional_id=10,
        fecha="2026-09-20",
        hora="09:00",
        estado="pendiente",
    )

    cita_odontologia = Cita(
        id=200,
        profesional_id=20,
        fecha="2026-09-20",
        hora="10:00",
        estado="pendiente",
    )

    db.add_all([
        cita_nutricion,
        cita_odontologia,
    ])

    db.flush()

    correo_nutricion = CorreoLog(
        destinatario="uno@utem.cl",
        asunto="Nutrici?n",
        cuerpo="Correo vinculado a Nutrici?n",
        tipo="cancelacion",
        referencia_id=100,
    )

    correo_odontologia = CorreoLog(
        destinatario="dos@utem.cl",
        asunto="Odontolog?a",
        cuerpo="Correo vinculado a Odontolog?a",
        tipo="cancelacion",
        referencia_id=200,
    )

    correo_sin_referencia = CorreoLog(
        destinatario="tres@utem.cl",
        asunto="Seguridad",
        cuerpo="Correo sin cita relacionada",
        tipo="info",
        referencia_id=None,
    )

    db.add_all([
        correo_nutricion,
        correo_odontologia,
        correo_sin_referencia,
    ])

    db.commit()

    return {
        "nutricion": correo_nutricion.id,
        "odontologia": correo_odontologia.id,
        "sin_referencia": correo_sin_referencia.id,
    }


def test_get_correos_usa_reportes_ver_efectivo():
    source = inspect.getsource(
        m.get_correos
    )

    assert "require_effective_permission" in source

    assert (
        "Permission.REPORTES_VER"
        in source
    )

    assert "require_permission(" not in source


def test_sin_alcance_falla_antes_de_consultar_bd(
    monkeypatch,
):
    class ExplodingDB:
        def query(self, *args, **kwargs):
            raise AssertionError(
                "No deb?a consultar BD sin alcance."
            )

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        m.get_correos(
            db=ExplodingDB(),
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403


def test_limitado_solo_ve_correos_de_citas_en_scope(
    db_session,
    monkeypatch,
):
    ids = _cargar_datos(db_session)

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    resultado = m.get_correos(
        db=db_session,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    ids_visibles = {
        fila["id"]
        for fila in resultado
    }

    assert ids_visibles == {
        ids["nutricion"]
    }

    assert ids["odontologia"] not in ids_visibles
    assert ids["sin_referencia"] not in ids_visibles


def test_scope_normalizado_funciona(
    db_session,
    monkeypatch,
):
    ids = _cargar_datos(db_session)

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "  NUTRICI?N  "
        ),
    )

    resultado = m.get_correos(
        db=db_session,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert {
        fila["id"]
        for fila in resultado
    } == {
        ids["nutricion"]
    }


def test_institucional_conserva_todos_los_correos(
    db_session,
    monkeypatch,
):
    ids = _cargar_datos(db_session)

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = m.get_correos(
        db=db_session,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert {
        fila["id"]
        for fila in resultado
    } == set(ids.values())


def test_limitado_sin_profesionales_visibles_devuelve_vacio(
    db_session,
    monkeypatch,
):
    _cargar_datos(db_session)

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Especialidad inexistente"
        ),
    )

    resultado = m.get_correos(
        db=db_session,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []


def test_scope_se_aplica_antes_de_order_limit_y_all():
    source = inspect.getsource(
        m.get_correos
    )

    pos_ids = source.find(
        "_ids_profesionales_en_alcance"
    )

    pos_join = source.find(
        ".join("
    )

    pos_filter = source.find(
        "Cita.profesional_id.in_"
    )

    pos_order = source.find(
        ".order_by("
    )

    pos_limit = source.find(
        ".limit(100)"
    )

    pos_all = source.find(
        ".all()"
    )

    assert (
        -1
        < pos_ids
        < pos_join
        < pos_filter
        < pos_order
        < pos_limit
        < pos_all
    )
