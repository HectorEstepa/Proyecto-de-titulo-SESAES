"""
SESAES — Fase 3.5A
Migración de backend administrativo desde guard global por rol hacia
autorización RBAC explícita endpoint por endpoint.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.routing import APIRoute

from app.rbac.permissions import Permission, has_permission
from app.routers import admin


ENDPOINTS = [
    ("GET", "/admin/estadisticas", Permission.REPORTES_VER),
    ("GET", "/admin/resumen-dia", Permission.AGENDA_VER),
    ("GET", "/admin/proximas-citas", Permission.AGENDA_VER),
    ("GET", "/admin/estudiantes", Permission.USUARIOS_VER),
    ("GET", "/admin/estudiantes/listado", Permission.USUARIOS_VER),
    ("GET", "/admin/estudiantes/{estudiante_id}/perfil", Permission.USUARIOS_VER),
    ("GET", "/admin/graficos/especialidad", Permission.REPORTES_VER),
    ("GET", "/admin/graficos/semana", Permission.REPORTES_VER),
    ("GET", "/admin/profesionales", Permission.PROFESIONALES_VER),
    ("POST", "/admin/profesionales", Permission.PROFESIONALES_GESTIONAR),
    ("PATCH", "/admin/profesionales/{prof_id}", Permission.PROFESIONALES_GESTIONAR),
    ("DELETE", "/admin/profesionales/{prof_id}", Permission.PROFESIONALES_GESTIONAR),
    ("PATCH", "/admin/profesionales/{prof_id}/estado", Permission.PROFESIONALES_GESTIONAR),
    ("GET", "/admin/profesionales/{prof_id}/historial-estados", Permission.PROFESIONALES_VER),
    ("POST", "/admin/citas/urgente", Permission.AGENDA_GESTIONAR),
    ("PATCH", "/admin/citas/{cita_id}/cancelar", Permission.AGENDA_GESTIONAR),
    ("PATCH", "/admin/citas/{cita_id}/prioridad", Permission.AGENDA_GESTIONAR),
    ("GET", "/admin/dias-cerrados", Permission.AGENDA_VER),
    ("POST", "/admin/dias-cerrados", Permission.AGENDA_GESTIONAR),
    ("GET", "/admin/dias-cerrados/{dia_id}/citas", Permission.AGENDA_VER),
    ("DELETE", "/admin/dias-cerrados/{dia_id}", Permission.AGENDA_GESTIONAR),
    ("GET", "/admin/historial", Permission.REPORTES_VER),
    ("GET", "/admin/exportar/cgr", Permission.REPORTES_CGR_EXPORTAR),
    ("GET", "/admin/exportar/alumnos", Permission.REPORTES_CGR_EXPORTAR),
    # CGR B2: datos JSON de las mismas exportaciones (el .xlsx se arma en el frontend).
    ("GET", "/admin/exportar/cgr/datos", Permission.REPORTES_CGR_EXPORTAR),
    ("GET", "/admin/exportar/alumnos/datos", Permission.REPORTES_CGR_EXPORTAR),
    ("GET", "/admin/auditoria", Permission.AUDITORIA_VER),
    ("GET", "/admin/configuracion", Permission.CONFIGURACION_GESTIONAR),
    ("PATCH", "/admin/configuracion", Permission.CONFIGURACION_GESTIONAR),
]


# Rutas dentro del router /admin que son self-service autenticado.
# No operan sobre recursos de terceros y por dise?o no requieren
# un Permission administrativo.
SELF_SERVICE_ENDPOINTS = {
    ("GET", "/admin/notificaciones"),
}


def _route(method: str, path: str) -> APIRoute:
    for route in admin.router.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f"No existe {method} {path}")


def _captured_permissions(route: APIRoute) -> list[Permission]:
    found: list[Permission] = []
    for param in inspect.signature(route.endpoint).parameters.values():
        dependency = getattr(param.default, "dependency", None)
        if dependency is None:
            continue
        closure = inspect.getclosurevars(dependency)
        permission = closure.nonlocals.get("permission")
        if isinstance(permission, Permission):
            found.append(permission)
    return found


def test_router_admin_ya_no_tiene_guard_global_por_rol():
    assert admin.router.dependencies == []
    assert not hasattr(admin, "solo_admin")


@pytest.mark.parametrize("method,path,permission", ENDPOINTS)
def test_cada_endpoint_admin_exige_su_permiso(method, path, permission):
    route = _route(method, path)
    assert _captured_permissions(route) == [permission]


def test_todas_las_rutas_admin_productivas_tienen_autorizacion_explicita():
    """
    Toda ruta productiva del router admin debe estar clasificada:

    - ENDPOINTS:
      exige exactamente un Permission administrativo.
    - SELF_SERVICE_ENDPOINTS:
      exige autenticaci?n propia, pero ning?n Permission
      administrativo de terceros.

    As? una ruta nueva no puede quedar fuera del inventario de
    seguridad por accidente.
    """
    expected_with_permission = {
        (method, path)
        for method, path, _ in ENDPOINTS
    }

    expected = (
        expected_with_permission
        | SELF_SERVICE_ENDPOINTS
    )

    actual = {
        (method, route.path)
        for route in admin.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method in {
            "GET",
            "POST",
            "PATCH",
            "PUT",
            "DELETE",
        }
    }

    assert actual == expected

    # Todas las rutas administrativas de terceros conservan
    # exactamente un permiso expl?cito.
    for method, path in sorted(
        expected_with_permission
    ):
        assert len(
            _captured_permissions(
                _route(method, path)
            )
        ) == 1

    # Las excepciones self-service no deben capturar ning?n
    # Permission administrativo y deben seguir autenticadas.
    for method, path in sorted(
        SELF_SERVICE_ENDPOINTS
    ):
        route = _route(method, path)

        assert _captured_permissions(route) == []

        current_user = inspect.signature(
            route.endpoint
        ).parameters["current_user"]

        dependency = getattr(
            current_user.default,
            "dependency",
            None,
        )

        assert dependency is admin.get_current_user


# ══════════════════════════════════════════════════════════════════
# SA-5 — auditoría append-only
# ══════════════════════════════════════════════════════════════════
# La auditoría de SESAES es append-only a nivel de aplicación: no debe
# existir ningún endpoint DELETE/PATCH/PUT sobre /admin/auditoria, y el
# permiso AUDITORIA_GESTIONAR ya no existe en el catálogo (ni siquiera
# para SUPERADMIN).

def _rutas_por_path(path: str) -> set[str]:
    """Métodos HTTP realmente registrados para un path dado del router admin."""
    metodos: set[str] = set()
    for route in admin.router.routes:
        if isinstance(route, APIRoute) and route.path == path:
            metodos |= route.methods
    return metodos


def test_no_existe_delete_auditoria_individual():
    with pytest.raises(AssertionError):
        _route("DELETE", "/admin/auditoria/{auditoria_id}")


def test_no_existe_delete_auditoria_masivo():
    metodos = _rutas_por_path("/admin/auditoria")
    assert "DELETE" not in metodos


def test_no_existe_patch_ni_put_auditoria():
    for path in ("/admin/auditoria", "/admin/auditoria/{auditoria_id}"):
        metodos = _rutas_por_path(path)
        assert "PATCH" not in metodos
        assert "PUT" not in metodos


def test_get_auditoria_sigue_existiendo_y_exige_auditoria_ver():
    route = _route("GET", "/admin/auditoria")
    assert _captured_permissions(route) == [Permission.AUDITORIA_VER]


def test_auditoria_gestionar_ya_no_existe_en_el_catalogo():
    assert not hasattr(Permission, "AUDITORIA_GESTIONAR")
    assert "auditoria.gestionar" not in {p.value for p in Permission}


def test_superadmin_conserva_auditoria_ver_y_admin_sigue_sin_ella():
    assert has_permission("superadmin", Permission.AUDITORIA_VER)
    assert not has_permission("admin", Permission.AUDITORIA_VER)


def test_historial_admin_no_expone_campos_clinicos():
    source = inspect.getsource(admin.get_historial_admin)
    assert '"medicamento"' not in source
    assert '"observaciones_atencion"' not in source


def test_notificaciones_admin_usan_usuario_autenticado():
    source = inspect.getsource(admin.get_notificaciones_admin)
    assert 'current_user["id"]' in source
    assert 'Usuario.rol == "admin"' not in source
    assert "admin.id" not in source
