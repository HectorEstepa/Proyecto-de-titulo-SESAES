from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.cita import Cita
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

    def join(self, *args, **kwargs):
        self.events.append("join")
        return self

    def filter(self, *conditions):
        self.events.append("filter")
        self.filter_calls.append(conditions)
        return self

    def order_by(self, *args, **kwargs):
        self.events.append("order_by")
        return self

    def all(self):
        self.events.append("all")
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDB:
    def __init__(
        self,
        *,
        citas=None,
        profesionales=None,
        usuarios=None,
    ):
        self.cita_query = RecordingQuery(
            citas or []
        )

        self.profesionales = list(
            profesionales or []
        )

        self.usuarios = list(
            usuarios or []
        )

        self.query_calls = []

    def query(self, model):
        self.query_calls.append(model)

        if model is Cita:
            return self.cita_query

        if model is Profesional:
            return RecordingQuery(
                self.profesionales
            )

        if model is Usuario:
            return RecordingQuery(
                self.usuarios
            )

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


def test_historial_limitado_aplica_scope(
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
        lambda db, alcance: [
            10,
            11,
        ],
    )

    resultado = admin.get_historial_admin(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []

    assert _filtros_scope(
        db.cita_query
    ) == [
        [10, 11],
    ]


def test_profesional_id_del_request_no_bypassea_scope(
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
        lambda db, alcance: [
            10,
        ],
    )

    admin.get_historial_admin(
        profesional_id=999,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert _filtros_scope(
        db.cita_query
    ) == [
        [10],
    ]

    # Debe existir adem?s un segundo filtro sobre profesional_id:
    # el solicitado por el usuario.
    filtros_profesional = []

    for call in db.cita_query.filter_calls:
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
            ) == "profesional_id":
                filtros_profesional.append(
                    condition
                )

    assert len(filtros_profesional) >= 2


def test_especialidad_del_request_no_elimina_scope(
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
        lambda db, alcance: [
            10,
        ],
    )

    admin.get_historial_admin(
        especialidad="Odontolog?a",
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert _filtros_scope(
        db.cita_query
    ) == [
        [10],
    ]


def test_historial_institucional_no_agrega_scope(
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

    resultado = admin.get_historial_admin(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado == []

    assert _filtros_scope(
        db.cita_query
    ) == []


def test_historial_sin_profesionales_devuelve_vacio(
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

    resultado = admin.get_historial_admin(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []

    # No debe ejecutar una consulta global de Cita.
    assert Cita not in db.query_calls


def test_historial_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_historial_admin(
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []


def test_historial_conserva_formato_operacional(
    monkeypatch,
):
    cita = SimpleNamespace(
        id=100,
        profesional_id=10,
        estudiante_id=20,
        fecha="2026-09-01",
        hora="09:00",
        estado="completada",
        urgente=True,
    )

    profesional = SimpleNamespace(
        id=10,
        nombre="Profesional Uno",
        especialidad="Nutrici?n",
        iniciales="PU",
    )

    estudiante = SimpleNamespace(
        id=20,
        nombre="Ana",
        rut="11.111.111-1",
        carrera="Gastronom?a",
    )

    db = FakeDB(
        citas=[
            cita,
        ],
        profesionales=[
            profesional,
        ],
        usuarios=[
            estudiante,
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = admin.get_historial_admin(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 1

    assert resultado[0] == {
        "id": 100,
        "estudiante": "Ana",
        "rut": "11.111.111-1",
        "carrera": "Gastronom?a",
        "especialidad": "Nutrici?n",
        "profesional": "Profesional Uno",
        "iniciales": "PU",
        "fecha": "2026-09-01",
        "hora": "09:00",
        "estado": "completada",
        "urgente": True,
        "tiene_pdf": True,
    }
