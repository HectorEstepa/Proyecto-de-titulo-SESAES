from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.models.dia_cerrado import DiaCerrado
from app.models.profesional import Profesional
from app.models.usuario import Usuario
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

    def all(self):
        self.events.append("all")
        return list(self.rows)

    def first(self):
        self.events.append("first")
        return self.rows[0] if self.rows else None


class FakeDB:
    def __init__(
        self,
        *,
        dia=None,
        citas=None,
        estudiantes=None,
        profesionales=None,
    ):
        self.dia = dia
        self.citas = list(citas or [])
        self.estudiantes = list(estudiantes or [])
        self.profesionales = list(profesionales or [])

        self.cita_queries = []
        self.query_calls = []

    def query(self, model):
        self.query_calls.append(model)

        if model is DiaCerrado:
            return RecordingQuery(
                [self.dia] if self.dia is not None else []
            )

        if model is Cita:
            query = RecordingQuery(self.citas)
            self.cita_queries.append(query)
            return query

        if model is Usuario:
            return RecordingQuery(self.estudiantes)

        if model is Profesional:
            return RecordingQuery(self.profesionales)

        return RecordingQuery([])


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


def _dia():
    return SimpleNamespace(
        id=5,
        fecha="2026-09-18",
        motivo="Centro cerrado",
    )


def _cita():
    return SimpleNamespace(
        id=100,
        fecha="2026-09-18",
        hora="09:00",
        estudiante_id=20,
        profesional_id=10,
        cancelada_por_admin=True,
    )


def _estudiante():
    return SimpleNamespace(
        id=20,
        nombre="Ana",
        rut="11.111.111-1",
        correo="ana@ejemplo.cl",
    )


def _profesional():
    return SimpleNamespace(
        id=10,
        nombre="Profesional Uno",
        especialidad="Nutrici?n",
    )


def test_detalle_limitado_filtra_scope_antes_de_all(
    monkeypatch,
):
    db = FakeDB(
        dia=_dia(),
        citas=[_cita()],
        estudiantes=[_estudiante()],
        profesionales=[_profesional()],
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

    resultado = admin.citas_canceladas_por_dia_cerrado(
        dia_id=5,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == [
        {
            "cita_id": 100,
            "estudiante": "Ana",
            "rut": "11.111.111-1",
            "correo": "ana@ejemplo.cl",
            "profesional": "Profesional Uno",
            "especialidad": "Nutrici?n",
            "hora": "09:00",
        }
    ]

    assert len(db.cita_queries) == 1

    query = db.cita_queries[0]

    assert _filtros_scope(query) == [
        [10, 11],
    ]

    filter_indexes = [
        i
        for i, event in enumerate(query.events)
        if event == "filter"
    ]

    all_index = query.events.index("all")

    assert any(
        i < all_index
        for i in filter_indexes
    )


def test_detalle_institucional_no_agrega_scope(
    monkeypatch,
):
    db = FakeDB(
        dia=_dia(),
        citas=[_cita()],
        estudiantes=[_estudiante()],
        profesionales=[_profesional()],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.citas_canceladas_por_dia_cerrado(
        dia_id=5,
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 1

    assert _filtros_scope(
        db.cita_queries[0]
    ) == []


def test_detalle_sin_profesionales_visibles_devuelve_vacio(
    monkeypatch,
):
    db = FakeDB(
        dia=_dia(),
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
        lambda db, alcance: [],
    )

    resultado = admin.citas_canceladas_por_dia_cerrado(
        dia_id=5,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []

    # Se puede verificar el D?aCerrado institucional,
    # pero no debe consultar citas globales.
    assert db.cita_queries == []


def test_detalle_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB(
        dia=_dia(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.citas_canceladas_por_dia_cerrado(
            dia_id=5,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []


def test_detalle_dia_inexistente_conserva_404(
    monkeypatch,
):
    db = FakeDB(
        dia=None,
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    with pytest.raises(HTTPException) as exc:
        admin.citas_canceladas_por_dia_cerrado(
            dia_id=999,
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 404
    assert db.cita_queries == []
