# -*- coding: utf-8 -*-
"""
SESAES — Migración puntual: índice de consulta del registro de
auditoría de la agenda médica.

Contexto
--------
La tabla `auditoria` (SA-2) ya guarda, para cada evento, el actor
(`usuario_id`, `actor_rol`), la acción, los detalles y el timestamp
exacto (`fecha`, DEFAULT now()). A partir de este cambio, TODA creación,
modificación de estado/prioridad y anulación de una cita genera una fila
con `entidad="cita"` y `entidad_id=<id de la cita>`, por lo que el
historial completo de una cita se consulta con:

    GET /admin/auditoria?entidad=cita&entidad_id=<id>

Para que esa consulta (y la de cualquier otra entidad: profesional,
usuario, documento_clinico, ...) no degrade con el crecimiento del log,
esta migración crea el índice compuesto declarado en
app/models/auditoria.py:

    (entidad, entidad_id, fecha)

Qué hace
--------
  - `CREATE INDEX IF NOT EXISTS ix_auditoria_entidad_entidad_id_fecha`
    sobre `auditoria (entidad, entidad_id, fecha)`.
  - Verifica, DENTRO de la misma transacción/conexión, que el índice
    existe y que sus columnas son exactamente las esperadas (mismo
    patrón que scripts/migrar_auditoria_sa2.py: no se asume éxito solo
    porque el CREATE INDEX no lanzó excepción).
  - Si la validación falla, la excepción se propaga antes de salir del
    `with engine.begin()`, que hace rollback automático: no queda un
    índice "a medias" confirmado con una validación fallida.

Qué NO hace (deliberado)
------------------------
  - No crea ni recrea la tabla `auditoria` (ya existe desde SA-2).
  - No agrega `actor_rol`/`resultado`: eso es
    scripts/migrar_auditoria_sa2.py, que debe estar aplicado antes.
  - No borra, actualiza ni reescribe ninguna fila de auditoría.
  - No usa `DROP INDEX`: es idempotente y se puede correr más de una vez.
  - No se ejecuta automáticamente al levantar FastAPI ni se integra en
    init_db.py: es un script manual de un solo uso.
  - No imprime DATABASE_URL, credenciales ni ningún otro secreto.

Prerrequisito
-------------
    python -m scripts.migrar_auditoria_sa2

Ejecución manual (desde backend/, con el venv activado):

    python -m scripts.migrar_auditoria_agenda
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.database import engine
from app.models.auditoria import Auditoria  # registra la tabla antes de inspeccionarla

NOMBRE_INDICE = "ix_auditoria_entidad_entidad_id_fecha"
COLUMNAS_ESPERADAS = ["entidad", "entidad_id", "fecha"]

_CREATE_INDEX = (
    f"CREATE INDEX IF NOT EXISTS {NOMBRE_INDICE} "
    "ON auditoria (entidad, entidad_id, fecha);"
)


class MigracionIncompletaError(RuntimeError):
    """El índice no quedó con las columnas exactas esperadas."""


def migrar_auditoria_agenda() -> None:
    with engine.begin() as conn:
        columnas_auditoria = {
            c["name"] for c in inspect(conn).get_columns("auditoria")
        }
        requeridas = {"entidad", "entidad_id", "fecha"}
        faltantes = requeridas - columnas_auditoria
        if faltantes:
            raise MigracionIncompletaError(
                "La tabla auditoria no tiene las columnas requeridas: "
                f"{sorted(faltantes)}. Aplica primero "
                "scripts.migrar_auditoria_sa2 (actor_rol/resultado) y "
                "verifica el esquema base."
            )

        conn.execute(text(_CREATE_INDEX))

        # Se inspecciona la MISMA conexión/transacción: si esto no
        # confirma el índice, se hace rollback de todo.
        indices = {
            indice["name"]: indice
            for indice in inspect(conn).get_indexes("auditoria")
        }
        indice = indices.get(NOMBRE_INDICE)
        if indice is None:
            raise MigracionIncompletaError(
                f"El índice {NOMBRE_INDICE} no aparece tras el CREATE INDEX."
            )

        columnas = [c.lower() for c in (indice.get("column_names") or [])]
        if columnas != COLUMNAS_ESPERADAS:
            raise MigracionIncompletaError(
                f"El índice {NOMBRE_INDICE} tiene columnas {columnas!r}; "
                f"se esperaban {COLUMNAS_ESPERADAS!r}."
            )


if __name__ == "__main__":
    migrar_auditoria_agenda()
    print(
        "Migración de auditoría de agenda aplicada: "
        f"índice {NOMBRE_INDICE} verificado."
    )
