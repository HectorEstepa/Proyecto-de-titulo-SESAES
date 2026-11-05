import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.notificacion import Notificacion
from app.models.usuario import Usuario
from app.rbac.permissions import Permission
from app.routers import citas
from app.routers import profesionales
from app.routers import solicitudes_horario


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, usuarios):
        self.usuarios = list(usuarios)
        self.added = []

    def query(self, model):
        assert model is Usuario
        return FakeQuery(self.usuarios)

    def add(self, obj):
        self.added.append(obj)


def _usuario(
    usuario_id,
    rol,
    *,
    activo=True,
):
    return SimpleNamespace(
        id=usuario_id,
        rol=rol,
        activo=activo,
        correo=f"u{usuario_id}@utem.cl",
    )


def test_citas_agenda_gestionar_usa_resolver_efectivo(
    monkeypatch,
):
    db = object()

    current_user = {
        "id": 10,
        "rol": "admin",
    }

    llamadas = []

    def fake_resolver(
        db_recibida,
        usuario,
        permiso,
    ):
        llamadas.append(
            (
                db_recibida,
                usuario,
                permiso,
            )
        )
        return True

    monkeypatch.setattr(
        citas,
        "tiene_permiso_efectivo",
        fake_resolver,
    )

    assert citas._puede_gestionar_agenda(
        current_user,
        db,
    )

    assert llamadas == [
        (
            db,
            current_user,
            Permission.AGENDA_GESTIONAR,
        )
    ]


def test_citas_scope_fuera_de_especialidad_responde_404(
    monkeypatch,
):
    alcance = object()

    monkeypatch.setattr(
        citas,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: alcance,
    )

    monkeypatch.setattr(
        citas,
        "especialidad_permitida_por_alcance",
        lambda alcance_recibido, especialidad: False,
    )

    with pytest.raises(HTTPException) as exc:
        citas._verificar_alcance_profesional_agenda(
            object(),
            {
                "id": 10,
                "rol": "admin",
            },
            SimpleNamespace(
                especialidad="Odontologia",
            ),
        )

    assert exc.value.status_code == 404


@pytest.mark.parametrize(
    "modulo,nombre_funcion",
    [
        (
            profesionales,
            "_notificar_con_agenda_gestionar",
        ),
        (
            solicitudes_horario,
            "_notificar_admin",
        ),
    ],
)
def test_notificadores_admin_respetan_permiso_scope_y_activo(
    monkeypatch,
    modulo,
    nombre_funcion,
):
    usuarios = [
        _usuario(1, "admin"),
        _usuario(2, "admin"),
        _usuario(
            3,
            "admin",
            activo=False,
        ),
        _usuario(4, "superadmin"),
        _usuario(5, "profesional"),
        _usuario(6, "estudiante"),
    ]

    db = FakeDB(usuarios)
    llamadas_admin = []

    def fake_admin_en_especialidad(
        db_recibida,
        usuario_id,
        permiso,
        especialidad,
    ):
        llamadas_admin.append(
            (
                usuario_id,
                permiso,
                especialidad,
            )
        )

        return (
            usuario_id == 1
            and permiso
            == Permission.AGENDA_GESTIONAR
            and especialidad == "Nutricion"
        )

    monkeypatch.setattr(
        modulo,
        "tiene_permiso_admin_en_especialidad",
        fake_admin_en_especialidad,
    )

    funcion = getattr(
        modulo,
        nombre_funcion,
    )

    funcion(
        db,
        "Nutricion",
        "evento administrativo",
    )

    notificaciones = [
        obj
        for obj in db.added
        if isinstance(
            obj,
            Notificacion,
        )
    ]

    destinatarios = {
        obj.usuario_id
        for obj in notificaciones
    }

    # ADMIN valido + SUPERADMIN.
    assert destinatarios == {
        1,
        4,
    }

    # ADMIN sin permiso/scope no recibe.
    assert 2 not in destinatarios

    # ADMIN inactivo se descarta incluso antes del resolver.
    assert 3 not in {
        usuario_id
        for usuario_id, _, _
        in llamadas_admin
    }

    # Solo ADMIN activos entran al resolver persistido.
    assert {
        usuario_id
        for usuario_id, _, _
        in llamadas_admin
    } == {
        1,
        2,
    }


def test_reportar_ausencia_legacy_no_esta_registrado_como_endpoint():
    paths = {
        route.path
        for route in profesionales.router.routes
    }

    assert (
        "/profesional/{prof_id}/reportar-ausencia"
        not in paths
    )


def test_solicitudes_pasan_especialidad_al_notificador():
    for endpoint in (
        solicitudes_horario.solicitar_colacion,
        solicitudes_horario.solicitar_jornada,
    ):
        source = inspect.getsource(
            endpoint
        )

        assert "_notificar_admin(" in source
        assert "prof.especialidad" in source


def test_crear_y_cancelar_cita_aplican_scope_administrativo():
    crear = inspect.getsource(
        citas.crear_cita
    )

    cancelar = inspect.getsource(
        citas.cancelar_cita
    )

    assert (
        "_verificar_alcance_profesional_agenda"
        in crear
    )

    assert (
        "_verificar_alcance_profesional_agenda"
        in cancelar
    )
