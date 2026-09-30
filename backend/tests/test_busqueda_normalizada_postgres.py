# -*- coding: utf-8 -*-
"""
Tests contra PostgreSQL REAL — búsqueda tolerante (app/busqueda.py).

Demuestran que la normalización SQL de producción (translate /
regexp_replace / lower / btrim, sin extensiones) es IDÉNTICA a la
definición canónica en Python, y que los endpoints de Reportes devuelven
el mismo resultado que en SQLite.

Aislamiento: todo ocurre en un SCHEMA temporal que el propio test crea y
elimina (no toca `public`).

    TEST_POSTGRES_URL="postgresql+psycopg2://..." \\
        pytest tests/test_busqueda_normalizada_postgres.py -m postgres -q
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.postgres

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

if not TEST_POSTGRES_URL:
    pytest.skip(
        "Búsqueda tolerante: TEST_POSTGRES_URL no está definida — la "
        "paridad SQL↔Python NO se validó contra PostgreSQL real en esta ejecución.",
        allow_module_level=True,
    )

from sqlalchemy import Column, Integer, String, create_engine, select, text  # noqa: E402
from sqlalchemy.orm import declarative_base, sessionmaker  # noqa: E402

import app.models.init  # noqa: E402,F401
import app.models.solicitud_horario  # noqa: E402,F401
from app.busqueda import (  # noqa: E402
    filtro_texto,
    igual_normalizado,
    normaliza_rut,
    normaliza_texto,
    normalizar_busqueda,
    normalizar_rut,
)
from app.database import Base as BaseApp  # noqa: E402
from app.models.cita import Cita  # noqa: E402
from app.models.profesional import Profesional  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.routers import admin  # noqa: E402

BaseLocal = declarative_base()


class Muestra(BaseLocal):
    __tablename__ = "muestra"
    id = Column(Integer, primary_key=True)
    valor = Column(String)


CORPUS = [
    "José Pérez García", "JOSÉ PÉREZ GARCÍA", "Nutrición y Dietética", "NUTRICIÓN Y DIETÉTICA",
    "Ñandú", "ÑANDÚ", "ñu", "Pingüino", "PINGÜINO", "Françoise", "FRANÇOISE", "São João",
    "  espacios  extremos  ", "Jose  \t  Perez", "linea1\nlinea2", "cr\rlf", "ff\fvt\vx",
    "con\u00a0nbsp\u00a0\u00a0doble", "MAYÚSCULAS ÁÉÍÓÚ ÀÈÌÒÙ ÄËÏÖÜ ÂÊÎÔÛ ÃÕ", "minúsculas áéíóú àèìòù äëïöü âêîôû ãõ",
    "100%_real\\", "12.345.678-K", "", "   ", "\t\n", "a", "A", "ÁÁÁ",
]


@pytest.fixture()
def engine_pg():
    schema = f"test_busq_{uuid.uuid4().hex[:10]}"
    base = create_engine(TEST_POSTGRES_URL)
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(TEST_POSTGRES_URL, connect_args={"options": f"-csearch_path={schema}"})
    BaseLocal.metadata.create_all(bind=engine)
    BaseApp.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def test_la_normalizacion_sql_es_identica_a_la_de_python(engine_pg):
    db = sessionmaker(bind=engine_pg)()
    db.add_all([Muestra(valor=v) for v in CORPUS] + [Muestra(valor=None)])
    db.commit()

    filas = db.execute(select(Muestra.valor, normaliza_texto(Muestra.valor))).all()
    assert len(filas) == len(CORPUS) + 1

    for original, normalizado_sql in filas:
        if original is None:
            assert normalizado_sql is None
        else:
            assert normalizado_sql == normalizar_busqueda(original), repr(original)
    db.close()


def test_la_normalizacion_de_rut_sql_es_identica_a_la_de_python(engine_pg):
    ruts = ["12.345.678-9", "12345678-9", "12 345 678-9", "12.345.678-K", "12345678k", "1-9", ""]
    db = sessionmaker(bind=engine_pg)()
    db.add_all([Muestra(valor=r) for r in ruts])
    db.commit()

    for original, sql in db.execute(select(Muestra.valor, normaliza_rut(Muestra.valor))).all():
        assert sql == normalizar_rut(original), repr(original)
    db.close()


def test_los_datos_guardados_no_se_alteran_al_buscar(engine_pg):
    db = sessionmaker(bind=engine_pg)()
    db.add_all([Muestra(valor=v) for v in CORPUS])
    db.commit()
    antes = sorted(v for (v,) in db.execute(select(Muestra.valor)))

    db.execute(select(Muestra.id).where(filtro_texto([Muestra.valor], "  JOSE   PEREZ ")))
    db.commit()

    assert sorted(v for (v,) in db.execute(select(Muestra.valor))) == antes
    db.close()


@pytest.mark.parametrize("consulta", [
    "jose", "JOSE", "José", "jose perez", "JOSE PEREZ", "Jose  Perez", "  jose  ",
    "perez jose", "garcia", "nutricion", "nutricion y dietetica", "NUTRICION Y DIETETICA",
    "nandu", "ÑANDU", "pinguino", "francoise", "sao joao", "espacios extremos",
    "con nbsp doble", "linea1 linea2", "mayusculas aeiou", "100%", "_real", "\\", "%", "_",
    "12.345", "12345678", "xyz", "", "a",
])
def test_la_busqueda_da_el_mismo_resultado_que_la_referencia_python(engine_pg, consulta):
    db = sessionmaker(bind=engine_pg)()
    db.add_all([Muestra(valor=v) for v in CORPUS])
    db.commit()

    cond = filtro_texto([Muestra.valor], consulta, columnas_rut=[Muestra.valor])
    q = select(Muestra.valor) if cond is None else select(Muestra.valor).where(cond)
    obtenido = sorted(v for (v,) in db.execute(q))

    tokens = [t for t in normalizar_busqueda(consulta).split(" ") if t]
    esperado = sorted(
        v for v in CORPUS
        if all(
            t in normalizar_busqueda(v)
            or (normalizar_rut(t) and normalizar_rut(t) in normalizar_rut(v))
            for t in tokens
        )
    )
    assert obtenido == esperado, consulta
    db.close()


def test_igualdad_normalizada_en_postgres(engine_pg):
    db = sessionmaker(bind=engine_pg)()
    db.add_all([Muestra(valor=v) for v in ["Nutrición y Dietética", "NUTRICION  Y  DIETETICA", "Psicología", "Nutrición"]])
    db.commit()

    cond = igual_normalizado(Muestra.valor, "  nutricion y dietetica ")
    assert sorted(v for (v,) in db.execute(select(Muestra.valor).where(cond))) == [
        "NUTRICION  Y  DIETETICA", "Nutrición y Dietética",
    ]
    db.close()


# ── Endpoints reales de Reportes sobre PostgreSQL ─────────────────
def _poblar(db):
    sa = Usuario(correo="sa@sesaes.cl", password="x", rol="superadmin", nombre="Sofía")
    jose = Usuario(correo="j@sesaes.cl", password="x", rol="estudiante",
                   nombre="José Pérez García", rut="12.345.678-9", carrera="Kinesiología")
    alvaro = Usuario(correo="a@sesaes.cl", password="x", rol="estudiante",
                     nombre="ÁLVARO NÚÑEZ", rut="9876543-2", carrera="Diseño")
    maria = Profesional(nombre="Dra. María Núñez", especialidad="Nutrición y Dietética", iniciales="MN", estado="activo")
    andres = Profesional(nombre="Dr. Andrés", especialidad="Psicología", iniciales="AN", estado="activo")
    db.add_all([sa, jose, alvaro, maria, andres])
    db.flush()
    db.add_all([
        Cita(estudiante_id=jose.id, profesional_id=maria.id, fecha="2026-09-15", hora="10:00", estado="completada"),
        Cita(estudiante_id=alvaro.id, profesional_id=andres.id, fecha="2026-09-14", hora="09:30", estado="completada"),
    ])
    db.commit()
    return sa


def _historial(db, sa, **filtros):
    args = dict(estudiante=None, fecha_inicio=None, fecha_fin=None, especialidad=None,
                estado=None, profesional_id=None, carrera=None)
    args.update(filtros)
    return admin.get_historial_admin(db=db, current_user={"id": sa.id, "rol": "superadmin"}, **args)


def test_historial_tolerante_en_postgres_devuelve_los_originales(engine_pg):
    db = sessionmaker(bind=engine_pg)()
    sa = _poblar(db)

    for consulta in ("jose perez", "JOSE", "  perez   jose ", "garcia"):
        r = _historial(db, sa, estudiante=consulta)
        assert [c["estudiante"] for c in r] == ["José Pérez García"], consulta

    assert [c["estudiante"] for c in _historial(db, sa, estudiante="alvaro nunez")] == ["ÁLVARO NÚÑEZ"]
    # RUT con y sin formato, almacenado con y sin puntos.
    assert [c["rut"] for c in _historial(db, sa, estudiante="12345678-9")] == ["12.345.678-9"]
    assert [c["rut"] for c in _historial(db, sa, estudiante="9.876.543-2")] == ["9876543-2"]
    assert [c["especialidad"] for c in _historial(db, sa, especialidad="NUTRICION y dietetica")] == ["Nutrición y Dietética"]
    assert [c["carrera"] for c in _historial(db, sa, carrera="kinesio")] == ["Kinesiología"]
    db.close()


def test_grafico_tolerante_en_postgres(engine_pg):
    db = sessionmaker(bind=engine_pg)()
    sa = _poblar(db)
    cu = {"id": sa.id, "rol": "superadmin"}

    r = admin.get_grafico_especialidad(mes=None, anio=None, profesional_id=None,
                                       especialidad=None, carrera="KINESIOLOGIA", db=db, current_user=cu)
    assert [d["especialidad"] for d in r] == ["Nutrición y Dietética"]

    r2 = admin.get_grafico_especialidad(mes=None, anio=None, profesional_id=None,
                                        especialidad="psicologia", carrera=None, db=db, current_user=cu)
    assert [d["especialidad"] for d in r2] == ["Psicología"]
    db.close()
