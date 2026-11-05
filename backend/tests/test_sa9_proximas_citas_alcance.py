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


class BasicQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class CitaRecordingQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self.events = []
        self.filter_calls = []
        self.limit_value = None

    def filter(self, *conditions):
        self.events.append("filter")
        self.filter_calls.append(conditions)
        return self

    def order_by(self, *args):
        self.events.append("order_by")
        return self

    def limit(self, value):
        self.events.append("limit")
        self.limit_value = value
        return self

    def all(self):
        self.events.append("all")
        return list(self.rows)


class FakeDB:
    def __init__(
        self,
        *,
        profesionales=None,
        citas=None,
        usuarios=None,
    ):
        self.profesionales = list(profesionales or [])
        self.usuarios = list(usuarios or [])
        self.cita_query = CitaRecordingQuery(citas or [])
        self.cita_query_count = 0

    def query(self, model):
        if model is Cita:
            self.cita_query_count += 1
            return self.cita_query

        if model is Profesional:
            return BasicQuery(self.profesionales)

        if model is Usuario:
            return BasicQuery(self.usuarios)

        return BasicQuery([])


def _prof(
    id_,
    especialidad,
    nombre="Profesional",
):
    return SimpleNamespace(
        id=id_,
        especialidad=especialidad,
        nombre=nombre,
    )


def _cita(
    id_,
    *,
    profesional_id,
    estudiante_id=20,
):
    return SimpleNamespace(
        id=id_,
        profesional_id=profesional_id,
        estudiante_id=estudiante_id,
        fecha="2099-01-01",
        hora="09:00",
        estado="pendiente",
        urgente=False,
    )


def _usuario(
    id_=20,
    nombre="Ana",
):
    return SimpleNamespace(
        id=id_,
        nombre=nombre,
        rut="11.111.111-1",
    )


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


def test_helper_ids_profesionales_filtra_y_normaliza():
    db = FakeDB(
        profesionales=[
            _prof(
                1,
                "  NUTRICI?N ",
            ),
            _prof(
                2,
                "Odontolog?a",
            ),
            _prof(
                3,
                "Kinesiolog?a",
            ),
        ]
    )

    ids = admin._ids_profesionales_en_alcance(
        db,
        _alcance_limitado(
            "Nutrici?n",
            "Kinesiolog?a",
        ),
    )

    assert ids == [1, 3]


def test_proximas_citas_limitado_aplica_alcance_antes_del_limit(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _prof(
                2,
                "Nutrici?n",
                "Nutri",
            )
        ],
        citas=[
            _cita(
                10,
                profesional_id=2,
            )
        ],
        usuarios=[
            _usuario(),
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
        lambda db, alcance: [2],
    )

    resultado = admin.get_proximas_citas(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert len(resultado) == 1

    # Primera llamada: fecha + estado.
    # Segunda llamada: profesional_id IN ids permitidos.
    # El filtro de alcance ocurre antes de order_by y limit.
    assert db.cita_query.events == [
        "filter",
        "filter",
        "order_by",
        "limit",
        "all",
    ]

    assert db.cita_query.limit_value == 20

    scope_conditions = db.cita_query.filter_calls[1]
    assert len(scope_conditions) == 1

    condition = scope_conditions[0]

    assert getattr(
        condition.left,
        "name",
        None,
    ) == "profesional_id"

    assert list(condition.right.value) == [2]


def test_proximas_citas_institucional_no_aplica_filtro_in(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _prof(
                2,
                "Nutrici?n",
                "Nutri",
            )
        ],
        citas=[
            _cita(
                10,
                profesional_id=2,
            )
        ],
        usuarios=[
            _usuario(),
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.get_proximas_citas(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 1

    assert db.cita_query.events == [
        "filter",
        "order_by",
        "limit",
        "all",
    ]

    assert db.cita_query.limit_value == 20


def test_proximas_citas_sin_profesionales_en_alcance_devuelve_vacio(
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

    resultado = admin.get_proximas_citas(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []

    # Se crea la query base, pero nunca se ejecuta order/limit/all.
    assert db.cita_query.events == [
        "filter",
    ]


def test_proximas_citas_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_proximas_citas(
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.cita_query_count == 0


def test_proximas_citas_conserva_campos_operacionales(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _prof(
                2,
                "Nutrici?n",
                "Nutri",
            )
        ],
        citas=[
            _cita(
                10,
                profesional_id=2,
            )
        ],
        usuarios=[
            _usuario(),
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.get_proximas_citas(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert set(resultado[0]) == {
        "id",
        "estudiante",
        "rut",
        "especialidad",
        "profesional",
        "profesional_id",
        "fecha",
        "hora",
        "urgente",
        "estado",
    }

    assert "medicamento" not in resultado[0]
    assert "observaciones_atencion" not in resultado[0]
