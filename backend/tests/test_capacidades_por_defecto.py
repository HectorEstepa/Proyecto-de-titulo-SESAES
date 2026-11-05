# -*- coding: utf-8 -*-
"""Capacidades que trae cada especialidad de fábrica (sin autorización del superadmin)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.especialidad_capability import EspecialidadCapability
from app.services.capacidades_por_defecto import capacidades_efectivas_profesional, capacidades_por_defecto

TODAS = {"registrar_medicamento_suministrado", "emitir_receta", "emitir_justificativo"}


@pytest.mark.parametrize("especialidad", [
    "Medicina General", "medicina general", "  MEDICINA   INTERNA ", "Odontología", "odontologia",
    "Otorrinolaringología", "Pediatría", "Psiquiatría", "Ginecología y Obstetricia",
])
def test_especialidades_que_recetan_traen_las_tres(especialidad):
    assert capacidades_por_defecto(especialidad) == TODAS


@pytest.mark.parametrize("especialidad", [
    "Psicología", "Kinesiología", "Nutrición y Dietética", "Fonoaudiología", "Terapia Ocupacional", "Matrona",
])
def test_especialidades_que_no_recetan_solo_certifican(especialidad):
    assert capacidades_por_defecto(especialidad) == {"emitir_justificativo"}


@pytest.mark.parametrize("especialidad", ["Enfermería", "Enfermeria", "Administración", "Cualquier cosa", "", None, "   "])
def test_enfermeria_y_lo_desconocido_no_traen_nada_fail_closed(especialidad):
    assert capacidades_por_defecto(especialidad) == frozenset()


def test_las_autorizaciones_adicionales_se_suman_a_lo_de_fabrica():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    assert capacidades_efectivas_profesional("Enfermería", db) == []
    db.add(EspecialidadCapability(especialidad_normalizada="enfermeria", capability="emitir_receta", activo=True))
    db.commit()
    assert capacidades_efectivas_profesional("Enfermería", db) == ["emitir_receta"]            # supervisada
    assert capacidades_efectivas_profesional("Psicología", db) == ["emitir_justificativo"]     # de fábrica
    db.close()
    engine.dispose()
