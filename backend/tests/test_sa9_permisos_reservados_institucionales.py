"""
SA-9.6D ? permisos administrativos reservados/institucionales.

Estos permisos NO forman parte del modelo delegable de perfiles ADMIN:

- configuracion.gestionar
- reportes.cgr.exportar
- auditoria.ver
- roles.gestionar

Deben permanecer reservados a SUPERADMIN y protegidos mediante
require_permission legacy. No participan del scope por especialidad.
"""

import inspect

import pytest
from fastapi.routing import APIRoute

from app.rbac.admin_access import (
    PerfilAccesoAdmin,
    permisos_permitidos_para_perfil,
    validar_permisos_para_perfil,
)
from app.rbac.permissions import (
    Permission,
    ROLE_DEFAULT_PERMISSIONS,
    has_permission,
)
from app.rbac.roles import Role
from app.routers import admin, usuarios


RESERVADOS = frozenset({
    Permission.CONFIGURACION_GESTIONAR,
    Permission.REPORTES_CGR_EXPORTAR,
    Permission.AUDITORIA_VER,
    Permission.ROLES_GESTIONAR,
})


def _dependency(endpoint):
    parametro = inspect.signature(
        endpoint
    ).parameters["current_user"]

    dependency = getattr(
        parametro.default,
        "dependency",
        None,
    )

    assert dependency is not None

    return dependency


def _permiso(endpoint):
    dependency = _dependency(endpoint)

    closure = inspect.getclosurevars(
        dependency
    )

    return closure.nonlocals.get(
        "permission"
    )


def test_catalogo_reservado_es_exactamente_el_acordado():
    assert RESERVADOS == {
        Permission.CONFIGURACION_GESTIONAR,
        Permission.REPORTES_CGR_EXPORTAR,
        Permission.AUDITORIA_VER,
        Permission.ROLES_GESTIONAR,
    }


@pytest.mark.parametrize(
    "perfil",
    list(PerfilAccesoAdmin),
)
def test_ningun_perfil_admin_contiene_permisos_reservados(
    perfil,
):
    techo = permisos_permitidos_para_perfil(
        perfil
    )

    assert techo.isdisjoint(
        RESERVADOS
    )


@pytest.mark.parametrize(
    "perfil",
    list(PerfilAccesoAdmin),
)
@pytest.mark.parametrize(
    "permiso",
    sorted(
        RESERVADOS,
        key=lambda p: p.value,
    ),
)
def test_validador_rechaza_permiso_reservado_en_todo_perfil(
    perfil,
    permiso,
):
    with pytest.raises(ValueError):
        validar_permisos_para_perfil(
            perfil=perfil,
            permisos=[permiso],
        )


@pytest.mark.parametrize(
    "permiso",
    sorted(
        RESERVADOS,
        key=lambda p: p.value,
    ),
)
def test_admin_no_recibe_reservados_por_role_defaults(
    permiso,
):
    assert (
        permiso
        not in ROLE_DEFAULT_PERMISSIONS[Role.ADMIN]
    )

    assert (
        has_permission(
            Role.ADMIN,
            permiso,
        )
        is False
    )


@pytest.mark.parametrize(
    "permiso",
    sorted(
        RESERVADOS,
        key=lambda p: p.value,
    ),
)
def test_superadmin_conserva_reservados_explicitos(
    permiso,
):
    assert (
        permiso
        in ROLE_DEFAULT_PERMISSIONS[
            Role.SUPERADMIN
        ]
    )

    assert (
        has_permission(
            Role.SUPERADMIN,
            permiso,
        )
        is True
    )


@pytest.mark.parametrize(
    "endpoint,permiso",
    [
        (
            admin.exportar_cgr,
            Permission.REPORTES_CGR_EXPORTAR,
        ),
        (
            admin.exportar_listado_alumnos,
            Permission.REPORTES_CGR_EXPORTAR,
        ),
        (
            admin.get_auditoria,
            Permission.AUDITORIA_VER,
        ),
        (
            admin.get_configuracion,
            Permission.CONFIGURACION_GESTIONAR,
        ),
        (
            admin.actualizar_configuracion,
            Permission.CONFIGURACION_GESTIONAR,
        ),
    ],
)
def test_endpoints_institucionales_conservan_permiso_reservado(
    endpoint,
    permiso,
):
    assert _permiso(endpoint) == permiso


@pytest.mark.parametrize(
    "endpoint",
    [
        admin.exportar_cgr,
        admin.exportar_listado_alumnos,
        admin.get_auditoria,
        admin.get_configuracion,
        admin.actualizar_configuracion,
    ],
)
def test_endpoints_institucionales_siguen_en_dependency_legacy(
    endpoint,
):
    dependency = _dependency(endpoint)

    # require_permission usa has_permission().
    assert (
        "has_permission"
        in dependency.__code__.co_names
    )

    # No deben entrar al resolver configurable de ADMIN.
    assert (
        "tiene_permiso_efectivo"
        not in dependency.__code__.co_names
    )


RUTAS_GOBERNANZA_ROLES_GESTIONAR = frozenset({
    ("GET", "/usuarios/administradores"),
    ("POST", "/usuarios/administradores"),
    ("PATCH", "/usuarios/administradores/{usuario_id}/estado"),
    ("PATCH", "/usuarios/administradores/{usuario_id}/rol"),
    ("GET", "/usuarios/administradores/catalogo-acceso"),
    ("GET", "/usuarios/administradores/{usuario_id}/acceso-administrativo"),
    ("PUT", "/usuarios/administradores/{usuario_id}/acceso-administrativo"),
})


def _rutas_con_roles_gestionar():
    encontrados = set()

    for route in usuarios.router.routes:
        if not isinstance(route, APIRoute):
            continue

        endpoint = route.endpoint

        if (
            "current_user"
            not in inspect.signature(endpoint).parameters
        ):
            continue

        dependency = _dependency(endpoint)
        closure = inspect.getclosurevars(dependency)
        permiso = closure.nonlocals.get("permission")

        if permiso != Permission.ROLES_GESTIONAR:
            continue

        for method in route.methods:
            encontrados.add((method, route.path))

    return encontrados


def test_gobernanza_conserva_endpoints_roles_gestionar_acordados():
    assert (
        _rutas_con_roles_gestionar()
        == RUTAS_GOBERNANZA_ROLES_GESTIONAR
    )


def test_gobernanza_roles_gestionar_sigue_fuera_del_resolver_admin():
    encontrados = set()

    for route in usuarios.router.routes:
        if not isinstance(route, APIRoute):
            continue

        endpoint = route.endpoint

        if (
            "current_user"
            not in inspect.signature(endpoint).parameters
        ):
            continue

        dependency = _dependency(endpoint)
        closure = inspect.getclosurevars(dependency)
        permiso = closure.nonlocals.get("permission")

        if permiso != Permission.ROLES_GESTIONAR:
            continue

        for method in route.methods:
            encontrados.add((method, route.path))

        assert (
            "has_permission"
            in dependency.__code__.co_names
        )

        assert (
            "tiene_permiso_efectivo"
            not in dependency.__code__.co_names
        )

    assert encontrados == RUTAS_GOBERNANZA_ROLES_GESTIONAR
