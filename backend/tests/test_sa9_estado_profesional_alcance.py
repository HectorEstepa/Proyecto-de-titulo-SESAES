import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.models.ausencia_profesional import AusenciaProfesional
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class RecordingQuery:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def filter(self, *conditions):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(
        self,
        *,
        profesional=None,
        citas=None,
        estudiante=None,
    ):
        self.profesional = profesional
        self.citas = list(citas or [])
        self.estudiante = estudiante

        self.query_calls = []
        self.add_calls = []
        self.commit_calls = 0

    def query(self, model):
        self.query_calls.append(model)

        if model is Profesional:
            return RecordingQuery(
                [self.profesional]
                if self.profesional is not None
                else []
            )

        if model is Cita:
            return RecordingQuery(
                self.citas
            )

        if model is Usuario:
            return RecordingQuery(
                [self.estudiante]
                if self.estudiante is not None
                else []
            )

        return RecordingQuery([])

    def add(self, obj):
        self.add_calls.append(obj)

    def commit(self):
        self.commit_calls += 1


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


def _profesional(
    *,
    especialidad="Nutrici?n",
    estado="activo",
):
    return SimpleNamespace(
        id=10,
        nombre="Profesional Uno",
        especialidad=especialidad,
        estado=estado,
    )


def _cita():
    return SimpleNamespace(
        id=100,
        profesional_id=10,
        estudiante_id=20,
        fecha="2026-09-20",
        hora="09:00",
        estado="pendiente",
        cancelada_por_admin=False,
        motivo_cancelacion=None,
    )


def _estudiante():
    return SimpleNamespace(
        id=20,
        correo="ana@utem.cl",
    )


def test_estado_profesional_usa_gestionar_efectivo():
    source = inspect.getsource(
        admin.cambiar_estado_profesional
    )

    assert (
        "require_effective_permission"
        in source
    )

    assert (
        "Permission.PROFESIONALES_GESTIONAR"
        in source
    )

    assert (
        "require_permission(Permission.PROFESIONALES_GESTIONAR)"
        not in source
    )


def test_estado_sin_alcance_falla_antes_de_bd(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.cambiar_estado_profesional(
            prof_id=10,
            body={"estado": "inactivo"},
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []
    assert db.add_calls == []
    assert db.commit_calls == 0


def test_estado_profesional_fuera_de_scope_da_404_sin_mutar(
    monkeypatch,
):
    prof = _profesional(
        especialidad="Odontolog?a"
    )

    db = FakeDB(
        profesional=prof,
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.cambiar_estado_profesional(
            prof_id=10,
            body={
                "estado": "inactivo",
                "cancelar_citas": True,
            },
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Profesional no encontrado"

    assert prof.estado == "activo"

    assert Cita not in db.query_calls
    assert Usuario not in db.query_calls

    assert db.add_calls == []
    assert db.commit_calls == 0


def test_estado_profesional_inexistente_conserva_404(
    monkeypatch,
):
    db = FakeDB(
        profesional=None,
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    with pytest.raises(HTTPException) as exc:
        admin.cambiar_estado_profesional(
            prof_id=999,
            body={"estado": "inactivo"},
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 404
    assert db.commit_calls == 0


def test_estado_dentro_de_scope_sin_cancelar_conserva_semantica(
    monkeypatch,
):
    prof = _profesional()

    db = FakeDB(
        profesional=prof,
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
        "registrar_evento_auditoria",
        lambda *args, **kwargs: None,
    )

    resultado = admin.cambiar_estado_profesional(
        prof_id=10,
        body={
            "estado": "inactivo",
            "motivo": "Licencia",
        },
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "message": "Estado actualizado a 'inactivo'"
    }

    assert prof.estado == "inactivo"

    # HistorialEstadoProfesional.
    assert len(db.add_calls) == 1
    assert db.commit_calls == 1
    assert Cita not in db.query_calls


def test_estado_dentro_de_scope_cancelando_citas_conserva_flujo(
    monkeypatch,
):
    prof = _profesional()
    cita = _cita()

    db = FakeDB(
        profesional=prof,
        citas=[cita],
        estudiante=_estudiante(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    correos = []
    auditorias = []

    monkeypatch.setattr(
        admin,
        "simular_envio_correo",
        lambda *args, **kwargs: correos.append(
            (args, kwargs)
        ),
    )

    monkeypatch.setattr(
        admin,
        "registrar_evento_auditoria",
        lambda *args, **kwargs: auditorias.append(
            (args, kwargs)
        ),
    )

    resultado = admin.cambiar_estado_profesional(
        prof_id=10,
        body={
            "estado": "inactivo",
            "cancelar_citas": True,
            "fecha": "2026-09-20",
        },
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "message": (
            "Estado 'inactivo'. "
            "1 citas canceladas."
        ),
        "citas_canceladas": 1,
    }

    assert prof.estado == "inactivo"

    assert cita.estado == "cancelada"
    assert cita.cancelada_por_admin is True
    assert (
        cita.motivo_cancelacion
        == "Profesional: inactivo"
    )

    # 1 historial + 1 AusenciaProfesional (bloquea agendamiento nuevo
    # ese día — ver app.models.ausencia_profesional) + 1 notificación.
    assert len(db.add_calls) == 3
    assert any(
        isinstance(obj, AusenciaProfesional) and obj.fecha == "2026-09-20"
        for obj in db.add_calls
    )
    assert len(correos) == 1

    # Auditor?a estado + auditor?a cancelaci?n masiva.
    assert len(auditorias) == 2

    # Conserva los dos commits hist?ricos.
    assert db.commit_calls == 2


def test_scope_se_verifica_antes_de_estado_historial_y_commit():
    source = inspect.getsource(
        admin.cambiar_estado_profesional
    )

    pos_resolver = source.find(
        "obtener_alcance_administrativo_efectivo"
    )

    pos_prof = source.find(
        "db.query(Profesional)"
    )

    pos_scope = source.find(
        "especialidad_permitida_por_alcance"
    )

    pos_mutacion = source.find(
        "prof.estado = estado_nuevo"
    )

    pos_historial = source.find(
        "HistorialEstadoProfesional("
    )

    pos_cita = source.find(
        "db.query(Cita)"
    )

    pos_commit = source.find(
        "db.commit()"
    )

    assert (
        -1
        < pos_resolver
        < pos_prof
        < pos_scope
        < pos_mutacion
        < pos_historial
        < pos_commit
    )

    assert pos_scope < pos_cita
