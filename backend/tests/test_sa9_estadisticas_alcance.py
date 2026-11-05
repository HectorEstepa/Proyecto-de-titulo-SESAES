import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.models.profesional import Profesional
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class RecordingQuery:
    def __init__(
        self,
        model,
        count_value,
    ):
        self.model = model
        self.count_value = count_value
        self.filter_calls = []

    def filter(self, *conditions):
        self.filter_calls.append(conditions)
        return self

    def count(self):
        return self.count_value


class FakeDB:
    def __init__(
        self,
        *,
        cita_counts=None,
        profesional_counts=None,
    ):
        self.cita_counts = list(cita_counts or [])
        self.profesional_counts = list(
            profesional_counts or []
        )
        self.records = []

    def query(self, model):
        if model is Cita:
            value = (
                self.cita_counts.pop(0)
                if self.cita_counts
                else 0
            )
        elif model is Profesional:
            value = (
                self.profesional_counts.pop(0)
                if self.profesional_counts
                else 0
            )
        else:
            value = 0

        query = RecordingQuery(
            model,
            value,
        )

        self.records.append(query)

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


def _condiciones_por_modelo(db, model):
    return [
        condition
        for record in db.records
        if record.model is model
        for call in record.filter_calls
        for condition in call
    ]


def _valores_in_para_columna(
    db,
    model,
    nombre_columna,
):
    encontrados = []

    for condition in _condiciones_por_modelo(
        db,
        model,
    ):
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


def test_estadisticas_limitadas_filtran_todos_los_conteos(
    monkeypatch,
):
    # Orden de queries del endpoint:
    # Cita reservas
    # Profesional activos
    # Cita citas_hoy
    # Cita urgentes
    db = FakeDB(
        cita_counts=[
            4,
            6,
            2,
        ],
        profesional_counts=[
            3,
        ],
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
            11,
            12,
        ],
    )

    resultado = admin.get_estadisticas(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "reservas_hoy": 4,
        "profesionales_activos": 3,
        "horas_disponibles": 24,
        "urgentes": 2,
    }

    filtros_cita = _valores_in_para_columna(
        db,
        Cita,
        "profesional_id",
    )

    assert filtros_cita == [
        [11, 12],
        [11, 12],
        [11, 12],
    ]

    filtros_profesional = _valores_in_para_columna(
        db,
        Profesional,
        "id",
    )

    assert filtros_profesional == [
        [11, 12],
    ]


def test_estadisticas_institucionales_no_agregan_filtro_scope(
    monkeypatch,
):
    db = FakeDB(
        cita_counts=[
            10,
            12,
            3,
        ],
        profesional_counts=[
            5,
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.get_estadisticas(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado == {
        "reservas_hoy": 10,
        "profesionales_activos": 5,
        "horas_disponibles": 38,
        "urgentes": 3,
    }

    assert _valores_in_para_columna(
        db,
        Cita,
        "profesional_id",
    ) == []

    assert _valores_in_para_columna(
        db,
        Profesional,
        "id",
    ) == []


def test_estadisticas_sin_profesionales_en_alcance_devuelve_ceros(
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

    resultado = admin.get_estadisticas(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "reservas_hoy": 0,
        "profesionales_activos": 0,
        "horas_disponibles": 0,
        "urgentes": 0,
    }

    # No debe ejecutar conteos globales.
    assert db.records == []


def test_estadisticas_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_estadisticas(
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.records == []


def test_horas_disponibles_nunca_son_negativas(
    monkeypatch,
):
    db = FakeDB(
        cita_counts=[
            1,
            15,
            0,
        ],
        profesional_counts=[
            1,
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.get_estadisticas(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado["horas_disponibles"] == 0
