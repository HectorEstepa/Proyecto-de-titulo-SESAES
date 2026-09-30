# -*- coding: utf-8 -*-
"""
SESAES — Búsqueda tolerante para filtros de texto de Reportes.

La normalización sirve SOLO para COMPARAR. Nunca modifica el dato: la
columna se normaliza dentro de la consulta (no se guarda ni se devuelve
normalizada) y los valores que llegan al usuario y a las exportaciones son
siempre los originales.

Qué tolera una búsqueda:
  · mayúsculas/minúsculas;
  · tildes y diéresis (ñ→n, ü→u, ç→c y las vocales acentuadas);
  · espacios: iniciales/finales, múltiples y tabulaciones/saltos de línea;
  · coincidencia PARCIAL (subcadena);
  · palabras en CUALQUIER ORDEN ("perez jose" encuentra "José Pérez García");
  · `%`, `_` y `\\` se buscan como texto literal (no son comodines);
  · RUT con o sin puntos/guion/espacios: `12345678-9` ↔ `12.345.678-9`.

Definición canónica (idéntica en Python y en SQL)
─────────────────────────────────────────────────
  1. Cada carácter de ORIGEN se reemplaza por su equivalente de DESTINO
     (letras acentuadas → letra base, mayúscula y minúscula).
  2. Todo carácter de ESPACIOS (espacio, \\t, \\n, \\r, \\f, \\v y NBSP) se
     considera espacio; las rachas se colapsan en uno solo.
  3. Minúsculas y `strip`.

En PostgreSQL se usan solo funciones del núcleo (`translate`,
`regexp_replace`, `lower`, `btrim`): no requiere extensiones ni migración.
En SQLite (solo pruebas) SQLAlchemy emite una función registrada en la
conexión con la MISMA lógica Python; una cadena de `replace()` anidados
desborda el parser de SQLite.

Alcance de la tolerancia: letras latinas del español/portugués/francés
(ver ORIGEN). Otros diacríticos exóticos no se unifican.
"""

from __future__ import annotations

import re
import sqlite3

from sqlalchemy import String, and_, event, or_
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement, FunctionElement

# ── Definición canónica ──────────────────────────────────────────
ORIGEN = "áàäâãéèëêíìïîóòöôõúùüûñçÁÀÄÂÃÉÈËÊÍÌÏÎÓÒÖÔÕÚÙÜÛÑÇ"
DESTINO = "aaaaaeeeeiiiiooooouuuuncAAAAAEEEEIIIIOOOOOUUUUNC"
assert len(ORIGEN) == len(DESTINO)

ESPACIOS = " \t\n\r\f\v\u00a0"

_TABLA_ACENTOS = str.maketrans(ORIGEN, DESTINO)
_RE_ESPACIOS = re.compile(f"[{re.escape(ESPACIOS)}]+")
_RE_SEPARADORES_RUT = re.compile(r"[.\- ]")


# ── Normalización en Python (referencia y términos de búsqueda) ──
def normalizar_busqueda(valor: object) -> str:
    """Texto normalizado para COMPARAR. No modifica el original."""
    if valor is None:
        return ""
    texto = str(valor).translate(_TABLA_ACENTOS)
    return _RE_ESPACIOS.sub(" ", texto).lower().strip(ESPACIOS)


def normalizar_rut(valor: object) -> str:
    """RUT sin puntos, guion ni espacios y en minúscula: 12.345.678-K → 12345678k."""
    if valor is None:
        return ""
    return _RE_SEPARADORES_RUT.sub("", str(valor)).lower()


def tokens_busqueda(texto: object) -> list[str]:
    """Palabras normalizadas de la consulta (sin vacíos)."""
    return [t for t in normalizar_busqueda(texto).split(" ") if t]


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ── Normalización de la COLUMNA dentro de la consulta ────────────
class normaliza_texto(FunctionElement):
    """SQL: la columna normalizada, solo para comparar."""

    type = String()
    name = "normaliza_texto"
    inherit_cache = True


class normaliza_rut(FunctionElement):
    """SQL: la columna sin puntos/guion/espacios y en minúscula."""

    type = String()
    name = "normaliza_rut"
    inherit_cache = True


@compiles(normaliza_texto, "postgresql")
def _normaliza_texto_pg(element, compiler, **kw):
    columna = compiler.process(element.clauses, **kw)
    return (
        f"btrim(lower(regexp_replace("
        f"translate({columna}, '{ORIGEN}', '{DESTINO}'), "
        f"'[[:space:]\u00a0]+', ' ', 'g')), "
        f"' ')"
    )


@compiles(normaliza_texto, "sqlite")
def _normaliza_texto_sqlite(element, compiler, **kw):
    return f"sesaes_normaliza_texto({compiler.process(element.clauses, **kw)})"


@compiles(normaliza_texto)
def _normaliza_texto_generico(element, compiler, **kw):
    raise NotImplementedError(
        "normaliza_texto solo está definido para PostgreSQL y SQLite."
    )


@compiles(normaliza_rut)
def _normaliza_rut(element, compiler, **kw):
    # replace() anidado x3: portable (PostgreSQL y SQLite), sin funciones propias.
    columna = compiler.process(element.clauses, **kw)
    return f"lower(replace(replace(replace({columna}, '.', ''), '-', ''), ' ', ''))"


@event.listens_for(Engine, "connect")
def _registrar_funciones_sqlite(dbapi_connection, _record):
    """Registra la función de normalización en toda conexión SQLite (pruebas)."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function(
            "sesaes_normaliza_texto",
            1,
            lambda v: None if v is None else normalizar_busqueda(v),
            deterministic=True,
        )


# ── Filtros listos para usar en consultas ────────────────────────
def filtro_texto(
    columnas_texto: list,
    texto: object,
    columnas_rut: list | None = None,
) -> ColumnElement | None:
    """
    Condición de búsqueda tolerante, o None si la consulta está vacía
    (una consulta vacía no filtra).

    Cada palabra debe aparecer (parcialmente) en ALGUNA de las columnas;
    todas las palabras deben cumplirse (AND), en cualquier orden. Las
    columnas de RUT se comparan sin puntos/guion/espacios.
    """
    tokens = tokens_busqueda(texto)
    if not tokens:
        return None

    condiciones = []
    for token in tokens:
        alternativas = [
            normaliza_texto(c).like(f"%{_escapar_like(token)}%", escape="\\")
            for c in columnas_texto
        ]

        token_rut = normalizar_rut(token)
        if token_rut and columnas_rut:
            alternativas += [
                normaliza_rut(c).like(f"%{_escapar_like(token_rut)}%", escape="\\")
                for c in columnas_rut
            ]

        condiciones.append(or_(*alternativas))

    return and_(*condiciones)


def igual_normalizado(columna, valor: object) -> ColumnElement | None:
    """
    Igualdad tolerante (mayúsculas, tildes y espacios) para filtros que
    reciben un valor completo, p. ej. especialidad. None si el valor está
    vacío (no filtra).
    """
    objetivo = normalizar_busqueda(valor)
    if not objetivo:
        return None
    return normaliza_texto(columna) == objetivo
