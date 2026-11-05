# -*- coding: utf-8 -*-
"""El cuestionario previo es OPCIONAL: lo decide el profesional."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.cita import Cita
from app.models.notificacion import Notificacion
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import historial_clinico as m

PROF_USER = {"id": 10, "rol": "profesional"}
EST_USER = {"id": 99, "rol": "estudiante"}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    s.add(Usuario(id=10, correo="p@utem.cl", password="x", rol="profesional", activo=True, nombre="P"))
    s.add(Usuario(id=99, correo="e@utem.cl", password="x", rol="estudiante", activo=True, nombre="E"))
    s.add(Profesional(id=5, usuario_id=10, nombre="Dra. Owner", especialidad="Medicina", iniciales="DO"))
    s.add(Cita(id=1, profesional_id=5, estudiante_id=99, estado="pendiente", fecha="2030-01-01", hora="09:00"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _pendientes(db):
    return m.cuestionarios_pendientes(estudiante_id=99, db=db, current_user=EST_USER)


def test_por_defecto_no_se_pide_nada(db):
    assert _pendientes(db) == []
    with pytest.raises(HTTPException) as exc:
        m.obtener_cuestionario_para_estudiante(profesional_id=5, db=db, current_user=EST_USER)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        m.responder_cuestionario_estudiante(profesional_id=5, datos=m.RespuestasEstudianteIn(respuestas={"1": "x"}),
                                            db=db, current_user=EST_USER)
    assert exc.value.status_code == 403


def test_enviar_a_un_estudiante_lo_deja_pendiente_y_le_avisa(db):
    m.decidir_cuestionario(5, 99, m.CuestionarioDecisionIn(solicitar=True), db=db, current_user=PROF_USER)
    assert [p["profesional_id"] for p in _pendientes(db)] == [5]
    assert m.obtener_cuestionario_para_estudiante(profesional_id=5, db=db, current_user=EST_USER)["preguntas"]
    assert db.query(Notificacion).filter_by(usuario_id=99).count() == 1


def test_ajuste_general_activo_aplica_a_todos(db):
    m.actualizar_config_cuestionario(5, m.CuestionarioConfigIn(enviar_por_defecto=True), db=db, current_user=PROF_USER)
    assert m.obtener_config_cuestionario(5, db=db, current_user=PROF_USER) == {"enviar_por_defecto": True}
    assert [p["profesional_id"] for p in _pendientes(db)] == [5]


def test_omitir_a_un_estudiante_gana_sobre_el_ajuste_general(db):
    m.actualizar_config_cuestionario(5, m.CuestionarioConfigIn(enviar_por_defecto=True), db=db, current_user=PROF_USER)
    m.decidir_cuestionario(5, 99, m.CuestionarioDecisionIn(solicitar=False), db=db, current_user=PROF_USER)
    assert _pendientes(db) == []
    # y volver al ajuste general quita la excepción
    assert m.volver_a_ajuste_general(5, 99, db=db, current_user=PROF_USER) == {"cuestionario_solicitado": True}
    assert [p["profesional_id"] for p in _pendientes(db)] == [5]


def test_solo_el_profesional_dueno_decide(db):
    db.add(Usuario(id=11, correo="p2@utem.cl", password="x", rol="profesional", activo=True, nombre="P2"))
    db.add(Profesional(id=6, usuario_id=11, nombre="Otro", especialidad="Medicina", iniciales="OT"))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        m.decidir_cuestionario(5, 99, m.CuestionarioDecisionIn(solicitar=True), db=db, current_user={"id": 11, "rol": "profesional"})
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        m.decidir_cuestionario(5, 99, m.CuestionarioDecisionIn(solicitar=True), db=db, current_user=EST_USER)
    assert exc.value.status_code == 403
