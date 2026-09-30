# -*- coding: utf-8 -*-
"""
SESAES — Migración puntual: agenda semanal por bloques, ausencias por
fecha exacta y rechazo de citas por el profesional.

Sigue el mismo patrón que scripts/migrar_a4_1_trazabilidad.py:
  - ALTER TABLE ... ADD COLUMN IF NOT EXISTS sobre tablas existentes
    (cita, solicitud_horario), sin DEFAULT que reescriba filas
    históricas;
  - Table.create(..., checkfirst=True) para las tablas nuevas
    (bloque_horario_semanal, ausencia_profesional);
  - todo en una sola transacción;
  - verifica el esquema resultante con inspect(conn) antes de dar la
    migración por exitosa.

Qué hace:
  1. cita: agrega rechazada_por_profesional BOOLEAN (NULL, sin default
     — las citas históricas no tienen este dato, igual que
     cancelada_por_admin en su momento).
  2. solicitud_horario: agrega bloques_json TEXT (NULL).
  3. Crea bloque_horario_semanal y ausencia_profesional si no existen.

Qué NO hace:
  - No toca ni migra profesionales existentes a agenda por bloques —
    eso es explícito, vía /profesional/{id}/solicitar-bloques-horario
    + aprobación del admin. Los profesionales con horario_inicio/
    horario_fin simple siguen funcionando igual (ver app/reglas_horario.py
    y app/services/agenda_disponibilidad_service.py).

Ejecución manual (desde backend/, con el venv activado):

    python -m scripts.migrar_agenda_bloques

Si la base es nueva (sin datos), no hace falta correr esto:
Base.metadata.create_all() ya crea las tablas nuevas solo al levantar
el backend — este script solo es necesario contra una base EXISTENTE.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database import engine, Base
from app.models.cita import Cita  # noqa: F401 — registra 'cita'
from app.models.solicitud_horario import SolicitudHorario  # noqa: F401
from app.models.profesional import Profesional  # noqa: F401 — FK de las tablas nuevas
from app.models.bloque_horario_semanal import BloqueHorarioSemanal
from app.models.ausencia_profesional import AusenciaProfesional


class MigracionAgendaBloquesIncompletaError(RuntimeError):
    """El esquema resultante no cumple exactamente lo esperado."""


_ALTER_CITA = (
    "ALTER TABLE cita ADD COLUMN IF NOT EXISTS "
    "rechazada_por_profesional BOOLEAN NULL;"
)

_ALTER_SOLICITUD_HORARIO = (
    "ALTER TABLE solicitud_horario ADD COLUMN IF NOT EXISTS "
    "bloques_json TEXT NULL;"
)


def _run() -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Esta migración es específica de PostgreSQL "
            f"(dialecto detectado: {engine.dialect.name})."
        )

    with engine.begin() as conn:
        conn.execute(text(_ALTER_CITA))
        conn.execute(text(_ALTER_SOLICITUD_HORARIO))

        # Tablas nuevas — checkfirst=True es idempotente (no falla ni
        # duplica si ya existen de una corrida anterior).
        BloqueHorarioSemanal.__table__.create(bind=conn, checkfirst=True)
        AusenciaProfesional.__table__.create(bind=conn, checkfirst=True)

        insp = inspect(conn)

        cols_cita = {c["name"] for c in insp.get_columns("cita")}
        if "rechazada_por_profesional" not in cols_cita:
            raise MigracionAgendaBloquesIncompletaError(
                "cita.rechazada_por_profesional no quedó creada."
            )

        cols_solicitud = {c["name"] for c in insp.get_columns("solicitud_horario")}
        if "bloques_json" not in cols_solicitud:
            raise MigracionAgendaBloquesIncompletaError(
                "solicitud_horario.bloques_json no quedó creada."
            )

        tablas = set(insp.get_table_names())
        for tabla in ("bloque_horario_semanal", "ausencia_profesional"):
            if tabla not in tablas:
                raise MigracionAgendaBloquesIncompletaError(
                    f"La tabla {tabla} no quedó creada."
                )

    print("Migración agenda_bloques aplicada correctamente.")


if __name__ == "__main__":
    _run()
