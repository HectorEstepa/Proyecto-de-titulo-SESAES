"""
SESAES — RBAC: roles canónicos (Fase 3.1)

Roles reales verificados en backend/app/models/usuario.py
(`Usuario.rol = Column(String)`, sin constraint de DB) y en su uso en
backend/app/auth_dependencies.py y backend/app/routers/*.py:

    "estudiante", "profesional", "admin"

"superadmin" NO existe todavía en el código productivo. Se agrega acá
como rol canónico para esta fase, pero no se le concede ningún permiso
clínico ni un atajo de "acceso total" (ver rbac/permissions.py).

IMPORTANTE — este módulo NO reemplaza la columna Usuario.rol (sigue
siendo un String libre en esta fase) ni cambia el payload del JWT.
Solo agrega una capa de normalización y tipado sobre el valor de rol
que ya circula hoy por el sistema (JWT, sessionStorage, DB).
"""

from __future__ import annotations

import enum
from typing import Optional, Union


class Role(str, enum.Enum):
    """Roles canónicos de SESAES."""

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    PROFESIONAL = "profesional"
    ESTUDIANTE = "estudiante"


_VALUE_TO_ROLE = {rol.value: rol for rol in Role}


def normalizar_rol(value: Optional[Union[str, "Role"]]) -> Optional[Role]:
    """
    Normaliza un valor de rol (string crudo desde JWT/DB, o ya un Role)
    a un Role válido.

    Fail-closed: cualquier valor null, vacío, con espacios, o no
    reconocido devuelve None. NUNCA hace fallback a ADMIN/SUPERADMIN
    ni a ningún otro rol por defecto — quien llama debe tratar None
    como "sin rol válido" y denegar en consecuencia.
    """
    if value is None:
        return None

    if isinstance(value, Role):
        return value

    if not isinstance(value, str):
        return None

    valor_normalizado = value.strip().lower()
    if not valor_normalizado:
        return None

    return _VALUE_TO_ROLE.get(valor_normalizado)
