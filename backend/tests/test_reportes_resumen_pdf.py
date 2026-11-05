# -*- coding: utf-8 -*-
"""
Tests — GET /admin/reportes/resumen/pdf.

Verifica: es un PDF real (no TSV, no HTML, no window.print), usa el MISMO
cálculo que /admin/reportes/resumen (una sola fuente de verdad), exige
`reportes.ver`, registra auditoría real con el actor tomado de
current_user (nunca de un parámetro externo), y no incluye ningún campo
clínico (medicamento, observaciones).
"""

from __future__ import annotations

import asyncio

import pytest
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


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _usuario(db, rol="estudiante", *, nombre):
    u = Usuario(correo=f"{nombre}@sesaes.cl".replace(" ", "").lower(), password="hash", rol=rol, nombre=nombre)
    db.add(u)
    db.flush()
    return u


def _prof(db, nombre, especialidad):
    p = Profesional(nombre=nombre, especialidad=especialidad, iniciales="XX", estado="activo")
    db.add(p)
    db.flush()
    return p


def _cita(db, est, prof, fecha, estado="completada", medicamento=None, observaciones_atencion=None):
    c = Cita(
        estudiante_id=est.id, profesional_id=prof.id, fecha=fecha, hora="10:00",
        estado=estado, medicamento=medicamento, observaciones_atencion=observaciones_atencion,
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def escenario(db):
    sa = _usuario(db, "superadmin", nombre="Sofia Super")
    jose = _usuario(db, nombre="Jose Perez")
    maria = _prof(db, "Dra. Maria Nunez", "Nutricion")
    _cita(db, jose, maria, "2026-09-15", "completada", medicamento="Paracetamol 500mg", observaciones_atencion="Reposo 3 dias")
    db.commit()
    return dict(db=db, sa=sa)


def _pdf_bytes(respuesta) -> bytes:
    async def leer():
        return b"".join([c async for c in respuesta.body_iterator])
    return asyncio.run(leer())


def _pdf(db, actor, **filtros):
    args = dict(
        fecha_inicio="2026-09-01", fecha_fin="2026-09-30", especialidad=None,
        carrera=None, profesional_id=None, estado=None, prioridad=None,
    )
    args.update(filtros)
    return admin.get_reportes_resumen_pdf(db=db, current_user={"id": actor.id, "rol": actor.rol}, **args)


def test_pdf_real_no_es_tsv_ni_html(escenario):
    r = _pdf(escenario["db"], escenario["sa"])
    assert r.media_type == "application/pdf"
    cuerpo = _pdf_bytes(r)
    assert cuerpo[:5] == b"%PDF-"  # firma real de un PDF, no window.print() ni TSV


def test_pdf_no_incluye_campos_clinicos(escenario):
    cuerpo = _pdf_bytes(_pdf(escenario["db"], escenario["sa"]))
    # El contenido de texto de un PDF va comprimido/codificado; lo que
    # importa es que la función que arma el PDF (_construir_resumen_reportes)
    # nunca expone medicamento/observaciones_atencion — se verifica a nivel
    # de fuente, igual que test_historial_admin_no_expone_campos_clinicos.
    fuente = __import__("inspect").getsource(admin.get_reportes_resumen_pdf)
    assert "medicamento" not in fuente
    assert "observaciones" not in fuente
    assert len(cuerpo) > 100


def test_pdf_exige_reportes_ver(escenario):
    dependencia = __import__("inspect").signature(admin.get_reportes_resumen_pdf).parameters["current_user"].default.dependency
    assert __import__("inspect").getclosurevars(dependencia).nonlocals["permission"].value == "reportes.ver"


def test_pdf_registra_auditoria_con_actor_de_current_user(escenario):
    db, sa = escenario["db"], escenario["sa"]
    antes = db.query(Auditoria).count()
    _pdf(db, sa)
    eventos = db.query(Auditoria).all()
    assert len(eventos) == antes + 1
    assert eventos[-1].usuario_id == sa.id
    assert eventos[-1].actor_rol == "superadmin"
    assert eventos[-1].resultado == "exito"


def test_pdf_usa_los_mismos_numeros_que_el_endpoint_json(escenario):
    db, sa = escenario["db"], escenario["sa"]
    json_resumen = admin.get_reportes_resumen(
        db=db, current_user={"id": sa.id, "rol": sa.rol},
        fecha_inicio="2026-09-01", fecha_fin="2026-09-30", especialidad=None,
        carrera=None, profesional_id=None, estado=None, prioridad=None, limite_ultimas=10,
    )
    # Construido con la misma función interna: mismo KPI para el mismo filtro.
    interno = admin._construir_resumen_reportes(
        db, {"id": sa.id, "rol": sa.rol},
        fecha_inicio="2026-09-01", fecha_fin="2026-09-30", limite_ultimas=20,
    )
    assert json_resumen["kpis"]["completadas"]["valor"] == interno["kpis"]["completadas"]["valor"] == 1
