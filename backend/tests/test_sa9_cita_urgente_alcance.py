import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.dia_cerrado import DiaCerrado
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
        self.filter_calls = []

    def filter(self, *conditions):
        self.filter_calls.append(conditions)
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDB:
    def __init__(
        self,
        *,
        dia_cerrado=None,
        profesional=None,
        estudiante=None,
    ):
        self.dia_cerrado = dia_cerrado
        self.profesional = profesional
        self.estudiante = estudiante

        self.query_calls = []
        self.add_calls = []
        self.flush_calls = 0
        self.commit_calls = 0
        self.refresh_calls = []

    def query(self, model):
        self.query_calls.append(model)

        if model is DiaCerrado:
            return RecordingQuery(
                [self.dia_cerrado]
                if self.dia_cerrado is not None
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

    def flush(self):
        self.flush_calls += 1

    def commit(self):
        self.commit_calls += 1

    def refresh(self, obj):
        self.refresh_calls.append(obj)


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


def _cita_input(
    *,
    profesional_id=10,
):
    return SimpleNamespace(
        estudiante_id=20,
        profesional_id=profesional_id,
        fecha="2026-09-20",
        hora="09:00",
        observaciones=None,
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
        rol="estudiante",
    )


def test_cita_urgente_usa_agenda_gestionar_efectivo():
    source = inspect.getsource(
        admin.crear_cita_urgente
    )

    assert (
        "require_effective_permission(Permission.AGENDA_GESTIONAR)"
        in source
    )

    assert (
        "require_permission(Permission.AGENDA_GESTIONAR)"
        not in source
    )


def test_cita_urgente_sin_alcance_falla_antes_de_bd(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(
            cita=_cita_input(),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403

    assert db.query_calls == []
    assert db.add_calls == []
    assert db.flush_calls == 0
    assert db.commit_calls == 0


def test_cita_urgente_profesional_fuera_de_scope_da_404(
    monkeypatch,
):
    db = FakeDB(
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
        admin.crear_cita_urgente(
            cita=_cita_input(),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Profesional no encontrado"

    # Puede consultar el cierre institucional y el profesional,
    # pero no debe acceder al estudiante ni crear la cita.
    assert DiaCerrado in db.query_calls
    assert Profesional in db.query_calls
    assert Usuario not in db.query_calls

    assert db.add_calls == []
    assert db.flush_calls == 0
    assert db.commit_calls == 0


def test_cita_urgente_profesional_inexistente_conserva_404(
    monkeypatch,
):
    db = FakeDB(
        profesional=None,
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(
            cita=_cita_input(
                profesional_id=999
            ),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404

    assert Usuario not in db.query_calls
    assert db.add_calls == []
    assert db.commit_calls == 0


def test_cita_urgente_dia_cerrado_conserva_validacion(
    monkeypatch,
):
    db = FakeDB(
        dia_cerrado=SimpleNamespace(
            id=1,
            fecha="2026-09-20",
        ),
        profesional=_profesional(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(
            cita=_cita_input(),
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 400
    assert "cerrado" in exc.value.detail.lower()

    assert db.add_calls == []
    assert db.flush_calls == 0
    assert db.commit_calls == 0


def test_guard_scope_profesional_esta_antes_de_crear_cita():
    source = inspect.getsource(
        admin.crear_cita_urgente
    )

    pos_scope_general = source.find(
        "obtener_alcance_administrativo_efectivo"
    )

    pos_prof_scope = source.find(
        "especialidad_permitida_por_alcance"
    )

    pos_create = source.find(
        "nueva = Cita("
    )

    pos_add = source.find(
        "db.add(nueva)"
    )

    pos_flush = source.find(
        "db.flush()"
    )

    pos_commit = source.find(
        "db.commit()"
    )

    assert -1 < pos_scope_general < pos_create
    assert -1 < pos_prof_scope < pos_create
    assert -1 < pos_prof_scope < pos_add
    assert -1 < pos_prof_scope < pos_flush
    assert -1 < pos_prof_scope < pos_commit
