# -*- coding: utf-8 -*-
"""
Tests — normalización de búsqueda en los filtros de Reportes
(especialidad y carrera, GET /admin/reportes/resumen).

Objetivo explícito: probar que Reportes es tolerante a
  · tildes/diacríticos (García ↔ Garcia, Kinesiología ↔ kinesiologia);
  · mayúsculas/minúsculas;
  · ñ (Muñoz ↔ Munoz/munoz, Diseño ↔ diseno);
  · espacios iniciales/finales y múltiples,
reutilizando EXACTAMENTE `app.busqueda` (igual_normalizado para
especialidad, filtro_texto para carrera) — no se reimplementa nada nuevo
para Reportes. El primer bloque de tests lo verifica a nivel de import
(misma función, no una copia); el resto lo verifica de punta a punta a
través del endpoint real, con datos reales (no fixtures que maquillen la
lógica de producción).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app import busqueda
from app.busqueda import filtro_texto, igual_normalizado, normalizar_busqueda
from app.database import Base
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import admin


# ── Reportes reutiliza app.busqueda, no reimplementa nada ───────────
def test_admin_importa_las_mismas_funciones_de_busqueda_py_sin_copiarlas():
    # Identidad de objeto (`is`), no solo mismo nombre: si alguien agregara
    # una segunda implementación de normalización dentro de admin.py con el
    # mismo nombre, este test lo detecta.
    assert admin.igual_normalizado is igual_normalizado
    assert admin.filtro_texto is filtro_texto
    assert admin.igual_normalizado.__module__ == busqueda.__name__
    assert admin.filtro_texto.__module__ == busqueda.__name__


# ── La normalización subyacente: tildes/ñ/mayúsculas (nivel unitario) ──
@pytest.mark.parametrize("original,variante", [
    ("García", "Garcia"),
    ("García", "garcia"),
    ("García", "GARCIA"),
    ("Muñoz", "Munoz"),
    ("Muñoz", "munoz"),
    ("Kinesiología", "kinesiologia"),
    ("Diseño Gráfico", "diseno grafico"),
    ("  Odontología  ", "odontologia"),
    ("Pérez   García", "perez garcia"),  # espacios múltiples colapsados
])
def test_normalizar_busqueda_hace_equivalentes_tildes_ene_y_mayusculas(original, variante):
    assert normalizar_busqueda(original) == normalizar_busqueda(variante)


# ── Fixtures de integración (datos reales vía la sesión SQLite) ────
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


def _usuario(db, *, nombre, carrera=None, rol="estudiante"):
    u = Usuario(correo=f"{nombre}@sesaes.cl".replace(" ", "").lower(), password="hash", rol=rol, nombre=nombre, carrera=carrera)
    db.add(u)
    db.flush()
    return u


def _prof(db, nombre, especialidad):
    p = Profesional(nombre=nombre, especialidad=especialidad, iniciales="XX", estado="activo")
    db.add(p)
    db.flush()
    return p


def _cita(db, est, prof, fecha, estado="completada"):
    c = Cita(estudiante_id=est.id, profesional_id=prof.id, fecha=fecha, hora="10:00", estado=estado)
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def escenario(db):
    sa = _usuario(db, nombre="Sofía Súper", rol="superadmin")
    jose = _usuario(db, nombre="José Pérez", carrera="Diseño Gráfico")
    ignacio = _usuario(db, nombre="Ignacio Soto", carrera="Ingeniería Civil")

    barbara = _prof(db, "Dra. Bárbara García", "Otorrinolaringología")
    andres = _prof(db, "Klgo. Andrés Muñoz", "Kinesiología")

    _cita(db, jose, barbara, "2026-09-10", "completada")
    _cita(db, jose, barbara, "2026-09-11", "completada")
    _cita(db, ignacio, andres, "2026-09-12", "completada")

    db.commit()
    return dict(db=db, sa=sa)


def _resumen(db, actor, **filtros):
    args = dict(
        fecha_inicio="2026-09-01", fecha_fin="2026-09-30", especialidad=None,
        carrera=None, profesional_id=None, estado=None, prioridad=None, limite_ultimas=10,
    )
    args.update(filtros)
    return admin.get_reportes_resumen(db=db, current_user={"id": actor.id, "rol": actor.rol}, **args)


# ── Especialidad (igual_normalizado — igualdad tolerante) ──────────
class TestFiltroEspecialidadNormalizado:
    def test_sin_tildes_encuentra_especialidad_con_tildes(self, escenario):
        r = _resumen(escenario["db"], escenario["sa"], especialidad="Otorrinolaringologia")
        assert r["kpis"]["completadas"]["valor"] == 2

    def test_mayusculas_encuentran_especialidad_en_minusculas_del_backend(self, escenario):
        r = _resumen(escenario["db"], escenario["sa"], especialidad="OTORRINOLARINGOLOGÍA")
        assert r["kpis"]["completadas"]["valor"] == 2

    def test_espacios_iniciales_finales_no_afectan_la_coincidencia(self, escenario):
        r = _resumen(escenario["db"], escenario["sa"], especialidad="  Kinesiología  ")
        assert r["kpis"]["completadas"]["valor"] == 1

    def test_especialidad_inexistente_normalizada_no_devuelve_datos_ajenos(self, escenario):
        r = _resumen(escenario["db"], escenario["sa"], especialidad="Nutricion")
        assert r["kpis"]["completadas"]["valor"] == 0


# ── Carrera (filtro_texto — subcadena tolerante, sin reimplementar) ──
class TestFiltroCarreraNormalizado:
    def test_carrera_sin_ene_ni_tildes_encuentra_carrera_con_ene_y_tildes(self, escenario):
        r = _resumen(escenario["db"], escenario["sa"], carrera="diseno grafico")
        assert r["kpis"]["completadas"]["valor"] == 2  # las 2 citas de José (Diseño Gráfico)

    def test_coincidencia_parcial_en_mayusculas(self, escenario):
        r = _resumen(escenario["db"], escenario["sa"], carrera="GRAFICO")
        assert r["kpis"]["completadas"]["valor"] == 2

    def test_carrera_distinta_no_mezcla_datos_de_otro_estudiante(self, escenario):
        r = _resumen(escenario["db"], escenario["sa"], carrera="ingenieria civil")
        assert r["kpis"]["completadas"]["valor"] == 1

    def test_carrera_vacia_no_filtra_nada(self, escenario):
        sin_filtro = _resumen(escenario["db"], escenario["sa"])
        con_filtro_vacio = _resumen(escenario["db"], escenario["sa"], carrera="   ")
        assert sin_filtro["kpis"]["completadas"]["valor"] == con_filtro_vacio["kpis"]["completadas"]["valor"] == 3
