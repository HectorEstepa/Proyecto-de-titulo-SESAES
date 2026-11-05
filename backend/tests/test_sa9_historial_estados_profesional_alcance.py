import inspect
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.profesional import Profesional
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class RecordingQuery:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.events = []

    def filter(self, *conditions):
        self.events.append("filter")
        return self

    def order_by(self, *args):
        self.events.append("order_by")
        return self

    def first(self):
        self.events.append("first")
        return self.rows[0] if self.rows else None

    def all(self):
        self.events.append("all")
        return list(self.rows)


class FakeDB:
    def __init__(
        self,
        *,
        profesional=None,
        historial=None,
    ):
        self.profesional = profesional
        self.historial = list(historial or [])

        self.query_calls = []
        self.queries = []

    def query(self, model):
        name = getattr(
            model,
            "__name__",
            str(model),
        )

        self.query_calls.append(name)

        if model is Profesional:
            query = RecordingQuery(
                [self.profesional]
                if self.profesional is not None
                else []
            )
        elif name == "HistorialEstadoProfesional":
            query = RecordingQuery(
                self.historial
            )
        else:
            query = RecordingQuery([])

        self.queries.append(
            (name, query)
        )

        return query


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


def _profesional(
    *,
    especialidad="Nutrici?n",
):
    return SimpleNamespace(
        id=10,
        nombre="Profesional Uno",
        especialidad=especialidad,
    )


def _historial():
    return [
        SimpleNamespace(
            id=1,
            estado_anterior="activo",
            estado_nuevo="inactivo",
            motivo="Licencia",
            fecha=datetime(
                2026,
                9,
                1,
                10,
                30,
            ),
        ),
        SimpleNamespace(
            id=2,
            estado_anterior="inactivo",
            estado_nuevo="activo",
            motivo=None,
            fecha=None,
        ),
    ]


def test_historial_estados_usa_profesionales_ver_efectivo():
    source = inspect.getsource(
        admin.get_historial_estados
    )

    assert (
        "require_effective_permission(Permission.PROFESIONALES_VER)"
        in source
    )

    assert (
        "require_permission(Permission.PROFESIONALES_GESTIONAR)"
        not in source
    )


def test_historial_sin_alcance_falla_antes_de_bd(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_historial_estados(
            prof_id=10,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []


def test_historial_profesional_inexistente_da_404_sin_consultar_historial(
    monkeypatch,
):
    db = FakeDB(
        profesional=None,
        historial=_historial(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_historial_estados(
            prof_id=999,
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Profesional no encontrado"

    assert db.query_calls == [
        "Profesional"
    ]


def test_historial_fuera_de_scope_da_404_sin_consultar_historial(
    monkeypatch,
):
    db = FakeDB(
        profesional=_profesional(
            especialidad="Odontolog?a"
        ),
        historial=_historial(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_historial_estados(
            prof_id=10,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Profesional no encontrado"

    assert db.query_calls == [
        "Profesional"
    ]


def test_historial_dentro_de_scope_conserva_formato(
    monkeypatch,
):
    db = FakeDB(
        profesional=_profesional(),
        historial=_historial(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    resultado = admin.get_historial_estados(
        prof_id=10,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == [
        {
            "id": 1,
            "estado_anterior": "activo",
            "estado_nuevo": "inactivo",
            "motivo": "Licencia",
            "fecha": "2026-09-01T10:30:00",
        },
        {
            "id": 2,
            "estado_anterior": "inactivo",
            "estado_nuevo": "activo",
            "motivo": None,
            "fecha": None,
        },
    ]

    assert db.query_calls == [
        "Profesional",
        "HistorialEstadoProfesional",
    ]

    history_queries = [
        query
        for name, query in db.queries
        if name == "HistorialEstadoProfesional"
    ]

    assert len(history_queries) == 1
    assert history_queries[0].events == [
        "filter",
        "order_by",
        "all",
    ]


def test_historial_institucional_tambien_permite_profesional(
    monkeypatch,
):
    db = FakeDB(
        profesional=_profesional(
            especialidad="Odontolog?a"
        ),
        historial=[],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.get_historial_estados(
        prof_id=10,
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado == []

    assert db.query_calls == [
        "Profesional",
        "HistorialEstadoProfesional",
    ]


def test_scope_se_comprueba_antes_de_consultar_historial():
    source = inspect.getsource(
        admin.get_historial_estados
    )

    pos_prof = source.find(
        "db.query(Profesional)"
    )

    pos_scope = source.find(
        "especialidad_permitida_por_alcance"
    )

    pos_history = source.find(
        "db.query(HistorialEstadoProfesional)"
    )

    assert -1 < pos_prof < pos_scope < pos_history
