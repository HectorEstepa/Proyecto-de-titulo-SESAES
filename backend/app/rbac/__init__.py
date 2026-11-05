"""
SESAES — RBAC (Fase 3.1): fundación de roles y permisos.

Ver:
  - roles.py         Role, normalizar_rol
  - permissions.py   Permission, ROLE_DEFAULT_PERMISSIONS, has_permission
  - dependencies.py  require_permission (dependency factory de FastAPI)

Esta fase NO migra routers productivos existentes a require_permission;
solo crea la fundación reutilizable. Ver checklist de Fase 3.1 para el
alcance exacto.
"""
