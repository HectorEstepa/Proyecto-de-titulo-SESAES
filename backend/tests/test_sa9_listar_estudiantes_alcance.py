from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.models.usuario import Usuario
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class RecordingQuery:
    def __init__(
        self,
        *,
        rows=None,
        count_value=0,
    ):
        self.rows = list(rows or [])
        self.count_value = count_value
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

    def count(self):
        self.events.append("count")
        return self.count_value

    def order_by(self, *args, **kwargs):
        self.events.append("order_by")
        return self

    def offset(self, value):
        self.events.append(("offset", value))
        return self

    def limit(self, value):
        self.events.append(("limit", value))
        return self

    def group_by(self, *args):
        self.events.append("group_by")
        return self

    def all(self):
        self.events.append("all")
        return list(self.rows)


class FakeDB:
    def __init__(
        self,
        *,
        estudiantes=None,
        total=0,
        conteos=None,
        atendidas=None,
    ):
        self.estudiante_query = RecordingQuery(
            rows=estudiantes,
            count_value=total,
        )

        self.aggregate_rows = [
            list(conteos or []),
            list(atendidas or []),
        ]

        self.aggregate_queries = []
        self.query_calls = []

    def query(self, *entities):
        self.query_calls.append(entities)

        if len(entities) == 1 and entities[0] is Usuario:
            return self.estudiante_query

        query = RecordingQuery(
            rows=(
                self.aggregate_rows.pop(0)
                if self.aggregate_rows
                else []
            )
        )

        self.aggregate_queries.append(query)

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


def _filtros_in_columna(
    query,
    nombre_columna,
):
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
            ) != nombre_columna:
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


def test_listado_limitado_scopea_total_y_paginacion(
    monkeypatch,
):
    db = FakeDB(
        estudiantes=[_estudiante()],
        total=1,
        conteos=[(20, 2)],
        atendidas=[(20, 1)],
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
        lambda db, alcance: [10, 11],
    )

    resultado = admin.listar_estudiantes(
        pagina=1,
        por_pagina=20,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "total": 1,
        "pagina": 1,
        "por_pagina": 20,
        "estudiantes": [
            {
                "id": 20,
                "nombre": "Ana",
                "rut": "11.111.111-1",
                "carrera": "Gastronom?a",
                "correo": "ana@ejemplo.cl",
                "citas_totales": 2,
                "citas_atendidas": 1,
            }
        ],
    }

    assert _filtros_in_columna(
        db.estudiante_query,
        "profesional_id",
    ) == [[10, 11]]

    events = db.estudiante_query.events

    assert events.index("distinct") < events.index("count")
    assert events.index("count") < events.index("order_by")
    assert events.index("count") < events.index(("offset", 0))
    assert events.index("count") < events.index(("limit", 20))


def test_metricas_limitadas_scopean_ambas_consultas(
    monkeypatch,
):
    db = FakeDB(
        estudiantes=[_estudiante()],
        total=1,
        conteos=[(20, 3)],
        atendidas=[(20, 2)],
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
        lambda db, alcance: [10],
    )

    resultado = admin.listar_estudiantes(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado["estudiantes"][0]["citas_totales"] == 3
    assert resultado["estudiantes"][0]["citas_atendidas"] == 2

    assert len(db.aggregate_queries) == 2

    for query in db.aggregate_queries:
        assert _filtros_in_columna(
            query,
            "profesional_id",
        ) == [[10]]


def test_listado_institucional_no_agrega_scope(
    monkeypatch,
):
    db = FakeDB(
        estudiantes=[_estudiante()],
        total=1,
        conteos=[(20, 5)],
        atendidas=[(20, 4)],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.listar_estudiantes(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado["total"] == 1
    assert resultado["estudiantes"][0]["citas_totales"] == 5
    assert resultado["estudiantes"][0]["citas_atendidas"] == 4

    assert "join" not in db.estudiante_query.events
    assert "distinct" not in db.estudiante_query.events

    assert _filtros_in_columna(
        db.estudiante_query,
        "profesional_id",
    ) == []

    for query in db.aggregate_queries:
        assert _filtros_in_columna(
            query,
            "profesional_id",
        ) == []


def test_listado_sin_profesionales_devuelve_vacio(
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

    resultado = admin.listar_estudiantes(
        pagina=2,
        por_pagina=10,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "total": 0,
        "pagina": 2,
        "por_pagina": 10,
        "estudiantes": [],
    }

    assert db.query_calls == []


def test_listado_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.listar_estudiantes(
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []


def test_listado_sin_estudiantes_no_ejecuta_metricas(
    monkeypatch,
):
    db = FakeDB(
        estudiantes=[],
        total=0,
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.listar_estudiantes(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado["total"] == 0
    assert resultado["estudiantes"] == []
    assert db.aggregate_queries == []
