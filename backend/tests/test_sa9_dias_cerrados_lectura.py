import inspect
from types import SimpleNamespace

from app.routers import admin


class RecordingQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self.events = []

    def order_by(self, *args):
        self.events.append("order_by")
        return self

    def all(self):
        self.events.append("all")
        return list(self.rows)


class FakeDB:
    def __init__(self, rows):
        self.query_obj = RecordingQuery(rows)
        self.query_calls = []

    def query(self, model):
        self.query_calls.append(model)
        return self.query_obj


def test_dias_cerrados_usa_agenda_ver_efectivo():
    source = inspect.getsource(
        admin.listar_dias_cerrados
    )

    assert (
        "require_effective_permission(Permission.AGENDA_VER)"
        in source
    )

    assert (
        "require_permission(Permission.AGENDA_GESTIONAR)"
        not in source
    )


def test_dias_cerrados_es_lectura_institucional_sin_scope():
    source = inspect.getsource(
        admin.listar_dias_cerrados
    )

    assert (
        "obtener_alcance_administrativo_efectivo"
        not in source
    )

    assert (
        "_ids_profesionales_en_alcance"
        not in source
    )

    assert (
        "Cita.profesional_id"
        not in source
    )


def test_dias_cerrados_conserva_todos_los_registros():
    dias = [
        SimpleNamespace(
            id=1,
            fecha="2026-09-18",
            motivo="Feriado",
            fecha_creacion="2026-09-01",
        ),
        SimpleNamespace(
            id=2,
            fecha="2026-12-25",
            motivo="Centro cerrado",
            fecha_creacion="2026-09-02",
        ),
    ]

    db = FakeDB(dias)

    resultado = admin.listar_dias_cerrados(
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == [
        {
            "id": 1,
            "fecha": "2026-09-18",
            "motivo": "Feriado",
            "fecha_creacion": "2026-09-01",
        },
        {
            "id": 2,
            "fecha": "2026-12-25",
            "motivo": "Centro cerrado",
            "fecha_creacion": "2026-09-02",
        },
    ]

    assert db.query_obj.events == [
        "order_by",
        "all",
    ]
