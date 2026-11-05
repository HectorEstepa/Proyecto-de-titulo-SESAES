from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class RecordingQuery:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.events = []
        self.filter_calls = []

    def filter(self, *conditions):
        self.events.append("filter")
        self.filter_calls.append(conditions)
        return self

    def join(self, *args, **kwargs):
        self.events.append("join")
        return self

    def distinct(self):
        self.events.append("distinct")
        return self

    def limit(self, value):
        self.events.append(("limit", value))
        return self

    def all(self):
        self.events.append("all")
        return list(self.rows)


class FakeDB:
    def __init__(self, estudiantes=None):
        self.estudiantes = list(estudiantes or [])
        self.query_calls = []
        self.usuario_query = None

    def query(self, model):
        self.query_calls.append(model)

        query = RecordingQuery(
            self.estudiantes
        )

        if getattr(model, "__name__", None) == "Usuario":
            self.usuario_query = query

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


def _filtros_scope(query):
    encontrados = []

    for call in query.filter_calls:
        for condition in call:
            left = getattr(
                condition,
                "left",
                None,
            )

            if getattr(
                left,
                "name",
                None,
            ) != "profesional_id":
                continue

            right = getattr(
                condition,
                "right",
                None,
            )

            value = getattr(
                right,
                "value",
                None,
            )

            if isinstance(
                value,
                (list, tuple, set),
            ):
                encontrados.append(
                    list(value)
                )

    return encontrados


def _estudiante():
    return SimpleNamespace(
        id=20,
        nombre="Ana",
        rut="11.111.111-1",
        carrera="Gastronom?a",
        correo="ana@ejemplo.cl",
    )


def test_busqueda_limitada_aplica_scope_antes_del_limit(
    monkeypatch,
):
    db = FakeDB(
        estudiantes=[
            _estudiante(),
        ]
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    monkeypatch.setattr(
        admin,
        "_ids_profesionales_en_alcance",
        lambda db, alcance: [
            10,
            11,
        ],
    )

    resultado = admin.buscar_estudiantes(
        q="Ana",
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == [
        {
            "id": 20,
            "nombre": "Ana",
            "rut": "11.111.111-1",
            "carrera": "Gastronom?a",
            "correo": "ana@ejemplo.cl",
        }
    ]

    assert _filtros_scope(
        db.usuario_query
    ) == [
        [10, 11],
    ]

    events = db.usuario_query.events

    scope_filter_indexes = [
        i
        for i, event in enumerate(events)
        if event == "filter"
    ]

    limit_index = events.index(
        ("limit", 10)
    )

    assert any(
        i < limit_index
        for i in scope_filter_indexes
    )

    assert events.index("distinct") < limit_index


def test_busqueda_institucional_no_agrega_scope(
    monkeypatch,
):
    db = FakeDB(
        estudiantes=[
            _estudiante(),
        ]
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = admin.buscar_estudiantes(
        q="Ana",
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 1

    assert _filtros_scope(
        db.usuario_query
    ) == []

    assert "join" not in db.usuario_query.events


def test_busqueda_sin_profesionales_en_scope_devuelve_vacio(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    monkeypatch.setattr(
        admin,
        "_ids_profesionales_en_alcance",
        lambda db, alcance: [],
    )

    resultado = admin.buscar_estudiantes(
        q="Ana",
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []

    # La query de Usuario puede construirse, pero nunca debe
    # llegar a limit/all sin profesionales visibles.
    assert db.usuario_query is not None
    assert ("limit", 10) not in db.usuario_query.events
    assert "all" not in db.usuario_query.events


def test_busqueda_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.buscar_estudiantes(
            q="Ana",
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []


def test_busqueda_corta_conserva_respuesta_vacia(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = admin.buscar_estudiantes(
        q="A",
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado == []
    assert db.query_calls == []
