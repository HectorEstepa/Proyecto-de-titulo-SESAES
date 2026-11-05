from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.profesional import Profesional
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class FakeQuery:
    def __init__(self, results):
        self._results = list(results)

    def all(self):
        return list(self._results)


class FakeDB:
    def __init__(self, profesionales):
        self.profesionales = profesionales

    def query(self, model):
        if model is Profesional:
            return FakeQuery(self.profesionales)
        return FakeQuery([])


def _prof(id_, nombre, especialidad):
    return SimpleNamespace(
        id=id_,
        nombre=nombre,
        tratamiento=None,
        especialidad=especialidad,
        iniciales="XX",
        descripcion=None,
        duracion_min=45,
        estado="activo",
        correo=f"prof{id_}@utem.cl",
        rut=None,
        usuario_id=None,
        horario_inicio="08:00",
        horario_fin="18:00",
        hora_almuerzo_inicio="13:00",
        hora_almuerzo_fin="13:30",
        foto_url=None,
        color_identificador=None,
    )


def _alcance_limitado(*especialidades):
    return AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset(
            normalizar_especialidad(e).normalizada
            for e in especialidades
        ),
    )


def test_limitado_filtra_profesionales_fuera_de_alcance(
    monkeypatch,
):
    db = FakeDB([
        _prof(1, "Nutri", "Nutrici?n"),
        _prof(2, "Odonto", "Odontolog?a"),
    ])

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    resultado = admin.get_profesionales_admin(
        db=db,
        current_user={"id": 10, "rol": "admin"},
    )

    assert [x["nombre"] for x in resultado] == ["Nutri"]


def test_limitado_admite_multiples_especialidades(
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

    resultado = admin.get_profesionales_admin(
        db=db,
        current_user={"id": 10, "rol": "admin"},
    )

    assert {x["especialidad"] for x in resultado} == {
        "Nutrici?n",
        "Kinesiolog?a",
    }


def test_institucional_ve_todos(monkeypatch):
    db = FakeDB([
        _prof(1, "Nutri", "Nutrici?n"),
        _prof(2, "Odonto", "Odontolog?a"),
    ])

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: AlcanceAdministrativoEfectivo(
            institucional=True,
            especialidades_normalizadas=frozenset(),
        ),
    )

    resultado = admin.get_profesionales_admin(
        db=db,
        current_user={"id": 1, "rol": "superadmin"},
    )

    assert len(resultado) == 2


def test_sin_alcance_da_403(monkeypatch):
    db = FakeDB([])

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.get_profesionales_admin(
            db=db,
            current_user={"id": 10, "rol": "admin"},
        )

    assert exc.value.status_code == 403


def test_el_listado_incluye_la_jornada_y_la_colacion_vigentes(monkeypatch):
    """La agenda administrativa necesita estas horas para mostrar la colación
    y la salida del profesional; sin ellas decía «Sin colación» aunque la
    grilla sí la tuviera."""
    db = FakeDB([_prof(1, "Nutri", "Nutrición")])
    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado("Nutrición"),
    )

    [fila] = admin.get_profesionales_admin(
        db=db, current_user={"id": 10, "rol": "admin"},
    )

    assert fila["horario_inicio"] == "08:00"
    assert fila["horario_fin"] == "18:00"
    assert fila["hora_almuerzo_inicio"] == "13:00"
    assert fila["hora_almuerzo_fin"] == "13:30"
