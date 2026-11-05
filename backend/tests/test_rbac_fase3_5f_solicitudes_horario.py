"""
SESAES — Fase 3.5F (bloque solicitudes_horario.py):
tests dirigidos a las 4 operaciones "propias" del profesional y a
_notificar_admin en app/routers/solicitudes_horario.py.

Cubre:
  - solicitar_colacion / solicitar_jornada / get_mis_solicitudes /
    eliminar_solicitud -> Permission.AGENDA_GESTIONAR_PROPIA + ownership
    profesional (vía _exigir_agenda_gestionar_propia_y_ownership)
  - profesional dueño permitido
  - profesional ajeno -> 403
  - ADMIN/SUPERADMIN no pasan como recurso propio del profesional
  - _notificar_admin resuelto por has_permission(..., AGENDA_GESTIONAR),
    no por Usuario.rol == "admin"
  - ADMIN y SUPERADMIN con AGENDA_GESTIONAR reciben notificación
  - profesional/estudiante sin ese permiso no reciben notificación

No toca las rutas /admin/solicitudes-horario/* (ya protegidas con
require_permission(Permission.AGENDA_GESTIONAR), fuera de alcance de
este bloque) ni agenda.py.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.models.solicitud_horario import SolicitudHorario
from app.rbac.permissions import Permission
from app.routers import solicitudes_horario as m
from app.auth_dependencies import verificar_acceso_profesional


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
        self.added: list = []
        self.deleted: list = []
        self.commit_called = False

    def query(self, model):
        # Incluye lo agregado en la misma "sesión" para que
        # get_mis_solicitudes vea lo que solicitar_colacion/jornada añadió.
        base = list(self._data.get(model, []))
        extra = [o for o in self.added if isinstance(o, model)]
        return FakeQuery(base + extra)

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.commit_called = True


def _prof(id_=5, usuario_id=10, nombre="Dra. Owner"):
    return SimpleNamespace(id=id_, usuario_id=usuario_id, nombre=nombre, especialidad="Medicina")


def _usuario(id_, rol, correo="x@utem.cl"):
    return SimpleNamespace(id=id_, rol=rol, correo=correo)


def _solicitud(id_=1, prof_id=5, tipo="colacion", estado="pendiente"):
    return SimpleNamespace(
        id=id_, profesional_id=prof_id, tipo=tipo, hora_inicio="13:00", hora_fin="14:00",
        estado=estado, motivo_rechazo=None, fecha_solicitud=None,
    )


# ══════════════════════════════════════════════════════════════════
# Helper _exigir_agenda_gestionar_propia_y_ownership
# ══════════════════════════════════════════════════════════════════
def test_helper_sin_permiso_lanza_403_aunque_sea_dueno():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m._exigir_agenda_gestionar_propia_y_ownership({"id": 10, "rol": "estudiante"}, 5, db)
    assert exc.value.status_code == 403


def test_helper_con_permiso_pero_ajeno_lanza_403():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m._exigir_agenda_gestionar_propia_y_ownership({"id": 999, "rol": "profesional"}, 5, db)
    assert exc.value.status_code == 403


def test_helper_con_permiso_y_dueno_pasa():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    m._exigir_agenda_gestionar_propia_y_ownership({"id": 10, "rol": "profesional"}, 5, db)  # no debe lanzar


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_helper_no_tiene_bypass_admin_ni_superadmin(rol):
    """ADMIN/SUPERADMIN no pasan como recurso propio del profesional, incluso con id coincidente."""
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m._exigir_agenda_gestionar_propia_y_ownership({"id": 10, "rol": rol}, 5, db)
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# Confirma en el código real que las 4 operaciones propias usan el
# helper con AGENDA_GESTIONAR_PROPIA (no verificar_acceso_profesional
# directo sin permiso).
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("func", [
    m.solicitar_colacion, m.solicitar_jornada, m.get_mis_solicitudes, m.eliminar_solicitud,
])
def test_operaciones_propias_usan_helper_agenda_gestionar_propia(func):
    source = inspect.getsource(func)
    assert "_exigir_agenda_gestionar_propia_y_ownership" in source


# ══════════════════════════════════════════════════════════════════
# A. solicitar_colacion
# ══════════════════════════════════════════════════════════════════
def test_solicitar_colacion_dueno_permitido():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)], Usuario: []})
    resultado = m.solicitar_colacion(
        prof_id=5, body={"hora_almuerzo_inicio": "13:00"}, db=db,
        current_user={"id": 10, "rol": "profesional"},
    )
    assert resultado["hora_inicio"] == "13:00"
    assert db.commit_called


def test_solicitar_colacion_profesional_ajeno_da_403():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.solicitar_colacion(
            prof_id=5, body={"hora_almuerzo_inicio": "13:00"}, db=db,
            current_user={"id": 999, "rol": "profesional"},
        )
    assert exc.value.status_code == 403
    assert not db.commit_called


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_solicitar_colacion_admin_superadmin_da_403(rol):
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.solicitar_colacion(
            prof_id=5, body={"hora_almuerzo_inicio": "13:00"}, db=db,
            current_user={"id": 10, "rol": rol},
        )
    assert exc.value.status_code == 403
    assert not db.commit_called


# ══════════════════════════════════════════════════════════════════
# B. solicitar_jornada
# ══════════════════════════════════════════════════════════════════
def test_solicitar_jornada_dueno_permitido():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)], Usuario: []})
    resultado = m.solicitar_jornada(
        prof_id=5, body={"horario_inicio": "08:00", "horario_fin": "17:00"}, db=db,
        current_user={"id": 10, "rol": "profesional"},
    )
    assert resultado["hora_inicio"] == "08:00"
    assert db.commit_called


def test_solicitar_jornada_profesional_ajeno_da_403():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.solicitar_jornada(
            prof_id=5, body={"horario_inicio": "08:00", "horario_fin": "17:00"}, db=db,
            current_user={"id": 999, "rol": "profesional"},
        )
    assert exc.value.status_code == 403
    assert not db.commit_called


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_solicitar_jornada_admin_superadmin_da_403(rol):
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.solicitar_jornada(
            prof_id=5, body={"horario_inicio": "08:00", "horario_fin": "17:00"}, db=db,
            current_user={"id": 10, "rol": rol},
        )
    assert exc.value.status_code == 403
    assert not db.commit_called


# ══════════════════════════════════════════════════════════════════
# C. get_mis_solicitudes
# ══════════════════════════════════════════════════════════════════
def test_get_mis_solicitudes_dueno_permitido():
    db = FakeDB({
        Profesional: [_prof(5, usuario_id=10)],
        SolicitudHorario: [_solicitud(1, prof_id=5)],
    })
    resultado = m.get_mis_solicitudes(prof_id=5, db=db, current_user={"id": 10, "rol": "profesional"})
    assert len(resultado) == 1
    assert resultado[0]["id"] == 1


def test_get_mis_solicitudes_profesional_ajeno_da_403():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.get_mis_solicitudes(prof_id=5, db=db, current_user={"id": 999, "rol": "profesional"})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_get_mis_solicitudes_admin_superadmin_da_403(rol):
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.get_mis_solicitudes(prof_id=5, db=db, current_user={"id": 10, "rol": rol})
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# D. eliminar_solicitud
# ══════════════════════════════════════════════════════════════════
def test_eliminar_solicitud_dueno_permitido():
    db = FakeDB({
        Profesional: [_prof(5, usuario_id=10)],
        SolicitudHorario: [_solicitud(1, prof_id=5)],
    })
    resultado = m.eliminar_solicitud(solicitud_id=1, db=db, current_user={"id": 10, "rol": "profesional"})
    assert resultado["message"]
    assert db.commit_called


def test_eliminar_solicitud_profesional_ajeno_da_403():
    db = FakeDB({
        Profesional: [_prof(5, usuario_id=10)],
        SolicitudHorario: [_solicitud(1, prof_id=5)],
    })
    with pytest.raises(HTTPException) as exc:
        m.eliminar_solicitud(solicitud_id=1, db=db, current_user={"id": 999, "rol": "profesional"})
    assert exc.value.status_code == 403
    assert not db.commit_called


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_eliminar_solicitud_admin_superadmin_da_403(rol):
    db = FakeDB({
        Profesional: [_prof(5, usuario_id=10)],
        SolicitudHorario: [_solicitud(1, prof_id=5)],
    })
    with pytest.raises(HTTPException) as exc:
        m.eliminar_solicitud(solicitud_id=1, db=db, current_user={"id": 10, "rol": rol})
    assert exc.value.status_code == 403
    assert not db.commit_called


# ══════════════════════════════════════════════════════════════════
# E. _notificar_admin — resuelto por has_permission(..., AGENDA_GESTIONAR)
# ══════════════════════════════════════════════════════════════════
def test_notificar_admin_no_busca_rol_admin_hardcodeado():
    source = inspect.getsource(m._notificar_admin)
    assert 'Usuario.rol == "admin"' not in source
    assert "has_permission" in source
    assert "Permission.AGENDA_GESTIONAR" in source


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_notificar_admin_notifica_admin_y_superadmin_con_permiso(
    rol,
    monkeypatch,
):
    db = FakeDB({
        Usuario: [
            _usuario(
                1,
                rol,
            ),
        ]
    })

    monkeypatch.setattr(
        m,
        "tiene_permiso_admin_en_especialidad",
        lambda db_recibida, usuario_id, permiso, especialidad: (
            usuario_id == 1
            and permiso == Permission.AGENDA_GESTIONAR
            and especialidad == "Nutricion"
        ),
    )

    m._notificar_admin(
        db,
        "Nutricion",
        "mensaje de prueba",
    )

    assert len(db.added) == 1
    assert db.added[0].usuario_id == 1


@pytest.mark.parametrize("rol", ["profesional", "estudiante"])
def test_notificar_admin_no_notifica_roles_sin_agenda_gestionar(
    rol,
    monkeypatch,
):
    db = FakeDB({
        Usuario: [
            _usuario(
                1,
                rol,
            ),
        ]
    })

    monkeypatch.setattr(
        m,
        "tiene_permiso_admin_en_especialidad",
        lambda *args, **kwargs: False,
    )

    m._notificar_admin(
        db,
        "Nutricion",
        "mensaje de prueba",
    )

    assert len(db.added) == 0


def test_notificar_admin_notifica_solo_a_quienes_tienen_el_permiso(
    monkeypatch,
):
    db = FakeDB({
        Usuario: [
            _usuario(
                1,
                "admin",
            ),
            _usuario(
                2,
                "superadmin",
            ),
            _usuario(
                3,
                "profesional",
            ),
            _usuario(
                4,
                "estudiante",
            ),
        ]
    })

    monkeypatch.setattr(
        m,
        "tiene_permiso_admin_en_especialidad",
        lambda db_recibida, usuario_id, permiso, especialidad: (
            usuario_id == 1
            and permiso == Permission.AGENDA_GESTIONAR
            and especialidad == "Nutricion"
        ),
    )

    m._notificar_admin(
        db,
        "Nutricion",
        "mensaje de prueba",
    )

    notificados = {
        n.usuario_id
        for n in db.added
    }

    assert notificados == {
        1,
        2,
    }
