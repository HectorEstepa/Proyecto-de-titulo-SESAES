"""
Migración puntual SA-2: agrega las columnas `actor_rol` y `resultado`
a la tabla `auditoria` ya existente.

- Idempotente: usa `IF NOT EXISTS`, se puede correr más de una vez sin error.
- Una única transacción (`engine.begin()`): ambos ALTER TABLE se aplican
  juntos o no se aplica ninguno.
- No usa DROP ni TRUNCATE. No borra ni recrea la tabla. No modifica
  filas existentes (el DEFAULT las completa automáticamente a nivel de
  motor, no vía UPDATE explícito).
- NO se integra en init_db.py ni se ejecuta automáticamente al levantar
  FastAPI: es un script manual, de un solo uso, antes de desplegar el
  código de SA-2 que empieza a escribir en estas columnas.
- No imprime DATABASE_URL, credenciales ni ningún otro secreto.
- No asume éxito solo porque el ALTER no lanzó excepción: inspecciona
  el esquema real DENTRO de la misma transacción/conexión (inspect(conn),
  no inspect(engine) en una conexión nueva) y valida que las columnas no
  solo existan, sino que tengan las propiedades exactas que el contrato
  de auditoria.py necesita:
    * actor_rol -> nullable (compatibilidad histórica con filas viejas)
    * resultado -> NOT NULL
    * resultado -> DEFAULT 'exito'
  Si alguna validación falla, la excepción se propaga antes de salir del
  `with engine.begin()`, que hace rollback automático de los ALTER
  también — no queda un ALTER "a medias" confirmado con una validación
  fallida.

Ejecución manual (desde backend/, con el venv activado):

    python -m scripts.migrar_auditoria_sa2
"""

from sqlalchemy import text, inspect

from app.database import engine

_ALTER_STATEMENTS = (
    "ALTER TABLE auditoria ADD COLUMN IF NOT EXISTS actor_rol VARCHAR NULL;",
    "ALTER TABLE auditoria ADD COLUMN IF NOT EXISTS resultado VARCHAR NOT NULL DEFAULT 'exito';",
)

_COLUMNAS_ESPERADAS = {"actor_rol", "resultado"}


class MigracionIncompletaError(RuntimeError):
    """
    Las sentencias ALTER TABLE se ejecutaron sin lanzar excepción, pero al
    inspeccionar la tabla después no aparecen (todas) las columnas
    esperadas, o alguna de ellas no cumple las propiedades esperadas
    (nullability / NOT NULL / default). No se asume éxito solo porque no
    hubo excepción: se confirma inspeccionando el esquema real.
    """
    pass


def migrar_auditoria_sa2() -> None:
    with engine.begin() as conn:
        for statement in _ALTER_STATEMENTS:
            conn.execute(text(statement))

        # La inspección y TODAS las validaciones críticas ocurren DENTRO
        # de esta misma transacción/conexión (inspect(conn), no
        # inspect(engine)): si algo falla, la excepción se propaga antes
        # de salir del `with`, y engine.begin() hace rollback automático
        # de los ALTER TABLE también. No se asume éxito solo porque el
        # ALTER no lanzó excepción, ni se valida fuera de la transacción.
        inspector = inspect(conn)
        columnas = {c["name"]: c for c in inspector.get_columns("auditoria")}

        faltantes = _COLUMNAS_ESPERADAS - columnas.keys()
        if faltantes:
            raise MigracionIncompletaError(
                "La migración no dejó las columnas esperadas en 'auditoria': "
                f"faltan {sorted(faltantes)}. Revisa el esquema manualmente "
                "antes de continuar."
            )

        actor_rol = columnas["actor_rol"]
        resultado = columnas["resultado"]

        errores = []

        # actor_rol debe seguir siendo nullable (compatibilidad histórica
        # / legacy, ver auditoria_MODELO.py): filas antiguas, creadas antes
        # de SA-2 por los helpers locales ya eliminados, no tienen rol
        # conocido. Los eventos NUEVOS, creados vía
        # registrar_evento_auditoria, SIEMPRE exigen current_user["rol"]
        # (ValueError si falta — ver app/auditoria.py); la columna es
        # nullable solo por el legado, no porque un evento nuevo pueda
        # quedar sin actor_rol. Si esta columna quedó NOT NULL, romperían
        # los inserts legítimos de esas filas legacy.
        if not actor_rol.get("nullable", True):
            errores.append(
                "'actor_rol' quedó NOT NULL; se esperaba nullable=True "
                "(compatibilidad histórica con filas existentes)."
            )

        # resultado debe ser NOT NULL: el contrato de registrar_evento_auditoria
        # nunca deja resultado en blanco, y la columna debe reforzar eso a
        # nivel de esquema, no solo a nivel de aplicación.
        if resultado.get("nullable", True):
            errores.append(
                "'resultado' quedó nullable; se esperaba NOT NULL."
            )

        # resultado debe tener DEFAULT 'exito' a nivel de motor (server_default
        # en el modelo). SQLAlchemy refleja el default como texto crudo del
        # dialecto (p.ej. "'exito'::character varying" en Postgres), por eso
        # se valida por contención en vez de igualdad exacta.
        default_resultado = resultado.get("default") or ""
        if "exito" not in default_resultado:
            errores.append(
                "'resultado' no tiene el DEFAULT 'exito' esperado a nivel de "
                f"motor (valor reflejado: {default_resultado!r})."
            )

        if errores:
            raise MigracionIncompletaError(
                "La migración ejecutó los ALTER TABLE sin error, pero el "
                "esquema resultante no cumple el contrato esperado por "
                "auditoria.py:\n- " + "\n- ".join(errores)
            )
        # Fin del `with`: si llegamos hasta aquí sin excepción, engine.begin()
        # confirma (commit) el ALTER TABLE al salir del bloque.

    # Solo se imprime éxito DESPUÉS de salir del `with` sin excepción, es
    # decir, después de que la transacción ya quedó confirmada.
    print(
        "Migración SA-2 verificada: auditoria.actor_rol (nullable) y "
        "auditoria.resultado (NOT NULL, default 'exito') existen y "
        "cumplen el contrato esperado."
    )


if __name__ == "__main__":
    migrar_auditoria_sa2()
