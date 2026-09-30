# -*- coding: utf-8 -*-
"""
SESAES — Migración puntual A.4.4.1: sanea de forma controlada e
idempotente un índice único legacy sobre `cita` incompatible con
A.4.4.

── Contexto ──

A.4.4 autoriza explícitamente un segundo cupo "pendiente" sobre el
MISMO (profesional_id, fecha, hora) cuando el actor ejerce un
sobrecupo intencional válido (agenda.gestionar + agenda.sobrecupo +
motivo humano + conflicto overridable + ningún bloqueo absoluto — ver
app.services.sobrecupo_policy_service y
CAPACIDAD_MAXIMA_CITAS_SIMULTANEAS en
app.services.agenda_disponibilidad_service). El modelo vigente
(app/models/cita.py) NO declara ningún UniqueConstraint/Index único
sobre esas tres columnas — la protección real contra doble reserva es
pg_advisory_xact_lock() + re-evaluación de disponibilidad DENTRO del
lock, nunca una constraint de esquema (ver docstring de
CAPACIDAD_MAXIMA_CITAS_SIMULTANEAS: modelar el máximo 2 con un
UniqueConstraint simple es exactamente el error que A.4.4 evita).

Sin embargo, una base PostgreSQL desplegada puede conservar
físicamente el índice parcial:

    CREATE UNIQUE INDEX ux_cita_profesional_fecha_hora_pendiente
    ON public.cita
    USING btree (profesional_id, fecha, hora)
    WHERE ((estado)::text = 'pendiente'::text)

que el modelo actual ya no declara. Cuando eso ocurre, A.4.4 autoriza
correctamente el segundo cupo, el router intenta el INSERT, y
PostgreSQL lo rechaza con IntegrityError — que
app.routers.citas.crear_cita() traduce en un 409 genérico ("Esa hora
acaba de ser reservada por otra persona"), indistinguible en el
cliente del 409 legítimo de A.3 (dos requests normales compitiendo por
el mismo slot). El síntoma es un sobrecupo válido rechazado sin
ninguna razón de negocio.

git log --all -S/-G sobre el nombre exacto de este índice no encontró
ningún commit que lo cree — no se afirma aquí quién ni cuándo lo
introdujo (posiblemente una migración manual anterior a A.3/A.4.x, o
un ajuste directo sobre una base concreta, fuera del historial
disponible). Lo único que se afirma, y que esta migración verifica
activamente en cada corrida:

  - existe físicamente en algunas bases;
  - el modelo SQLAlchemy vigente no lo declara (ver
    test_a4_4_1_migracion_indice_legacy.py, caso
    test_modelo_cita_no_declara_unicidad_incompatible_slot);
  - contradice A.4.4.

── Qué hace esta migración ──

  1. Rechaza explícitamente cualquier dialecto que no sea PostgreSQL
     (mismo criterio que migrar_a4_1_trazabilidad.py /
     migrar_a4_3_permiso_sobrecupo.py — no finge éxito sobre un motor
     donde ni siquiera aplica).
  2. Busca, en el catálogo real de PostgreSQL (pg_indexes, sin filtrar
     por schema/tabla) un índice llamado
     'ux_cita_profesional_fecha_hora_pendiente'. Si no existe en
     ninguna parte: no-op, exit 0 — "esquema ya compatible".
  3. Si existe pero vive en un schema/tabla distinto de
     public.cita: FAIL CLOSED. Un nombre así de específico en un
     lugar inesperado es una anomalía que merece revisión manual, no
     una corrección automática silenciosa — nunca se asume que "no es
     el nuestro, así que no hacemos nada".
  4. Si vive en public.cita: se inspecciona su definición REAL
     (unicidad, columnas exactas y predicado parcial, vía
     inspect(conn) de SQLAlchemy) y se compara contra la huella
     conocida del índice legacy. La comparación del predicado tolera
     diferencias normales de representación de PostgreSQL (casts
     ::text, espacios, paréntesis) — nunca compara el `indexdef`
     completo como string literal exacto.
  5. Si la huella NO coincide exactamente (no es unique, columnas
     distintas, o predicado distinto): FAIL CLOSED. No se ejecuta
     ningún DROP — se levanta una excepción con un mensaje explícito
     de qué no coincidió, para revisión manual.
  6. Si coincide exactamente: DROP INDEX (quoting seguro de
     identificadores) del índice, dentro de la MISMA transacción, y
     se verifica inmediatamente después que el catálogo ya no lo
     reporta — no se asume éxito solo porque el DROP no lanzó
     excepción.
  7. Idempotente: una segunda corrida no encuentra el índice (ya fue
     eliminado) y termina en el paso 2, no-op.

── Qué NO hace (deliberado) ──

  - NO crea ningún índice/constraint de reemplazo. NO
    UNIQUE(profesional_id, fecha, hora). NO UNIQUE WHERE
    estado='pendiente'. Modelar la capacidad máxima (2) con una
    constraint de esquema simple es exactamente el error que esta
    migración corrige, no algo que deba reintroducir de otra forma.
  - NO toca ninguna fila de `cita` — es una migración puramente de
    esquema (una eliminación de índice no borra ni modifica datos).
  - NO asume que el índice, de existir, es seguro de eliminar por
    nombre — su identidad completa se valida antes de cualquier DROP.

Ejecución manual (desde backend/, con el venv activado):

    python -m scripts.migrar_a4_4_1_eliminar_indice_unico_slot

Repetible: correrlo dos veces seguidas contra la misma base no debe
fallar (ver test_a4_4_1_migracion_indice_legacy.py, que exige
TEST_POSTGRES_URL y se salta explícitamente si no está definida —
nunca se simula esta garantía contra SQLite).
"""

from __future__ import annotations

import re

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database import engine
from app.models.cita import Cita  # noqa: F401 — registra 'cita'


class MigracionA441RevisionManualError(RuntimeError):
    """
    Se encontró un índice cuyo nombre coincide con el índice legacy
    conocido, pero su identidad real (tabla/schema, unicidad, columnas
    o predicado) NO coincide exactamente con la huella esperada. Por
    diseño, esto NUNCA dispara un DROP automático — el fail-closed es
    intencional: es preferible detener la migración y pedir revisión
    manual que arriesgarse a eliminar un índice distinto del que
    A.4.4.1 sabe, con certeza, que es seguro de retirar.
    """


class MigracionA441IncompletaError(RuntimeError):
    """
    El DROP INDEX se ejecutó sin lanzar excepción, pero el catálogo de
    PostgreSQL, inspeccionado de nuevo dentro de la MISMA transacción,
    todavía reporta el índice legacy. No se asume éxito solo porque no
    hubo excepción.
    """


_ESQUEMA = "public"
_TABLA = "cita"
_NOMBRE_INDICE = "ux_cita_profesional_fecha_hora_pendiente"

# Huella EXACTA del índice legacy incompatible con A.4.4 — ver
# docstring del módulo. El orden de columnas importa: es el orden
# físico real del btree (profesional_id, fecha, hora), no un conjunto.
_COLUMNAS_LEGACY = ("profesional_id", "fecha", "hora")

# Predicado parcial esperado, en su forma "canónica" antes de
# normalizar — ver _normalizar_predicado(). La base real puede
# reportarlo con casts/paréntesis distintos
# (p. ej. "((estado)::text = 'pendiente'::text)"); ambos lados de la
# comparación pasan por la misma normalización, así que la forma
# exacta en que se escriba acá no importa mientras sea equivalente.
_PREDICADO_LEGACY_CRUDO = "estado = 'pendiente'"


def _normalizar_predicado(predicado: str | None) -> str:
    """
    Normaliza un predicado parcial de PostgreSQL para compararlo por
    EQUIVALENCIA, no por igualdad literal de string — tolera las
    diferencias de representación que el propio catálogo de Postgres
    introduce de forma rutinaria (casts explícitos tipo ::text,
    espacios, paréntesis de agrupación, comillas de identificador).

    NO es un parser SQL genérico: es deliberadamente estrecho, pensado
    solo para reconocer variantes razonables de
    "estado = 'pendiente'". Cualquier predicado que, tras esta
    normalización, no quede idéntico al esperado se trata como
    DISTINTO (fail-closed), nunca como "probablemente equivalente".
    """
    if not predicado:
        return ""

    texto = predicado.strip().lower()
    texto = re.sub(r"::[a-z_][a-z0-9_]*", "", texto)  # ::text, ::varchar, ...
    texto = texto.replace('"', "")  # comillas de identificador
    texto = texto.replace("(", "").replace(")", "")  # paréntesis de agrupación
    texto = re.sub(r"\s+", "", texto)  # espacios/tabs/saltos de línea
    return texto


_PREDICADO_LEGACY_NORMALIZADO = _normalizar_predicado(_PREDICADO_LEGACY_CRUDO)


def _ubicaciones_indice(conn) -> list[tuple[str, str]]:
    """
    Busca en el catálogo real de PostgreSQL (pg_indexes) TODAS las
    ubicaciones (schema, tabla) donde exista un índice llamado
    `_NOMBRE_INDICE` — deliberadamente SIN filtrar por schema ni tabla
    todavía, para poder distinguir "no existe en ninguna parte" de
    "existe, pero no en public.cita" (este segundo caso es el que
    dispara fail-closed más abajo, en vez de tratarse silenciosamente
    como ausente).
    """
    filas = conn.execute(
        text(
            "SELECT schemaname, tablename FROM pg_indexes "
            "WHERE indexname = :nombre_indice"
        ),
        {"nombre_indice": _NOMBRE_INDICE},
    ).all()
    return [(fila.schemaname, fila.tablename) for fila in filas]


def _inspeccionar_indice_en_cita(conn) -> dict | None:
    """
    Devuelve la definición reflejada (vía inspect(conn)) del índice
    `_NOMBRE_INDICE` tal como existe HOY sobre `_ESQUEMA`.`_TABLA`, o
    None si no aparece ahí. Se asume que quien llama ya confirmó, con
    `_ubicaciones_indice`, que su única ubicación es esa tabla.
    """
    inspector = inspect(conn)
    for indice in inspector.get_indexes(_TABLA, schema=_ESQUEMA):
        if indice.get("name") == _NOMBRE_INDICE:
            return indice
    return None


def _diferencias_con_legacy_conocido(indice: dict) -> list[str]:
    """
    Compara `indice` (tal como lo devuelve inspector.get_indexes())
    contra la huella exacta del índice legacy conocido. Devuelve la
    lista de discrepancias encontradas — vacía si coincide en todo.
    """
    diferencias: list[str] = []

    if not indice.get("unique"):
        diferencias.append(
            "no es un índice UNIQUE (unique=False) — el legacy conocido sí lo es."
        )

    columnas = tuple(indice.get("column_names") or ())
    if columnas != _COLUMNAS_LEGACY:
        diferencias.append(
            f"columnas {columnas!r} no coinciden con las esperadas "
            f"{_COLUMNAS_LEGACY!r} (orden incluido)."
        )

    predicado_crudo = (indice.get("dialect_options") or {}).get("postgresql_where")
    predicado_normalizado = _normalizar_predicado(predicado_crudo)
    if predicado_normalizado != _PREDICADO_LEGACY_NORMALIZADO:
        diferencias.append(
            f"predicado parcial {predicado_crudo!r} (normalizado: "
            f"{predicado_normalizado!r}) no equivale al esperado "
            f"{_PREDICADO_LEGACY_CRUDO!r} (normalizado: "
            f"{_PREDICADO_LEGACY_NORMALIZADO!r})."
        )

    return diferencias


def migrar_a4_4_1_eliminar_indice_unico_slot(
    bind: Engine = engine,
    *,
    emitir_mensaje: bool = True,
) -> None:
    dialecto = bind.dialect.name
    if dialecto != "postgresql":
        raise RuntimeError(
            "A.4.4.1: esta migración manual asume PostgreSQL (consulta "
            "pg_indexes y usa DROP INDEX, sintaxis/catálogo específicos "
            f"de este motor). No se debe correr contra un dialecto no "
            f"contemplado ({dialecto!r}) sin revisar antes si sigue "
            "siendo válida — y de hacerlo, NUNCA se debe fingir éxito."
        )

    with bind.begin() as conn:
        ubicaciones = _ubicaciones_indice(conn)

        if not ubicaciones:
            if emitir_mensaje:
                print(
                    f"A.4.4.1: el índice legacy {_NOMBRE_INDICE!r} no "
                    "existe en esta base; esquema ya compatible."
                )
            return

        ubicaciones_inesperadas = [
            (esquema, tabla)
            for (esquema, tabla) in ubicaciones
            if (esquema, tabla) != (_ESQUEMA, _TABLA)
        ]
        if ubicaciones_inesperadas:
            raise MigracionA441RevisionManualError(
                f"A.4.4.1: existe un índice llamado {_NOMBRE_INDICE!r} "
                f"pero NO en {_ESQUEMA}.{_TABLA} sino en: "
                + ", ".join(f"{e}.{t}" for e, t in ubicaciones_inesperadas)
                + ". No se ejecuta ningún DROP automático — revisar "
                "manualmente antes de continuar (podría ser un índice "
                "legítimo no relacionado con A.4.4, o una copia parcial "
                "de un despliegue anterior)."
            )

        indice_actual = _inspeccionar_indice_en_cita(conn)
        if indice_actual is None:
            # No debería ocurrir (pg_indexes ya confirmó su ubicación
            # exacta), pero si el catálogo cambió entre ambas
            # consultas dentro de esta misma transacción, no se asume
            # nada — se trata como fail-closed por seguridad.
            raise MigracionA441RevisionManualError(
                f"A.4.4.1: pg_indexes reporta {_NOMBRE_INDICE!r} en "
                f"{_ESQUEMA}.{_TABLA}, pero no se pudo reflejar su "
                "definición completa para validarla. Revisar "
                "manualmente antes de continuar."
            )

        diferencias = _diferencias_con_legacy_conocido(indice_actual)
        if diferencias:
            raise MigracionA441RevisionManualError(
                f"A.4.4.1: existe un índice llamado {_NOMBRE_INDICE!r} "
                f"sobre {_ESQUEMA}.{_TABLA}, pero su definición real no "
                "coincide con la huella exacta del índice legacy "
                "conocido — no se ejecuta ningún DROP automático:\n- "
                + "\n- ".join(diferencias)
                + "\nRevisar manualmente antes de continuar."
            )

        conn.execute(
            text(f'DROP INDEX "{_ESQUEMA}"."{_NOMBRE_INDICE}";')
        )

        if _inspeccionar_indice_en_cita(conn) is not None:
            raise MigracionA441IncompletaError(
                f"A.4.4.1: se ejecutó DROP INDEX sobre {_NOMBRE_INDICE!r} "
                "sin errores, pero el catálogo de PostgreSQL — "
                "inspeccionado de nuevo dentro de la misma transacción — "
                "todavía lo reporta sobre "
                f"{_ESQUEMA}.{_TABLA}. La migración no puede darse por "
                "exitosa."
            )

    if emitir_mensaje:
        print(
            f"Migración A.4.4.1 aplicada: índice legacy {_NOMBRE_INDICE!r} "
            f"eliminado de {_ESQUEMA}.{_TABLA}. No se creó ningún índice "
            "de reemplazo — la protección de capacidad máxima (2) sigue "
            "siendo pg_advisory_xact_lock + re-evaluación dentro del "
            "lock (ver app.services.agenda_disponibilidad_service)."
        )


if __name__ == "__main__":
    migrar_a4_4_1_eliminar_indice_unico_slot()
