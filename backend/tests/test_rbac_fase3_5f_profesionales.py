"""
SESAES — Fase 3.5F (checkpoint 2): tests dirigidos para el bloque de
endpoints "propios" del profesional en app/routers/profesionales.py.

Cubre únicamente lo migrado en este bloque:
  - marcar_inasistencia            -> AGENDA_GESTIONAR_PROPIA + ownership
  - completar_cita                 -> ATENCIONES_REGISTRAR + ownership
  - get_citas_profesional          -> ATENCIONES_VER_ASIGNADAS + ownership
  - get_estadisticas_dia           -> AGENDA_VER_PROFESIONAL + ownership
  - get_citas_sin_cerrar           -> AGENDA_VER_PROFESIONAL + ownership
  - get_perfil / cambiar_password  -> ownership estricto (sin permiso nuevo)
  - notificaciones administrativas -> resueltas por has_permission(...,
                                       AGENDA_GESTIONAR), no por rol=="admin"

No toca historial_clinico.py, estudiante.py, solicitudes_horario.py,
frontend, ni agenda.py (fuera de alcance de este checkpoint).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.models.init  # noqa: F401 — registra todas las relaciones SQLAlchemy
import app.models.solicitud_horario  # noqa: F401 — referenciado por Profesional pero ausente de models/init.py
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rbac.permissions import Permission
from app.routers import profesionales as m
from app.auth_dependencies import verificar_acceso_profesional
from app.schemas import CompletarCitaBody


# ══════════════════════════════════════════════════════════════════
# Fake DB — resultados preconfigurados por modelo, sin evaluar filtros
# reales (mismo criterio de aislamiento que test_notificaciones_privacidad_fase3_5d.py)
# ══════════════════════════════════════════════════════════════════
class FakeQuery:
    def __init__(self, results):
        self._results = list(results)

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def first(self):
        return self._results[0] if self._results else None

    def all(self):
        return list(self._results)


class FakeDB:
    def __init__(self, data: dict):
        self._data = data
        self.added: list = []
        self.commit_called = False

    def query(self, model):
        return FakeQuery(self._data.get(model, []))

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_called = True


def _prof(id_=5, usuario_id=10, estado="activo"):
    return SimpleNamespace(
        id=id_, usuario_id=usuario_id, nombre="Dra. Owner", especialidad="Medicina", estado=estado,
    )


def _cita(id_=7, profesional_id=5, estudiante_id=99, estado="pendiente", fecha="2020-01-01", hora="09:00"):
    return SimpleNamespace(
        id=id_, profesional_id=profesional_id, estudiante_id=estudiante_id,
        estado=estado, fecha=fecha, hora=hora, medicamento=None, observaciones_atencion=None,
    )


def _usuario(id_, rol, nombre="—", correo="x@utem.cl"):
    return SimpleNamespace(id=id_, rol=rol, nombre=nombre, correo=correo)


# ══════════════════════════════════════════════════════════════════
# Helper compartido: _exigir_permiso_y_ownership_propio
# ══════════════════════════════════════════════════════════════════
def test_helper_sin_permiso_lanza_403_aunque_sea_dueno():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m._exigir_permiso_y_ownership_propio(
            {"id": 10, "rol": "estudiante"}, 5, db, Permission.AGENDA_GESTIONAR_PROPIA
        )
    assert exc.value.status_code == 403


def test_helper_con_permiso_pero_ajeno_lanza_403():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m._exigir_permiso_y_ownership_propio(
            {"id": 999, "rol": "profesional"}, 5, db, Permission.AGENDA_GESTIONAR_PROPIA
        )
    assert exc.value.status_code == 403


def test_helper_con_permiso_y_dueno_pasa():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    m._exigir_permiso_y_ownership_propio(
        {"id": 10, "rol": "profesional"}, 5, db, Permission.AGENDA_GESTIONAR_PROPIA
    )  # no debe lanzar


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_helper_no_tiene_bypass_admin_ni_superadmin(rol):
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m._exigir_permiso_y_ownership_propio(
            {"id": 999, "rol": rol}, 5, db, Permission.AGENDA_GESTIONAR_PROPIA
        )
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# Checkpoint 2 — corrección de seguridad: roles_permitidos default de
# verificar_acceso_profesional ya NO incluye "admin". Estos tests usan
# a propósito el MISMO id para current_user y Profesional.usuario_id
# (no solo ids distintos), para probar que el rechazo es por ROL, no
# porque el ownership numérico también falle.
# ══════════════════════════════════════════════════════════════════
def test_verificar_acceso_profesional_admin_con_mismo_usuario_id_da_403():
    """rol=admin, current_user.id == Profesional.usuario_id => 403 (por rol, no por ownership)."""
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        verificar_acceso_profesional({"id": 10, "rol": "admin"}, 5, db)
    assert exc.value.status_code == 403


def test_verificar_acceso_profesional_superadmin_con_mismo_usuario_id_da_403():
    """rol=superadmin, current_user.id == Profesional.usuario_id => 403 (por rol, no por ownership)."""
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        verificar_acceso_profesional({"id": 10, "rol": "superadmin"}, 5, db)
    assert exc.value.status_code == 403


def test_verificar_acceso_profesional_profesional_con_mismo_usuario_id_permitido():
    """rol=profesional, current_user.id == Profesional.usuario_id => permitido (no lanza)."""
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    verificar_acceso_profesional({"id": 10, "rol": "profesional"}, 5, db)  # no debe lanzar


def test_verificar_acceso_profesional_default_ya_no_incluye_admin():
    """Corrección de seguridad: el default de roles_permitidos ya no es ["profesional", "admin"]."""
    source = inspect.getsource(verificar_acceso_profesional)
    assert '["profesional", "admin"]' not in source
    assert '["profesional"]' in source


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_perfil_profesional_admin_con_mismo_usuario_id_da_403(rol):
    """
    Perfil propio del profesional: un ADMIN/SUPERADMIN con el MISMO
    usuario_id que el Profesional consultado sigue recibiendo 403 —
    el rol se exige antes que el ownership numérico.
    """
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.get_perfil(prof_id=5, db=db, current_user={"id": 10, "rol": rol})
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# A. Marcar inasistencia
# ══════════════════════════════════════════════════════════════════
def test_marcar_inasistencia_usa_agenda_gestionar_propia_no_atenciones_registrar():
    """
    Confirma en el código real conectado al endpoint que usa
    AGENDA_GESTIONAR_PROPIA y NO depende de ATENCIONES_REGISTRAR.
    """
    source = inspect.getsource(m.marcar_inasistencia)
    assert "Permission.AGENDA_GESTIONAR_PROPIA" in source
    assert "Permission.ATENCIONES_REGISTRAR" not in source


def test_marcar_inasistencia_profesional_ajeno_no_autorizado():
    db = FakeDB({
        Profesional: [_prof(5, usuario_id=10)],
        Cita: [_cita(profesional_id=5)],
    })
    with pytest.raises(HTTPException) as exc:
        m.marcar_inasistencia(
            prof_id=5, cita_id=7, db=db, current_user={"id": 999, "rol": "profesional"}
        )
    assert exc.value.status_code == 403


def test_marcar_inasistencia_dueno_con_agenda_gestionar_propia_autoriza(
    monkeypatch,
):
    cita = _cita(
        profesional_id=5,
        fecha="2020-01-01",
        estado="pendiente",
    )

    db = FakeDB({
        Profesional: [
            _prof(5, usuario_id=10),
        ],
        Cita: [
            cita,
        ],
        Usuario: [
            _usuario(
                99,
                "estudiante",
                nombre="Ana",
            ),
            _usuario(
                1,
                "admin",
                correo="admin@utem.cl",
            ),
        ],
    })

    # Este test verifica ownership/inasistencia, no seleccion de
    # destinatarios administrativos.
    monkeypatch.setattr(
        m,
        "_notificar_con_agenda_gestionar",
        lambda *args, **kwargs: None,
    )

    resultado = m.marcar_inasistencia(
        prof_id=5,
        cita_id=7,
        db=db,
        current_user={
            "id": 10,
            "rol": "profesional",
        },
    )

    assert cita.estado == "inasistencia"
    assert resultado == {
        "message": "Inasistencia registrada"
    }


# ══════════════════════════════════════════════════════════════════
# B. Completar cita
# ══════════════════════════════════════════════════════════════════
def test_completar_exige_atenciones_registrar():
    source = inspect.getsource(m.completar_cita)
    assert "Permission.ATENCIONES_REGISTRAR" in source


def test_completar_profesional_ajeno_no_autorizado():
    db = FakeDB({
        Profesional: [_prof(5, usuario_id=10)],
        Cita: [_cita(profesional_id=5, fecha="2020-01-01")],
    })
    with pytest.raises(HTTPException) as exc:
        m.completar_cita(
            prof_id=5, cita_id=7, body=CompletarCitaBody(), db=db, current_user={"id": 999, "rol": "profesional"}
        )
    assert exc.value.status_code == 403


def test_completar_dueno_autoriza():
    cita = _cita(profesional_id=5, fecha="2020-01-01")
    db = FakeDB({
        Profesional: [_prof(5, usuario_id=10)],
        Cita: [cita],
        Usuario: [_usuario(99, "estudiante", nombre="Ana")],
    })
    m.completar_cita(prof_id=5, cita_id=7, body=CompletarCitaBody(), db=db, current_user={"id": 10, "rol": "profesional"})
    assert cita.estado == "completada"
    assert cita.medicamento is None


# ══════════════════════════════════════════════════════════════════
# C. GET /profesional/{id}/citas — clínico
# ══════════════════════════════════════════════════════════════════
def test_get_citas_profesional_exige_atenciones_ver_asignadas():
    source = inspect.getsource(m.get_citas_profesional)
    assert "Permission.ATENCIONES_VER_ASIGNADAS" in source


def test_get_citas_profesional_rechaza_id_de_otro_profesional():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.get_citas_profesional(
            prof_id=5, fecha=None, estado=None, db=db, current_user={"id": 999, "rol": "profesional"}
        )
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# D. estadisticas-dia y citas-sin-cerrar
# ══════════════════════════════════════════════════════════════════
def test_estadisticas_dia_exige_agenda_ver_profesional():
    source = inspect.getsource(m.get_estadisticas_dia)
    assert "Permission.AGENDA_VER_PROFESIONAL" in source


def test_estadisticas_dia_rechaza_otro_profesional():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.get_estadisticas_dia(prof_id=5, db=db, current_user={"id": 999, "rol": "profesional"})
    assert exc.value.status_code == 403


def test_citas_sin_cerrar_exige_agenda_ver_profesional():
    source = inspect.getsource(m.get_citas_sin_cerrar)
    assert "Permission.AGENDA_VER_PROFESIONAL" in source


def test_citas_sin_cerrar_rechaza_otro_profesional():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.get_citas_sin_cerrar(prof_id=5, db=db, current_user={"id": 999, "rol": "profesional"})
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# E. Perfil / password / notificaciones propias — ownership estricto
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("rol", ["admin", "superadmin", "profesional"])
def test_perfil_rechaza_otro_profesional_sin_bypass(rol):
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.get_perfil(prof_id=5, db=db, current_user={"id": 999, "rol": rol})
    assert exc.value.status_code == 403


def test_cambiar_password_rechaza_otro_profesional():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.cambiar_password(
            prof_id=5, body={"contrasena_actual": "x", "contrasena_nueva": "y"},
            db=db, current_user={"id": 999, "rol": "profesional"},
        )
    assert exc.value.status_code == 403


def test_notificaciones_profesional_rechaza_otro_profesional():
    db = FakeDB({Profesional: [_prof(5, usuario_id=10)]})
    with pytest.raises(HTTPException) as exc:
        m.get_notificaciones_profesional(prof_id=5, db=db, current_user={"id": 999, "rol": "profesional"})
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# Flujo legacy de ausencia retirado
# ══════════════════════════════════════════════════════════════════
def test_reportar_ausencia_legacy_ya_no_existe_en_router_profesional():
    """La ausencia ya no se registra/cancela automáticamente desde este router."""
    assert not hasattr(m, "reportar_ausencia")


# ══════════════════════════════════════════════════════════════════
# F. Notificaciones administrativas — por permiso, no por rol=="admin"
# ══════════════════════════════════════════════════════════════════
def test_notificar_con_agenda_gestionar_no_usa_rol_admin_hardcodeado():
    source = inspect.getsource(m._notificar_con_agenda_gestionar)
    assert 'Usuario.rol == "admin"' not in source
    assert "has_permission" in source
    assert "Permission.AGENDA_GESTIONAR" in source


def test_notificar_con_agenda_gestionar_incluye_superadmin_no_solo_admin(
    monkeypatch,
):
    """
    ADMIN se resuelve por permiso persistido + alcance.
    SUPERADMIN conserva agenda.gestionar por RBAC explicito.
    """
    db = FakeDB({
        Usuario: [
            _usuario(
                1,
                "admin",
                correo="admin@utem.cl",
            ),
            _usuario(
                2,
                "superadmin",
                correo="super@utem.cl",
            ),
            _usuario(
                3,
                "profesional",
                correo="prof@utem.cl",
            ),
            _usuario(
                4,
                "estudiante",
                correo="est@utem.cl",
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

    m._notificar_con_agenda_gestionar(
        db,
        "Nutricion",
        mensaje="hola",
        tipo="info",
    )

    ids_notificados = {
        o.usuario_id
        for o in db.added
    }

    assert ids_notificados == {
        1,
        2,
    }


def test_marcar_inasistencia_notifica_por_permiso_no_por_rol_admin_string():
    source = inspect.getsource(m.marcar_inasistencia)
    assert 'Usuario.rol == "admin"' not in source
    assert "_notificar_con_agenda_gestionar" in source
