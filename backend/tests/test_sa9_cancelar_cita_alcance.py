import inspect
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
from app.routers import admin


class RecordingQuery:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def filter(self, *conditions):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDB:
    def __init__(
        self,
        *,
        cita=None,
        profesional=None,
        estudiante=None,
    ):
        self.cita = cita
        self.profesional = profesional
        self.estudiante = estudiante

        self.query_calls = []
        self.add_calls = []
        self.commit_calls = 0

    def query(self, model):
        self.query_calls.append(model)

        if model is Cita:
            return RecordingQuery(
                [self.cita]
                if self.cita is not None
                else []
            )

        if model is Profesional:
            return RecordingQuery(
                [self.profesional]
                if self.profesional is not None
                else []
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


def _cita():
    return SimpleNamespace(
        id=100,
        estudiante_id=20,
        profesional_id=10,
        fecha="2026-09-20",
        hora="09:00",
        estado="pendiente",
        cancelada_por_admin=False,
        motivo_cancelacion=None,
    )


def _profesional(
    *,
    especialidad="Nutrici?n",
):
    return SimpleNamespace(
        id=10,
        nombre="Profesional Uno",
        especialidad=especialidad,
    )


def _estudiante():
    return SimpleNamespace(
        id=20,
        nombre="Ana",
        correo="ana@ejemplo.cl",
    )


def test_cancelar_cita_usa_agenda_gestionar_efectivo():
    source = inspect.getsource(
        admin.cancelar_cita_admin
    )

    assert (
        "require_effective_permission(Permission.AGENDA_GESTIONAR)"
        in source
    )

    assert (
        "require_permission(Permission.AGENDA_GESTIONAR)"
        not in source
    )


def test_cancelar_sin_alcance_falla_antes_de_bd(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.cancelar_cita_admin(
            cita_id=100,
            body={},
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


def test_cancelar_cita_fuera_de_scope_da_404_sin_leer_estudiante(
    monkeypatch,
):
    cita = _cita()

    db = FakeDB(
        cita=cita,
        profesional=_profesional(
            especialidad="Odontolog?a"
        ),
        estudiante=_estudiante(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.cancelar_cita_admin(
            cita_id=100,
            body={
                "motivo": "Prueba"
            },
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Cita no encontrada"

    assert Cita in db.query_calls
    assert Profesional in db.query_calls
    assert Usuario not in db.query_calls

    assert cita.estado == "pendiente"
    assert cita.cancelada_por_admin is False
    assert cita.motivo_cancelacion is None

    assert db.add_calls == []
    assert db.commit_calls == 0


def test_cancelar_cita_con_profesional_inexistente_falla_cerrado(
    monkeypatch,
):
    cita = _cita()

    db = FakeDB(
        cita=cita,
        profesional=None,
        estudiante=_estudiante(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    with pytest.raises(HTTPException) as exc:
        admin.cancelar_cita_admin(
            cita_id=100,
            body={},
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 404

    assert Usuario not in db.query_calls
    assert cita.estado == "pendiente"
    assert db.add_calls == []
    assert db.commit_calls == 0


def test_cancelar_cita_inexistente_conserva_404(
    monkeypatch,
):
    db = FakeDB(
        cita=None,
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    with pytest.raises(HTTPException) as exc:
        admin.cancelar_cita_admin(
            cita_id=999,
            body={},
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 404
    assert Profesional not in db.query_calls
    assert Usuario not in db.query_calls
    assert db.commit_calls == 0


def test_cancelar_cita_dentro_de_scope_muta_y_confirma(
    monkeypatch,
):
    cita = _cita()

    db = FakeDB(
        cita=cita,
        profesional=_profesional(),
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

    resultado = admin.cancelar_cita_admin(
        cita_id=100,
        body={
            "motivo": "Ausencia del profesional"
        },
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "message": "Cita cancelada y estudiante notificado"
    }

    assert cita.estado == "cancelada"
    assert cita.cancelada_por_admin is True
    assert (
        cita.motivo_cancelacion
        == "Ausencia del profesional"
    )

    assert Usuario in db.query_calls
    assert len(db.add_calls) == 1
    assert len(correos) == 1
    assert len(auditorias) == 1
    assert db.commit_calls == 1


def test_scope_se_verifica_antes_de_estudiante_y_mutaciones():
    source = inspect.getsource(
        admin.cancelar_cita_admin
    )

    pos_scope_general = source.find(
        "obtener_alcance_administrativo_efectivo"
    )

    pos_prof = source.find(
        "db.query(Profesional)"
    )

    pos_prof_scope = source.find(
        "especialidad_permitida_por_alcance"
    )

    pos_est = source.find(
        "db.query(Usuario)"
    )

    pos_estado = source.find(
        'cita.estado = "cancelada"'
    )

    pos_notificacion = source.find(
        "Notificacion("
    )

    pos_commit = source.find(
        "db.commit()"
    )

    assert -1 < pos_scope_general < pos_prof
    assert -1 < pos_prof < pos_prof_scope
    assert -1 < pos_prof_scope < pos_est
    assert -1 < pos_prof_scope < pos_estado
    assert -1 < pos_prof_scope < pos_notificacion
    assert -1 < pos_prof_scope < pos_commit
