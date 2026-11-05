from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.models.profesional import Profesional
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class FakeQuery:
    def __init__(self, results):
        self._results = list(results)

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._results)

    def count(self):
        return len(self._results)


class FakeDB:
    def __init__(self, profesionales, citas=None):
        self.profesionales = list(profesionales)
        self.citas = list(citas or [])

    def query(self, model):
        if model is Profesional:
            return FakeQuery(self.profesionales)

        if model is Cita:
            return FakeQuery(self.citas)

        return FakeQuery([])


def _prof(
    id_,
    nombre,
    especialidad,
):
    return SimpleNamespace(
        id=id_,
        nombre=nombre,
        tratamiento=None,
        especialidad=especialidad,
        color_identificador=None,
        estado="activo",
    )


def _alcance_limitado(*especialidades):
    return AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset(
            normalizar_especialidad(e).normalizada
            for e in especialidades
        ),
    )


def test_resumen_limitado_excluye_profesionales_fuera_de_alcance(
    monkeypatch,
):
    db = FakeDB([
        _prof(
            1,
            "Nutri",
            "Nutrici?n",
        ),
        _prof(
            2,
            "Odonto",
            "Odontolog?a",
        ),
    ])

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    resultado = admin.get_resumen_dia(
        db=db,
        current_user={
            "id": 10,
            "rol": "admin",
        },
    )

    assert len(resultado) == 1
    assert resultado[0]["nombre"] == "Nutri"
    assert resultado[0]["especialidad"] == "Nutrici?n"


def test_resumen_limitado_admite_multiples_especialidades(
    monkeypatch,
):
    db = FakeDB([
        _prof(1, "Nutri", "Nutrici?n"),
        _prof(2, "Odonto", "Odontolog?a"),
        _prof(3, "Kine", "Kinesiolog?a"),
    ])

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n",
            "Kinesiolog?a",
        ),
    )

    resultado = admin.get_resumen_dia(
        db=db,
        current_user={
            "id": 10,
            "rol": "admin",
        },
    )

    assert {
        fila["especialidad"]
        for fila in resultado
    } == {
        "Nutrici?n",
        "Kinesiolog?a",
    }


def test_resumen_institucional_ve_todos(
    monkeypatch,
):
    db = FakeDB([
        _prof(1, "Nutri", "Nutrici?n"),
        _prof(2, "Odonto", "Odontolog?a"),
    ])

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            AlcanceAdministrativoEfectivo(
                institucional=True,
                especialidades_normalizadas=frozenset(),
            )
        ),
    )

    resultado = admin.get_resumen_dia(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 2


def test_resumen_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB([])

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_resumen_dia(
            db=db,
            current_user={
                "id": 10,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403


def test_resumen_conserva_campos_operacionales(
    monkeypatch,
):
    db = FakeDB([
        _prof(
            1,
            "Nutri",
            "Nutrici?n",
        ),
    ])

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            AlcanceAdministrativoEfectivo(
                institucional=True,
                especialidades_normalizadas=frozenset(),
            )
        ),
    )

    resultado = admin.get_resumen_dia(
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert set(resultado[0]) == {
        "profesional_id",
        "nombre",
        "tratamiento",
        "especialidad",
        "color_identificador",
        "estado",
        "citas_hoy",
    }
