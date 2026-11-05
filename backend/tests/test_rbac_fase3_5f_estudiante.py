"""
SESAES — Fase 3.5F (bloque estudiante.py / IDOR):
tests dirigidos a los endpoints de recursos propios del estudiante en
app/routers/estudiante.py.

Antes de este bloque, los 3 endpoints usaban:

    verificar_acceso(current_user, id_esperado=estudiante_id,
                      roles_permitidos=["estudiante", "admin"])

verificar_acceso ya exige ownership estricto (current_user["id"] ==
id_esperado) independientemente del rol, por lo que un ADMIN/SUPERADMIN
solo podía "colarse" si su propio Usuario.id coincidía por accidente con
el estudiante_id solicitado. Este bloque retira "admin" de
roles_permitidos por defensa en profundidad — mismo criterio ya aplicado
en verificar_acceso_profesional (checkpoint 2) — y añade pruebas de
comportamiento que confirman:

  - estudiante dueño -> permitido
  - estudiante intentando otro estudiante_id -> 403
  - ADMIN sobre recurso propio de estudiante (incluso con id coincidente
    por accidente) -> 403
  - SUPERADMIN sobre recurso propio de estudiante (ídem) -> 403

Cubre: obtener_estudiante, actualizar_estudiante, resolver_primer_acceso.
No toca profesionales.py, historial_clinico.py, solicitudes_horario.py,
agenda.py ni frontend (fuera de alcance de este bloque).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.usuario import Usuario
from app.routers import estudiante as m
from app.auth_dependencies import verificar_acceso


# ══════════════════════════════════════════════════════════════════
# Fake DB — mismo criterio de aislamiento que los demás módulos de
# fase 3.5F: resultados preconfigurados por modelo, sin evaluar los
# filtros reales.
# ══════════════════════════════════════════════════════════════════
class FakeQuery:
    def __init__(self, results):
        self._results = list(results)

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._results[0] if self._results else None

    def all(self):
        return list(self._results)


class FakeDB:
    def __init__(self, data: dict):
        self._data = data
        self.commit_called = False
        self.refresh_called_with = None

    def query(self, model):
        return FakeQuery(self._data.get(model, []))

    def commit(self):
        self.commit_called = True

    def refresh(self, obj):
        self.refresh_called_with = obj


def _estudiante(id_=99, nombre="Ana", correo="ana@utem.cl", rol="estudiante"):
    return SimpleNamespace(
        id=id_, rol=rol, nombre=nombre, correo=correo,
        correo_secundario=None, telefono=None, foto_url=None,
        tema_oscuro=False, carrera=None, rut=None,
        debe_cambiar_password=True, password="hash-vieja",
    )


# ══════════════════════════════════════════════════════════════════
# Corrección de seguridad: roles_permitidos ya NO incluye "admin" en
# ninguno de los 3 endpoints de recursos propios del estudiante.
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("func", [m.obtener_estudiante, m.actualizar_estudiante, m.resolver_primer_acceso])
def test_endpoints_estudiante_ya_no_incluyen_admin_en_roles_permitidos(func):
    source = inspect.getsource(func)
    assert '["estudiante", "admin"]' not in source
    assert '["estudiante"]' in source


# ══════════════════════════════════════════════════════════════════
# verificar_acceso directo — casos de ownership por rol, usando a
# propósito el MISMO id para current_user y id_esperado, para probar
# que el rechazo de admin/superadmin es por ROL y no solo por ownership
# numérico (igual criterio que test_verificar_acceso_profesional_*).
# ══════════════════════════════════════════════════════════════════
def test_verificar_acceso_estudiante_dueno_permitido():
    verificar_acceso({"id": 99, "rol": "estudiante"}, id_esperado=99, roles_permitidos=["estudiante"])  # no debe lanzar


def test_verificar_acceso_estudiante_otro_id_da_403():
    with pytest.raises(HTTPException) as exc:
        verificar_acceso({"id": 99, "rol": "estudiante"}, id_esperado=100, roles_permitidos=["estudiante"])
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_verificar_acceso_admin_superadmin_con_mismo_id_da_403(rol):
    """rol=admin/superadmin, current_user.id == id_esperado => 403 (por rol, no por ownership)."""
    with pytest.raises(HTTPException) as exc:
        verificar_acceso({"id": 99, "rol": rol}, id_esperado=99, roles_permitidos=["estudiante"])
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# A. GET /estudiante/{estudiante_id}
# ══════════════════════════════════════════════════════════════════
def test_obtener_estudiante_dueno_permitido():
    db = FakeDB({Usuario: [_estudiante(99)]})
    resultado = m.obtener_estudiante(estudiante_id=99, db=db, current_user={"id": 99, "rol": "estudiante"})
    assert resultado.id == 99


def test_obtener_estudiante_otro_estudiante_da_403():
    db = FakeDB({Usuario: [_estudiante(99)]})
    with pytest.raises(HTTPException) as exc:
        m.obtener_estudiante(estudiante_id=100, db=db, current_user={"id": 99, "rol": "estudiante"})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_obtener_estudiante_admin_superadmin_da_403(rol):
    """ADMIN/SUPERADMIN no pueden consultar el recurso propio de un estudiante vía este endpoint."""
    db = FakeDB({Usuario: [_estudiante(99)]})
    with pytest.raises(HTTPException) as exc:
        m.obtener_estudiante(estudiante_id=99, db=db, current_user={"id": 1, "rol": rol})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_obtener_estudiante_admin_superadmin_con_id_coincidente_da_403(rol):
    """Incluso si el Usuario.id del admin coincide por accidente con estudiante_id, sigue siendo 403 (rechazo por rol)."""
    db = FakeDB({Usuario: [_estudiante(99)]})
    with pytest.raises(HTTPException) as exc:
        m.obtener_estudiante(estudiante_id=99, db=db, current_user={"id": 99, "rol": rol})
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# B. PATCH /estudiante/{estudiante_id}
# ══════════════════════════════════════════════════════════════════
def test_actualizar_estudiante_dueno_permitido():
    from app.schemas import EstudianteUpdate
    db = FakeDB({Usuario: [_estudiante(99)]})
    datos = EstudianteUpdate(nombre="Ana Nueva")
    resultado = m.actualizar_estudiante(estudiante_id=99, datos=datos, db=db, current_user={"id": 99, "rol": "estudiante"})
    assert resultado.nombre == "Ana Nueva"
    assert db.commit_called


def test_actualizar_estudiante_otro_estudiante_da_403():
    from app.schemas import EstudianteUpdate
    db = FakeDB({Usuario: [_estudiante(99)]})
    datos = EstudianteUpdate(nombre="Hackeado")
    with pytest.raises(HTTPException) as exc:
        m.actualizar_estudiante(estudiante_id=99, datos=datos, db=db, current_user={"id": 100, "rol": "estudiante"})
    assert exc.value.status_code == 403
    assert not db.commit_called


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_actualizar_estudiante_admin_superadmin_da_403(rol):
    from app.schemas import EstudianteUpdate
    db = FakeDB({Usuario: [_estudiante(99)]})
    datos = EstudianteUpdate(nombre="Modificado por admin")
    with pytest.raises(HTTPException) as exc:
        m.actualizar_estudiante(estudiante_id=99, datos=datos, db=db, current_user={"id": 99, "rol": rol})
    assert exc.value.status_code == 403
    assert not db.commit_called


# ══════════════════════════════════════════════════════════════════
# C. PATCH /estudiante/{estudiante_id}/primer-acceso
# ══════════════════════════════════════════════════════════════════
def test_primer_acceso_dueno_permitido():
    from app.routers.estudiante import PrimerAccesoIn
    db = FakeDB({Usuario: [_estudiante(99)]})
    resultado = m.resolver_primer_acceso(
        estudiante_id=99, datos=PrimerAccesoIn(nueva_password=None), db=db,
        current_user={"id": 99, "rol": "estudiante"},
    )
    assert resultado["message"]
    assert db.commit_called


def test_primer_acceso_otro_estudiante_da_403():
    from app.routers.estudiante import PrimerAccesoIn
    db = FakeDB({Usuario: [_estudiante(99)]})
    with pytest.raises(HTTPException) as exc:
        m.resolver_primer_acceso(
            estudiante_id=99, datos=PrimerAccesoIn(nueva_password=None), db=db,
            current_user={"id": 100, "rol": "estudiante"},
        )
    assert exc.value.status_code == 403
    assert not db.commit_called


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_primer_acceso_admin_superadmin_da_403(rol):
    from app.routers.estudiante import PrimerAccesoIn
    db = FakeDB({Usuario: [_estudiante(99)]})
    with pytest.raises(HTTPException) as exc:
        m.resolver_primer_acceso(
            estudiante_id=99, datos=PrimerAccesoIn(nueva_password="nueva123"), db=db,
            current_user={"id": 99, "rol": rol},
        )
    assert exc.value.status_code == 403
    assert not db.commit_called
