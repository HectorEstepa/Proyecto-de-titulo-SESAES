import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import citas, configuracion_centro
from app.schemas import ConfiguracionCentroUpdate
from app.rbac.permissions import Permission


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_admin_y_superadmin_tienen_agenda_global(
    rol,
    monkeypatch,
):
    db = object()

    monkeypatch.setattr(
        citas,
        "tiene_permiso_efectivo",
        lambda db_recibida, current_user, permiso: (
            db_recibida is db
            and current_user["rol"] == rol
            and permiso == Permission.AGENDA_GESTIONAR
        ),
    )

    assert citas._puede_gestionar_agenda(
        {"id": 10, "rol": rol},
        db,
    )


@pytest.mark.parametrize("rol", ["estudiante", "profesional"])
def test_roles_no_administrativos_no_tienen_agenda_global(
    rol,
    monkeypatch,
):
    db = object()

    monkeypatch.setattr(
        citas,
        "tiene_permiso_efectivo",
        lambda db_recibida, current_user, permiso: False,
    )

    assert not citas._puede_gestionar_agenda(
        {"id": 10, "rol": rol},
        db,
    )


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_agenda_global_permite_operar_para_otro_estudiante(
    rol,
    monkeypatch,
):
    db = object()

    monkeypatch.setattr(
        citas,
        "tiene_permiso_efectivo",
        lambda db_recibida, current_user, permiso: True,
    )

    assert citas._verificar_propietario_o_agenda(
        {"id": 10, "rol": rol},
        20,
        db,
    ) is True


def test_estudiante_solo_puede_operar_su_agenda(
    monkeypatch,
):
    db = object()

    monkeypatch.setattr(
        citas,
        "tiene_permiso_efectivo",
        lambda db_recibida, current_user, permiso: False,
    )

    assert citas._verificar_propietario_o_agenda(
        {"id": 20, "rol": "estudiante"},
        20,
        db,
    ) is False

    with pytest.raises(HTTPException) as exc:
        citas._verificar_propietario_o_agenda(
            {"id": 20, "rol": "estudiante"},
            21,
            db,
        )

    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_roles_administrativos_no_tienen_bypass_a_cita_privada(rol):
    cita = SimpleNamespace(
        estudiante_id=20,
        profesional_id=3,
    )

    with pytest.raises(HTTPException) as exc:
        citas._verificar_acceso_a_cita(
            cita,
            {"id": 10, "rol": rol},
            db=None,
        )

    assert exc.value.status_code == 403


def test_estudiante_dueno_accede_a_cita_privada():
    cita = SimpleNamespace(
        estudiante_id=20,
        profesional_id=3,
    )

    citas._verificar_acceso_a_cita(
        cita,
        {"id": 20, "rol": "estudiante"},
        db=None,
    )


def test_historial_estudiante_es_exclusivo_del_dueno():
    source = inspect.getsource(citas.get_historial)

    assert 'roles_permitidos=["estudiante"]' in source
    assert '"admin"' not in source
    assert '"superadmin"' not in source


def test_pdf_exige_identidad_y_acceso_privado():
    signature = inspect.signature(citas.descargar_pdf_cita)
    source = inspect.getsource(citas.descargar_pdf_cita)

    assert "current_user" in signature.parameters
    assert "_verificar_acceso_a_cita" in source


def test_crear_cita_protege_urgencia_y_sobrecupo():
    source = inspect.getsource(citas.crear_cita)

    assert "_verificar_propietario_o_agenda" in source
    assert "puede_gestionar_agenda" in source
    assert "_verificar_alcance_profesional_agenda" in source

    assert (
        "_puede_gestionar_agenda(current_user)"
        not in source
    )

    assert source.count(
        "if puede_gestionar_agenda"
    ) >= 2

    assert '"urgente":      nueva.urgente or False' in source


def test_cancelacion_administrativa_depende_de_agenda():
    source = inspect.getsource(citas.cancelar_cita)

    assert (
        "puede_gestionar_agenda = "
        "_puede_gestionar_agenda"
        in source
    )

    assert "_verificar_alcance_profesional_agenda" in source
    assert 'current_user["rol"] != "admin"' not in source

    assert (
        "_puede_gestionar_agenda(current_user)"
        not in source
    )


def test_admin_no_modifica_configuracion_global_por_defecto():
    datos = ConfiguracionCentroUpdate(
        nombre_centro="Centro modificado"
    )

    with pytest.raises(HTTPException) as exc:
        configuracion_centro._autorizar_actualizacion_configuracion(
            datos,
            {"id": 10, "rol": "admin"},
        )

    assert exc.value.status_code == 403


def test_superadmin_si_modifica_configuracion_global():
    datos = ConfiguracionCentroUpdate(
        nombre_centro="Centro modificado"
    )

    configuracion_centro._autorizar_actualizacion_configuracion(
        datos,
        {"id": 10, "rol": "superadmin"},
    )


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_roles_admin_pueden_actualizar_perfil_compat(rol):
    datos = ConfiguracionCentroUpdate(
        nombre_admin="Cuenta administrativa",
        foto_admin_url="data:image/png;base64,ABC",
    )

    configuracion_centro._autorizar_actualizacion_configuracion(
        datos,
        {"id": 10, "rol": rol},
    )


def test_profesional_no_modifica_perfil_admin():
    datos = ConfiguracionCentroUpdate(
        nombre_admin="No autorizado"
    )

    with pytest.raises(HTTPException) as exc:
        configuracion_centro._autorizar_actualizacion_configuracion(
            datos,
            {"id": 10, "rol": "profesional"},
        )

    assert exc.value.status_code == 403


def test_password_admite_admin_superadmin_y_usa_current_user():
    source = inspect.getsource(
        configuracion_centro.cambiar_password_admin
    )

    assert 'roles_permitidos=["admin", "superadmin"]' in source
    assert 'Usuario.id == current_user["id"]' in source
    assert 'Usuario.rol == "admin"' not in source
