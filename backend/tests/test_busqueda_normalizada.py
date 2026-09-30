# -*- coding: utf-8 -*-
"""
Tests — helper de búsqueda tolerante (app/busqueda.py).

La normalización sirve solo para COMPARAR. Se verifica: definición
canónica en Python, expresión SQL (SQLite aquí; PostgreSQL real en
test_busqueda_normalizada_postgres.py), coincidencia parcial, palabras en
cualquier orden, comodines literales, tolerancia de RUT y que ningún dato
original se modifique.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String, create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import declarative_base, sessionmaker

from app.busqueda import (
    DESTINO,
    ESPACIOS,
    ORIGEN,
    filtro_texto,
    igual_normalizado,
    normaliza_rut,
    normaliza_texto,
    normalizar_busqueda,
    normalizar_rut,
    tokens_busqueda,
)

Base = declarative_base()


class Persona(Base):
    __tablename__ = "persona"
    id = Column(Integer, primary_key=True)
    nombre = Column(String)
    rut = Column(String)
    carrera = Column(String)


DATOS = [
    ("José Pérez García", "12.345.678-9", "Nutrición y Dietética"),
    ("ÁLVARO NÚÑEZ", "9.876.543-2", "Psicología"),
    ("Ñandú Soto", "12345678-K", "Kinesiología"),
    ("Jose  Perez", "1-9", "Psicologia"),
    ("María  del   Carmen", "2-7", "Nutrición y Dietética"),
    ("Ana\tGómez\nLópez", "3-5", "Odontología"),
    ("Cien% Real_Nombre", "4-3", "Arte_Visual"),
    ("Constanza Muñoz", "5-1", "Ingeniería"),
    ("Nombre\u00a0Con\u00a0NBSP", "6-K", "Diseño"),
    (None, None, None),
]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([Persona(nombre=n, rut=r, carrera=c) for n, r, c in DATOS])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _buscar(db, texto, **kw):
    cond = filtro_texto([Persona.nombre], texto, columnas_rut=[Persona.rut], **kw)
    q = db.query(Persona.nombre)
    if cond is not None:
        q = q.filter(cond)
    return sorted(n for (n,) in q.all())


# ── Definición canónica (Python) ─────────────────────────────────
@pytest.mark.parametrize("entrada,esperado", [
    ("José Pérez García", "jose perez garcia"),
    ("JOSÉ PÉREZ GARCÍA", "jose perez garcia"),
    ("jose", "jose"),
    ("  jose  ", "jose"),
    ("Jose  Perez", "jose perez"),
    ("Jose \t\n Perez", "jose perez"),
    ("Nutrición y Dietética", "nutricion y dietetica"),
    ("NUTRICIÓN Y DIETÉTICA", "nutricion y dietetica"),
    ("Ñandú", "nandu"),
    ("ÑANDÚ", "nandu"),
    ("Pingüino", "pinguino"),
    ("Françoise", "francoise"),
    ("São João", "sao joao"),
    ("a\u00a0b", "a b"),
    ("", ""),
    ("   ", ""),
    (None, ""),
    (123, "123"),
    ("100%_real", "100%_real"),
])
def test_normalizar_busqueda(entrada, esperado):
    assert normalizar_busqueda(entrada) == esperado


def test_normalizar_busqueda_es_idempotente_y_no_muta_el_origen():
    original = "  José   PÉREZ\tGarcía "
    una_vez = normalizar_busqueda(original)
    assert normalizar_busqueda(una_vez) == una_vez
    assert original == "  José   PÉREZ\tGarcía "          # el original queda intacto


def test_toda_letra_acentuada_definida_tiene_su_equivalente_base():
    assert len(ORIGEN) == len(DESTINO)
    for origen, destino in zip(ORIGEN, DESTINO):
        assert normalizar_busqueda(origen) == destino.lower()
        assert destino.isascii() and destino.isalpha()


def test_todos_los_espacios_definidos_se_colapsan():
    for espacio in ESPACIOS:
        assert normalizar_busqueda(f"a{espacio}{espacio}b") == "a b"
        assert normalizar_busqueda(f"{espacio}a{espacio}") == "a"


@pytest.mark.parametrize("entrada,esperado", [
    ("12.345.678-9", "123456789"),
    ("12345678-9", "123456789"),
    ("12 345 678-9", "123456789"),
    ("12.345.678-K", "12345678k"),
    ("12345678k", "12345678k"),
    ("", ""),
    (None, ""),
])
def test_normalizar_rut(entrada, esperado):
    assert normalizar_rut(entrada) == esperado


def test_tokens_de_busqueda():
    assert tokens_busqueda("  José   PÉREZ ") == ["jose", "perez"]
    assert tokens_busqueda("") == []
    assert tokens_busqueda(None) == []
    assert tokens_busqueda(" \t\n ") == []


# ── Expresión SQL (SQLite) ───────────────────────────────────────
def test_la_columna_se_normaliza_en_la_consulta_sin_alterar_lo_guardado(db):
    r = db.execute(select(normaliza_texto(Persona.nombre)).where(Persona.id == 1)).scalar()
    assert r == "jose perez garcia"
    db.expire_all()
    assert db.query(Persona.nombre).filter(Persona.id == 1).scalar() == "José Pérez García"


def test_columna_nula_no_coincide_ni_rompe(db):
    assert None not in _buscar(db, "jose")
    assert db.execute(select(normaliza_texto(Persona.nombre)).where(Persona.id == 10)).scalar() is None


@pytest.mark.parametrize("consulta", [
    "jose", "JOSE", "José", "JOSÉ", "jose perez", "JOSE PEREZ", "Jose  Perez",
    "  jose  ", "perez jose", "garcia", "GARCÍA PÉREZ", "erez",
])
def test_jose_perez_garcia_se_encuentra_con_cualquier_escritura(db, consulta):
    assert "José Pérez García" in _buscar(db, consulta)


@pytest.mark.parametrize("consulta,esperado", [
    ("nunez", ["ÁLVARO NÚÑEZ"]),
    ("NÚÑEZ", ["ÁLVARO NÚÑEZ"]),
    ("alvaro nunez", ["ÁLVARO NÚÑEZ"]),
    ("nandu", ["Ñandú Soto"]),
    ("ÑANDU SOTO", ["Ñandú Soto"]),
    ("maria del carmen", ["María  del   Carmen"]),
    ("carmen   maria", ["María  del   Carmen"]),
    ("gomez lopez", ["Ana\tGómez\nLópez"]),
    ("con nbsp", ["Nombre\u00a0Con\u00a0NBSP"]),
    ("munoz", ["Constanza Muñoz"]),
    ("xyz", []),
])
def test_busquedas_tolerantes(db, consulta, esperado):
    assert _buscar(db, consulta) == esperado


def test_coincidencia_parcial_y_palabras_en_cualquier_orden(db):
    assert _buscar(db, "ala") == []
    assert "Constanza Muñoz" in _buscar(db, "stanz")
    assert _buscar(db, "perez garcia jose") == ["José Pérez García"]
    assert _buscar(db, "garcia zzz") == []              # todas las palabras deben cumplirse


def test_comodines_like_se_tratan_como_texto_literal(db):
    assert _buscar(db, "%") == ["Cien% Real_Nombre"]
    assert _buscar(db, "_") == ["Cien% Real_Nombre"]
    assert _buscar(db, "real_") == ["Cien% Real_Nombre"]
    assert _buscar(db, "cien%") == ["Cien% Real_Nombre"]
    assert _buscar(db, "\\") == []


def test_consulta_vacia_no_filtra():
    for vacia in ("", "   ", "\t\n", None):
        assert filtro_texto([Persona.nombre], vacia) is None


# ── RUT ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("consulta", [
    "12.345.678-9", "12345678-9", "123456789", "678-9", "12 345 678-9",
])
def test_rut_con_o_sin_formato_encuentra_el_almacenado_con_puntos(db, consulta):
    assert _buscar(db, consulta) == ["José Pérez García"]


@pytest.mark.parametrize("consulta", ["12.345", "12345", "345.678"])
def test_fragmento_de_rut_coincide_con_todos_los_que_lo_contienen(db, consulta):
    # 12.345.678-9 y 12345678-K comparten esos dígitos: ambos deben aparecer.
    assert _buscar(db, consulta) == ["José Pérez García", "Ñandú Soto"]


@pytest.mark.parametrize("consulta", ["12.345.678-K", "12345678-k", "12345678K"])
def test_rut_almacenado_sin_puntos_se_encuentra_con_puntos(db, consulta):
    assert _buscar(db, consulta) == ["Ñandú Soto"]


def test_signos_de_puntuacion_solos_no_coinciden_con_todos_los_ruts(db):
    # "." o "-" normalizados como RUT quedan vacíos: no deben comparar contra todo.
    assert _buscar(db, ".") == []
    assert _buscar(db, "-") == []


def test_rut_se_normaliza_en_la_columna_sin_alterarla(db):
    r = db.execute(select(normaliza_rut(Persona.rut)).where(Persona.id == 3)).scalar()
    assert r == "12345678k"
    assert db.query(Persona.rut).filter(Persona.id == 3).scalar() == "12345678-K"


# ── Igualdad normalizada ─────────────────────────────────────────
def test_igual_normalizado(db):
    def cuantas(valor):
        cond = igual_normalizado(Persona.carrera, valor)
        return db.query(Persona).filter(cond).count()

    assert cuantas("Nutrición y Dietética") == 2
    assert cuantas("NUTRICION  Y   DIETETICA") == 2
    assert cuantas("  nutricion y dietetica ") == 2
    assert cuantas("nutricion") == 0                       # igualdad, no parcial
    assert igual_normalizado(Persona.carrera, "") is None
    assert igual_normalizado(Persona.carrera, "   ") is None
    assert igual_normalizado(Persona.carrera, None) is None


# ── Compilación por dialecto ─────────────────────────────────────
def test_postgresql_usa_solo_funciones_del_nucleo():
    sql = str(normaliza_texto(Persona.nombre).compile(dialect=postgresql.dialect()))
    for funcion in ("translate(", "regexp_replace(", "lower(", "btrim("):
        assert funcion in sql
    assert "unaccent" not in sql.lower()                  # sin extensiones


def test_dialecto_no_soportado_falla_de_forma_explicita():
    with pytest.raises(NotImplementedError):
        str(normaliza_texto(Persona.nombre))


def test_la_funcion_sqlite_se_registra_en_toda_conexion_nueva():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        assert conn.exec_driver_sql("select sesaes_normaliza_texto('  ÁRBOL  ñu ')").scalar() == "arbol nu"
    engine.dispose()
