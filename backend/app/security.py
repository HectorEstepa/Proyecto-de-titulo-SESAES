import bcrypt
import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

_HASH_PREFIXES = ("$2a$", "$2b$", "$2y$")

PASSWORD_POLICY_MESSAGE = (
    "La nueva contraseña debe tener al menos 8 caracteres, "
    "una mayúscula, una minúscula, un número y un carácter especial, "
    "sin espacios."
)


def evaluar_politica_password(password) -> dict[str, bool]:
    """
    Evalúa la política única de contraseñas SESAES.

    Mantener esta función como fuente de verdad del backend. El frontend
    replica estas reglas únicamente para dar feedback inmediato; el backend
    siempre vuelve a validarlas antes de persistir un cambio.
    """
    value = password if isinstance(password, str) else ""
    checks = {
        "minimo8": len(value) >= 8,
        "mayuscula": any(c.isupper() for c in value),
        "minuscula": any(c.islower() for c in value),
        "numero": any(c.isdigit() for c in value),
        "especial": any((not c.isalnum()) and (not c.isspace()) for c in value),
        "sin_espacios": not any(c.isspace() for c in value),
    }
    return checks


def password_cumple_politica(password) -> bool:
    """True solo cuando la contraseña cumple todas las reglas SESAES."""
    return all(evaluar_politica_password(password).values())

# ══════════════════════════════════════════════════════════
# JWT
# ══════════════════════════════════════════════════════════
# La clave se lee desde la variable de entorno JWT_SECRET_KEY.
# En producción (Render) esta variable DEBE estar configurada con un
# valor largo y aleatorio propio; el valor por defecto de acá abajo
# solo existe para que el proyecto no truene en desarrollo local si
# alguien olvidó definirla, y nunca debe usarse en producción.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-inseguro-cambiar-en-produccion")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))  # 12 horas


def create_access_token(data: dict) -> str:
    """
    Genera un JWT firmado con los datos mínimos necesarios para identificar
    al usuario en cada petición (id, rol, correo). No incluir datos sensibles
    acá: el payload de un JWT es legible por cualquiera (no está cifrado,
    solo firmado), solo garantiza que no fue alterado.
    """
    to_encode = data.copy()
    expira = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expira})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Valida la firma y expiración del token y devuelve su payload.
    Lanza jose.JWTError si el token es inválido, fue alterado, o expiró.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def hash_password(password: str) -> str:
    """Genera el hash bcrypt de una contraseña en texto plano."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def is_legacy_plaintext(stored_password: str) -> bool:
    """
    True si la contraseña guardada todavía es texto plano (usuarios creados
    antes de esta migración a bcrypt), False si ya es un hash bcrypt.
    """
    return not (stored_password and stored_password.startswith(_HASH_PREFIXES))


def verify_password(plain_password: str, stored_password: str) -> bool:
    """
    Verifica una contraseña contra lo guardado en la base de datos.
    Soporta tanto hashes bcrypt (usuarios ya migrados) como texto plano
    (usuarios antiguos, hasta que inicien sesión y se migren automáticamente).
    """
    if not stored_password or not plain_password:
        return False
    if is_legacy_plaintext(stored_password):
        return stored_password == plain_password
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), stored_password.encode("utf-8"))
    except ValueError:
        return False
