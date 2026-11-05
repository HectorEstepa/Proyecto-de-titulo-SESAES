# -*- coding: utf-8 -*-
"""GET /historial-clinico/cuestionarios-respondidos/{estudiante_id}: lo que el estudiante ya respondió."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.historial_paciente import HistorialPaciente
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import historial_clinico as m

EST_USER = {"id": 99, "rol": "estudiante"}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    s.add(Usuario(id=10, correo="p1@utem.cl", password="x", rol="profesional", activo=True, nombre="P1"))
    s.add(Usuario(id=11, correo="p2@utem.cl", password="x", rol="profesional", activo=True, nombre="P2"))
    s.add(Usuario(id=99, correo="e@utem.cl", password="x", rol="estudiante", activo=True, nombre="E"))
    s.add(Usuario(id=100, correo="e2@utem.cl", password="x", rol="estudiante", activo=True, nombre="E2"))
    s.add(Profesional(id=5, usuario_id=10, nombre="Dra. Owner", especialidad="Medicina General", iniciales="DO"))
    s.add(Profesional(id=6, usuario_id=11, nombre="Carlos Muñoz", especialidad="Nutrición", iniciales="CM"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _ficha(db, prof, est, por="estudiante", revisada=False, fecha=datetime(2026, 7, 20, 8, 45)):
    db.add(HistorialPaciente(profesional_id=prof, estudiante_id=est, respuestas={"1": "x"},
                             completado_por=por, revisado_por_profesional=revisada, fecha_creacion=fecha))
    db.commit()


def _respondidos(db, estudiante_id=99, user=EST_USER):
    return m.cuestionarios_respondidos(estudiante_id=estudiante_id, db=db, current_user=user)


def test_sin_fichas_devuelve_lista_vacia(db):
    assert _respondidos(db) == []


def test_lista_lo_que_respondio_con_su_estado(db):
    _ficha(db, 5, 99, revisada=False, fecha=datetime(2026, 7, 20, 8, 45))
    _ficha(db, 6, 99, revisada=True, fecha=datetime(2026, 7, 15, 11, 20))
    r = _respondidos(db)
    assert [(x["profesional_id"], x["estado"]) for x in r] == [(5, "respondido"), (6, "revisado")]
    assert r[0]["profesional_nombre"] == "Dra. Owner"
    assert r[0]["especialidad"] == "Medicina General"
    assert r[0]["fecha_respuesta"].startswith("2026-07-20")


def test_va_del_mas_reciente_al_mas_antiguo(db):
    _ficha(db, 5, 99, fecha=datetime(2026, 1, 1))
    _ficha(db, 6, 99, fecha=datetime(2026, 9, 1))
    assert [x["profesional_id"] for x in _respondidos(db)] == [6, 5]


def test_una_ficha_llenada_por_el_profesional_no_cuenta_como_respondida(db):
    _ficha(db, 5, 99, por="profesional")
    assert _respondidos(db) == []


def test_no_incluye_fichas_de_otros_estudiantes(db):
    _ficha(db, 5, 100)
    assert _respondidos(db) == []


def test_no_expone_las_respuestas(db):
    _ficha(db, 5, 99)
    assert "respuestas" not in _respondidos(db)[0]


def test_otro_estudiante_no_puede_consultarlo(db):
    _ficha(db, 5, 99)
    with pytest.raises(HTTPException) as exc:
        _respondidos(db, estudiante_id=99, user={"id": 100, "rol": "estudiante"})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["profesional", "admin", "superadmin"])
def test_otros_roles_no_acceden_aunque_el_id_coincida(db, rol):
    _ficha(db, 5, 99)
    with pytest.raises(HTTPException) as exc:
        _respondidos(db, user={"id": 99, "rol": rol})
    assert exc.value.status_code == 403
