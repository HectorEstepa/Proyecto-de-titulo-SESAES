from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.configuracion_centro import ConfiguracionCentro
from app.models.usuario import Usuario
from app.schemas import ConfiguracionCentroOut, ConfiguracionCentroUpdate
from app.security import verify_password, hash_password
from app.auth_dependencies import get_current_user, verificar_rol
from app.rbac.permissions import Permission, has_permission


router = APIRouter(
    prefix="/configuracion-centro",
    tags=["configuracion-centro"],
)


CAMPOS_CONFIGURACION_GLOBAL = frozenset({
    "nombre_centro",
    "direccion",
    "telefono",
    "correo_contacto",
    "horario_atencion",
})

# Compatibilidad temporal:
# Mi Perfil administrativo todavía usa el singleton ConfiguracionCentro
# para nombre/foto. Más adelante debe desacoplarse hacia Usuario.
CAMPOS_PERFIL_ADMIN_COMPAT = frozenset({
    "nombre_admin",
    "foto_admin_url",
})


def _autorizar_actualizacion_configuracion(
    datos: ConfiguracionCentroUpdate,
    current_user: dict,
) -> None:
    campos = set(datos.model_fields_set)

    if campos & CAMPOS_CONFIGURACION_GLOBAL:
        if not has_permission(
            current_user,
            Permission.CONFIGURACION_GESTIONAR,
        ):
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para modificar la configuración global.",
            )

    if campos & CAMPOS_PERFIL_ADMIN_COMPAT:
        verificar_rol(
            current_user,
            roles_permitidos=["admin", "superadmin"],
        )


@router.get("", response_model=ConfiguracionCentroOut)
def get_configuracion_centro(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Información institucional visible para cualquier usuario autenticado.
    config = db.query(ConfiguracionCentro).first()

    if not config:
        config = ConfiguracionCentro()
        db.add(config)
        db.commit()
        db.refresh(config)

    return config


@router.patch("", response_model=ConfiguracionCentroOut)
def actualizar_configuracion_centro(
    datos: ConfiguracionCentroUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _autorizar_actualizacion_configuracion(datos, current_user)

    config = db.query(ConfiguracionCentro).first()

    if not config:
        config = ConfiguracionCentro()
        db.add(config)
        db.commit()
        db.refresh(config)

    if datos.nombre_centro is not None:
        config.nombre_centro = datos.nombre_centro

    if datos.direccion is not None:
        config.direccion = datos.direccion

    if datos.telefono is not None:
        config.telefono = datos.telefono

    if datos.correo_contacto is not None:
        config.correo_contacto = datos.correo_contacto

    if datos.horario_atencion is not None:
        config.horario_atencion = datos.horario_atencion

    if datos.foto_admin_url is not None:
        config.foto_admin_url = datos.foto_admin_url

    if datos.nombre_admin is not None:
        config.nombre_admin = datos.nombre_admin

    db.commit()
    db.refresh(config)

    return config


@router.patch("/cambiar-password")
def cambiar_password_admin(
    body: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    ADMIN y SUPERADMIN pueden cambiar exclusivamente la contraseña de
    SU propia cuenta autenticada.
    """
    verificar_rol(
        current_user,
        roles_permitidos=["admin", "superadmin"],
    )

    contrasena_actual = body.get("contrasena_actual")
    contrasena_nueva = body.get("contrasena_nueva")

    if not contrasena_actual or not contrasena_nueva:
        raise HTTPException(
            status_code=400,
            detail="Debes ingresar la contraseña actual y la nueva",
        )

    usuario = (
        db.query(Usuario)
        .filter(Usuario.id == current_user["id"])
        .first()
    )

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Usuario administrativo no encontrado",
        )

    if not verify_password(contrasena_actual, usuario.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña actual es incorrecta",
        )

    usuario.password = hash_password(contrasena_nueva)
    db.commit()

    return {"message": "Contraseña actualizada correctamente"}
