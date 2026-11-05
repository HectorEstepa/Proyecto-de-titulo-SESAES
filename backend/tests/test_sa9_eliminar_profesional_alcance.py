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

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(
        self,
        *,
        profesional=None,
        citas=None,
        usuarios=None,
    ):
        self.profesional = profesional
        self.citas = list(citas or [])
        self.usuarios = list(usuarios or [])

        self.query_calls = []
        self.add_calls = []
        self.delete_calls = []
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
            if self.usuarios:
                usuario = self.usuarios.pop(0)
                return RecordingQuery(
                    [usuario]
                    if usuario is not None
                    else []
                )

            return RecordingQuery([])

        return RecordingQuery([])

    def add(self, obj):
        self.add_calls.append(obj)

    def delete(self, obj):
        self.delete_calls.append(obj)

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
    usuario_id=30,
):
    return SimpleNamespace(
        id=10,
        nombre="Profesional Uno",
        especialidad=especialidad,
        usuario_id=usuario_id,
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
        activo=True,
    )


def _usuario_profesional():
    return SimpleNamespace(
        id=30,
        correo="prof@utem.cl",
        activo=True,
    )


def test_eliminar_profesional_usa_gestionar_efectivo():
    source = inspect.getsource(
        admin.eliminar_profesional
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


def test_eliminar_sin_alcance_falla_antes_de_bd(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.eliminar_profesional(
            prof_id=10,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403

    assert db.query_calls == []
    assert db.add_calls == []
    assert db.delete_calls == []
    assert db.commit_calls == 0


def test_eliminar_profesional_fuera_de_scope_da_404_sin_efectos(
    monkeypatch,
):
    prof = _profesional(
        especialidad="Odontolog?a"
    )

    cita = _cita()

    db = FakeDB(
        profesional=prof,
        citas=[cita],
        usuarios=[
            _estudiante(),
            _usuario_profesional(),
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.eliminar_profesional(
            prof_id=10,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Profesional no encontrado"

    assert Cita not in db.query_calls
    assert Usuario not in db.query_calls

    assert cita.estado == "pendiente"
    assert cita.cancelada_por_admin is False
    assert cita.motivo_cancelacion is None

    assert db.add_calls == []
    assert db.delete_calls == []
    assert db.commit_calls == 0


def test_eliminar_profesional_inexistente_conserva_404(
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
        admin.eliminar_profesional(
            prof_id=999,
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 404

    assert Cita not in db.query_calls
    assert Usuario not in db.query_calls
    assert db.delete_calls == []
    assert db.commit_calls == 0


def test_eliminar_dentro_de_scope_conserva_cancelacion_y_desactivacion(
    monkeypatch,
):
    prof = _profesional()
    cita = _cita()

    estudiante = _estudiante()
    usuario_prof = _usuario_profesional()

    db = FakeDB(
        profesional=prof,
        citas=[cita],
        usuarios=[
            estudiante,
            usuario_prof,
        ],
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

    # Registro de auditoría de la agenda: además del evento agregado
    # "Eliminó profesional", se registra una fila POR CITA anulada.
    monkeypatch.setattr(
        admin,
        "registrar_evento_cita",
        lambda *args, **kwargs: auditorias.append(
            (args, kwargs)
        ),
    )

    resultado = admin.eliminar_profesional(
        prof_id=10,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "message": "Profesional eliminado correctamente"
    }

    assert cita.estado == "cancelada"
    assert cita.cancelada_por_admin is True
    assert (
        cita.motivo_cancelacion
        == "Profesional eliminado del sistema"
    )

    assert usuario_prof.activo is False

    # Estudiante no debe ser desactivado.
    assert estudiante.activo is True

    # Una notificaci?n por la cita.
    assert len(db.add_calls) == 1
    assert len(correos) == 1

    # Se elimina ?nicamente el Profesional.
    assert db.delete_calls == [prof]

    # 1 evento agregado ("Eliminó profesional") + 1 por la cita anulada.
    assert len(auditorias) == 2
    assert db.commit_calls == 1


def test_eliminar_sin_citas_tambien_desactiva_usuario_y_elimina(
    monkeypatch,
):
    prof = _profesional()
    usuario_prof = _usuario_profesional()

    db = FakeDB(
        profesional=prof,
        citas=[],
        usuarios=[
            usuario_prof,
        ],
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

    resultado = admin.eliminar_profesional(
        prof_id=10,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado["message"] == (
        "Profesional eliminado correctamente"
    )

    assert usuario_prof.activo is False
    assert db.add_calls == []
    assert db.delete_calls == [prof]
    assert db.commit_calls == 1


def test_scope_se_verifica_antes_de_citas_usuarios_y_delete():
    source = inspect.getsource(
        admin.eliminar_profesional
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

    pos_citas = source.find(
        "db.query(Cita)"
    )

    pos_usuario = source.find(
        "db.query(Usuario)"
    )

    pos_delete = source.find(
        "db.delete(prof)"
    )

    pos_commit = source.find(
        "db.commit()"
    )

    assert (
        -1
        < pos_resolver
        < pos_prof
        < pos_scope
        < pos_citas
        < pos_usuario
        < pos_delete
        < pos_commit
    )
