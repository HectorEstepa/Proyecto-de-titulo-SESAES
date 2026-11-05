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

    def join(self, *args, **kwargs):
        self.events.append("join")
        return self

    def filter(self, *conditions):
        self.events.append("filter")
        self.filter_calls.append(conditions)
        return self

    def group_by(self, *args):
        self.events.append("group_by")
        return self

    def all(self):
        self.events.append("all")
        return list(self.rows)


class FakeDB:
    def __init__(self, rows=None):
        self.query_obj = RecordingQuery(rows)

    def query(self, *entities):
        return self.query_obj


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


def _filtros_in_profesional_id(query):
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


def test_grafico_limitado_aplica_scope_antes_de_group_by(
    monkeypatch,
):
    db = FakeDB(
        rows=[
            ("Nutrici?n", 4),
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

    resultado = admin.get_grafico_especialidad(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == [
        {
            "especialidad": "Nutrici?n",
            "cantidad": 4,
            "porcentaje": 100,
        }
    ]

    assert _filtros_in_profesional_id(
        db.query_obj
    ) == [
        [10, 11],
    ]

    # Debe existir un filter de alcance antes de group_by.
    indice_group = db.query_obj.events.index(
        "group_by"
    )

    indices_filter = [
        i
        for i, event in enumerate(
            db.query_obj.events
        )
        if event == "filter"
    ]

    assert any(
        i < indice_group
        for i in indices_filter
    )


def test_grafico_institucional_no_agrega_scope_in(
    monkeypatch,
):
    db = FakeDB(
        rows=[
            ("Nutrici?n", 3),
            ("Odontolog?a", 1),
        ]
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.get_grafico_especialidad(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 2

    assert _filtros_in_profesional_id(
        db.query_obj
    ) == []


def test_grafico_sin_profesionales_en_scope_devuelve_vacio(
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

    resultado = admin.get_grafico_especialidad(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []

    # No debe ejecutar la query agregada.
    assert db.query_obj.events == []


def test_grafico_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_grafico_especialidad(
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_obj.events == []


def test_filtro_profesional_id_usuario_no_bypassea_scope(
    monkeypatch,
):
    db = FakeDB(
        rows=[]
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
        ],
    )

    admin.get_grafico_especialidad(
        profesional_id=999,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    # El filtro de alcance sigue presente aunque el usuario
    # solicite otro profesional por parametro.
    assert _filtros_in_profesional_id(
        db.query_obj
    ) == [
        [10],
    ]
