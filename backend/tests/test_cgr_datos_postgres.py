# -*- coding: utf-8 -*-
"""
Tests contra PostgreSQL REAL — endpoints de datos CGR (B2).

Comprueba en el motor de producción que /admin/exportar/cgr/datos y
/admin/exportar/alumnos/datos aplican las reglas actuales (completadas,
año, fecha_fin inclusiva, exclusiones de RUT, orden por fecha y hora) y que
entregan las mismas filas que el texto tabulado.

Aislamiento: SCHEMA temporal creado y eliminado por el propio test.

    TEST_POSTGRES_URL="postgresql+psycopg2://..." \\
        pytest tests/test_cgr_datos_postgres.py -m postgres -q
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.postgres

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

if not TEST_POSTGRES_URL:
    pytest.skip(
        "CGR datos: TEST_POSTGRES_URL no está definida — los endpoints de datos "
        "NO se validaron contra PostgreSQL real en esta ejecución.",
        allow_module_level=True,
    )

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.models.init  # noqa: E402,F401
import app.models.solicitud_horario  # noqa: E402,F401
from app.database import Base  # noqa: E402
from app.models.cita import Cita  # noqa: E402
from app.models.profesional import Profesional  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.routers import admin  # noqa: E402


@pytest.fixture()
def db_pg():
    schema = f"test_cgr_{uuid.uuid4().hex[:10]}"
    base = create_engine(TEST_POSTGRES_URL)
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(TEST_POSTGRES_URL, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def _poblar(db):
    sa = Usuario(correo="sa@sesaes.cl", password="x", rol="superadmin", nombre="Sofía")
    jose = Usuario(correo="j@sesaes.cl", password="x", rol="estudiante", nombre="José Pérez García",
                   rut="12.345.678-9", carrera="Kinesiología")
    alvaro = Usuario(correo="a@sesaes.cl", password="x", rol="estudiante", nombre="ÁLVARO NÚÑEZ",
                     rut="9.876.543-2", carrera="Diseño")
    excl1 = Usuario(correo="e1@sesaes.cl", password="x", rol="estudiante", nombre="Excluido 1", rut="16.458.880-7")
    excl2 = Usuario(correo="e2@sesaes.cl", password="x", rol="estudiante", nombre="Excluido 2", rut="19.741.131-7")
    sin_datos = Usuario(correo="s@sesaes.cl", password="x", rol="estudiante")
    maria = Profesional(nombre="Dra. María Núñez", especialidad="Nutrición y Dietética", iniciales="MN", estado="activo")
    db.add_all([sa, jose, alvaro, excl1, excl2, sin_datos, maria])
    db.flush()

    def cita(est, fecha, hora, estado="completada", med=None):
        db.add(Cita(estudiante_id=est.id, profesional_id=maria.id, fecha=fecha, hora=hora, estado=estado, medicamento=med))

    cita(jose, "2026-09-15", "10:00")
    cita(alvaro, "2026-09-15", "08:30", med="Paracetamol")
    cita(alvaro, "2026-09-14", "16:00")
    cita(jose, "2026-09-13", "09:00", estado="pendiente")
    cita(jose, "2025-12-05", "12:00")
    cita(excl1, "2026-09-10", "08:00")
    cita(excl2, "2026-09-11", "08:00")
    cita(sin_datos, "2026-09-16", "11:00")
    db.commit()
    return sa


def _leer(respuesta) -> list[list[str]]:
    async def cuerpo():
        return b"".join([c async for c in respuesta.body_iterator])
    texto = asyncio.run(cuerpo()).decode("utf-8-sig")
    return [l.split("\t") for l in texto.split("\n")][1:]


def test_atenciones_en_postgres_reglas_orden_y_exclusiones(db_pg):
    sa = _poblar(db_pg)
    cu = {"id": sa.id, "rol": "superadmin"}

    r = admin.exportar_cgr_datos(anio=2026, fecha_fin=None, db=db_pg, current_user=cu)

    assert r["columnas"][:3] == ["Nombre Completo", "RUT", "Tipo de Atención"]
    assert r["total"] == len(r["filas"]) == 4
    assert [(f[3], f[4]) for f in r["filas"]] == [
        ("2026-09-14", "16:00"), ("2026-09-15", "08:30"), ("2026-09-15", "10:00"), ("2026-09-16", "11:00"),
    ]                                                              # fecha y luego hora, ascendente
    ruts = {f[1] for f in r["filas"]}
    assert "16.458.880-7" not in ruts and "19.741.131-7" not in ruts
    assert r["filas"][1][5] == "Paracetamol" and r["filas"][0][5] == "No aplica"
    assert r["filas"][3][:2] == ["—", "—"]                          # estudiante sin nombre ni RUT
    assert r["filas"][2][0] == "José Pérez García"                  # Unicode original
    assert admin.exportar_cgr_datos(anio=2026, fecha_fin="2026-09-14", db=db_pg, current_user=cu)["total"] == 1
    assert [f[0] for f in admin.exportar_cgr_datos(anio=2025, fecha_fin=None, db=db_pg, current_user=cu)["filas"]] == ["José Pérez García"]


def test_datos_y_texto_tabulado_coinciden_en_postgres(db_pg):
    sa = _poblar(db_pg)
    cu = {"id": sa.id, "rol": "superadmin"}

    json_filas = admin.exportar_cgr_datos(anio=2026, fecha_fin=None, db=db_pg, current_user=cu)["filas"]
    tsv = _leer(admin.exportar_cgr(anio=2026, fecha_fin=None, db=db_pg, current_user=cu))
    assert [[admin._celda_tsv(v) for v in f] for f in json_filas] == tsv

    al_json = admin.exportar_listado_alumnos_datos(db=db_pg, current_user=cu)["filas"]
    al_tsv = _leer(admin.exportar_listado_alumnos(db=db_pg, current_user=cu))
    assert [[admin._celda_tsv(v) for v in f] for f in al_json] == al_tsv


def test_alumnos_en_postgres_orden_y_exclusiones(db_pg):
    sa = _poblar(db_pg)
    r = admin.exportar_listado_alumnos_datos(db=db_pg, current_user={"id": sa.id, "rol": "superadmin"})

    nombres = [f[0] for f in r["filas"]]
    assert "Excluido 1" not in nombres and "Excluido 2" not in nombres
    assert set(nombres) == {"José Pérez García", "ÁLVARO NÚÑEZ", "—"}
    assert r["columnas"] == ["Nombre Completo", "RUT", "Carrera", "Correo"]
