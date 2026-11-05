# -*- coding: utf-8 -*-
"""
Tests — GET /admin/reportes/resumen/excel y tasa de inasistencia.

Verifica:
  · El backend devuelve un .xlsx REAL (ZIP/OOXML válido, cargable con
    OpenPyXL) — no un TSV renombrado ni HTML.
  · Usa EXACTAMENTE el mismo cálculo que /reportes/resumen y el PDF:
    no hay una segunda fuente de números.
  · La tasa de inasistencia = inasistencias / (completadas + inasistencias),
    con denominador "citas resueltas": pendientes y canceladas no cuentan.
    Sin citas resueltas devuelve "Sin datos", nunca 0%.
  · Exige reportes.ver y registra auditoría con el actor de current_user.
  · No expone campos clínicos y neutraliza valores que Excel podría
    interpretar como fórmula.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from inspect import getclosurevars, getsource, signature

import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.auditoria import Auditoria
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import admin
from app.services.reportes_resumen_service import tasa_inasistencia


# ══════════════════════════════════════
# Fixtures
# ══════════════════════════════════════
@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


_n = {"i": 0}


def _usuario(db, rol="estudiante", *, nombre, carrera=None):
    _n["i"] += 1
    u = Usuario(
        correo=f"x{_n['i']}@sesaes.cl", password="hash", rol=rol,
        nombre=nombre, carrera=carrera,
    )
    db.add(u)
    db.flush()
    return u


def _prof(db, nombre, especialidad):
    p = Profesional(
        nombre=nombre, especialidad=especialidad,
        iniciales=nombre[:2].upper(), estado="activo",
    )
    db.add(p)
    db.flush()
    return p


def _cita(db, est, prof, fecha, hora="10:00", estado="completada",
          medicamento=None, observaciones_atencion=None):
    c = Cita(
        estudiante_id=est.id, profesional_id=prof.id, fecha=fecha, hora=hora,
        estado=estado, medicamento=medicamento,
        observaciones_atencion=observaciones_atencion,
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def escenario(db):
    sa = _usuario(db, "superadmin", nombre="Sofía Súper")
    jose = _usuario(db, nombre="José Pérez", carrera="Kinesiología")
    alvaro = _usuario(db, nombre="Álvaro Núñez", carrera="Diseño")

    maria = _prof(db, "Dra. María Núñez", "Nutrición y Dietética")
    andres = _prof(db, "Dr. Andrés de la Fuente", "Psicología")

    # 3 completadas, 1 inasistencia, 1 pendiente, 2 canceladas.
    _cita(db, jose, maria, "2026-09-15", "10:00", "completada",
          medicamento="Paracetamol 500mg",
          observaciones_atencion="Reposo 3 días")
    _cita(db, jose, maria, "2026-09-16", "10:00", "completada")
    _cita(db, alvaro, andres, "2026-09-14", "09:30", "completada")
    _cita(db, alvaro, andres, "2026-09-13", "15:45", "pendiente")
    _cita(db, jose, andres, "2026-09-12", "11:15", "cancelada")
    _cita(db, jose, andres, "2026-09-11", "11:15", "cancelada")
    _cita(db, alvaro, maria, "2026-09-10", "08:00", "inasistencia")

    db.commit()
    return dict(db=db, sa=sa, maria=maria, andres=andres)


PERIODO = dict(fecha_inicio="2026-09-01", fecha_fin="2026-09-30")


def _excel(db, actor, **filtros):
    args = dict(
        fecha_inicio=None, fecha_fin=None, especialidad=None, carrera=None,
        profesional_id=None, estado=None, prioridad=None,
    )
    args.update(filtros)
    return admin.get_reportes_resumen_excel(
        db=db, current_user={"id": actor.id, "rol": actor.rol}, **args
    )


def _bytes(respuesta) -> bytes:
    async def leer():
        return b"".join([chunk async for chunk in respuesta.body_iterator])

    return asyncio.run(leer())


def _workbook(db, actor, **filtros):
    respuesta = _excel(db, actor, **filtros)
    return respuesta, load_workbook(BytesIO(_bytes(respuesta)))


# ══════════════════════════════════════
# 1) Es un Excel real y trae las hojas esperadas
# ══════════════════════════════════════
def test_excel_es_un_xlsx_real(escenario):
    respuesta, wb = _workbook(escenario["db"], escenario["sa"], **PERIODO)

    assert respuesta.media_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert respuesta.headers["content-disposition"].endswith(
        'reporte-atenciones-inasistencias-2026-09-30.xlsx"'
    )
    assert wb.sheetnames == [
        "Resumen", "Profesionales", "Evolución semanal",
        "Inasistencias", "Últimas atenciones", "Especialidades y carreras",
    ]


# ══════════════════════════════════════
# 2) Tasa de inasistencia: definición y cálculo
# ══════════════════════════════════════
def test_tasa_inasistencia_usa_citas_resueltas_como_denominador(escenario):
    r = admin.get_reportes_resumen(
        db=escenario["db"],
        current_user={"id": escenario["sa"].id, "rol": "superadmin"},
        fecha_inicio="2026-09-01", fecha_fin="2026-09-30",
        especialidad=None, carrera=None, profesional_id=None,
        estado=None, prioridad=None, limite_ultimas=10,
    )

    inas = r["inasistencia"]
    assert inas["inasistencias"] == 1
    assert inas["atenciones"] == 3
    # Pendiente (1) y canceladas (2) quedan fuera del denominador.
    assert inas["citas_resueltas"] == 4
    assert inas["tasa_pct"] == 25.0


def test_tasa_por_profesional_y_global_coinciden_en_el_excel(escenario):
    _, wb = _workbook(escenario["db"], escenario["sa"], **PERIODO)

    hoja = wb["Profesionales"]
    filas = {
        hoja.cell(row=f, column=1).value: {
            "inasistencias": hoja.cell(row=f, column=6).value,
            "tasa": hoja.cell(row=f, column=7).value,
        }
        for f in range(2, hoja.max_row + 1)
    }
    assert filas["Dra. María Núñez"]["inasistencias"] == 1
    # La tasa se redondea a un decimal (33.3%) antes de dividir por 100.
    assert filas["Dra. María Núñez"]["tasa"] == pytest.approx(0.333)
    assert filas["Dr. Andrés de la Fuente"]["inasistencias"] == 0
    assert filas["Dr. Andrés de la Fuente"]["tasa"] == 0

    resumen = wb["Resumen"]
    valores = {
        resumen.cell(row=f, column=1).value: resumen.cell(row=f, column=2).value
        for f in range(1, resumen.max_row + 1)
    }
    assert valores["Citas resueltas"] == 4
    assert valores["Tasa de inasistencia"] == pytest.approx(0.25)


def test_sin_citas_resueltas_no_inventa_tasa(escenario):
    _, wb = _workbook(
        escenario["db"], escenario["sa"],
        fecha_inicio="2027-01-01", fecha_fin="2027-01-31",
    )

    resumen = wb["Resumen"]
    valores = {
        resumen.cell(row=f, column=1).value: resumen.cell(row=f, column=2).value
        for f in range(1, resumen.max_row + 1)
    }
    assert valores["Tasa de inasistencia"] == "Sin datos"

    hoja = wb["Inasistencias"]
    assert hoja.cell(row=4, column=2).value == "Sin datos"


@pytest.mark.parametrize(
    "inasistencias,completadas,esperado",
    [(0, 0, None), (0, 5, 0.0), (1, 3, 25.0), (2, 2, 50.0), (1, 0, 100.0)],
)
def test_tasa_inasistencia_unitaria(inasistencias, completadas, esperado):
    assert tasa_inasistencia(inasistencias, completadas) == esperado


# ══════════════════════════════════════
# 3) Misma fuente de verdad que el JSON
# ══════════════════════════════════════
def test_excel_usa_los_mismos_numeros_que_el_json(escenario):
    db, sa = escenario["db"], escenario["sa"]
    json_resumen = admin.get_reportes_resumen(
        db=db, current_user={"id": sa.id, "rol": sa.rol},
        fecha_inicio="2026-09-01", fecha_fin="2026-09-30",
        especialidad=None, carrera=None, profesional_id=None,
        estado=None, prioridad=None, limite_ultimas=10,
    )
    _, wb = _workbook(db, sa, **PERIODO)

    hoja = wb["Resumen"]
    valores = {
        hoja.cell(row=f, column=1).value: hoja.cell(row=f, column=2).value
        for f in range(1, hoja.max_row + 1)
    }
    assert valores["Completadas"] == json_resumen["kpis"]["completadas"]["valor"]
    assert valores["Canceladas"] == json_resumen["kpis"]["canceladas"]["valor"]
    assert valores["Urgentes"] == json_resumen["kpis"]["urgentes"]["valor"]
    assert valores["Sobrecupos"] == json_resumen["kpis"]["sobrecupos"]["valor"]
    assert valores["Citas resueltas"] == json_resumen["inasistencia"]["citas_resueltas"]


# ══════════════════════════════════════
# 4) Seguridad: permiso, auditoría y datos
# ══════════════════════════════════════
def test_excel_exige_reportes_ver():
    dependencia = signature(
        admin.get_reportes_resumen_excel
    ).parameters["current_user"].default.dependency
    assert getclosurevars(dependencia).nonlocals["permission"].value == "reportes.ver"


def test_excel_registra_auditoria_con_actor_de_current_user(escenario):
    db, sa = escenario["db"], escenario["sa"]
    antes = db.query(Auditoria).count()

    _excel(db, sa, **PERIODO)

    eventos = db.query(Auditoria).order_by(Auditoria.id).all()
    assert len(eventos) == antes + 1
    assert eventos[-1].usuario_id == sa.id
    assert eventos[-1].actor_rol == "superadmin"
    assert eventos[-1].accion == (
        "Exportó el reporte de atenciones e inasistencias (Excel)"
    )
    assert eventos[-1].resultado == "exito"


def test_excel_no_expone_campos_clinicos(escenario):
    _, wb = _workbook(escenario["db"], escenario["sa"], **PERIODO)

    textos = []
    for hoja in wb.worksheets:
        for fila in hoja.iter_rows(values_only=True):
            textos.extend(str(v) for v in fila if v is not None)
    contenido = " ".join(textos)

    assert "Paracetamol" not in contenido
    assert "Reposo" not in contenido
    # La fuente tampoco puede consultarlos: todo sale del resumen.
    fuente = getsource(admin.get_reportes_resumen_excel)
    assert "medicamento" not in fuente
    assert "observaciones" not in fuente


def test_excel_neutraliza_valores_que_parecen_formulas(db):
    sa = _usuario(db, "superadmin", nombre="Sofía Súper")
    est = _usuario(db, nombre="=WEBSERVICE(\"http://malicioso\")")
    prof = _prof(db, "Dra. Normal", "Nutrición")
    _cita(db, est, prof, "2026-09-15", "10:00", "completada")
    db.commit()

    _, wb = _workbook(db, sa, **PERIODO)

    # Ninguna celda del libro puede quedar marcada como fórmula.
    for hoja in wb.worksheets:
        for fila in hoja.iter_rows():
            for celda in fila:
                assert celda.data_type != "f", (hoja.title, celda.coordinate, celda.value)
                if isinstance(celda.value, str):
                    assert not celda.value.startswith("="), (hoja.title, celda.coordinate)
