"""
SESAES — Fase 3.5F (bloque agenda.py): tests dirigidos al nuevo
endpoint administrativo/operacional GET /agenda/profesional/{prof_id}/citas
en app/routers/agenda.py.

Cubre:
  - conectado a require_permission(Permission.AGENDA_VER) (Permission
    exacto leído del closure, mismo criterio que test_rbac_fase3_2.py)
  - ADMIN con AGENDA_VER -> permitido
  - SUPERADMIN con AGENDA_VER -> permitido
  - profesional (sin AGENDA_VER) -> 403
  - estudiante -> 403
  - la respuesta contiene únicamente los campos operacionales:
    id, estudiante, estudiante_id, especialidad, fecha, hora, estado,
    urgente, sobrecupo
  - la respuesta NO contiene ningún campo clínico
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rbac.permissions import Permission
from app.routers import agenda as m


# ══════════════════════════════════════════════════════════════════
# Helpers para llegar a la dependencia REAL conectada al endpoint
# (mismo criterio que test_rbac_fase3_2.py: inspeccionar el closure
# de require_permission(...) por nombre de variable).
# ══════════════════════════════════════════════════════════════════
def _dependencia_de(endpoint):
    parametro = inspect.signature(endpoint).parameters["current_user"]
    return parametro.default.dependency


def _permiso_de(endpoint) -> Permission:
    dependencia = _dependencia_de(endpoint)
    closure = inspect.getclosurevars(dependencia)
    return closure.nonlocals.get("permission")


# ══════════════════════════════════════════════════════════════════
# Fake DB — mismo criterio de aislamiento que los demás módulos de
# fase 3.5F.
# ══════════════════════════════════════════════════════════════════
class FakeQuery:
    def __init__(self, results):
        self._results = list(results)

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self._results[0] if self._results else None

    def all(self):
        return list(self._results)


class FakeDB:
    def __init__(self, data: dict):
        self._data = data

    def query(self, model):
        return FakeQuery(self._data.get(model, []))


def _prof(id_=5, usuario_id=10, especialidad="Medicina"):
    return SimpleNamespace(id=id_, usuario_id=usuario_id, especialidad=especialidad)


def _cita(id_=7, prof_id=5, estudiante_id=99, estado="pendiente", fecha="2026-01-01", hora="09:00"):
    return SimpleNamespace(
        id=id_, profesional_id=prof_id, estudiante_id=estudiante_id, estado=estado,
        fecha=fecha, hora=hora, urgente=True, sobrecupo=False,
        observaciones="obs administrativa", medicamento="Paracetamol",
        observaciones_atencion="notas clínicas confidenciales",
    )


def _usuario(id_=99, nombre="Ana", rut="11.111.111-1"):
    return SimpleNamespace(id=id_, nombre=nombre, rut=rut)


# ══════════════════════════════════════════════════════════════════
# A. Permiso conectado — el endpoint debe exigir exactamente
#    Permission.AGENDA_VER (no AGENDA_VER_PROFESIONAL ni
#    ATENCIONES_VER_ASIGNADAS, que son del endpoint clínico).
# ══════════════════════════════════════════════════════════════════
def test_endpoint_agenda_usa_agenda_ver():
    assert _permiso_de(m.get_citas_profesional_admin) == Permission.AGENDA_VER


# ══════════════════════════════════════════════════════════════════
# B. Autorización — ADMIN/SUPERADMIN pasan, profesional/estudiante no.
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_admin_superadmin_con_agenda_ver_permitido(
    rol,
    monkeypatch,
):
    dependencia = _dependencia_de(
        m.get_citas_profesional_admin
    )

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        lambda db, current_user, permission: (
            current_user["rol"] in {"admin", "superadmin"}
            and permission is Permission.AGENDA_VER
        ),
    )

    current_user = {
        "id": 1,
        "rol": rol,
        "correo": "x@utem.cl",
    }

    resuelto = dependencia(
        current_user=current_user,
        db=object(),
    )

    assert resuelto == current_user


@pytest.mark.parametrize("rol", ["profesional", "estudiante"])
def test_rol_sin_agenda_ver_da_403(
    rol,
    monkeypatch,
):
    dependencia = _dependencia_de(
        m.get_citas_profesional_admin
    )

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        lambda db, current_user, permission: False,
    )

    current_user = {
        "id": 1,
        "rol": rol,
        "correo": "x@utem.cl",
    }

    with pytest.raises(HTTPException) as exc:
        dependencia(
            current_user=current_user,
            db=object(),
        )

    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# C. Contenido de la respuesta — únicamente campos operacionales,
#    nunca campos clínicos.
# ══════════════════════════════════════════════════════════════════
CAMPOS_ESPERADOS = {
    "id", "estudiante", "estudiante_id", "especialidad",
    "fecha", "hora", "estado", "urgente", "sobrecupo",
}

CAMPOS_CLINICOS_PROHIBIDOS = {
    "medicamento", "observaciones_atencion", "observaciones",
    "anamnesis", "diagnostico", "diagnóstico", "ficha", "cuestionario",
}


def test_respuesta_contiene_unicamente_campos_operacionales():
    db = FakeDB({
        Profesional: [_prof(5)],
        Cita: [_cita(7, prof_id=5)],
        Usuario: [_usuario(99)],
    })
    resultado = m.get_citas_profesional_admin(prof_id=5, db=db, current_user={"id": 1, "rol": "superadmin"})
    assert len(resultado) == 1
    fila = resultado[0]
    assert set(fila.keys()) == CAMPOS_ESPERADOS


def test_respuesta_no_contiene_campos_clinicos():
    db = FakeDB({
        Profesional: [_prof(5)],
        Cita: [_cita(7, prof_id=5)],
        Usuario: [_usuario(99)],
    })
    resultado = m.get_citas_profesional_admin(prof_id=5, db=db, current_user={"id": 1, "rol": "superadmin"})
    fila = resultado[0]
    for campo in CAMPOS_CLINICOS_PROHIBIDOS:
        assert campo not in fila


def test_respuesta_valores_correctos():
    db = FakeDB({
        Profesional: [_prof(5, especialidad="Odontología")],
        Cita: [_cita(7, prof_id=5, estudiante_id=99, estado="completada", fecha="2026-03-01", hora="10:30")],
        Usuario: [_usuario(99, nombre="Ana Pérez")],
    })
    resultado = m.get_citas_profesional_admin(prof_id=5, db=db, current_user={"id": 1, "rol": "superadmin"})
    fila = resultado[0]
    assert fila == {
        "id": 7,
        "estudiante": "Ana Pérez",
        "estudiante_id": 99,
        "especialidad": "Odontología",
        "fecha": "2026-03-01",
        "hora": "10:30",
        "estado": "completada",
        "urgente": True,
        "sobrecupo": False,
    }


def test_profesional_no_encontrado_da_404():
    from fastapi import HTTPException as HTTPExc
    db = FakeDB({Profesional: []})
    with pytest.raises(HTTPExc) as exc:
        m.get_citas_profesional_admin(prof_id=999, db=db, current_user={"id": 1, "rol": "superadmin"})
    assert exc.value.status_code == 404
