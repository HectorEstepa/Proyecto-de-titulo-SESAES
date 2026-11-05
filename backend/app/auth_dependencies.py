"""
Dependencias de autenticación/autorización reutilizables en todos los routers.

Uso típico en un endpoint:

    @router.get("/citas/estudiante/{estudiante_id}")
    def get_citas_estudiante(
        estudiante_id: int,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user),
    ):
        verificar_acceso(current_user, id_esperado=estudiante_id, roles_permitidos=["estudiante"])
        ...

Esto asegura dos cosas para cada request:
  1. Que el token JWT enviado sea válido, no haya expirado, y que la
     identidad/rol resuelta refleje el estado ACTUAL del usuario en BD
     (get_current_user).
  2. Que el usuario autenticado tenga permiso para ver/modificar ESE
     recurso específico: ownership estricto (verificar_acceso /
     verificar_acceso_profesional exigen que current_user['id'] sea
     dueño del recurso), sin bypass por rol. Desde Fase 3.5F, ADMIN y
     SUPERADMIN NO tienen un atajo automático a recursos ajenos por esta
     vía: el acceso administrativo a un recurso concreto se resuelve
     mediante un permiso RBAC explícito (has_permission /
     require_permission) en el endpoint correspondiente, nunca como
     bypass de rol dentro de estos helpers de ownership.
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.rbac.roles import normalizar_rol
from app.security import decode_access_token

_bearer_scheme = HTTPBearer(
    description="Token JWT obtenido en POST /login (campo access_token).",
    auto_error=False,
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """
    Extrae y valida el JWT del header 'Authorization: Bearer <token>' y
    luego resuelve la identidad ACTUAL del usuario contra la base de
    datos (SA-3).

    Usa fastapi.security.HTTPBearer en vez de leer el header a mano para que
    Swagger (/docs) muestre el candado de autenticación y permita probar los
    endpoints protegidos directamente desde ahí.

    SA-3 — corrección obligatoria: antes, esta dependencia solo validaba
    la firma/expiración del JWT y devolvía el payload congelado tal cual
    fue emitido en el login. Eso significaba que:
      - un JWT emitido antes de desactivar una cuenta seguía funcionando
        indefinidamente (hasta su expiración natural), y
      - un JWT emitido con un rol anterior conservaba ese rol viejo
        aunque la cuenta hubiera sido reasignada a otro rol.

    Ahora, además de validar el token (fail-closed: firma inválida o
    expirada -> 401, igual que antes), se consulta Usuario por
    payload["id"] y:
      1. si no existe -> 401 (cuenta eliminada / inconsistencia);
      2. si usuario.activo is False -> 401 (cuenta desactivada);
      3. se normaliza el rol ACTUAL de la fila de BD con normalizar_rol();
      4. si ese rol no es válido -> 401 (fail-closed, nunca se hace
         fallback a un rol por defecto);
      5. current_user se construye con el rol/correo/nombre/foto_url
         ACTUALES de BD, nunca con los valores (potencialmente viejos)
         que traía el JWT.

    Se usa Depends(get_db) explícito (inyección de FastAPI) en vez de
    abrir una SessionLocal manualmente acá adentro.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="No autenticado. Inicia sesión nuevamente.")

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada. Inicia sesión nuevamente.")

    if "id" not in payload or "rol" not in payload:
        raise HTTPException(status_code=401, detail="Token inválido.")

    usuario = db.query(Usuario).filter(Usuario.id == payload["id"]).first()
    if usuario is None:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada. Inicia sesión nuevamente.")

    if usuario.activo is False:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada. Inicia sesión nuevamente.")

    rol_actual = normalizar_rol(usuario.rol)
    if rol_actual is None:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada. Inicia sesión nuevamente.")

    return {
        "id": usuario.id,
        "rol": rol_actual.value,
        "correo": usuario.correo,
        "nombre": usuario.nombre,
        "foto_url": usuario.foto_url,
    }


def verificar_rol(current_user: dict, roles_permitidos: list[str]) -> None:
    """Exige que el usuario autenticado tenga uno de los roles indicados."""
    if current_user["rol"] not in roles_permitidos:
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso.")


def verificar_acceso(current_user: dict, id_esperado: int, roles_permitidos: list[str]) -> None:
    """
    Exige que el usuario autenticado:
      - tenga uno de los roles permitidos para este endpoint, Y
      - sea dueño del recurso (current_user['id'] == id_esperado).

    Fase 3.5F: se eliminó el bypass automático para rol 'admin'. ADMIN y
    SUPERADMIN NO tienen acceso general a recursos ajenos por esta vía;
    el acceso administrativo a un recurso concreto debe resolverse con un
    permiso RBAC explícito (has_permission / require_permission) en el
    endpoint correspondiente, nunca como atajo por rol dentro de este
    helper de ownership.

    Ejemplo: un estudiante solo puede pedir SU historial (id coincide).
    Un profesional nunca puede pedir /historial/estudiante/{id} por esta vía
    (tiene sus propios endpoints en historial_clinico.py).

    OJO: esta función compara directo contra current_user['id'], que es
    Usuario.id (el id que viaja en el JWT). Válida para endpoints cuyo
    parámetro de ruta también es un Usuario.id (ej. estudiante_id).
    Para endpoints cuyo parámetro de ruta es Profesional.id (una PK
    DISTINTA), usar verificar_acceso_profesional en su lugar.
    """
    verificar_rol(current_user, roles_permitidos)

    if current_user["id"] != id_esperado:
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso.")


def verificar_acceso_profesional(current_user: dict, profesional_id: int, db, roles_permitidos: list[str] = None) -> None:
    """
    Igual que verificar_acceso, pero para endpoints cuyo parámetro de ruta
    es Profesional.id (tabla 'profesional'), NO Usuario.id. Resuelve el
    Profesional y compara su usuario_id contra el id del JWT.

    Fase 3.5F: se eliminó el bypass automático para rol 'admin'. El
    ownership es estricto — solo el profesional dueño del recurso pasa
    esta verificación. Acceso administrativo, si corresponde, se resuelve
    con un permiso RBAC explícito en el endpoint (no aquí).

    Corrección de seguridad (checkpoint 2): el default de roles_permitidos
    ya NO incluye "admin". Recursos propios del profesional exigen
    ROLE == "profesional" + ownership. Un usuario ADMIN o SUPERADMIN cuyo
    Usuario.id coincidiera (por error o coincidencia) con el usuario_id de
    un Profesional NO debe pasar esta verificación solo por compartir ese
    id — el rol se exige primero, en defensa en profundidad respecto del
    chequeo de ownership. Ningún llamador real del proyecto dependía del
    "admin" en este default (todos los endpoints administrativos usan
    require_permission / has_permission explícitos, no este helper).
    """
    from app.models.profesional import Profesional

    verificar_rol(current_user, roles_permitidos or ["profesional"])

    prof = db.query(Profesional).filter(Profesional.id == profesional_id).first()
    if not prof or prof.usuario_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso.")
