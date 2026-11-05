import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class RecordingQuery:
    def __init__(self, count_value):
        self.count_value = count_value
        self.filter_calls = []

    def filter(self, *conditions):
        self.filter_calls.append(conditions)
        return self

    def count(self):
        return self.count_value


class FakeDB:
    def __init__(self, counts=None):
        self.counts = list(counts or [])
        self.queries = []

    def query(self, model):
        assert model is Cita

        value = (
            self.counts.pop(0)
            if self.counts
            else 0
        )

        query = RecordingQuery(value)

        self.queries.append(query)

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


def _filtros_scope(db):
    encontrados = []

    for query in db.queries:
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


def test_grafico_semana_limitado_filtra_los_7_dias(
    monkeypatch,
):
    db = FakeDB(
        counts=[
            1,
            2,
            3,
            4,
            5,
            6,
            7,
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

    resultado = admin.get_grafico_semana(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert len(resultado) == 7

    assert [
        fila["cantidad"]
        for fila in resultado
    ] == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
    ]

    assert _filtros_scope(db) == [
        [10, 11],
        [10, 11],
        [10, 11],
        [10, 11],
        [10, 11],
        [10, 11],
        [10, 11],
    ]


def test_grafico_semana_institucional_no_agrega_scope(
    monkeypatch,
):
    db = FakeDB(
        counts=[
            1,
            1,
            1,
            1,
            1,
            1,
            1,
        ]
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = admin.get_grafico_semana(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 7
    assert _filtros_scope(db) == []


def test_grafico_semana_sin_profesionales_devuelve_7_ceros(
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

    resultado = admin.get_grafico_semana(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert len(resultado) == 7

    assert all(
        fila["cantidad"] == 0
        for fila in resultado
    )

    # Nunca debe ejecutar conteos globales.
    assert db.queries == []


def test_grafico_semana_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_grafico_semana(
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.queries == []


def test_grafico_semana_conserva_los_7_dias(
    monkeypatch,
):
    db = FakeDB(
        counts=[
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = admin.get_grafico_semana(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert [
        fila["dia"]
        for fila in resultado
    ] == [
        "Lun",
        "Mar",
        "Mi?",
        "Jue",
        "Vie",
        "S?b",
        "Dom",
    ]

    assert all(
        set(fila) == {
            "dia",
            "fecha",
            "cantidad",
        }
        for fila in resultado
    )
