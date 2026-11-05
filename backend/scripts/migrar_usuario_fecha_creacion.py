# -*- coding: utf-8 -*-
"""
SESAES — Migración puntual: agrega `usuario.fecha_creacion` (Inicio de
SUPERADMIN, bloque "Últimos usuarios registrados").

Sigue el mismo patrón que backend/scripts/migrar_a4_1_trazabilidad.py
para `cita.fecha_creacion` (ALTER TABLE ... IF NOT EXISTS dentro de una
sola transacción, verificado con inspect(conn) antes de confirmar).

── Por qué NO lleva DEFAULT en el ADD COLUMN ──

Si el ALTER TABLE que agrega la columna incluyera `DEFAULT now()`,
PostgreSQL rellenaría TODAS las filas existentes con el instante en que
se corrió la migración, y cada usuario histórico pasaría a "registrarse"
ese día. Eso sería un dato inventado. Por eso se hace en dos pasos:

  1. `ADD COLUMN fecha_creacion TIMESTAMP NULL` (sin DEFAULT): las
     cuentas existentes quedan en NULL, es decir, "fecha desconocida".
  2. `ALTER COLUMN fecha_creacion SET DEFAULT now()`: a partir de acá,
     toda cuenta NUEVA nace con su fecha real de registro.

La UI muestra "—" para las cuentas con NULL. Esta migración NO ejecuta
ningún UPDATE ni backfill.

── Despliegue ──

Es un script manual, de un solo uso, e idempotente. Debe ejecutarse
ANTES de desplegar el código que declara `Usuario.fecha_creacion` en el
modelo: con la columna ausente en la base, cualquier SELECT sobre
`usuario` (incluido el login) fallaría.

No se integra en init_db.py ni corre al levantar FastAPI. No usa DROP ni
TRUNCATE, no recrea la tabla y no imprime DATABASE_URL ni credenciales.

Ejecución manual (desde backend/, con el venv activado):

    python -m scripts.migrar_usuario_fecha_creacion
"""

from sqlalchemy import inspect, text

from app.database import engine

_ADD_COLUMNA = (
    "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS fecha_creacion TIMESTAMP NULL;"
)
_SET_DEFAULT = (
    "ALTER TABLE usuario ALTER COLUMN fecha_creacion SET DEFAULT now();"
)


class MigracionIncompletaError(RuntimeError):
    """
    Los ALTER TABLE no lanzaron excepción, pero el esquema resultante no
    cumple el contrato esperado. No se asume éxito por ausencia de error:
    se confirma inspeccionando el esquema real dentro de la transacción.
    """


def _validar_esquema(conn) -> None:
    columnas = {c["name"]: c for c in inspect(conn).get_columns("usuario")}

    if "fecha_creacion" not in columnas:
        raise MigracionIncompletaError(
            "La migración no dejó la columna 'usuario.fecha_creacion'. "
            "Revisa el esquema manualmente antes de continuar."
        )

    columna = columnas["fecha_creacion"]
    errores = []

    # Debe seguir siendo nullable: las cuentas históricas no tienen fecha
    # real de registro y NO se les asigna una inventada.
    if not columna.get("nullable", True):
        errores.append(
            "'usuario.fecha_creacion' quedó NOT NULL; se esperaba "
            "nullable=True (compatibilidad histórica)."
        )

    # Las filas nuevas deben nacer con la fecha real (DEFAULT a nivel de
    # motor). SQLAlchemy refleja el default como texto crudo del dialecto,
    # por eso se valida por contención.
    default = (columna.get("default") or "").lower()
    if "now" not in default and "current_timestamp" not in default:
        errores.append(
            "'usuario.fecha_creacion' no tiene el DEFAULT now() esperado "
            f"para filas nuevas (reflejado: {columna.get('default')!r})."
        )

    if errores:
        raise MigracionIncompletaError(
            "La migración ejecutó los ALTER TABLE sin error, pero el "
            "esquema resultante no cumple el contrato esperado:\n- "
            + "\n- ".join(errores)
        )


def migrar_usuario_fecha_creacion(bind=None, emitir_mensaje: bool = True) -> None:
    """
    `bind` permite apuntar la migración a otro engine (tests contra un
    Postgres desechable); por defecto usa el engine de la aplicación.
    """
    destino = bind if bind is not None else engine

    with destino.begin() as conn:
        conn.execute(text(_ADD_COLUMNA))
        conn.execute(text(_SET_DEFAULT))
        # Si la validación falla, la excepción sale del `with` y
        # engine.begin() revierte ambos ALTER TABLE.
        _validar_esquema(conn)

    if emitir_mensaje:
        print(
            "Migración verificada: usuario.fecha_creacion existe (nullable, "
            "DEFAULT now() para filas nuevas). Las cuentas anteriores "
            "quedaron en NULL a propósito: no se les asignó ninguna fecha "
            "inventada."
        )


if __name__ == "__main__":
    migrar_usuario_fecha_creacion()
