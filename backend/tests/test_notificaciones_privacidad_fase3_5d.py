import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.notificacion import Notificacion
from app.routers import notificaciones


@pytest.mark.parametrize(
    "rol",
    ["estudiante", "profesional", "admin", "superadmin"],
)
def test_todos_los_roles_pueden_operar_solo_su_usuario(rol):
    notificaciones._verificar_usuario_actual(
        {"id": 15, "rol": rol},
        15,
    )


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_roles_administrativos_no_tienen_bypass_sobre_otro_usuario(rol):
    with pytest.raises(HTTPException) as exc:
        notificaciones._verificar_usuario_actual(
            {"id": 15, "rol": rol},
            20,
        )

    assert exc.value.status_code == 403


def test_rol_desconocido_falla_cerrado():
    with pytest.raises(HTTPException) as exc:
        notificaciones._verificar_usuario_actual(
            {"id": 15, "rol": "gerente"},
            15,
        )

    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_admin_y_superadmin_pueden_modificar_notificacion_propia(rol):
    notif = SimpleNamespace(usuario_id=15)

    notificaciones._verificar_dueno_notificacion(
        notif,
        {"id": 15, "rol": rol},
    )


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_admin_y_superadmin_no_pueden_modificar_notificacion_ajena(rol):
    notif = SimpleNamespace(usuario_id=20)

    with pytest.raises(HTTPException) as exc:
        notificaciones._verificar_dueno_notificacion(
            notif,
            {"id": 15, "rol": rol},
        )

    assert exc.value.status_code == 403


class FakeQuery:
    def __init__(self):
        self.criterios = []
        self.delete_called = False

    def filter(self, *criterios):
        self.criterios.extend(criterios)
        return self

    def delete(self):
        self.delete_called = True
        return 1


class FakeDB:
    def __init__(self):
        self.query_obj = FakeQuery()
        self.commit_called = False

    def query(self, model):
        assert model is Notificacion
        return self.query_obj

    def commit(self):
        self.commit_called = True


def test_eliminar_todas_filtra_por_usuario_autenticado():
    db = FakeDB()

    respuesta = notificaciones.eliminar_todas_notificaciones(
        usuario_id=15,
        db=db,
        current_user={"id": 15, "rol": "admin"},
    )

    assert respuesta == {
        "message": "Todas las notificaciones eliminadas"
    }
    assert db.query_obj.delete_called is True
    assert db.commit_called is True

    assert len(db.query_obj.criterios) == 1

    criterio = db.query_obj.criterios[0]

    assert criterio.left.name == "usuario_id"
    assert criterio.left.table.name == Notificacion.__tablename__
    assert getattr(criterio.right, "value", None) == 15


def test_eliminar_todas_ajenas_falla_antes_del_delete():
    db = FakeDB()

    with pytest.raises(HTTPException) as exc:
        notificaciones.eliminar_todas_notificaciones(
            usuario_id=20,
            db=db,
            current_user={"id": 15, "rol": "superadmin"},
        )

    assert exc.value.status_code == 403
    assert db.query_obj.delete_called is False
    assert db.commit_called is False


def test_endpoints_de_usuario_aplican_propiedad_estricta():
    for funcion in (
        notificaciones.get_notificaciones,
        notificaciones.marcar_todas_leidas,
        notificaciones.eliminar_todas_notificaciones,
    ):
        source = inspect.getsource(funcion)
        assert "_verificar_usuario_actual" in source


def test_endpoints_individuales_validan_dueno():
    for funcion in (
        notificaciones.marcar_leida,
        notificaciones.eliminar_notificacion,
    ):
        source = inspect.getsource(funcion)
        assert "_verificar_dueno_notificacion" in source


def test_delete_masivo_contiene_filtro_usuario_id():
    source = inspect.getsource(
        notificaciones.eliminar_todas_notificaciones
    )

    assert "Notificacion.usuario_id == usuario_id" in source
    assert ".filter(Notificacion.usuario_id == usuario_id)" in source
