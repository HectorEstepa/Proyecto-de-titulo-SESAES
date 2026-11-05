import inspect

import pytest
from fastapi import HTTPException

from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    especialidad_permitida_por_alcance,
    normalizar_especialidad,
)
from app.rbac.dependencies import require_effective_permission
from app.rbac.permissions import Permission


def _alcance_limitado(*especialidades):
    return AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset(
            normalizar_especialidad(e).normalizada
            for e in especialidades
        ),
    )


def test_alcance_institucional_no_restringe_especialidad():
    alcance = AlcanceAdministrativoEfectivo(
        institucional=True,
        especialidades_normalizadas=frozenset(),
    )

    assert especialidad_permitida_por_alcance(
        alcance,
        "Nutrici?n",
    )

    assert especialidad_permitida_por_alcance(
        alcance,
        None,
    )


def test_alcance_limitado_permite_solo_especialidad_asignada():
    alcance = _alcance_limitado(
        "Nutrici?n",
    )

    assert especialidad_permitida_por_alcance(
        alcance,
        "  NUTRICI?N ",
    )

    assert not especialidad_permitida_por_alcance(
        alcance,
        "Odontolog?a",
    )


@pytest.mark.parametrize(
    "especialidad",
    [
        None,
        "",
        "   ",
        123,
    ],
)
def test_alcance_limitado_falla_cerrado_con_especialidad_invalida(
    especialidad,
):
    alcance = _alcance_limitado(
        "Nutrici?n",
    )

    assert not especialidad_permitida_por_alcance(
        alcance,
        especialidad,
    )


def test_dependencia_captura_permiso_en_closure():
    dependencia = require_effective_permission(
        Permission.AGENDA_VER
    )

    closure = inspect.getclosurevars(
        dependencia
    )

    assert (
        closure.nonlocals["permission"]
        is Permission.AGENDA_VER
    )


def test_dependencia_permite_si_resolver_efectivo_autoriza(
    monkeypatch,
):
    dependencia = require_effective_permission(
        Permission.AGENDA_VER
    )

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        lambda db, current_user, permission: (
            permission is Permission.AGENDA_VER
        ),
    )

    current_user = {
        "id": 10,
        "rol": "admin",
    }

    assert dependencia(
        current_user=current_user,
        db=object(),
    ) == current_user


def test_dependencia_da_403_si_resolver_efectivo_rechaza(
    monkeypatch,
):
    dependencia = require_effective_permission(
        Permission.PROFESIONALES_VER
    )

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        lambda db, current_user, permission: False,
    )

    with pytest.raises(HTTPException) as exc:
        dependencia(
            current_user={
                "id": 10,
                "rol": "admin",
            },
            db=object(),
        )

    assert exc.value.status_code == 403
