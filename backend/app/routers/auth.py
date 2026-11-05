from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.usuario import Usuario
from app.security import verify_password, hash_password, is_legacy_plaintext, create_access_token
from app.rate_limiter import limiter

router = APIRouter()


class LoginRequest(BaseModel):
    correo: str
    password: str


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.correo == data.correo).first()

    # Mismo mensaje genérico tanto si el correo no existe como si la
    # contraseña es incorrecta. Devolver mensajes distintos permite a
    # cualquiera comprobar qué correos están registrados en el sistema
    # (enumeración de usuarios) con solo probar login.
    credenciales_invalidas = HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")

    if not user or not verify_password(data.password, user.password):
        raise credenciales_invalidas

    # Migración transparente: si la contraseña seguía en texto plano
    # (usuarios creados antes de esta actualización), se re-hashea ahora
    # que sabemos que el usuario la escribió correctamente.
    if is_legacy_plaintext(user.password):
        user.password = hash_password(data.password)
        db.commit()

    if user.activo is False:
        raise HTTPException(status_code=403, detail="Esta cuenta ha sido desactivada. Contacta al administrador.")

    token = create_access_token({
        "id":     user.id,
        "rol":    user.rol,
        "correo": user.correo,
    })

    return {
        "message": "Login correcto",
        "access_token": token,
        "token_type": "bearer",
        "rol":     user.rol,
        "id":      user.id,
        "nombre":  user.nombre,
        "foto_url": user.foto_url,
        "correo":  user.correo
    }
