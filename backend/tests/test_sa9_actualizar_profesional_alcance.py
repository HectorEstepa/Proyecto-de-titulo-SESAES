import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin
from app.schemas import ProfesionalUpdate


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
        profesional=None,
        usuario=None,
    ):
        self.profesional = profesional
        self.usuario = usuario

        self.query_calls = []
        self.commit_calls = 0
        self.refresh_calls = []

    def query(self, model):
        self.query_calls.append(model)

        if model is Profesional:
            return RecordingQuery(
                [self.profesional]
                if self.profesional is not None
                else []
            )

        if model is Usuario:
            return RecordingQuery(
                [self.usuario]
                if self.usuario is not None
                else []
            )

        return RecordingQuery([])

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


def _profesional(
    *,
    especialidad="Nutrici?n",
):
    return SimpleNamespace(
        id=10,
        nombre="Profesional Uno",
        tratamiento=None,
        especialidad=especialidad,
        iniciales="PU",
        descripcion="",
        duracion_min=45,
        correo="prof@utem.cl",
        rut=None,
        estado="activo",
        usuario_id=None,
        color_identificador=None,
    )


def test_actualizar_profesional_usa_gestionar_efectivo():
    source = inspect.getsource(
        admin.actualizar_profesional
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


def test_actualizar_sin_alcance_falla_antes_de_bd(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.actualizar_profesional(
            prof_id=10,
            datos=ProfesionalUpdate(
                nombre="Nuevo nombre"
            ),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []
    assert db.commit_calls == 0


def test_actualizar_profesional_fuera_de_scope_da_404(
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
        admin.actualizar_profesional(
            prof_id=10,
            datos=ProfesionalUpdate(
                nombre="Intento"
            ),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Profesional no encontrado"

    assert prof.nombre == "Profesional Uno"
    assert db.commit_calls == 0


def test_actualizar_profesional_inexistente_conserva_404(
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
        admin.actualizar_profesional(
            prof_id=999,
            datos=ProfesionalUpdate(
                nombre="Nada"
            ),
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 404
    assert db.commit_calls == 0


def test_no_puede_mover_profesional_a_especialidad_fuera_del_scope(
    monkeypatch,
):
    prof = _profesional(
        especialidad="Nutrici?n"
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
        admin.actualizar_profesional(
            prof_id=10,
            datos=ProfesionalUpdate(
                especialidad="Odontolog?a"
            ),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert "especialidad" in exc.value.detail.lower()

    assert prof.especialidad == "Nutrici?n"
    assert db.commit_calls == 0


def test_destino_normalizado_dentro_del_scope_es_permitido(
    monkeypatch,
):
    prof = _profesional(
        especialidad="Nutrici?n"
    )

    db = FakeDB(
        profesional=prof,
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "  Nutrici?n  "
        ),
    )

    monkeypatch.setattr(
        admin,
        "registrar_evento_auditoria",
        lambda *args, **kwargs: None,
    )

    resultado = admin.actualizar_profesional(
        prof_id=10,
        datos=ProfesionalUpdate(
            especialidad="NUTRICI?N"
        ),
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado is prof
    assert prof.especialidad == "NUTRICI?N"
    assert db.commit_calls == 1
    assert db.refresh_calls == [prof]


def test_actualizacion_normal_dentro_del_scope_conserva_semantica(
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

    resultado = admin.actualizar_profesional(
        prof_id=10,
        datos=ProfesionalUpdate(
            duracion_min=30
        ),
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado is prof
    assert prof.duracion_min == 30
    assert prof.especialidad == "Nutrici?n"
    assert db.commit_calls == 1


def test_scope_actual_y_destino_se_validan_antes_de_mutar():
    source = inspect.getsource(
        admin.actualizar_profesional
    )

    pos_resolver = source.find(
        "obtener_alcance_administrativo_efectivo"
    )

    pos_prof = source.find(
        "db.query(Profesional)"
    )

    pos_scope_actual = source.find(
        "especialidad_permitida_por_alcance"
    )

    pos_scope_destino = source.find(
        "especialidad_permitida_por_alcance",
        pos_scope_actual + 1,
    )

    pos_rut = source.find(
        "validar_rut"
    )

    pos_mutacion = source.find(
        "prof.nombre = datos.nombre"
    )

    pos_commit = source.find(
        "db.commit()"
    )

    assert (
        -1
        < pos_resolver
        < pos_prof
        < pos_scope_actual
        < pos_scope_destino
        < pos_rut
        < pos_mutacion
        < pos_commit
    )
