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
from app.routers import agenda


class FakeQuery:
    def __init__(self, results):
        self._results = list(results)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._results[0] if self._results else None

    def all(self):
        return list(self._results)


class FakeDB:
    def __init__(
        self,
        profesionales=None,
        citas=None,
        usuarios=None,
    ):
        self.data = {
            Profesional: list(profesionales or []),
            Cita: list(citas or []),
            Usuario: list(usuarios or []),
        }

    def query(self, model):
        return FakeQuery(
            self.data.get(model, [])
        )


def _prof(
    id_,
    especialidad,
    nombre="Profesional",
):
    return SimpleNamespace(
        id=id_,
        nombre=nombre,
        especialidad=especialidad,
    )


def _cita(
    id_=10,
    profesional_id=1,
    estudiante_id=20,
):
    return SimpleNamespace(
        id=id_,
        profesional_id=profesional_id,
        estudiante_id=estudiante_id,
        fecha="2026-09-07",
        hora="09:00",
        estado="pendiente",
        urgente=False,
        sobrecupo=False,
        medicamento="NO DEBE SALIR",
        observaciones_atencion="NO DEBE SALIR",
    )


def _usuario(
    id_=20,
    nombre="Ana",
):
    return SimpleNamespace(
        id=id_,
        nombre=nombre,
    )


def _alcance_limitado(*especialidades):
    return AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset(
            normalizar_especialidad(e).normalizada
            for e in especialidades
        ),
    )


def test_admin_ve_profesional_dentro_de_alcance(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _prof(
                1,
                "Nutrici?n",
                "Nutri",
            )
        ],
        citas=[
            _cita(
                profesional_id=1,
                estudiante_id=20,
            )
        ],
        usuarios=[
            _usuario(20, "Ana"),
        ],
    )

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    resultado = agenda.get_citas_profesional_admin(
        prof_id=1,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert len(resultado) == 1
    assert resultado[0]["especialidad"] == "Nutrici?n"
    assert resultado[0]["estudiante"] == "Ana"


def test_admin_no_ve_profesional_fuera_de_alcance(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _prof(
                1,
                "Odontolog?a",
                "Odonto",
            )
        ]
    )

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    with pytest.raises(HTTPException) as exc:
        agenda.get_citas_profesional_admin(
            prof_id=1,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403


def test_alcance_normaliza_especialidad(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _prof(
                1,
                "  NUTRICI?N ",
            )
        ]
    )

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    resultado = agenda.get_citas_profesional_admin(
        prof_id=1,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []


def test_superadmin_conserva_alcance_institucional():
    db = FakeDB(
        profesionales=[
            _prof(
                1,
                "Odontolog?a",
            )
        ]
    )

    resultado = agenda.get_citas_profesional_admin(
        prof_id=1,
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado == []


def test_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _prof(
                1,
                "Nutrici?n",
            )
        ]
    )

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        agenda.get_citas_profesional_admin(
            prof_id=1,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403


def test_respuesta_no_expone_campos_clinicos(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _prof(
                1,
                "Nutrici?n",
            )
        ],
        citas=[
            _cita(
                profesional_id=1,
                estudiante_id=20,
            )
        ],
        usuarios=[
            _usuario(20),
        ],
    )

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    resultado = agenda.get_citas_profesional_admin(
        prof_id=1,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert set(resultado[0]) == {
        "id",
        "estudiante",
        "estudiante_id",
        "especialidad",
        "fecha",
        "hora",
        "estado",
        "urgente",
        "sobrecupo",
    }

    assert "medicamento" not in resultado[0]
    assert "observaciones_atencion" not in resultado[0]
