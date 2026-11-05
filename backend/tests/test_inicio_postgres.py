# -*- coding: utf-8 -*-
"""
Tests contra PostgreSQL REAL — Inicio institucional de SUPERADMIN.

Valida lo que SQLite no puede garantizar:
  · la migración scripts/migrar_usuario_fecha_creacion.py (ALTER TABLE
    ... IF NOT EXISTS, SET DEFAULT, idempotencia y NULL histórico);
  · que las consultas agrupadas del Inicio (substr + GROUP BY,
    subconsultas escalares, JOIN) se ejecutan y devuelven lo esperado en
    el motor de producción.

Aislamiento: todo ocurre en un SCHEMA temporal creado y eliminado por el
propio test (search_path apuntando a él). No toca el schema `public`.

Cómo correrlo (usar un Postgres de test DESECHABLE, nunca productivo):
    TEST_POSTGRES_URL="postgresql+psycopg2://..." \\
        pytest tests/test_inicio_postgres.py -m postgres -q
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest

pytestmark = pytest.mark.postgres

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

if not TEST_POSTGRES_URL:
    pytest.skip(
        "Inicio SUPERADMIN: TEST_POSTGRES_URL no está definida — la "
        "migración de usuario.fecha_creacion y las consultas agrupadas "
        "NO se validaron contra Postgres real en esta ejecución.",
        allow_module_level=True,
    )

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.models.init  # noqa: E402,F401
import app.models.solicitud_horario  # noqa: E402,F401
from app.database import Base  # noqa: E402
from app.models.auditoria import Auditoria  # noqa: E402
from app.models.cita import Cita  # noqa: E402
from app.models.profesional import Profesional  # noqa: E402
from app.models.solicitud_horario import SolicitudHorario  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.routers import admin  # noqa: E402
from app.routers.admin_inicio import construir_gestion, construir_resumen  # noqa: E402
from scripts.migrar_usuario_fecha_creacion import (  # noqa: E402
    migrar_usuario_fecha_creacion,
)

HOY = date(2026, 9, 19)
AHORA = datetime(2026, 9, 19, 12, 0, 0)


@pytest.fixture()
def engine_pg():
    schema = f"test_inicio_{uuid.uuid4().hex[:10]}"
    base = create_engine(TEST_POSTGRES_URL)
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(
        TEST_POSTGRES_URL,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def _simular_base_legacy(engine) -> None:
    """Deja `usuario` como estaba antes de la migración (sin la columna)."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE usuario DROP COLUMN fecha_creacion"))


def test_migracion_corre_dos_veces_y_no_inventa_fechas_historicas(engine_pg):
    _simular_base_legacy(engine_pg)
    with engine_pg.begin() as conn:
        conn.execute(text(
            "INSERT INTO usuario (correo, password, rol, activo) "
            "VALUES ('historico@sesaes.cl', 'x', 'estudiante', true)"
        ))

    migrar_usuario_fecha_creacion(bind=engine_pg, emitir_mensaje=False)
    migrar_usuario_fecha_creacion(bind=engine_pg, emitir_mensaje=False)  # idempotente

    columnas = {c["name"]: c for c in inspect(engine_pg).get_columns("usuario")}
    assert columnas["fecha_creacion"]["nullable"] is True
    assert "now" in (columnas["fecha_creacion"]["default"] or "").lower()

    with engine_pg.begin() as conn:
        # Histórico: NULL, NO la fecha de la migración.
        assert conn.execute(text(
            "SELECT fecha_creacion FROM usuario WHERE correo = 'historico@sesaes.cl'"
        )).scalar_one() is None

        # Cuenta nueva (sin indicar la columna): recibe la fecha real.
        conn.execute(text(
            "INSERT INTO usuario (correo, password, rol, activo) "
            "VALUES ('nuevo@sesaes.cl', 'x', 'estudiante', true)"
        ))
        assert conn.execute(text(
            "SELECT fecha_creacion FROM usuario WHERE correo = 'nuevo@sesaes.cl'"
        )).scalar_one() is not None


def _poblar(engine):
    db = sessionmaker(bind=engine, autoflush=False)()
    est = Usuario(correo="e@sesaes.cl", password="x", rol="estudiante", nombre="Est")
    sa = Usuario(correo="sa@sesaes.cl", password="x", rol="superadmin", nombre="Sofía")
    ana = Profesional(nombre="Ana", especialidad="Psicología", iniciales="AN", estado="activo")
    beto = Profesional(nombre="Beto", especialidad=" psicología", iniciales="BE", estado="licencia")
    db.add_all([est, sa, ana, beto])
    db.flush()

    for fecha, estado in (
        ("2025-09-30", "pendiente"),      # fuera de los 12 meses
        ("2025-10-01", "pendiente"),
        ("2026-09-10", "completada"),
        ("2026-09-11", "cancelada"),      # no cuenta
        ("2026-10-01", "pendiente"),      # fuera de la serie
    ):
        db.add(Cita(estudiante_id=est.id, profesional_id=ana.id,
                    fecha=fecha, hora="10:00", estado=estado))

    db.add(SolicitudHorario(profesional_id=ana.id, tipo="colacion",
                            hora_inicio="13:00", hora_fin="14:00",
                            estado="pendiente", fecha_solicitud=AHORA))
    db.add(Auditoria(usuario_id=sa.id, actor_rol="superadmin", accion="X",
                     resultado="denegado", fecha=AHORA - timedelta(days=2)))
    db.add(Auditoria(usuario_id=sa.id, actor_rol="superadmin", accion="Y",
                     resultado="exito", fecha=AHORA - timedelta(days=1)))
    db.commit()
    return db


def test_consultas_del_resumen_funcionan_en_postgres(engine_pg):
    db = _poblar(engine_pg)
    try:
        r = construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=True)
    finally:
        db.close()

    assert r["kpis"] == {
        "estudiantes_registrados": 1,
        "profesionales_activos": 1,
        "citas_mes": 1,
        "especialidades": 1,           # "Psicología" y " psicología" se unifican
        "solicitudes_pendientes": 1,
        "incidencias": {"total": 1, "dias": 30},
    }
    meses = {m["mes"]: m["cantidad"] for m in r["citas_por_mes"]["meses"]}
    assert list(meses)[0] == "2025-10" and list(meses)[-1] == "2026-09"
    assert meses["2025-10"] == 1 and meses["2026-09"] == 1
    assert sum(meses.values()) == 2

    items = r["profesionales_mas_solicitados"]["items"]
    assert [(i["nombre"], i["cantidad"]) for i in items] == [("Ana", 1)]


def test_consultas_de_gestion_y_auditoria_funcionan_en_postgres(engine_pg):
    db = _poblar(engine_pg)
    try:
        g = construir_gestion(db)
        filas = admin.get_auditoria(
            fecha_inicio=None, fecha_fin=None, limit=1, db=db,
            current_user={"id": 1, "rol": "superadmin"},
        )
    finally:
        db.close()

    assert [u["nombre"] for u in g["ultimos_usuarios"]] == ["Sofía", "Est"]
    assert g["ultimos_usuarios"][0]["fecha_creacion"] is not None
    assert g["solicitudes_pendientes"]["total"] == 1
    assert g["solicitudes_pendientes"]["items"][0]["profesional_nombre"] == "Ana"

    assert len(filas) == 1
    assert filas[0]["accion"] == "Y"            # la más reciente
    assert filas[0]["actor_nombre"] == "Sofía"
