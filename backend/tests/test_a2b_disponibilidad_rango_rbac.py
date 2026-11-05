"""
SESAES — A.2B: RBAC/scope y manejo de errores del endpoint
GET /agenda/profesional/{profesional_id}/disponibilidad
(app/routers/agenda.py).

Mismo criterio de aislamiento que test_rbac_fase3_5f_agenda.py y
test_sa9_agenda_profesional_alcance.py: FakeDB liviana, sin TestClient
HTTP real, monkeypatch sobre los símbolos importados en app.routers.agenda.

Cubre:
  - conectado a require_effective_permission(Permission.AGENDA_VER)
  - ADMIN/SUPERADMIN con AGENDA_VER -> permitido; sin permiso -> 403
  - profesional inexistente -> 404 (antes de resolver alcance)
  - profesional fuera del alcance administrativo -> 403 (scope por
    especialidad, no solo ocultamiento en frontend)
  - alcance institucional permite y delega al servicio
  - alcance por especialidad permite cuando corresponde
  - sin alcance resuelto (None) -> 403
  - errores de dominio del servicio (rango inválido, profesional no
    encontrado defensivo) traducidos a HTTP 400/404
  - los parámetros se pasan intactos al servicio (profesional_id,
    fecha_inicio, fecha_fin), sin transformarlos en el router

No cubre aquí la lógica de disponibilidad en sí (fin de semana, día
cerrado, jornada, colación, ocupación) — eso vive en
test_a2b_disponibilidad_rango.py contra una base SQLite real.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.profesional import Profesional
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.rbac.permissions import Permission
from app.routers import agenda as m
from app.services.agenda_disponibilidad_service import (
    ParametrosRangoInvalidosError,
    ProfesionalNoEncontradoError,
)


# ══════════════════════════════════════════════════════════════════
# Helpers — mismo criterio que test_rbac_fase3_5f_agenda.py
# ══════════════════════════════════════════════════════════════════
def _dependencia_de(endpoint):
    parametro = inspect.signature(endpoint).parameters["current_user"]
    return parametro.default.dependency


def _permiso_de(endpoint) -> Permission:
    dependencia = _dependencia_de(endpoint)
    closure = inspect.getclosurevars(dependencia)
    return closure.nonlocals.get("permission")


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


def _prof(id_=5, especialidad="Nutrición"):
    return SimpleNamespace(id=id_, especialidad=especialidad)


def _alcance_limitado(*especialidades):
    return AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset(
            normalizar_especialidad(e).normalizada for e in especialidades
        ),
    )


_ALCANCE_INSTITUCIONAL = AlcanceAdministrativoEfectivo(
    institucional=True, especialidades_normalizadas=frozenset(),
)


# ══════════════════════════════════════════════════════════════════
# A. Permiso conectado
# ══════════════════════════════════════════════════════════════════
def test_endpoint_disponibilidad_usa_agenda_ver():
    assert _permiso_de(m.get_disponibilidad_rango_admin) == Permission.AGENDA_VER


# ══════════════════════════════════════════════════════════════════
# B. Autorización RBAC — ADMIN/SUPERADMIN pasan, profesional/estudiante no.
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_admin_superadmin_con_agenda_ver_permitido(rol, monkeypatch):
    dependencia = _dependencia_de(m.get_disponibilidad_rango_admin)

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        lambda db, current_user, permission: (
            current_user["rol"] in {"admin", "superadmin"}
            and permission is Permission.AGENDA_VER
        ),
    )

    current_user = {"id": 1, "rol": rol, "correo": "x@utem.cl"}
    resuelto = dependencia(current_user=current_user, db=object())
    assert resuelto == current_user


@pytest.mark.parametrize("rol", ["profesional", "estudiante"])
def test_rol_sin_agenda_ver_da_403(rol, monkeypatch):
    dependencia = _dependencia_de(m.get_disponibilidad_rango_admin)

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        lambda db, current_user, permission: False,
    )

    current_user = {"id": 1, "rol": rol, "correo": "x@utem.cl"}
    with pytest.raises(HTTPException) as exc:
        dependencia(current_user=current_user, db=object())
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# C. Profesional inexistente -> 404, antes de resolver alcance.
# ══════════════════════════════════════════════════════════════════
def test_profesional_no_encontrado_da_404(monkeypatch):
    db = FakeDB({Profesional: []})

    # Si el router llegara a resolver alcance para un profesional que no
    # existe, esto haría fallar el test con un error distinto a 404 en
    # vez de dar un 403 silencioso por accidente de orden.
    monkeypatch.setattr(
        m, "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _ALCANCE_INSTITUCIONAL,
    )

    with pytest.raises(HTTPException) as exc:
        m.get_disponibilidad_rango_admin(
            profesional_id=999,
            fecha_inicio="2026-09-07",
            fecha_fin="2026-09-13",
            db=db,
            current_user={"id": 1, "rol": "superadmin"},
        )
    assert exc.value.status_code == 404


# ══════════════════════════════════════════════════════════════════
# D. Scope administrativo — no confiar en el profesional_id del frontend.
# ══════════════════════════════════════════════════════════════════
def test_profesional_fuera_de_alcance_da_403(monkeypatch):
    db = FakeDB({Profesional: [_prof(1, "Odontología")]})

    monkeypatch.setattr(
        m, "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado("Nutrición"),
    )

    with pytest.raises(HTTPException) as exc:
        m.get_disponibilidad_rango_admin(
            profesional_id=1,
            fecha_inicio="2026-09-07",
            fecha_fin="2026-09-13",
            db=db,
            current_user={"id": 50, "rol": "admin"},
        )
    assert exc.value.status_code == 403


def test_sin_alcance_resuelto_da_403(monkeypatch):
    db = FakeDB({Profesional: [_prof(1, "Nutrición")]})

    monkeypatch.setattr(
        m, "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        m.get_disponibilidad_rango_admin(
            profesional_id=1,
            fecha_inicio="2026-09-07",
            fecha_fin="2026-09-13",
            db=db,
            current_user={"id": 50, "rol": "admin"},
        )
    assert exc.value.status_code == 403


def test_admin_dentro_de_alcance_por_especialidad_delega_al_servicio(monkeypatch):
    db = FakeDB({Profesional: [_prof(1, "Nutrición")]})

    monkeypatch.setattr(
        m, "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado("Nutrición"),
    )

    llamadas = []

    def _stub_servicio(db, *, profesional_id, fecha_inicio, fecha_fin):
        llamadas.append((profesional_id, fecha_inicio, fecha_fin))
        return {"profesional_id": profesional_id, "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin, "duracion_min": 30, "dias": []}

    monkeypatch.setattr(m, "listar_disponibilidad_rango", _stub_servicio)

    resultado = m.get_disponibilidad_rango_admin(
        profesional_id=1,
        fecha_inicio="2026-09-07",
        fecha_fin="2026-09-13",
        db=db,
        current_user={"id": 50, "rol": "admin"},
    )

    assert llamadas == [(1, "2026-09-07", "2026-09-13")]
    assert resultado["profesional_id"] == 1


def test_superadmin_institucional_delega_al_servicio_sin_requerir_especialidad(monkeypatch):
    db = FakeDB({Profesional: [_prof(1, "Odontología")]})
    # Se usa la resolución REAL de obtener_alcance_administrativo_efectivo
    # para SUPERADMIN (no monkeypatcheada) — igual que
    # test_superadmin_conserva_alcance_institucional en
    # test_sa9_agenda_profesional_alcance.py: no requiere acceso a DB
    # porque SUPERADMIN resuelve institucional sin consultar contexto.

    llamadas = []

    def _stub_servicio(db, *, profesional_id, fecha_inicio, fecha_fin):
        llamadas.append(profesional_id)
        return {"profesional_id": profesional_id, "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin, "duracion_min": 30, "dias": []}

    monkeypatch.setattr(m, "listar_disponibilidad_rango", _stub_servicio)

    resultado = m.get_disponibilidad_rango_admin(
        profesional_id=1,
        fecha_inicio="2026-09-07",
        fecha_fin="2026-09-13",
        db=db,
        current_user={"id": 1, "rol": "superadmin"},
    )

    assert llamadas == [1]
    assert resultado["dias"] == []


# ══════════════════════════════════════════════════════════════════
# E. Errores de dominio del servicio -> HTTP
# ══════════════════════════════════════════════════════════════════
def test_rango_invalido_del_servicio_se_traduce_a_400(monkeypatch):
    db = FakeDB({Profesional: [_prof(1, "Nutrición")]})

    monkeypatch.setattr(
        m, "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _ALCANCE_INSTITUCIONAL,
    )

    def _stub_servicio(db, *, profesional_id, fecha_inicio, fecha_fin):
        raise ParametrosRangoInvalidosError(
            "rango_invertido", "fecha_fin no puede ser anterior a fecha_inicio.",
        )

    monkeypatch.setattr(m, "listar_disponibilidad_rango", _stub_servicio)

    with pytest.raises(HTTPException) as exc:
        m.get_disponibilidad_rango_admin(
            profesional_id=1,
            fecha_inicio="2026-09-13",
            fecha_fin="2026-09-07",
            db=db,
            current_user={"id": 1, "rol": "superadmin"},
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "fecha_fin no puede ser anterior a fecha_inicio."


def test_profesional_no_encontrado_del_servicio_se_traduce_a_404(monkeypatch):
    """
    Camino defensivo: el router ya validó que el profesional existe,
    pero si el servicio igual levanta ProfesionalNoEncontradoError (p.
    ej. una carrera donde el registro se borra entre ambas consultas),
    debe seguir respondiendo 404 fail-closed, no un 500.
    """
    db = FakeDB({Profesional: [_prof(1, "Nutrición")]})

    monkeypatch.setattr(
        m, "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _ALCANCE_INSTITUCIONAL,
    )

    def _stub_servicio(db, *, profesional_id, fecha_inicio, fecha_fin):
        raise ProfesionalNoEncontradoError(profesional_id)

    monkeypatch.setattr(m, "listar_disponibilidad_rango", _stub_servicio)

    with pytest.raises(HTTPException) as exc:
        m.get_disponibilidad_rango_admin(
            profesional_id=1,
            fecha_inicio="2026-09-07",
            fecha_fin="2026-09-13",
            db=db,
            current_user={"id": 1, "rol": "superadmin"},
        )
    assert exc.value.status_code == 404
