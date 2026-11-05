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


def _cita(
    *,
    estado="pendiente",
    urgente=False,
):
    return SimpleNamespace(
        id=100,
        estudiante_id=20,
        profesional_id=10,
        fecha="2026-09-20",
        hora="09:00",
        estado=estado,
        urgente=urgente,
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
    )


def test_prioridad_usa_agenda_gestionar_efectivo():
    source = inspect.getsource(
        admin.cambiar_prioridad_cita
    )

    assert (
        "require_effective_permission(Permission.AGENDA_GESTIONAR)"
        in source
    )

    assert (
        "require_permission(Permission.AGENDA_GESTIONAR)"
        not in source
    )


def test_prioridad_sin_alcance_falla_antes_de_bd(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.cambiar_prioridad_cita(
            cita_id=100,
            body={"urgente": True},
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


def test_prioridad_fuera_de_scope_da_404_sin_leer_estudiante(
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
        admin.cambiar_prioridad_cita(
            cita_id=100,
            body={"urgente": True},
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

    assert cita.urgente is False
    assert db.add_calls == []
    assert db.commit_calls == 0


def test_cita_cancelada_fuera_de_scope_no_revela_estado(
    monkeypatch,
):
    cita = _cita(
        estado="cancelada"
    )

    db = FakeDB(
        cita=cita,
        profesional=_profesional(
            especialidad="Odontolog?a"
        ),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.cambiar_prioridad_cita(
            cita_id=100,
            body={"urgente": True},
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    # No debe responder 400 revelando que la cita est? cancelada.
    assert exc.value.status_code == 404
    assert Usuario not in db.query_calls


def test_prioridad_inexistente_conserva_404(
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
        admin.cambiar_prioridad_cita(
            cita_id=999,
            body={"urgente": True},
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


@pytest.mark.parametrize(
    "estado",
    [
        "cancelada",
        "completada",
    ],
)
def test_prioridad_estado_no_editable_conserva_400_dentro_de_scope(
    monkeypatch,
    estado,
):
    cita = _cita(
        estado=estado
    )

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

    with pytest.raises(HTTPException) as exc:
        admin.cambiar_prioridad_cita(
            cita_id=100,
            body={"urgente": True},
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 400

    # El scope se resolvi? antes, pero no debe leer estudiante
    # ni mutar una cita no editable.
    assert Usuario not in db.query_calls
    assert cita.urgente is False
    assert db.add_calls == []
    assert db.commit_calls == 0


def test_prioridad_dentro_de_scope_marca_urgente(
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

    auditorias = []

    monkeypatch.setattr(
        admin,
        "registrar_evento_auditoria",
        lambda *args, **kwargs: auditorias.append(
            (args, kwargs)
        ),
    )

    resultado = admin.cambiar_prioridad_cita(
        cita_id=100,
        body={"urgente": True},
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "id": 100,
        "urgente": True,
        "estado": "pendiente",
    }

    assert cita.urgente is True
    assert Usuario in db.query_calls

    # Al marcar urgente se crea una notificaci?n.
    assert len(db.add_calls) == 1
    assert len(auditorias) == 1
    assert db.commit_calls == 1


def test_prioridad_dentro_de_scope_permite_quitar_urgencia(
    monkeypatch,
):
    cita = _cita(
        urgente=True
    )

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

    monkeypatch.setattr(
        admin,
        "registrar_evento_auditoria",
        lambda *args, **kwargs: None,
    )

    resultado = admin.cambiar_prioridad_cita(
        cita_id=100,
        body={"urgente": False},
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado["urgente"] is False
    assert cita.urgente is False

    # Quitar prioridad no genera nueva notificaci?n.
    assert db.add_calls == []
    assert db.commit_calls == 1


def test_scope_se_verifica_antes_del_estado_y_mutacion():
    source = inspect.getsource(
        admin.cambiar_prioridad_cita
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

    pos_estado = source.find(
        'if cita.estado in ('
    )

    pos_mutacion = source.find(
        "cita.urgente = nuevo_valor"
    )

    pos_estudiante = source.find(
        "db.query(Usuario)"
    )

    pos_commit = source.find(
        "db.commit()"
    )

    assert -1 < pos_scope_general < pos_prof
    assert -1 < pos_prof < pos_prof_scope
    assert -1 < pos_prof_scope < pos_estado
    assert -1 < pos_estado < pos_mutacion
    assert -1 < pos_mutacion < pos_estudiante
    assert -1 < pos_prof_scope < pos_commit
