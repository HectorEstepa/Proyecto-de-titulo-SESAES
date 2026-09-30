# -*- coding: utf-8 -*-
"""
Tests — Reportes: filtros de historial y exportaciones (CGR y alumnos).

Cubre lo que YA existe en el backend:
  · GET /admin/historial            (filtros que alimentan Historial y su Excel)
  · GET /admin/exportar/cgr         (Atenciones CGR)
  · GET /admin/exportar/alumnos     (Listado de alumnos)

Verifica: columnas esperadas, separación de campos (una celda = un dato),
conservación de tildes/ñ/mayúsculas, respeto de filtros y ausencia de datos
concatenados. Lo que TODAVÍA NO existe (hoy solo el .xlsx del CGR, ver el
último xfail) se registra con xfail(strict=True): al implementarse fallará
y avisará para retirar la marca (no se simula).

Patrón del proyecto: SQLite en memoria + endpoints llamados como funciones.
"""

from __future__ import annotations

import asyncio
import inspect
import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401 — registra todos los modelos
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rbac.permissions import Permission
from app.routers import admin

BOM = b"\xef\xbb\xbf"
HEADERS_CGR = [
    "Nombre Completo", "RUT", "Tipo de Atención", "Fecha", "Hora",
    "Medicamento Suministrado", "Profesional que Atendió",
]
HEADERS_ALUMNOS = ["Nombre Completo", "RUT", "Carrera", "Correo"]


# ══════════════════════════════════════
# Fixtures / helpers
# ══════════════════════════════════════

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


_n = {"i": 0}


def _usuario(db, rol="estudiante", *, nombre, rut=None, carrera=None, correo=None):
    _n["i"] += 1
    u = Usuario(
        correo=correo or f"u{_n['i']}@sesaes.cl",
        password="hash", rol=rol, nombre=nombre, rut=rut, carrera=carrera,
    )
    db.add(u)
    db.flush()
    return u


def _prof(db, nombre, especialidad):
    p = Profesional(nombre=nombre, especialidad=especialidad,
                    iniciales=nombre[:2].upper(), estado="activo")
    db.add(p)
    db.flush()
    return p


def _cita(db, est, prof, fecha, hora="10:00", estado="completada", medicamento=None):
    c = Cita(estudiante_id=est.id, profesional_id=prof.id, fecha=fecha,
             hora=hora, estado=estado, medicamento=medicamento)
    db.add(c)
    db.flush()
    return c


def _cuerpo(respuesta) -> bytes:
    async def leer():
        return b"".join([c async for c in respuesta.body_iterator])
    return asyncio.run(leer())


def _tabla(respuesta) -> list[list[str]]:
    """Cuerpo TSV → matriz de celdas (decodifica UTF-8 con BOM)."""
    texto = _cuerpo(respuesta).decode("utf-8-sig")
    return [linea.split("\t") for linea in texto.split("\n")]


def _historial(db, sa, **filtros):
    args = dict(estudiante=None, fecha_inicio=None, fecha_fin=None,
                especialidad=None, estado=None, profesional_id=None, carrera=None)
    args.update(filtros)
    return admin.get_historial_admin(db=db, current_user={"id": sa.id, "rol": "superadmin"}, **args)


@pytest.fixture()
def escenario(db):
    sa = _usuario(db, "superadmin", nombre="Sofía Súper")
    jose = _usuario(db, nombre="José Pérez García", rut="12.345.678-9", carrera="Kinesiología")
    alvaro = _usuario(db, nombre="ÁLVARO NÚÑEZ", rut="9.876.543-2", carrera="Diseño")
    nandu = _usuario(db, nombre="Ñandú Soto", rut="18.000.000-0", carrera="Derecho")
    excluido = _usuario(db, nombre="Excluido Prueba", rut="16.458.880-7", carrera="Prueba")

    maria = _prof(db, "Dra. María Núñez", "Nutrición y Dietética")
    andres = _prof(db, "Dr. Andrés de la Fuente", "Psicología")

    _cita(db, jose, maria, "2026-09-15", "10:00", "completada")
    _cita(db, alvaro, andres, "2026-09-14", "09:30", "completada", "Paracetamol")
    _cita(db, nandu, maria, "2026-09-13", "15:45", "pendiente")
    _cita(db, jose, andres, "2026-08-20", "11:15", "cancelada")
    _cita(db, nandu, andres, "2025-12-05", "12:00", "completada")   # año anterior
    _cita(db, excluido, maria, "2026-09-10", "08:00", "completada")  # RUT excluido CGR
    db.commit()

    return dict(db=db, sa=sa, jose=jose, alvaro=alvaro, nandu=nandu, maria=maria, andres=andres)


# ══════════════════════════════════════
# /admin/historial — filtros
# ══════════════════════════════════════

def test_historial_sin_filtros_devuelve_todo_ordenado_por_fecha_desc(escenario):
    r = _historial(escenario["db"], escenario["sa"])
    fechas = [c["fecha"] for c in r]
    assert len(r) == 6
    assert fechas == sorted(fechas, reverse=True)


def test_historial_filtra_por_estado(escenario):
    r = _historial(escenario["db"], escenario["sa"], estado="cancelada")
    assert [c["estudiante"] for c in r] == ["José Pérez García"]
    assert {c["estado"] for c in _historial(escenario["db"], escenario["sa"], estado="pendiente")} == {"pendiente"}


def test_historial_filtra_por_rango_de_fechas_inclusivo(escenario):
    r = _historial(escenario["db"], escenario["sa"],
                   fecha_inicio="2026-09-13", fecha_fin="2026-09-15")
    assert sorted(c["fecha"] for c in r) == ["2026-09-13", "2026-09-14", "2026-09-15"]


def test_historial_filtra_por_especialidad(escenario):
    r = _historial(escenario["db"], escenario["sa"], especialidad="Psicología")
    assert {c["especialidad"] for c in r} == {"Psicología"}
    assert len(r) == 3


def test_historial_filtra_por_profesional(escenario):
    r = _historial(escenario["db"], escenario["sa"], profesional_id=escenario["maria"].id)
    assert {c["profesional"] for c in r} == {"Dra. María Núñez"}


def test_historial_filtra_por_estudiante_nombre_y_rut(escenario):
    db, sa = escenario["db"], escenario["sa"]
    assert {c["estudiante"] for c in _historial(db, sa, estudiante="García")} == {"José Pérez García"}
    assert {c["estudiante"] for c in _historial(db, sa, estudiante="9.876.543")} == {"ÁLVARO NÚÑEZ"}


def test_historial_filtra_por_carrera_parcial(escenario):
    r = _historial(escenario["db"], escenario["sa"], carrera="derec")
    assert {c["estudiante"] for c in r} == {"Ñandú Soto"}


def test_historial_combina_filtros_con_AND(escenario):
    r = _historial(escenario["db"], escenario["sa"],
                   estado="completada", especialidad="Psicología",
                   fecha_inicio="2026-01-01")
    assert [c["estudiante"] for c in r] == ["ÁLVARO NÚÑEZ"]
    assert _historial(escenario["db"], escenario["sa"],
                      estado="cancelada", especialidad="Nutrición y Dietética") == []


def test_historial_devuelve_cada_dato_en_su_campo_y_sin_alterar_el_original(escenario):
    (fila,) = _historial(escenario["db"], escenario["sa"],
                         estudiante="García", fecha_inicio="2026-09-01")

    assert fila["estudiante"] == "José Pérez García"          # tildes/mayúsculas intactas
    assert fila["especialidad"] == "Nutrición y Dietética"
    assert fila["profesional"] == "Dra. María Núñez"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fila["fecha"])   # fecha sola
    assert re.fullmatch(r"\d{2}:\d{2}", fila["hora"])          # hora sola
    for campo in ("estudiante", "rut", "carrera", "especialidad", "profesional", "estado"):
        assert "\t" not in fila[campo] and "\n" not in fila[campo]


def test_historial_conserva_mayusculas_y_ene_originales(escenario):
    nombres = {c["estudiante"] for c in _historial(escenario["db"], escenario["sa"])}
    assert {"ÁLVARO NÚÑEZ", "Ñandú Soto", "José Pérez García"} <= nombres


def test_historial_busqueda_ignora_mayusculas_ascii(escenario):
    db, sa = escenario["db"], escenario["sa"]
    assert {c["estudiante"] for c in _historial(db, sa, estudiante="SOTO")} == {"Ñandú Soto"}
    assert {c["estudiante"] for c in _historial(db, sa, estudiante="soto")} == {"Ñandú Soto"}


# ── Búsqueda tolerante (Reportes) ──────────────────────────────────
# La normalización solo COMPARA: los valores devueltos (y por tanto los
# exportados) son los originales. Cobertura detallada del helper en
# test_busqueda_normalizada.py; aquí se comprueba el comportamiento de
# extremo a extremo de /admin/historial y /admin/graficos/especialidad.

def _estudiantes(filas):
    return sorted(c["estudiante"] for c in filas)


@pytest.mark.parametrize("consulta", [
    "jose", "JOSE", "José", "JOSÉ", "jose perez", "JOSE PEREZ", "Jose  Perez",
    "  jose  ", "pérez garcía", "garcia jose", "perez jose", "PEREZ", "gar",
])
def test_historial_encuentra_jose_perez_garcia_con_cualquier_escritura(escenario, consulta):
    r = _historial(escenario["db"], escenario["sa"], estudiante=consulta,
                   fecha_inicio="2026-09-01")
    assert _estudiantes(r) == ["José Pérez García"]      # valor ORIGINAL


def test_historial_busqueda_sin_tildes_encuentra_con_tildes(escenario):
    r = _historial(escenario["db"], escenario["sa"], estudiante="jose perez")
    assert {c["estudiante"] for c in r} == {"José Pérez García"}
    assert {c["estudiante"] for c in _historial(escenario["db"], escenario["sa"], estudiante="nunez")} == {"ÁLVARO NÚÑEZ"}
    assert {c["estudiante"] for c in _historial(escenario["db"], escenario["sa"], estudiante="NANDU")} == {"Ñandú Soto"}


def test_historial_busqueda_ignora_espacios_multiples(db):
    sa = _usuario(db, "superadmin", nombre="Sofía")
    est = _usuario(db, nombre="Jose Perez", rut="1-9", carrera="X")
    p = _prof(db, "Dr. X", "Psicologia")
    _cita(db, est, p, "2026-09-15")
    db.commit()

    assert len(_historial(db, sa, estudiante="jose    perez")) == 1
    assert len(_historial(db, sa, estudiante="jose\tperez")) == 1


def test_historial_busqueda_ignora_espacios_iniciales_y_finales(db):
    sa = _usuario(db, "superadmin", nombre="Sofía")
    est = _usuario(db, nombre="Jose Perez", rut="1-9", carrera="X")
    p = _prof(db, "Dr. X", "Psicologia")
    _cita(db, est, p, "2026-09-15")
    db.commit()

    assert len(_historial(db, sa, estudiante="  jose ")) == 1
    assert len(_historial(db, sa, estudiante="\tjose perez\n")) == 1


def test_historial_filtro_de_especialidad_tolerante(escenario):
    esperadas = _historial(escenario["db"], escenario["sa"], especialidad="Nutrición y Dietética")
    assert len(esperadas) == 3

    for consulta in ("nutricion y dietetica", "NUTRICION Y DIETETICA", "  Nutrición   y  Dietética ", "nUtRiCiÓn y DiEtÉtIcA"):
        r = _historial(escenario["db"], escenario["sa"], especialidad=consulta)
        assert len(r) == 3, consulta
        # El dato mostrado es el original, no el normalizado.
        assert {c["especialidad"] for c in r} == {"Nutrición y Dietética"}

    # Es igualdad normalizada (no parcial): "nutricion" no coincide con la especialidad completa.
    assert _historial(escenario["db"], escenario["sa"], especialidad="nutricion") == []


def test_historial_busqueda_por_carrera_tolerante_y_parcial(escenario):
    db, sa = escenario["db"], escenario["sa"]
    assert _estudiantes(_historial(db, sa, carrera="KINESIOLOGIA")) == ["José Pérez García", "José Pérez García"]
    assert _estudiantes(_historial(db, sa, carrera="kinesio")) == ["José Pérez García", "José Pérez García"]
    assert {c["carrera"] for c in _historial(db, sa, carrera="kinesiologia")} == {"Kinesiología"}


@pytest.mark.parametrize("consulta", [
    "12345678-9", "12.345.678-9", "123456789", "12.345", "12345", "345.678", "678-9",
])
def test_historial_rut_con_o_sin_formato(escenario, consulta):
    r = _historial(escenario["db"], escenario["sa"], estudiante=consulta)
    assert {c["rut"] for c in r} == {"12.345.678-9"}      # se muestra el RUT original


def test_historial_rut_almacenado_sin_puntos_se_encuentra_con_puntos(db):
    sa = _usuario(db, "superadmin", nombre="Sofía")
    est = _usuario(db, nombre="Sin Puntos", rut="12345678-9", carrera="X")
    _cita(db, est, _prof(db, "Dr. X", "Psicología"), "2026-09-15")
    db.commit()

    for consulta in ("12.345.678-9", "12345678-9", "12345678", "12.345.678"):
        r = _historial(db, sa, estudiante=consulta)
        assert [c["rut"] for c in r] == ["12345678-9"], consulta     # original intacto


def test_historial_rut_con_k_mayuscula_o_minuscula(escenario):
    db = escenario["db"]
    con_k = _usuario(db, nombre="Constanza Muñoz", rut="20.111.222-K", carrera="Ingeniería")
    _cita(db, con_k, escenario["maria"], "2026-09-17", "16:00", "pendiente")
    db.commit()

    for consulta in ("20.111.222-K", "20111222-k", "20111222K", "201112"):
        r = _historial(db, escenario["sa"], estudiante=consulta)
        assert {c["rut"] for c in r} == {"20.111.222-K"}, consulta


def test_historial_comodines_se_buscan_como_texto_literal(db):
    sa = _usuario(db, "superadmin", nombre="Sofía")
    a = _usuario(db, nombre="Cien% Real", rut="1-9", carrera="Arte_Visual")
    b = _usuario(db, nombre="Otro Nombre", rut="2-7", carrera="ArteXVisual")
    p = _prof(db, "Dr. X", "Psicología")
    _cita(db, a, p, "2026-09-15")
    _cita(db, b, p, "2026-09-16")
    db.commit()

    assert _estudiantes(_historial(db, sa, estudiante="%")) == ["Cien% Real"]      # no es comodín
    assert _estudiantes(_historial(db, sa, estudiante="cien%")) == ["Cien% Real"]
    assert _estudiantes(_historial(db, sa, carrera="arte_visual")) == ["Cien% Real"]   # "_" literal
    assert _historial(db, sa, estudiante="\\") == []


def test_historial_consulta_vacia_o_de_espacios_no_filtra(escenario):
    todas = len(_historial(escenario["db"], escenario["sa"]))
    for vacia in ("", "   ", "\t\n"):
        assert len(_historial(escenario["db"], escenario["sa"], estudiante=vacia)) == todas
        assert len(_historial(escenario["db"], escenario["sa"], carrera=vacia)) == todas
        assert len(_historial(escenario["db"], escenario["sa"], especialidad=vacia)) == todas


def test_historial_la_busqueda_no_altera_los_datos_ni_lo_devuelto(escenario):
    db, sa = escenario["db"], escenario["sa"]
    antes = {u.id: (u.nombre, u.rut, u.carrera) for u in db.query(Usuario).all()}

    r = _historial(db, sa, estudiante="  JOSE   PEREZ  ", carrera="KINESIOLOGIA",
                   especialidad="nutricion y dietetica")

    assert [(c["estudiante"], c["rut"], c["carrera"], c["especialidad"]) for c in r] == [
        ("José Pérez García", "12.345.678-9", "Kinesiología", "Nutrición y Dietética")
    ]
    db.expire_all()
    assert {u.id: (u.nombre, u.rut, u.carrera) for u in db.query(Usuario).all()} == antes


def test_historial_busqueda_se_combina_con_los_demas_filtros(escenario):
    db, sa = escenario["db"], escenario["sa"]
    r = _historial(db, sa, estudiante="jose", estado="cancelada", especialidad="PSICOLOGIA",
                   fecha_inicio="2026-08-01", fecha_fin="2026-08-31")
    assert [(c["estudiante"], c["estado"], c["fecha"]) for c in r] == [("José Pérez García", "cancelada", "2026-08-20")]
    assert _historial(db, sa, estudiante="jose", estado="pendiente") == []


def test_busqueda_devuelve_lo_mismo_que_se_exportaria_sin_normalizar(escenario):
    """El Excel se arma con lo que devuelve /historial: valores originales."""
    r = _historial(escenario["db"], escenario["sa"], estudiante="alvaro nunez")
    assert [c["estudiante"] for c in r] == ["ÁLVARO NÚÑEZ"]        # mayúsculas y tildes originales


# ── /admin/graficos/especialidad ───────────────────────────────────
def _grafico(esc, **filtros):
    args = dict(mes=None, anio=None, profesional_id=None, especialidad=None, carrera=None)
    args.update(filtros)
    return admin.get_grafico_especialidad(
        db=esc["db"], current_user={"id": esc["sa"].id, "rol": "superadmin"}, **args)


def test_grafico_filtra_por_carrera_tolerante(escenario):
    esperado = _grafico(escenario, carrera="Kinesiología")
    for consulta in ("kinesiologia", "KINESIOLOGIA", "kinesio", "  Kinesiología  "):
        assert _grafico(escenario, carrera=consulta) == esperado, consulta
    assert esperado != _grafico(escenario)


def test_grafico_filtra_por_especialidad_tolerante_y_conserva_la_etiqueta_original(escenario):
    r = _grafico(escenario, especialidad="NUTRICION  y dietetica")
    assert [d["especialidad"] for d in r] == ["Nutrición y Dietética"]
    assert r == _grafico(escenario, especialidad="Nutrición y Dietética")


def test_grafico_sin_filtros_no_cambia(escenario):
    r = _grafico(escenario)
    assert {d["especialidad"] for d in r} == {"Nutrición y Dietética", "Psicología"}
    assert sum(d["cantidad"] for d in r) == 5      # pendiente+completada; sin la cancelada


# ══════════════════════════════════════
# /admin/exportar/cgr
# ══════════════════════════════════════

def _cgr(esc, anio=2026, fecha_fin=None):
    return admin.exportar_cgr(anio=anio, fecha_fin=fecha_fin, db=esc["db"],
                              current_user={"id": esc["sa"].id, "rol": "superadmin"})


def test_cgr_tiene_las_columnas_esperadas(escenario):
    tabla = _tabla(_cgr(escenario))
    assert tabla[0] == HEADERS_CGR


def test_cgr_una_fila_por_atencion_con_cada_dato_en_su_celda(escenario):
    tabla = _tabla(_cgr(escenario))
    filas = tabla[1:]

    assert all(len(f) == len(HEADERS_CGR) for f in filas)   # sin columnas corridas
    por_rut = {f[1]: f for f in filas}
    assert por_rut["12.345.678-9"] == [
        "José Pérez García",           # Nombre Completo
        "12.345.678-9",                # RUT
        "Nutrición y Dietética",       # Tipo de Atención
        "2026-09-15",                  # Fecha
        "10:00",                       # Hora
        "No aplica",                   # Medicamento
        "Dra. María Núñez",            # Profesional
    ]
    assert por_rut["9.876.543-2"][5] == "Paracetamol"


def test_cgr_solo_incluye_atenciones_completadas(escenario):
    filas = _tabla(_cgr(escenario))[1:]
    # 2026: completadas = José(15/09), Álvaro(14/09) [+ Excluido, que se omite].
    assert {f[0] for f in filas} == {"José Pérez García", "ÁLVARO NÚÑEZ"}
    assert "Ñandú Soto" not in {f[0] for f in filas}      # su cita 2026 es pendiente


def test_cgr_respeta_el_filtro_de_anio(escenario):
    f26 = _tabla(_cgr(escenario, anio=2026))[1:]
    f25 = _tabla(_cgr(escenario, anio=2025))[1:]

    assert {f[3][:4] for f in f26} == {"2026"}
    assert [f[0] for f in f25] == ["Ñandú Soto"]
    assert _tabla(_cgr(escenario, anio=2024))[1:] == []      # solo encabezado


def test_cgr_respeta_fecha_fin_inclusiva(escenario):
    filas = _tabla(_cgr(escenario, fecha_fin="2026-09-14"))[1:]
    assert [f[3] for f in filas] == ["2026-09-14"]


def test_cgr_excluye_los_ruts_de_prueba(escenario):
    ruts = {f[1] for f in _tabla(_cgr(escenario))[1:]}
    assert "16.458.880-7" not in ruts


def test_cgr_ordena_por_fecha_ascendente(escenario):
    fechas = [f[3] for f in _tabla(_cgr(escenario))[1:]]
    assert fechas == sorted(fechas)


def test_cgr_conserva_tildes_enes_y_mayusculas_con_bom_utf8(escenario):
    crudo = _cuerpo(_cgr(escenario))

    assert crudo.startswith(BOM)                          # Excel detecta UTF-8
    texto = crudo.decode("utf-8-sig")
    for esperado in ("José Pérez García", "Nutrición y Dietética", "Dra. María Núñez",
                     "Tipo de Atención", "Profesional que Atendió", "ÁLVARO NÚÑEZ"):
        assert esperado in texto, esperado
    assert "\ufffd" not in texto and "Ã" not in texto


def test_cgr_no_concatena_campos(escenario):
    for fila in _tabla(_cgr(escenario))[1:]:
        nombre, rut, atencion, fecha, hora, _med, prof = fila
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha)
        assert re.fullmatch(r"\d{2}:\d{2}", hora)
        assert nombre not in (atencion, prof, rut)
        for celda in fila:
            assert " - " not in celda and ";" not in celda


def test_cgr_un_valor_con_tabulacion_o_salto_no_desplaza_columnas(escenario):
    db = escenario["db"]
    raro = _usuario(db, nombre="Ana\tPérez\nGómez", rut="11.111.111-1", carrera="X")
    _cita(db, raro, escenario["maria"], "2026-09-16", "10:30", "completada",
          medicamento="Ibuprofeno\t400mg\r\ncada 8h")
    db.commit()

    filas = _tabla(_cgr(escenario))[1:]
    fila = next(f for f in filas if f[1] == "11.111.111-1")

    assert len(fila) == len(HEADERS_CGR)
    assert fila[0] == "Ana Pérez Gómez"
    assert fila[5] == "Ibuprofeno 400mg  cada 8h"
    assert all(len(f) == len(HEADERS_CGR) for f in filas)


def test_cgr_nombre_de_archivo_refleja_los_filtros(escenario):
    r = _cgr(escenario, anio=2026, fecha_fin="2026-05-31")
    assert "cgr_atenciones_2026_hasta_2026-05-31.xls" in r.headers["content-disposition"]
    assert "cgr_atenciones_2026.xls" in _cgr(escenario).headers["content-disposition"]


def test_cgr_sigue_exigiendo_su_permiso_reservado():
    dependencia = inspect.signature(admin.exportar_cgr).parameters["current_user"].default.dependency
    assert inspect.getclosurevars(dependencia).nonlocals["permission"] == Permission.REPORTES_CGR_EXPORTAR
    dependencia = inspect.signature(admin.exportar_listado_alumnos).parameters["current_user"].default.dependency
    assert inspect.getclosurevars(dependencia).nonlocals["permission"] == Permission.REPORTES_CGR_EXPORTAR


# ══════════════════════════════════════
# /admin/exportar/cgr/datos  (B2: filas para armar el .xlsx en el frontend)
# ══════════════════════════════════════

def _cgr_datos(esc, anio=2026, fecha_fin=None):
    return admin.exportar_cgr_datos(anio=anio, fecha_fin=fecha_fin, db=esc["db"],
                                    current_user={"id": esc["sa"].id, "rol": "superadmin"})


def _tsv_filas(respuesta):
    return _tabla(respuesta)[1:]


def _sanear(filas):
    """Lo que el texto tabulado hace con cada valor (única diferencia con el JSON)."""
    return [[admin._celda_tsv(v) for v in fila] for fila in filas]


def test_datos_cgr_tienen_las_columnas_esperadas_en_orden_fijo(escenario):
    r = _cgr_datos(escenario)
    assert r["columnas"] == HEADERS_CGR == [
        "Nombre Completo", "RUT", "Tipo de Atención", "Fecha", "Hora",
        "Medicamento Suministrado", "Profesional que Atendió",
    ]


def test_datos_cgr_una_fila_por_atencion_y_un_valor_por_campo(escenario):
    r = _cgr_datos(escenario)

    assert r["total"] == len(r["filas"]) == 2
    assert all(len(f) == len(HEADERS_CGR) for f in r["filas"])
    por_rut = {f[1]: f for f in r["filas"]}
    assert por_rut["12.345.678-9"] == [
        "José Pérez García", "12.345.678-9", "Nutrición y Dietética",
        "2026-09-15", "10:00", "No aplica", "Dra. María Núñez",
    ]
    assert por_rut["9.876.543-2"][5] == "Paracetamol"


def test_datos_cgr_son_las_mismas_filas_que_el_texto_tabulado(escenario):
    """Una sola fuente de reglas: el JSON y el TSV entregan las mismas filas."""
    for anio, fin in ((2026, None), (2026, "2026-09-14"), (2025, None), (2024, None)):
        json_filas = _cgr_datos(escenario, anio, fin)["filas"]
        tsv = _tsv_filas(_cgr(escenario, anio=anio, fecha_fin=fin))
        assert _sanear(json_filas) == ([] if json_filas == [] else tsv), (anio, fin)


def test_datos_cgr_fecha_y_hora_van_separadas_y_sin_transformar(escenario):
    for fila in _cgr_datos(escenario)["filas"]:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fila[HEADERS_CGR.index("Fecha")])
        assert re.fullmatch(r"\d{2}:\d{2}", fila[HEADERS_CGR.index("Hora")])


def test_datos_cgr_solo_atenciones_completadas(escenario):
    nombres = {f[0] for f in _cgr_datos(escenario)["filas"]}
    assert nombres == {"José Pérez García", "ÁLVARO NÚÑEZ"}          # ni pendiente ni cancelada


def test_datos_cgr_respeta_el_filtro_de_anio(escenario):
    assert {f[3][:4] for f in _cgr_datos(escenario, 2026)["filas"]} == {"2026"}
    assert [f[0] for f in _cgr_datos(escenario, 2025)["filas"]] == ["Ñandú Soto"]
    vacio = _cgr_datos(escenario, 2024)
    assert vacio == {"columnas": HEADERS_CGR, "filas": [], "total": 0}


def test_datos_cgr_fecha_fin_es_inclusiva(escenario):
    assert [f[3] for f in _cgr_datos(escenario, fecha_fin="2026-09-14")["filas"]] == ["2026-09-14"]
    assert [f[3] for f in _cgr_datos(escenario, fecha_fin="2026-09-15")["filas"]] == ["2026-09-14", "2026-09-15"]
    assert _cgr_datos(escenario, fecha_fin="2026-09-13")["filas"] == []


def test_datos_cgr_orden_ascendente_por_fecha_y_hora(escenario):
    db = escenario["db"]
    est = _usuario(db, nombre="Orden Prueba", rut="30.000.000-1", carrera="X")
    for hora in ("16:00", "08:15", "12:00"):
        _cita(db, est, escenario["maria"], "2026-09-20", hora, "completada")
    db.commit()

    filas = _cgr_datos(escenario)["filas"]
    claves = [(f[3], f[4]) for f in filas]

    assert claves == sorted(claves)
    assert [f[4] for f in filas if f[3] == "2026-09-20"] == ["08:15", "12:00", "16:00"]


def test_datos_cgr_conservan_exactamente_las_dos_exclusiones_de_rut(escenario):
    assert admin.RUTS_EXCLUIDOS_CGR == {"16.458.880-7", "19.741.131-7"}
    db = escenario["db"]
    otro = _usuario(db, nombre="Segundo Excluido", rut="19.741.131-7", carrera="X")
    _cita(db, otro, escenario["andres"], "2026-09-11", "10:00", "completada")
    db.commit()

    ruts = {f[1] for f in _cgr_datos(escenario)["filas"]}
    assert "16.458.880-7" not in ruts and "19.741.131-7" not in ruts
    assert {"12.345.678-9", "9.876.543-2"} <= ruts             # el resto sí entra


def test_datos_cgr_semantica_de_vacios_no_aplica_y_guion(escenario):
    db = escenario["db"]
    sin_datos = _usuario(db, nombre=None, rut=None, carrera=None)
    prof_sin_esp = _prof(db, "Dr. Sin Especialidad", None)
    _cita(db, sin_datos, prof_sin_esp, "2026-09-21", "09:00", "completada", medicamento=None)
    _cita(db, sin_datos, prof_sin_esp, "2026-09-22", "09:00", "completada", medicamento="")
    _cita(db, sin_datos, prof_sin_esp, "2026-09-23", "09:00", "completada", medicamento="Ibuprofeno 400mg")
    db.commit()

    filas = {f[3]: f for f in _cgr_datos(escenario)["filas"]}

    ausente = filas["2026-09-21"]
    assert ausente[0] == "—"                          # nombre ausente
    assert ausente[1] == "—"                          # RUT ausente
    assert ausente[2] == "—"                          # especialidad ausente
    assert ausente[5] == "No aplica"                  # sin medicamento (None)
    assert filas["2026-09-22"][5] == "No aplica"      # sin medicamento ("")
    assert filas["2026-09-23"][5] == "Ibuprofeno 400mg"
    # Nunca se reemplaza por una cadena vacía.
    assert all(v != "" for f in filas.values() for v in f)


def test_datos_cgr_conservan_unicode_y_capitalizacion_originales(escenario):
    db = escenario["db"]
    est = _usuario(db, nombre="ÑANDÚ  DE LA Fuente", rut="31.000.000-K", carrera="Diseño")
    _cita(db, est, escenario["maria"], "2026-09-24", "10:00", "completada", "Ácido fólico 5 mg")
    db.commit()

    texto = " | ".join(v for f in _cgr_datos(escenario)["filas"] for v in f)
    for esperado in ("José Pérez García", "ÁLVARO NÚÑEZ", "ÑANDÚ  DE LA Fuente", "Nutrición y Dietética",
                     "Dra. María Núñez", "Dr. Andrés de la Fuente", "Ácido fólico 5 mg", "31.000.000-K"):
        assert esperado in texto, esperado
    assert "\ufffd" not in texto and "Ã" not in texto


def test_datos_cgr_no_usan_la_normalizacion_de_busqueda(escenario):
    from app.busqueda import normalizar_busqueda

    # Se usa la búsqueda tolerante sobre los mismos datos…
    assert _historial(escenario["db"], escenario["sa"], estudiante="  ALVARO   NUNEZ ")
    filas = _cgr_datos(escenario)["filas"]

    # …pero lo exportado sigue siendo el valor original, no el normalizado.
    for fila in filas:
        for valor in (fila[0], fila[2], fila[6]):
            assert valor != normalizar_busqueda(valor), valor
    assert "ÁLVARO NÚÑEZ" in [f[0] for f in filas]
    assert "alvaro nunez" not in [f[0] for f in filas]


def test_datos_cgr_no_sanean_los_valores_para_el_xlsx(escenario):
    """El saneamiento de tabulaciones es del texto tabulado; el JSON entrega el dato original."""
    db = escenario["db"]
    raro = _usuario(db, nombre="Ana\tPérez\nGómez", rut="11.111.111-1", carrera="X")
    _cita(db, raro, escenario["maria"], "2026-09-16", "10:30", "completada")
    db.commit()

    fila = next(f for f in _cgr_datos(escenario)["filas"] if f[1] == "11.111.111-1")
    assert fila[0] == "Ana\tPérez\nGómez"
    tsv = next(f for f in _tsv_filas(_cgr(escenario)) if f[1] == "11.111.111-1")
    assert tsv[0] == "Ana Pérez Gómez"


def test_datos_cgr_usan_una_cantidad_constante_de_consultas(escenario):
    from sqlalchemy import event

    def contar():
        escenario["db"].refresh(escenario["sa"])    # el usuario de prueba no cuenta
        sentencias = []
        motor = escenario["db"].get_bind()
        escucha = lambda c, cur, st, p, ctx, m: sentencias.append(st)
        event.listen(motor, "before_cursor_execute", escucha)
        try:
            _cgr_datos(escenario)
            _alumnos_datos(escenario)
        finally:
            event.remove(motor, "before_cursor_execute", escucha)
        return len(sentencias)

    pocas = contar()
    db = escenario["db"]
    for i in range(25):
        est = _usuario(db, nombre=f"Masivo {i}", rut=f"4{i:07d}-1", carrera="X")
        _cita(db, est, escenario["maria"], "2026-09-25", f"{8 + i % 10:02d}:00", "completada")
    db.commit()

    assert contar() == pocas                       # sin consultas por fila (N+1)
    assert pocas == 2                              # una consulta por endpoint


@pytest.mark.parametrize("endpoint", ["exportar_cgr_datos", "exportar_listado_alumnos_datos"])
def test_endpoints_de_datos_exigen_el_permiso_reservado_de_exportacion(endpoint):
    dependencia = inspect.signature(getattr(admin, endpoint)).parameters["current_user"].default.dependency
    assert inspect.getclosurevars(dependencia).nonlocals["permission"] == Permission.REPORTES_CGR_EXPORTAR


@pytest.mark.parametrize("rol,permitido", [
    ("superadmin", True), ("admin", False), ("profesional", False), ("estudiante", False),
])
def test_solo_quien_tiene_reportes_cgr_exportar_accede_a_los_datos(rol, permitido):
    from fastapi import HTTPException

    dependencia = inspect.signature(admin.exportar_cgr_datos).parameters["current_user"].default.dependency
    if permitido:
        assert dependencia(current_user={"id": 1, "rol": rol})["rol"] == rol
    else:
        with pytest.raises(HTTPException) as exc:
            dependencia(current_user={"id": 1, "rol": rol})
        assert exc.value.status_code == 403


def test_los_endpoints_de_datos_estan_publicados_junto_a_los_tsv():
    rutas = {(r.path, tuple(sorted(r.methods))) for r in admin.router.routes}
    for ruta in ("/admin/exportar/cgr", "/admin/exportar/cgr/datos",
                 "/admin/exportar/alumnos", "/admin/exportar/alumnos/datos"):
        assert (ruta, ("GET",)) in rutas, ruta


# ══════════════════════════════════════
# /admin/exportar/alumnos
# ══════════════════════════════════════

def _alumnos(esc):
    return admin.exportar_listado_alumnos(
        db=esc["db"], current_user={"id": esc["sa"].id, "rol": "superadmin"})


def test_alumnos_tiene_las_columnas_esperadas(escenario):
    assert _tabla(_alumnos(escenario))[0] == HEADERS_ALUMNOS


def test_alumnos_solo_estudiantes_ordenados_y_sin_ruts_de_prueba(escenario):
    _usuario(escenario["db"], "profesional", nombre="Prof Que No Sale", rut="1-1")
    escenario["db"].commit()

    filas = _tabla(_alumnos(escenario))[1:]
    nombres = [f[0] for f in filas]

    assert nombres == sorted(nombres)
    assert "Prof Que No Sale" not in nombres
    assert "Sofía Súper" not in nombres
    assert "Excluido Prueba" not in nombres
    assert set(nombres) == {"ÁLVARO NÚÑEZ", "José Pérez García", "Ñandú Soto"}


def test_alumnos_cada_dato_en_su_celda_con_tildes_intactas(escenario):
    filas = _tabla(_alumnos(escenario))[1:]
    assert all(len(f) == len(HEADERS_ALUMNOS) for f in filas)

    jose = next(f for f in filas if f[0] == "José Pérez García")
    assert jose[:3] == ["José Pérez García", "12.345.678-9", "Kinesiología"]
    assert jose[3].endswith("@sesaes.cl")

    crudo = _cuerpo(_alumnos(escenario))
    assert crudo.startswith(BOM)
    assert "Ñandú Soto" in crudo.decode("utf-8-sig")


def test_alumnos_un_valor_con_separadores_no_parte_la_fila(escenario):
    _usuario(escenario["db"], nombre="Luz\tMaría\nÁlvarez", rut="22.222.222-2", carrera="Arte\tVisual")
    escenario["db"].commit()

    filas = _tabla(_alumnos(escenario))[1:]
    assert all(len(f) == len(HEADERS_ALUMNOS) for f in filas)
    fila = next(f for f in filas if f[1] == "22.222.222-2")
    assert fila[0] == "Luz María Álvarez"
    assert fila[2] == "Arte Visual"


# ══════════════════════════════════════
# /admin/exportar/alumnos/datos
# ══════════════════════════════════════

def _alumnos_datos(esc):
    return admin.exportar_listado_alumnos_datos(
        db=esc["db"], current_user={"id": esc["sa"].id, "rol": "superadmin"})


def test_datos_alumnos_tienen_las_columnas_esperadas_en_orden_fijo(escenario):
    assert _alumnos_datos(escenario)["columnas"] == HEADERS_ALUMNOS == [
        "Nombre Completo", "RUT", "Carrera", "Correo"]


def test_datos_alumnos_una_fila_por_estudiante_ordenados_por_nombre(escenario):
    _usuario(escenario["db"], "profesional", nombre="Prof Que No Sale", rut="1-1")
    escenario["db"].commit()

    r = _alumnos_datos(escenario)
    nombres = [f[0] for f in r["filas"]]

    assert r["total"] == len(r["filas"]) == 3
    assert all(len(f) == len(HEADERS_ALUMNOS) for f in r["filas"])
    assert nombres == sorted(nombres)
    assert set(nombres) == {"ÁLVARO NÚÑEZ", "José Pérez García", "Ñandú Soto"}


def test_datos_alumnos_son_las_mismas_filas_que_el_texto_tabulado(escenario):
    _usuario(escenario["db"], nombre="Luz\tMaría", rut="22.222.222-2", carrera="Arte")
    escenario["db"].commit()

    assert _sanear(_alumnos_datos(escenario)["filas"]) == _tabla(_alumnos(escenario))[1:]


def test_datos_alumnos_excluyen_los_dos_ruts_y_conservan_los_originales(escenario):
    db = escenario["db"]
    _usuario(db, nombre="Segundo Excluido", rut="19.741.131-7", carrera="X")
    _usuario(db, nombre=None, rut=None, carrera=None, correo="sin.datos@sesaes.cl")
    db.commit()

    filas = _alumnos_datos(escenario)["filas"]
    ruts = {f[1] for f in filas}

    assert "16.458.880-7" not in ruts and "19.741.131-7" not in ruts
    sin_datos = next(f for f in filas if f[3] == "sin.datos@sesaes.cl")
    assert sin_datos[:3] == ["—", "—", "—"]                       # ausentes → "—"
    jose = next(f for f in filas if f[1] == "12.345.678-9")
    assert jose[:3] == ["José Pérez García", "12.345.678-9", "Kinesiología"]   # originales
