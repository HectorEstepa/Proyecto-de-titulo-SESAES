import inspect
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.profesional import Profesional
from app.models.solicitud_horario import SolicitudHorario
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import solicitudes_horario as m


class RecordingQuery:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.filters = []
        self.order_calls = 0

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def order_by(self, *args):
        self.order_calls += 1
        return self

    def first(self):
        return (
            self.rows[0]
            if self.rows
            else None
        )

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(
        self,
        *,
        profesionales=None,
        solicitudes=None,
    ):
        self.profesionales = list(
            profesionales or []
        )
        self.solicitudes = list(
            solicitudes or []
        )

        self.query_calls = []
        self.add_calls = []
        self.commit_calls = 0

    def query(self, model):
        self.query_calls.append(model)

        if model is Profesional:
            return RecordingQuery(
                self.profesionales
            )

        if model is SolicitudHorario:
            return RecordingQuery(
                self.solicitudes
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
    id=10,
    especialidad="Nutrici?n",
):
    return SimpleNamespace(
        id=id,
        nombre=f"Profesional {id}",
        especialidad=especialidad,
        hora_almuerzo_inicio=None,
        hora_almuerzo_fin=None,
        horario_inicio=None,
        horario_fin=None,
    )


def _solicitud(
    *,
    id=100,
    profesional_id=10,
    estado="pendiente",
    tipo="colacion",
):
    return SimpleNamespace(
        id=id,
        profesional_id=profesional_id,
        tipo=tipo,
        hora_inicio="13:00",
        hora_fin="14:00",
        estado=estado,
        motivo_rechazo=None,
        fecha_solicitud=datetime(
            2026,
            9,
            7,
            12,
            0,
        ),
        fecha_resolucion=None,
    )


def test_tres_rutas_admin_usan_agenda_gestionar_efectivo():
    for endpoint in (
        m.get_solicitudes_admin,
        m.aprobar_solicitud,
        m.rechazar_solicitud,
    ):
        source = inspect.getsource(endpoint)

        assert (
            "require_effective_permission"
            in source
        )

        assert (
            "Permission.AGENDA_GESTIONAR"
            in source
        )

        assert (
            "require_permission("
            not in source
        )


def test_listado_sin_alcance_falla_antes_de_bd(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        m.get_solicitudes_admin(
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []
    assert db.commit_calls == 0


def test_listado_limitado_sin_profesionales_visibles_devuelve_vacio(
    monkeypatch,
):
    db = FakeDB(
        profesionales=[
            _profesional(
                id=20,
                especialidad="Odontolog?a",
            )
        ],
        solicitudes=[
            _solicitud(
                profesional_id=20
            )
        ],
    )

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    resultado = m.get_solicitudes_admin(
        estado="todas",
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []

    # db.query(SolicitudHorario) solo construye una query lazy.
    # Al no existir profesionales visibles, el endpoint retorna []
    # antes de ejecutar order_by().all() sobre solicitudes.
    assert db.query_calls == [
        SolicitudHorario,
        Profesional,
    ]
    assert db.commit_calls == 0


def test_listado_aplica_scope_antes_de_all():
    source = inspect.getsource(
        m.get_solicitudes_admin
    )

    pos_scope = source.find(
        "_ids_profesionales_en_alcance"
    )

    pos_filter_scope = source.find(
        "SolicitudHorario.profesional_id.in_"
    )

    pos_all = source.find(
        ".all()"
    )

    assert (
        -1
        < pos_scope
        < pos_filter_scope
        < pos_all
    )


def test_aprobar_fuera_de_scope_oculta_estado_resuelto(
    monkeypatch,
):
    solicitud = _solicitud(
        estado="aprobado",
    )

    prof = _profesional(
        especialidad="Odontolog?a",
    )

    db = FakeDB(
        profesionales=[prof],
        solicitudes=[solicitud],
    )

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    monkeypatch.setattr(
        m,
        "_notificar_profesional",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "No deb?a notificar fuera de scope."
            )
        ),
    )

    monkeypatch.setattr(
        m,
        "registrar_evento_auditoria",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "No deb?a auditar fuera de scope."
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        m.aprobar_solicitud(
            solicitud_id=100,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Solicitud no encontrada"

    assert solicitud.estado == "aprobado"
    assert prof.hora_almuerzo_inicio is None
    assert db.commit_calls == 0


def test_rechazar_fuera_de_scope_oculta_estado_resuelto(
    monkeypatch,
):
    solicitud = _solicitud(
        estado="rechazado",
    )

    prof = _profesional(
        especialidad="Odontolog?a",
    )

    db = FakeDB(
        profesionales=[prof],
        solicitudes=[solicitud],
    )

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    monkeypatch.setattr(
        m,
        "_notificar_profesional",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "No deb?a notificar fuera de scope."
            )
        ),
    )

    monkeypatch.setattr(
        m,
        "registrar_evento_auditoria",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "No deb?a auditar fuera de scope."
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        m.rechazar_solicitud(
            solicitud_id=100,
            body={"motivo": "No"},
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Solicitud no encontrada"

    assert solicitud.estado == "rechazado"
    assert solicitud.motivo_rechazo is None
    assert db.commit_calls == 0


def test_aprobar_dentro_de_scope_conserva_flujo(
    monkeypatch,
):
    solicitud = _solicitud()
    prof = _profesional()

    db = FakeDB(
        profesionales=[prof],
        solicitudes=[solicitud],
    )

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    notificaciones = []
    auditorias = []

    monkeypatch.setattr(
        m,
        "_notificar_profesional",
        lambda *args, **kwargs: notificaciones.append(
            (args, kwargs)
        ),
    )

    monkeypatch.setattr(
        m,
        "registrar_evento_auditoria",
        lambda *args, **kwargs: auditorias.append(
            (args, kwargs)
        ),
    )

    resultado = m.aprobar_solicitud(
        solicitud_id=100,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "message": "Solicitud aprobada correctamente"
    }

    assert solicitud.estado == "aprobado"
    assert solicitud.fecha_resolucion is not None

    assert prof.hora_almuerzo_inicio == "13:00"
    assert prof.hora_almuerzo_fin == "14:00"

    assert len(notificaciones) == 1
    assert len(auditorias) == 1
    assert db.commit_calls == 1


def test_rechazar_dentro_de_scope_conserva_flujo(
    monkeypatch,
):
    solicitud = _solicitud()
    prof = _profesional()

    db = FakeDB(
        profesionales=[prof],
        solicitudes=[solicitud],
    )

    monkeypatch.setattr(
        m,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    notificaciones = []
    auditorias = []

    monkeypatch.setattr(
        m,
        "_notificar_profesional",
        lambda *args, **kwargs: notificaciones.append(
            (args, kwargs)
        ),
    )

    monkeypatch.setattr(
        m,
        "registrar_evento_auditoria",
        lambda *args, **kwargs: auditorias.append(
            (args, kwargs)
        ),
    )

    resultado = m.rechazar_solicitud(
        solicitud_id=100,
        body={
            "motivo": "Horario incompatible"
        },
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "message": "Solicitud rechazada"
    }

    assert solicitud.estado == "rechazado"
    assert (
        solicitud.motivo_rechazo
        == "Horario incompatible"
    )
    assert solicitud.fecha_resolucion is not None

    assert len(notificaciones) == 1
    assert len(auditorias) == 1
    assert db.commit_calls == 1


def test_scope_precede_estado_mutaciones_y_commit():
    for endpoint in (
        m.aprobar_solicitud,
        m.rechazar_solicitud,
    ):
        source = inspect.getsource(endpoint)

        pos_resolver = source.find(
            "obtener_alcance_administrativo_efectivo"
        )

        pos_solicitud = source.find(
            "db.query(SolicitudHorario)"
        )

        pos_prof = source.find(
            "db.query(Profesional)"
        )

        pos_scope = source.find(
            "especialidad_permitida_por_alcance"
        )

        pos_estado = source.find(
            'solicitud.estado != "pendiente"'
        )

        pos_commit = source.find(
            "db.commit()"
        )

        assert (
            -1
            < pos_resolver
            < pos_solicitud
            < pos_prof
            < pos_scope
            < pos_estado
            < pos_commit
        )
