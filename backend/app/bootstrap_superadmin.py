"""
SESAES — Fase SA-1: bootstrap controlado del PRIMER SUPERADMIN.

Mecanismo local/CLI, deliberadamente SEPARADO del API HTTP y de
init_db()/SEED_DEMO_DATA (SA-0). Se ejecuta explícitamente por una
persona con acceso al servidor/proyecto, nunca automáticamente:

    cd backend
    python -m app.bootstrap_superadmin

NO se llama desde main.py, NO se llama desde el evento de startup, y
NO se integra con el seed demo de SA-0 (no usa ni depende de
SEED_DEMO_DATA / SEED_DEMO_PASSWORD).

Esquema de BD: este script asume que las tablas ya existen (mismo
patrón que el resto del proyecto: Base.metadata.create_all() vive en
init_db() / arranque normal de la app). El bootstrap NO llama
create_all() para no volver a acoplar seed/init y bootstrap — si las
tablas no existen todavía, la consulta de abajo fallará con un error
claro de SQLAlchemy en vez de crear tablas por un camino separado.

Reglas de negocio (ver diagnóstico SA-1):
  - Solo puede crear el PRIMER superadmin. Si ya existe cualquier
    Usuario con rol == "superadmin" (activo=True o activo=False), el
    bootstrap aborta sin modificar nada. La creación de SUPERADMIN
    adicionales queda para una fase posterior (gobernanza / roles.gestionar).
  - Tener ADMIN existentes no impide crear el primer SUPERADMIN, pero el
    bootstrap NUNCA promueve un ADMIN existente ni cambia el rol de
    ninguna cuenta ya existente.
  - Validaciones y consultas de solo lectura ANTES de db.add(); un único
    db.add() seguido de un único db.commit(); si ese commit falla, se
    hace db.rollback() y se propaga el error (ver más abajo). Después de
    un commit exitoso NO se ejecuta ninguna operación de base de datos
    (ni un segundo commit, ni refresh(), ni una consulta) para poder
    considerar exitoso el bootstrap: si tal operación fallara, un commit
    ya exitoso terminaría reportándose como fallo, y un rollback() en ese
    punto no podría deshacer un commit que ya ocurrió.
  - Correo y contraseña vienen de configuración externa explícita
    (SUPERADMIN_BOOTSTRAP_EMAIL / SUPERADMIN_BOOTSTRAP_PASSWORD). Nunca
    hay un valor hardcodeado ni un fallback conocido (ni "admin@utem.cl",
    ni "admin123", ni contraseñas generadas e impresas sin control).
  - La contraseña se hashea con hash_password() (mismo módulo que ya usa
    el resto del proyecto — no se introduce una segunda implementación
    de hashing) antes de persistirse. Nunca se imprime ni se incluye en
    excepciones/logs.
  - Si el correo ya pertenece a otro Usuario (de cualquier rol), el
    bootstrap aborta sin modificar esa cuenta.
  - Operación atómica: la existencia previa de un SUPERADMIN se consulta
    ANTES de leer cualquier variable de configuración de bootstrap (así
    el bootstrap queda cerrado sin exigir SUPERADMIN_BOOTSTRAP_EMAIL/
    _PASSWORD una vez que ya existe un superadmin). Si no existe
    ninguno, TODA la configuración se valida antes de agregar el
    Usuario a la sesión; un solo commit; rollback si ese commit falla,
    sin dejar una cuenta parcialmente creada. Ese rollback deshace un
    commit que falló, nunca uno que ya tuvo éxito: por eso, después de
    un commit exitoso, no se ejecuta ninguna operación de base de datos.

Riesgo residual de concurrencia (documentado, NO resuelto en SA-1):
  Usuario.rol es un String libre sin constraint de unicidad a nivel de
  BD para "como máximo un superadmin". La secuencia
  "SELECT ¿existe superadmin? -> INSERT" NO es atómica frente a dos
  ejecuciones de este script lanzadas casi simultáneamente: en una
  carrera muy ajustada, ambas podrían leer "no existe superadmin" antes
  de que la otra haga commit, y terminar creando dos superadmins. Se
  documenta deliberadamente en vez de "resolverse" con una migración o
  constraint de BD, porque a futuro existirán múltiples SUPERADMIN
  legítimos y un constraint de unicidad los rompería. Mitigación
  operacional sugerida (fuera de alcance de SA-1): ejecutar el bootstrap
  una sola vez, de forma controlada, no en paralelo.

Auditoría (SA-1, alcance mínimo): el bootstrap ocurre antes de que
exista necesariamente ningún actor autenticado, así que deliberadamente
NO escribe en la tabla de auditoría institucional (evitar inventar un
usuario_id / actor humano falso). La creación queda documentada acá y
en el mensaje de salida de la CLI. La auditoría de gobernanza
autenticada (quién ejecutó el bootstrap, desde dónde) se resolverá
antes de SA-2/SA-3.
"""

import os
import re
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.usuario import Usuario
from app.rbac.roles import Role
from app.security import hash_password

# Mismo patrón de formato de correo que ya usa el proyecto hoy (ver
# schemas.py: EstudianteUpdate.validar_correo_secundario) — es el único
# chequeo de formato de correo reutilizable que existe actualmente.
# NO se agrega una regla de dominio institucional (p. ej. "@utem.cl")
# porque, revisando el código existente, no hay ninguna regla real de
# ese tipo implementada en ningún lugar del proyecto para reutilizar;
# inventar una acá sería una segunda política no solicitada.
_EMAIL_FORMATO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _password_cumple_politica_existente(password: str) -> bool:
    """
    Misma política de fortaleza que ya aplica hoy el proyecto al cambiar
    contraseñas (ver routers/estudiante.py, PATCH .../cambiar-password):
    mínimo 8 caracteres, mayúscula, minúscula, dígito, carácter especial,
    sin espacios. Se reutiliza tal cual para no introducir una segunda
    política incompatible con la que ya conocen las cuentas existentes.
    """
    return (
        len(password) >= 8
        and any(c.isupper() for c in password)
        and any(c.islower() for c in password)
        and any(c.isdigit() for c in password)
        and any((not c.isalnum()) and (not c.isspace()) for c in password)
        and not any(c.isspace() for c in password)
    )


class BootstrapError(RuntimeError):
    """
    Config inválida, ya existe un SUPERADMIN, o el correo ya pertenece a
    otro Usuario. En todos estos casos el bootstrap no modifica nada.
    """
    pass


def _obtener_config() -> tuple[str, str, "str | None"]:
    """
    Lee y valida SUPERADMIN_BOOTSTRAP_EMAIL / _PASSWORD / _NAME. Lanza
    BootstrapError con un mensaje claro (sin revelar el valor de ningún
    secreto) si algo falta o no es válido. No toca la BD.
    """
    correo = os.getenv("SUPERADMIN_BOOTSTRAP_EMAIL")
    if not correo or not correo.strip():
        raise BootstrapError(
            "Falta la variable de entorno SUPERADMIN_BOOTSTRAP_EMAIL."
        )
    correo = correo.strip().lower()
    if not _EMAIL_FORMATO.match(correo):
        raise BootstrapError(
            "SUPERADMIN_BOOTSTRAP_EMAIL no tiene un formato de correo válido."
        )

    password = os.getenv("SUPERADMIN_BOOTSTRAP_PASSWORD")
    if not password or not password.strip():
        raise BootstrapError(
            "Falta la variable de entorno SUPERADMIN_BOOTSTRAP_PASSWORD."
        )
    if not _password_cumple_politica_existente(password):
        raise BootstrapError(
            "SUPERADMIN_BOOTSTRAP_PASSWORD no cumple la política de "
            "seguridad requerida (mínimo 8 caracteres, con mayúscula, "
            "minúscula, número y carácter especial, sin espacios)."
        )

    nombre = os.getenv("SUPERADMIN_BOOTSTRAP_NAME")
    if nombre is not None:
        nombre = nombre.strip() or None

    return correo, password, nombre


def bootstrap_superadmin() -> Usuario:
    """
    Ejecuta el bootstrap del primer SUPERADMIN.

    Devuelve el Usuario creado si tuvo éxito.
    Lanza BootstrapError si ya existe un SUPERADMIN, si la config es
    inválida, o si el correo ya está en uso — en ninguno de esos casos
    se modifica la base de datos.
    Lanza SQLAlchemyError (haciendo rollback antes) si falla el commit.
    """
    db = SessionLocal()
    # expire_on_commit=False es una configuración de la sesión en memoria,
    # NO una operación de base de datos: no ejecuta ninguna sentencia SQL.
    # Se fija ANTES del commit para que, después de un commit exitoso,
    # SQLAlchemy no marque los atributos de `nuevo` como "expirados"
    # (comportamiento por defecto de la sesión, ver app/database.py).
    # Sin esto, leer nuevo.correo/rol/etc. después de db.close() (en el
    # `finally` de abajo) dispararía un intento de recarga desde BD sobre
    # una sesión ya cerrada (DetachedInstanceError) — o, si la sesión
    # siguiera abierta, sería exactamente la operación posterior al
    # commit que este cambio busca eliminar. Como todos los valores que
    # el llamador necesita (correo, rol, nombre, activo, ...) ya fueron
    # asignados en Python antes de db.add()/db.commit(), no hace falta
    # ningún dato generado por BD para devolver `nuevo` utilizable.
    db.expire_on_commit = False
    try:
        # 1. Regla fundamental, ANTES de leer ninguna variable de config:
        #    solo puede existir un PRIMER superadmin. Cuenta también los
        #    inactivos: un superadmin institucional desactivado sigue
        #    "existiendo" a estos efectos. Esto deja el bootstrap
        #    efectivamente cerrado después de crear el primero, incluso
        #    si SUPERADMIN_BOOTSTRAP_EMAIL / _PASSWORD ya no están en el
        #    entorno (no se exigen ni se leen en este caso).
        ya_existe_superadmin = (
            db.query(Usuario).filter(Usuario.rol == Role.SUPERADMIN.value).first()
        )
        if ya_existe_superadmin is not None:
            raise BootstrapError(
                "El bootstrap no está disponible porque ya existe un "
                "SUPERADMIN en el sistema."
            )

        # 2. Solo si no existe ningún SUPERADMIN: leer y validar TODA la
        #    configuración externa, ANTES de tocar la sesión con db.add().
        correo, password, nombre = _obtener_config()

        # 3. No promover ni pisar una cuenta existente.
        correo_en_uso = db.query(Usuario).filter(Usuario.correo == correo).first()
        if correo_en_uso is not None:
            raise BootstrapError(
                "Ya existe un Usuario con ese correo. El bootstrap no "
                "modifica cuentas existentes."
            )

        nuevo = Usuario(
            correo=correo,
            password=hash_password(password),
            rol=Role.SUPERADMIN.value,
            nombre=nombre,
            activo=True,
            # debe_cambiar_password: el único flujo que hoy resuelve esta
            # bandera es PATCH /estudiante/{id}/primer-acceso, restringido
            # a rol == "estudiante" (ver routers/estudiante.py). login()
            # tampoco la consulta ni la devuelve. Activarla en True para
            # un SUPERADMIN la dejaría permanentemente sin forma de
            # resolverse por ningún flujo existente — no bloquearía el
            # login hoy, pero sería un estado inconsistente y sin salida.
            # Se deja en False: comportamiento seguro y compatible con el
            # código actual. Documentado para que una fase posterior
            # decida si construye un flujo de "primer acceso" también
            # para roles administrativos.
            debe_cambiar_password=False,
        )
        db.add(nuevo)
        db.commit()
        return nuevo
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    try:
        bootstrap_superadmin()
    except BootstrapError as exc:
        print(f"El bootstrap no se ejecutó: {exc}")
        return 1
    except SQLAlchemyError:
        print("El bootstrap no se ejecutó: error de base de datos.")
        return 1

    print("SUPERADMIN inicial creado correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
