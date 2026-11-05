# -*- coding: utf-8 -*-
"""
Tests — Reportes: GET /admin/reportes/resumen (Vista general).

Cubre lo que este encargo exige como reglas obligatorias:
  · "cita != atención": total_atenciones/estudiantes_atendidos = solo completadas.
  · urgente + sobrecupo son independientes y se cuentan ambos, sin duplicar
    ni eliminar la cita de otras métricas.
  · comparación con el período anterior: real cuando hay datos, `null`
    ("Sin datos comparables") cuando no los hay — nunca inventada.
  · especialidad/carrera narrowean las agregaciones (mismo criterio que
    /admin/historial).
  · alcance administrativo: un ADMIN sin acceso institucional no ve datos
    fuera de su alcance.
  · no exposición de campos clínicos (medicamento/observaciones) en la
    tabla de últimas atenciones.

Patrón del proyecto: SQLite en memoria + endpoints llamados como funciones
(ver tests/test_reportes_exportacion.py).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401 — registra todos los modelos
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
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


_n = {"i": 0}


def _usuario(db, rol="estudiante", *, nombre, carrera=None):
    _n["i"] += 1
    u = Usuario(correo=f"u{_n['i']}@sesaes.cl", password="hash", rol=rol, nombre=nombre, carrera=carrera)
    db.add(u)
    db.flush()
    return u


def _prof(db, nombre, especialidad):
    p = Profesional(nombre=nombre, especialidad=especialidad, iniciales=nombre[:2].upper(), estado="activo")
    db.add(p)
    db.flush()
    return p


def _cita(db, est, prof, fecha, hora="10:00", estado="completada", urgente=False,
          sobrecupo=False, cancelada_por_admin=False):
    c = Cita(
        estudiante_id=est.id, profesional_id=prof.id, fecha=fecha, hora=hora,
        estado=estado, urgente=urgente, sobrecupo=sobrecupo,
        cancelada_por_admin=cancelada_por_admin,
    )
    db.add(c)
    db.flush()
    return c


def _resumen(db, actor, **filtros):
    args = dict(
        fecha_inicio=None, fecha_fin=None, especialidad=None, carrera=None,
        profesional_id=None, estado=None, prioridad=None, limite_ultimas=10,
    )
    args.update(filtros)
    return admin.get_reportes_resumen(db=db, current_user={"id": actor.id, "rol": actor.rol}, **args)


@pytest.fixture()
def escenario(db):
    sa = _usuario(db, "superadmin", nombre="Sofía Súper")
    jose = _usuario(db, nombre="José Pérez García", carrera="Kinesiología")
    alvaro = _usuario(db, nombre="Álvaro Núñez", carrera="Diseño")

    maria = _prof(db, "Dra. María Núñez", "Nutrición y Dietética")
    andres = _prof(db, "Dr. Andrés de la Fuente", "Psicología")

    # Período actual: 2026-09-01 .. 2026-09-30
    _cita(db, jose, maria, "2026-09-15", "10:00", "completada")
    _cita(db, jose, maria, "2026-09-16", "10:00", "completada")
    _cita(db, alvaro, andres, "2026-09-14", "09:30", "completada", urgente=True, sobrecupo=True)
    _cita(db, alvaro, andres, "2026-09-13", "15:45", "pendiente")
    _cita(db, jose, andres, "2026-09-12", "11:15", "cancelada", cancelada_por_admin=True)
    _cita(db, jose, andres, "2026-09-11", "11:15", "cancelada", cancelada_por_admin=False)
    _cita(db, alvaro, maria, "2026-09-10", "08:00", "inasistencia")

    # Período anterior real: 2026-08-01 .. 2026-08-30 (30 días antes)
    _cita(db, jose, maria, "2026-08-15", "10:00", "completada")

    db.commit()
    return dict(db=db, sa=sa, jose=jose, alvaro=alvaro, maria=maria, andres=andres)


PERIODO = dict(fecha_inicio="2026-09-01", fecha_fin="2026-09-30")


def test_total_atenciones_y_completadas_solo_cuentan_estado_completada(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    assert r["kpis"]["total_atenciones"]["valor"] == 3
    assert r["kpis"]["completadas"]["valor"] == 3


def test_canceladas_cuenta_estado_cancelada(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    assert r["kpis"]["canceladas"]["valor"] == 2
    assert r["cancelaciones"]["total"] == 2


def test_urgente_y_sobrecupo_se_cuentan_ambos_sin_duplicar_la_cita(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    # La única cita urgente+sobrecupo cuenta en AMBOS KPI.
    assert r["kpis"]["urgentes"]["valor"] == 1
    assert r["kpis"]["sobrecupos"]["valor"] == 1
    # Y sigue contando como atención (está completada), sin excluirse.
    assert r["kpis"]["total_atenciones"]["valor"] == 3


def test_estudiantes_atendidos_cuenta_distinct_solo_completadas(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    # jose (2 completadas) + alvaro (1 completada) = 2 estudiantes distintos.
    assert r["kpis"]["estudiantes_atendidos"]["valor"] == 2


def test_comparacion_con_periodo_anterior_real(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    # Actual: 3 completadas. Anterior (agosto): 1 completada. +200%.
    assert r["periodo_anterior"]["disponible"] is True
    assert r["kpis"]["completadas"]["variacion_pct"] == 200.0


def test_sin_datos_comparables_cuando_no_hay_periodo_anterior(escenario):
    # Un rango cuyo período anterior (mismo largo, inmediatamente antes)
    # no tiene ninguna cita registrada.
    r = _resumen(escenario["db"], escenario["sa"], fecha_inicio="2027-01-01", fecha_fin="2027-01-31")
    assert r["periodo_anterior"]["disponible"] is False
    for kpi in r["kpis"].values():
        assert kpi["variacion_pct"] is None


def test_por_especialidad_filtra_solo_completadas(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    por_esp = {d["especialidad"]: d["cantidad"] for d in r["por_especialidad"]}
    assert por_esp == {"Nutrición y Dietética": 2, "Psicología": 1}


def test_filtro_especialidad_narrowea_todas_las_agregaciones(escenario):
    r = _resumen(escenario["db"], escenario["sa"], especialidad="Psicología", **PERIODO)
    assert r["kpis"]["completadas"]["valor"] == 1
    assert [d["especialidad"] for d in r["por_especialidad"]] == ["Psicología"]


def test_ultimas_atenciones_no_expone_campos_clinicos(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    assert len(r["ultimas_atenciones"]) == 3
    for fila in r["ultimas_atenciones"]:
        assert set(fila.keys()) == {
            "fecha", "hora", "estudiante", "profesional", "especialidad",
            "estado", "urgente", "sobrecupo",
        }
        assert fila["estado"] == "completada"


def test_ultimas_atenciones_marca_urgente_y_sobrecupo_simultaneos(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    fila = next(f for f in r["ultimas_atenciones"] if f["urgente"])
    assert fila["urgente"] is True
    assert fila["sobrecupo"] is True


def test_citas_por_estado_expone_los_4_estados_reales_para_la_pestana_citas(escenario):
    r = _resumen(escenario["db"], escenario["sa"], **PERIODO)
    # 3 completadas, 2 canceladas, 1 pendiente, 1 inasistencia (ver escenario).
    assert r["citas_por_estado"] == {
        "completada": 3, "cancelada": 2, "pendiente": 1, "inasistencia": 1,
    }
    # Esto NO debe filtrarse hacia los 6 KPI oficiales (regla punto 8).
    assert set(r["kpis"].keys()) == {
        "total_atenciones", "completadas", "canceladas",
        "urgentes", "sobrecupos", "estudiantes_atendidos",
    }


def test_admin_sin_alcance_no_ve_datos_de_otros_profesionales(escenario, monkeypatch):
    from app.rbac.admin_authorization import AlcanceAdministrativoEfectivo

    admin_restringido = _usuario(escenario["db"], "admin", nombre="Admin Restringido")

    def _alcance_falso(db, current_user):
        return AlcanceAdministrativoEfectivo(institucional=False, especialidades_normalizadas=frozenset())

    monkeypatch.setattr(admin, "obtener_alcance_administrativo_efectivo", _alcance_falso)
    monkeypatch.setattr(admin, "_ids_profesionales_en_alcance", lambda db, alcance: [])

    r = _resumen(escenario["db"], admin_restringido, **PERIODO)
    assert r["kpis"]["completadas"]["valor"] == 0
    assert r["ultimas_atenciones"] == []
    assert r["por_especialidad"] == []
