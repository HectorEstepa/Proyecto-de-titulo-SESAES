from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.usuario import Usuario
from app.schemas import EstudianteOut, EstudianteUpdate
from app.security import (
    PASSWORD_POLICY_MESSAGE,
    hash_password,
    password_cumple_politica,
    verify_password,
)
from app.routers.correos import simular_envio_correo
from app.auth_dependencies import get_current_user, verificar_acceso

router = APIRouter(prefix="/estudiante", tags=["Estudiante"])

# Fase 3.5F: se eliminó "admin" de roles_permitidos en los endpoints de
# recursos propios del estudiante (perfil, actualización de datos,
# primer acceso). verificar_acceso ya exige ownership estricto
# (current_user["id"] == estudiante_id), por lo que un ADMIN/SUPERADMIN
# solo podía "colarse" si su propio Usuario.id coincidía por accidente
# con el estudiante_id solicitado. Se retira igualmente el rol del
# default por defensa en profundidad, en línea con el mismo criterio ya
# aplicado en verificar_acceso_profesional: acceso administrativo a un
# recurso concreto se resuelve con un permiso RBAC explícito en un
# endpoint dedicado, nunca como atajo de rol dentro de este helper de
# ownership.


class PrimerAccesoIn(BaseModel):
    nueva_password: Optional[str] = None   # None o vacío = "mantener la actual"


class CambiarPasswordIn(BaseModel):
    contrasena_actual: str
    contrasena_nueva: str


@router.get("/{estudiante_id}", response_model=EstudianteOut)
def obtener_estudiante(
    estudiante_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    verificar_acceso(current_user, id_esperado=estudiante_id, roles_permitidos=["estudiante"])
    usuario = db.query(Usuario).filter(
        Usuario.id == estudiante_id,
        Usuario.rol == "estudiante"
    ).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return usuario


@router.patch("/{estudiante_id}", response_model=EstudianteOut)
def actualizar_estudiante(
    estudiante_id: int,
    datos: EstudianteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    verificar_acceso(current_user, id_esperado=estudiante_id, roles_permitidos=["estudiante"])
    usuario = db.query(Usuario).filter(
        Usuario.id == estudiante_id,
        Usuario.rol == "estudiante"
    ).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    if datos.nombre is not None:
        usuario.nombre = datos.nombre
    if datos.telefono is not None:
        usuario.telefono = datos.telefono
    if datos.correo_secundario is not None:
        usuario.correo_secundario = datos.correo_secundario or None
    if datos.foto_url is not None:
        usuario.foto_url = datos.foto_url
    if datos.tema_oscuro is not None:
        usuario.tema_oscuro = datos.tema_oscuro

    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/{estudiante_id}/cambiar-password")
def cambiar_password_estudiante(
    estudiante_id: int,
    datos: CambiarPasswordIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    verificar_acceso(
        current_user,
        id_esperado=estudiante_id,
        roles_permitidos=["estudiante"],
    )

    usuario = db.query(Usuario).filter(
        Usuario.id == estudiante_id,
        Usuario.rol == "estudiante"
    ).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    if not datos.contrasena_actual or not datos.contrasena_nueva:
        raise HTTPException(
            status_code=400,
            detail="Debes ingresar la contraseña actual y la nueva."
        )
    nueva = datos.contrasena_nueva
    if not password_cumple_politica(nueva):
        raise HTTPException(
            status_code=400,
            detail=PASSWORD_POLICY_MESSAGE,
        )
    if not verify_password(datos.contrasena_actual, usuario.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña actual es incorrecta."
        )
    if verify_password(datos.contrasena_nueva, usuario.password):
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña debe ser diferente a la actual."
        )

    usuario.password = hash_password(datos.contrasena_nueva)
    usuario.debe_cambiar_password = False

    # Aviso de seguridad: nunca se incluye la contraseña en el correo.
    simular_envio_correo(
        db=db,
        destinatario=usuario.correo,
        asunto="SESAES - Tu contraseña fue actualizada",
        cuerpo=(
            f"Hola {usuario.nombre or 'estudiante'},\n\n"
            "Te informamos que la contraseña de tu cuenta SESAES fue cambiada correctamente.\n\n"
            "Si realizaste este cambio, no necesitas hacer nada. "
            "Si no fuiste tú, comunícate de inmediato con SESAES.\n\n"
            "Por seguridad, este correo nunca incluye tu contraseña."
        ),
        tipo="seguridad",
        referencia_id=usuario.id,
    )

    db.commit()
    return {"message": "Contraseña actualizada correctamente."}


@router.patch("/{estudiante_id}/primer-acceso")
def resolver_primer_acceso(
    estudiante_id: int,
    datos: PrimerAccesoIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Se llama justo después del primer login de una cuenta creada con
    contraseña temporal (ej. carga masiva por CSV). El estudiante puede
    elegir una contraseña nueva (nueva_password con algo escrito) o
    simplemente mantener la temporal (nueva_password vacío/None) — en
    ambos casos, deja de pedírsele esto en logins futuros.
    """
    verificar_acceso(current_user, id_esperado=estudiante_id, roles_permitidos=["estudiante"])
    usuario = db.query(Usuario).filter(Usuario.id == estudiante_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not usuario.debe_cambiar_password:
        raise HTTPException(
            status_code=400,
            detail="El primer acceso de esta cuenta ya fue resuelto."
        )
    if datos.nueva_password and datos.nueva_password.strip():
        if not password_cumple_politica(datos.nueva_password):
            raise HTTPException(
                status_code=400,
                detail=PASSWORD_POLICY_MESSAGE,
            )
        usuario.password = hash_password(datos.nueva_password)

    usuario.debe_cambiar_password = False
    db.commit()
    return {"message": "Listo, ya puedes usar el sistema con normalidad."}