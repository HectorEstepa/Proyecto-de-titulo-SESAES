# -*- coding: utf-8 -*-
"""Administración de capacidades clínicas por especialidad (superadmin)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.especialidad_capability import EspecialidadCapability
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import admin_capacidades_clinicas as m
from app.services.clinical_capabilities_service import resolver_capacidades_efectivas

SUPER = {"id": 1, "rol": "superadmin"}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    s.add(Usuario(id=1, correo="s@utem.cl", password="x", rol="superadmin", activo=True, nombre="S"))
    for uid, esp in ((10, "Medicina General"), (11, "medicina general"), (12, "Odontología")):
        s.add(Usuario(id=uid, correo=f"p{uid}@utem.cl", password="x", rol="profesional", activo=True, nombre=f"P{uid}"))
        s.add(Profesional(id=uid, usuario_id=uid, nombre=f"Prof {uid}", especialidad=esp, iniciales="PP"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_solo_quien_gestiona_configuracion_puede_ver_y_cambiar(db):
    for rol in ("profesional", "estudiante", "admin"):
        with pytest.raises(HTTPException) as exc:
            m.listar_capacidades(db=db, current_user={"id": 9, "rol": rol})
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            m.actualizar_capacidades("odontologia", m.CapacidadesIn(capacidades=[]), db=db, current_user={"id": 9, "rol": rol})
        assert exc.value.status_code == 403


def test_listado_agrupa_especialidades_normalizadas_y_cuenta_profesionales(db):
    r = m.listar_capacidades(db=db, current_user=SUPER)
    por_clave = {e["clave"]: e for e in r["especialidades"]}
    assert set(por_clave) == {"medicina general", "odontologia"}
    assert por_clave["medicina general"]["profesionales"] == 2          # "Medicina General" y "medicina general"
    assert por_clave["odontologia"]["nombre"] == "Odontología"
    # Lo propio de la profesión viene de fábrica; nada se concede por autorización.
    assert por_clave["medicina general"]["incluidas"] == ["emitir_justificativo", "emitir_receta", "registrar_medicamento_suministrado"]
    assert por_clave["odontologia"]["incluidas"] == ["emitir_justificativo", "emitir_receta", "registrar_medicamento_suministrado"]
    activas = {c["valor"] for c in r["catalogo"] if c["activa_en_sistema"]}
    assert activas == {"registrar_medicamento_suministrado", "emitir_receta", "emitir_justificativo"}


def test_otorgar_se_refleja_en_la_resolucion_real_de_capacidades(db):
    m.actualizar_capacidades("enfermeria", m.CapacidadesIn(capacidades=["emitir_receta", "emitir_justificativo"]),
                             db=db, current_user=SUPER)
    assert resolver_capacidades_efectivas("Enfermería", db) == ["emitir_justificativo", "emitir_receta"]
    assert resolver_capacidades_efectivas("Kinesiología", db) == []     # otra especialidad no cambia


def test_retirar_desactiva_la_regla_sin_borrarla_y_se_puede_reactivar(db):
    m.actualizar_capacidades("enfermeria", m.CapacidadesIn(capacidades=["emitir_receta"]), db=db, current_user=SUPER)
    m.actualizar_capacidades("enfermeria", m.CapacidadesIn(capacidades=[]), db=db, current_user=SUPER)
    assert resolver_capacidades_efectivas("enfermeria", db) == []
    regla = db.query(EspecialidadCapability).filter_by(capability="emitir_receta").one()
    assert regla.activo is False
    m.actualizar_capacidades("enfermeria", m.CapacidadesIn(capacidades=["emitir_receta"]), db=db, current_user=SUPER)
    assert resolver_capacidades_efectivas("enfermeria", db) == ["emitir_receta"]
    assert db.query(EspecialidadCapability).count() == 1


def test_rechaza_capacidad_desconocida_y_clave_no_normalizada(db):
    with pytest.raises(HTTPException) as exc:
        m.actualizar_capacidades("medicina general", m.CapacidadesIn(capacidades=["hackear"]), db=db, current_user=SUPER)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        m.actualizar_capacidades("Odontología", m.CapacidadesIn(capacidades=[]), db=db, current_user=SUPER)
    assert exc.value.status_code == 400
    assert db.query(EspecialidadCapability).count() == 0


def test_especialidad_con_reglas_pero_sin_profesionales_sigue_apareciendo(db):
    m.actualizar_capacidades("enfermeria", m.CapacidadesIn(capacidades=["emitir_receta"]), db=db, current_user=SUPER)
    por_clave = {e["clave"]: e for e in m.listar_capacidades(db=db, current_user=SUPER)["especialidades"]}
    assert por_clave["enfermeria"]["profesionales"] == 0 and por_clave["enfermeria"]["capacidades"] == ["emitir_receta"]
    assert por_clave["enfermeria"]["incluidas"] == []


def test_lo_de_fabrica_no_se_guarda_como_regla_ni_se_puede_quitar(db):
    m.actualizar_capacidades("medicina general", m.CapacidadesIn(capacidades=["emitir_receta"]), db=db, current_user=SUPER)
    assert db.query(EspecialidadCapability).count() == 0                  # ya la trae de fábrica: no se persiste
    m.actualizar_capacidades("medicina general", m.CapacidadesIn(capacidades=[]), db=db, current_user=SUPER)
    por_clave = {e["clave"]: e for e in m.listar_capacidades(db=db, current_user=SUPER)["especialidades"]}
    assert "emitir_receta" in por_clave["medicina general"]["capacidades"]  # desmarcarla no la retira
