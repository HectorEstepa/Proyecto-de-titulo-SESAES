# -*- coding: utf-8 -*-
"""
SESAES — Resumen de Reportes (GET /admin/reportes/resumen y su PDF).

Una sola fuente de verdad: `calcular_resumen` arma el diccionario que
consumen tanto el JSON como el PDF, así los números nunca difieren.

Reglas (cubiertas por tests/test_reportes_resumen*.py):
  · "cita != atención": total_atenciones, completadas y estudiantes_atendidos
    cuentan SOLO citas en estado "completada". Urgentes y sobrecupos se miden
    sobre esas mismas atenciones y son independientes entre sí: una cita
    urgente Y sobrecupo cuenta en ambos KPI sin duplicarse en ningún otro.
  · La comparación con el período anterior (mismo largo, inmediatamente antes)
    es real o es `null`: nunca se inventa. Sin citas en el período anterior,
    `periodo_anterior.disponible` es False y toda variación es None.
  · Los filtros de especialidad y carrera usan app.busqueda (tolerantes a
    tildes, mayúsculas y ñ), igual que /admin/historial.
  · El alcance administrativo llega ya resuelto como `ids_profesionales`
    (None = institucional; lista = solo esos profesionales; vacía = nada).
  · Nunca se leen campos clínicos: la consulta solo selecciona columnas
    administrativas.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO

from sqlalchemy.orm import Session

from app.busqueda import filtro_texto, igual_normalizado
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario

ESTADOS = ("completada", "cancelada", "pendiente", "inasistencia")
KPIS = ("total_atenciones", "completadas", "canceladas", "urgentes", "sobrecupos", "estudiantes_atendidos")
DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
DIAS_DEFECTO = 30
MAX_ULTIMAS = 50

ETIQUETAS_KPI = {
    "total_atenciones": "Total de atenciones",
    "completadas": "Completadas",
    "canceladas": "Canceladas",
    "urgentes": "Urgentes",
    "sobrecupos": "Sobrecupos",
    "estudiantes_atendidos": "Estudiantes atendidos",
}


# ══════════════════════════════════════
# Período
# ══════════════════════════════════════
def _fecha(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return datetime.strptime(valor[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def resolver_periodo(fecha_inicio: str | None, fecha_fin: str | None) -> tuple[date, date]:
    """Sin fechas: últimos 30 días hasta hoy. Con una sola, la otra se completa."""
    fin = _fecha(fecha_fin)
    inicio = _fecha(fecha_inicio)
    if fin is None and inicio is None:
        fin = date.today()
    if fin is None:
        fin = max(inicio, date.today()) if inicio else date.today()
    if inicio is None:
        inicio = fin - timedelta(days=DIAS_DEFECTO - 1)
    if inicio > fin:
        inicio, fin = fin, inicio
    return inicio, fin


def periodo_anterior(inicio: date, fin: date) -> tuple[date, date]:
    largo = (fin - inicio).days + 1
    ant_fin = inicio - timedelta(days=1)
    return ant_fin - timedelta(days=largo - 1), ant_fin


# ══════════════════════════════════════
# Consulta
# ══════════════════════════════════════
def _filas(
    db: Session, ids_profesionales: list[int] | None, inicio: date, fin: date, *,
    especialidad, carrera, profesional_id, estado, prioridad,
):
    """Citas del período con los filtros pedidos. Solo columnas administrativas."""
    if ids_profesionales is not None and not ids_profesionales:
        return []

    q = (
        db.query(
            Cita.id, Cita.fecha, Cita.hora, Cita.estado, Cita.urgente, Cita.sobrecupo,
            Cita.cancelada_por_admin, Cita.estudiante_id, Cita.profesional_id,
            Profesional.nombre.label("prof_nombre"), Profesional.especialidad.label("especialidad"),
            Usuario.nombre.label("est_nombre"), Usuario.carrera.label("carrera"),
        )
        .join(Profesional, Cita.profesional_id == Profesional.id)
        .join(Usuario, Cita.estudiante_id == Usuario.id)
        .filter(Cita.fecha >= inicio.isoformat(), Cita.fecha <= fin.isoformat())
    )
    if ids_profesionales is not None:
        q = q.filter(Cita.profesional_id.in_(ids_profesionales))

    cond = igual_normalizado(Profesional.especialidad, especialidad)
    if cond is not None:
        q = q.filter(cond)
    cond = filtro_texto([Usuario.carrera], carrera)
    if cond is not None:
        q = q.filter(cond)
    if profesional_id:
        q = q.filter(Cita.profesional_id == profesional_id)
    if estado:
        q = q.filter(Cita.estado == estado)
    if prioridad == "urgente":
        q = q.filter(Cita.urgente.is_(True))
    elif prioridad == "no_urgente":
        q = q.filter((Cita.urgente.is_(False)) | (Cita.urgente.is_(None)))
    return q.all()


# ══════════════════════════════════════
# Cálculo
# ══════════════════════════════════════
def _kpis(filas) -> dict[str, int]:
    completadas = [f for f in filas if f.estado == "completada"]
    return {
        "total_atenciones": len(completadas),
        "completadas": len(completadas),
        "canceladas": sum(1 for f in filas if f.estado == "cancelada"),
        "urgentes": sum(1 for f in completadas if f.urgente),
        "sobrecupos": sum(1 for f in completadas if f.sobrecupo),
        "estudiantes_atendidos": len({f.estudiante_id for f in completadas}),
    }


def _variacion(actual: int, anterior: int | None) -> float | None:
    if not anterior:
        return None
    return round((actual - anterior) / anterior * 100, 1)


def tasa_inasistencia(inasistencias: int, completadas: int) -> float | None:
    """
    Tasa de inasistencia = inasistencias / (inasistencias + completadas).

    El denominador son las citas RESUELTAS del período: las que ya
    ocurrieron (completadas) o debían ocurrir y no ocurrieron
    (inasistencia). Se excluyen a propósito las pendientes (todavía no
    son inasistencia) y las canceladas (no son una falta del estudiante).
    Sin citas resueltas se devuelve None — nunca 0.0, que sería inventar
    una tasa cuando no hay datos.
    """
    resueltas = (inasistencias or 0) + (completadas or 0)
    if resueltas == 0:
        return None
    return round((inasistencias or 0) / resueltas * 100, 1)


def _ranking(contador: Counter, clave: str) -> list[dict]:
    return [
        {clave: nombre, "cantidad": cantidad}
        for nombre, cantidad in sorted(contador.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _lunes(fecha_iso: str) -> str:
    d = datetime.strptime(fecha_iso[:10], "%Y-%m-%d").date()
    return (d - timedelta(days=d.weekday())).isoformat()


def calcular_resumen(
    db: Session, ids_profesionales: list[int] | None, *,
    fecha_inicio: str | None, fecha_fin: str | None,
    especialidad=None, carrera=None, profesional_id=None, estado=None, prioridad=None,
    limite_ultimas: int = 10,
) -> dict:
    inicio, fin = resolver_periodo(fecha_inicio, fecha_fin)
    ant_inicio, ant_fin = periodo_anterior(inicio, fin)
    filtros = dict(especialidad=especialidad, carrera=carrera, profesional_id=profesional_id,
                   estado=estado, prioridad=prioridad)

    filas = _filas(db, ids_profesionales, inicio, fin, **filtros)
    filas_ant = _filas(db, ids_profesionales, ant_inicio, ant_fin, **filtros)

    actual = _kpis(filas)
    previo = _kpis(filas_ant)
    hay_anterior = len(filas_ant) > 0

    completadas = [f for f in filas if f.estado == "completada"]
    sin_carrera = "Sin carrera registrada"

    # Evolución semanal (semanas que empiezan en lunes)
    semanas: dict[str, dict] = defaultdict(lambda: {"total": 0, "completadas": 0, "canceladas": 0})
    for f in filas:
        s = semanas[_lunes(f.fecha)]
        s["total"] += 1
        if f.estado == "completada":
            s["completadas"] += 1
        elif f.estado == "cancelada":
            s["canceladas"] += 1

    # Cancelaciones por origen
    origen = Counter("admin" if f.cancelada_por_admin else "estudiante" for f in filas if f.estado == "cancelada")

    # Profesionales
    por_prof: dict[int, dict] = {}
    for f in filas:
        p = por_prof.setdefault(f.profesional_id, {
            "profesional_id": f.profesional_id, "profesional": f.prof_nombre,
            "especialidad": f.especialidad, "atenciones": 0, "citas": 0,
            "canceladas": 0, "inasistencias": 0, "sobrecupos": 0, "urgentes": 0,
        })
        p["citas"] += 1
        if f.estado == "completada":
            p["atenciones"] += 1
            p["sobrecupos"] += 1 if f.sobrecupo else 0
            p["urgentes"] += 1 if f.urgente else 0
        elif f.estado == "cancelada":
            p["canceladas"] += 1
        elif f.estado == "inasistencia":
            p["inasistencias"] += 1

    for p in por_prof.values():
        p["tasa_inasistencia_pct"] = tasa_inasistencia(
            p["inasistencias"], p["atenciones"]
        )

    # Jornada y asistencia
    por_dia = Counter()
    for f in completadas:
        por_dia[DIAS[datetime.strptime(f.fecha[:10], "%Y-%m-%d").weekday()]] += 1
    por_hora = Counter(f"{(f.hora or '00:00')[:2]}:00" for f in filas)
    inasist = Counter(f.fecha for f in filas if f.estado == "inasistencia")

    limite = max(1, min(int(limite_ultimas or 10), MAX_ULTIMAS))
    ultimas = sorted(completadas, key=lambda f: (f.fecha, f.hora or ""), reverse=True)[:limite]

    inasistencias_periodo = sum(1 for f in filas if f.estado == "inasistencia")
    citas_resueltas = len(completadas) + inasistencias_periodo

    return {
        "periodo": {"fecha_inicio": inicio.isoformat(), "fecha_fin": fin.isoformat()},
        "periodo_anterior": {
            "fecha_inicio": ant_inicio.isoformat(), "fecha_fin": ant_fin.isoformat(),
            "disponible": hay_anterior,
        },
        "kpis": {
            k: {"valor": actual[k], "variacion_pct": _variacion(actual[k], previo[k]) if hay_anterior else None}
            for k in KPIS
        },
        "citas_por_estado": {e: sum(1 for f in filas if f.estado == e) for e in ESTADOS},
        # Bloque ADITIVO (no forma parte de los 6 KPI oficiales, que se
        # mantienen intactos): tasa de inasistencia del período y su
        # desglose, usado por el PDF y el Excel.
        "inasistencia": {
            "inasistencias": inasistencias_periodo,
            "atenciones": len(completadas),
            "citas_resueltas": citas_resueltas,
            "tasa_pct": tasa_inasistencia(inasistencias_periodo, len(completadas)),
        },
        "evolucion_semanal": [{"semana_inicio": k, **v} for k, v in sorted(semanas.items())],
        "por_especialidad": _ranking(Counter(f.especialidad or "Sin especialidad" for f in completadas), "especialidad"),
        "por_carrera": _ranking(Counter(f.carrera or sin_carrera for f in completadas), "carrera"),
        "sobrecupos_por_especialidad": _ranking(
            Counter(f.especialidad or "Sin especialidad" for f in completadas if f.sobrecupo), "especialidad"),
        "cancelaciones": {
            "total": actual["canceladas"],
            "por_origen": [{"origen": o, "cantidad": c} for o, c in sorted(origen.items(), key=lambda kv: (-kv[1], kv[0]))],
        },
        "profesionales": sorted(por_prof.values(), key=lambda p: (-p["atenciones"], -p["citas"], p["profesional"] or "")),
        "jornada": {
            "por_dia_semana": [{"dia": d, "cantidad": por_dia.get(d, 0)} for d in DIAS],
            "por_hora": [{"hora": h, "cantidad": c} for h, c in sorted(por_hora.items())],
            "inasistencias_evolucion": [{"fecha": k, "cantidad": v} for k, v in sorted(inasist.items())],
        },
        "ultimas_atenciones": [
            {
                "fecha": f.fecha, "hora": f.hora, "estudiante": f.est_nombre, "profesional": f.prof_nombre,
                "especialidad": f.especialidad, "estado": f.estado,
                "urgente": bool(f.urgente), "sobrecupo": bool(f.sobrecupo),
            }
            for f in ultimas
        ],
    }


# ══════════════════════════════════════
# PDF
# ══════════════════════════════════════
_VERDE = (15, 118, 110)
_GRIS = (100, 116, 139)
_TINTA = (15, 23, 42)
_FONDO = (241, 245, 249)


def _l1(texto) -> str:
    """Las fuentes base de fpdf2 son latin-1: reemplaza lo que no cabe."""
    if texto is None:
        return ""
    return (
        str(texto).replace("\u2013", "-").replace("\u2014", "-").replace("\u2026", "...")
        .encode("latin-1", "replace").decode("latin-1")
    )


def _fecha_corta(iso: str) -> str:
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso or "—"


def renderizar_pdf(resumen: dict, filtros: dict[str, str]) -> bytes:
    """PDF administrativo del resumen. Solo usa el diccionario ya calculado."""
    from fpdf import FPDF

    class Informe(FPDF):
        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*_GRIS)
            self.cell(0, 6, f"SESAES - Reporte de atenciones - Página {self.page_no()}/{{nb}}", align="C")

    pdf = Informe(format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    ancho = pdf.w - 30

    def titulo(texto: str):
        pdf.ln(3)
        pdf.set_fill_color(*_FONDO)
        pdf.set_text_color(*_VERDE)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(ancho, 7, "  " + _l1(texto.upper()), new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(1)

    def fila(celdas: list[str], anchos: list[float], *, negrita=False, gris=False):
        pdf.set_font("Helvetica", "B" if negrita else "", 8.5)
        pdf.set_text_color(*(_GRIS if gris else _TINTA))
        for texto, w in zip(celdas, anchos):
            pdf.cell(w, 6, _l1(texto)[:46], border=0)
        pdf.ln(6)

    pdf.set_fill_color(*_VERDE)
    pdf.rect(0, 0, pdf.w, 3, style="F")
    pdf.set_xy(15, 10)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*_VERDE)
    pdf.cell(ancho, 9, "Reporte de atenciones", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GRIS)
    p = resumen["periodo"]
    pdf.cell(ancho, 5, _l1(f"Período: {_fecha_corta(p['fecha_inicio'])} al {_fecha_corta(p['fecha_fin'])}"),
             new_x="LMARGIN", new_y="NEXT")
    activos = [f"{k}: {v}" for k, v in filtros.items() if v]
    pdf.cell(ancho, 5, _l1("Filtros: " + (", ".join(activos) if activos else "ninguno")), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(ancho, 5, _l1("Una atención es una cita completada; las citas canceladas o pendientes no se cuentan como atenciones."),
             new_x="LMARGIN", new_y="NEXT")

    titulo("Indicadores")
    anterior = resumen["periodo_anterior"]
    for clave in KPIS:
        k = resumen["kpis"][clave]
        var = k["variacion_pct"]
        texto_var = "Sin datos comparables" if var is None else f"{var:+.1f}% vs. período anterior"
        fila([ETIQUETAS_KPI[clave], str(k["valor"]), texto_var], [70, 25, 85])
    if not anterior["disponible"]:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*_GRIS)
        pdf.cell(ancho, 5, "No hay citas en el período anterior para comparar.", new_x="LMARGIN", new_y="NEXT")

    titulo("Tasa de inasistencia")
    inas = resumen["inasistencia"]
    if inas["tasa_pct"] is None:
        fila(["Tasa de inasistencia", "Sin datos", "No hay citas resueltas en el período"], [70, 25, 85])
    else:
        fila(
            [
                "Tasa de inasistencia",
                f"{inas['tasa_pct']:.1f}%",
                f"{inas['inasistencias']} inasistencias sobre "
                f"{inas['citas_resueltas']} citas resueltas",
            ],
            [70, 25, 85],
        )
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_GRIS)
    pdf.cell(ancho, 5, _l1(
        "Citas resueltas = completadas + inasistencias; las pendientes y canceladas no entran en el denominador."
    ), new_x="LMARGIN", new_y="NEXT")

    titulo("Citas por estado")
    for estado, cantidad in resumen["citas_por_estado"].items():
        fila([estado.capitalize(), str(cantidad)], [70, 25])

    if resumen["por_especialidad"]:
        titulo("Atenciones por especialidad")
        for f in resumen["por_especialidad"][:12]:
            fila([f["especialidad"], str(f["cantidad"])], [110, 25])

    if resumen["profesionales"]:
        titulo("Profesionales")
        anchos = [55, 33, 18, 12, 16, 22, 24]
        fila(
            ["Profesional", "Especialidad", "Atenc.", "Citas", "Cancel.", "Inasist.", "Tasa inasist."],
            anchos, negrita=True,
        )
        for f in resumen["profesionales"][:15]:
            tasa = f.get("tasa_inasistencia_pct")
            fila([f["profesional"], f["especialidad"], str(f["atenciones"]), str(f["citas"]),
                  str(f["canceladas"]), str(f["inasistencias"]),
                  "—" if tasa is None else f"{tasa:.1f}%"], anchos)

    if resumen["ultimas_atenciones"]:
        titulo("Últimas atenciones")
        anchos = [22, 14, 50, 50, 44]
        fila(["Fecha", "Hora", "Estudiante", "Profesional", "Especialidad"], anchos, negrita=True)
        for f in resumen["ultimas_atenciones"]:
            marcas = ("U" if f["urgente"] else "") + ("S" if f["sobrecupo"] else "")
            fila([_fecha_corta(f["fecha"]), f["hora"] or "", f["estudiante"], f["profesional"],
                  f["especialidad"] + (f"  [{marcas}]" if marcas else "")], anchos)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*_GRIS)
        pdf.cell(ancho, 5, "U = urgente, S = sobrecupo.", new_x="LMARGIN", new_y="NEXT")

    buffer = BytesIO()
    buffer.write(bytes(pdf.output()))
    return buffer.getvalue()
