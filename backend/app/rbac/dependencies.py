"""
SESAES — RBAC: dependency factory para FastAPI (Fase 3.1)

require_permission(Permission.X) reutiliza get_current_user (la
autenticación ya existente) y agrega una capa de autorización por
permiso encima, sin crear una segunda autenticación ni tocar el JWT.

Comportamiento:
  - No autenticado / token inválido → conserva el 401 que ya lanza
    get_current_user (no se atrapa ni se reemplaza).
  - Autenticado pero sin el permiso → 403.
  - Con el permiso → devuelve current_user, permitiendo continuar
    al endpoint.
"""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth_dependencies import get_current_user
from app.database import get_db
from app.rbac.permissions import Permission, has_permission
from app.rbac.admin_authorization import tiene_permiso_efectivo


def require_permission(permission: Permission) -> Callable[..., dict]:
    """
    Devuelve una dependencia FastAPI que exige `permission` para el
    usuario autenticado actual.

    Uso típico en un endpoint:

        @router.get("/admin/auditoria")
        def get_auditoria(
            current_user: dict = Depends(require_permission(Permission.AUDITORIA_VER)),
        ):
            ...
    """

    def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para acceder a este recurso.",
            )
        return current_user

    return _dependency
def require_effective_permission(
    permission: Permission,
) -> Callable[..., dict]:
    """
    Exige autorizacion efectiva SA-9.

    ADMIN:
        perfil + permiso persistido + cuenta activa.

    SUPERADMIN/PROFESIONAL/ESTUDIANTE:
        permisos RBAC explicitos del rol actual.

    Esta dependencia verifica la capacidad general. El alcance del
    recurso concreto se verifica dentro del endpoint correspondiente.
    """

    def _dependency(
        current_user: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        if not tiene_permiso_efectivo(
            db,
            current_user,
            permission,
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "No tienes permiso para acceder "
                    "a este recurso."
                ),
            )

        return current_user

    return _dependency
