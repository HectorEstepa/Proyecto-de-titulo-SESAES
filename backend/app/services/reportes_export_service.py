# -*- coding: utf-8 -*-
"""
SESAES — Exportación real a Excel (.xlsx) del reporte de atenciones y
tasas de inasistencia.

Usa OpenPyXL y consume EXCLUSIVAMENTE el diccionario que arma
`reportes_resumen_service.calcular_resumen(...)`: no vuelve a consultar la
base ni recalcula indicadores. Así el JSON, el PDF y el Excel nunca
pueden diferir en sus números.

Seguridad:
  · Los valores de texto se escriben como texto. Si una celda empieza con
    "=", "+", "-" o "@" se antepone un apóstrofo para que Excel no la
    interprete como fórmula (mitigación de CSV/Excel formula injection).
  · No se incluyen campos clínicos (medicamento, observaciones).
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

_VERDE = "0F766E"
_VERDE_CLARO = "CCFBF1"
_FONDO = "F1F5F9"
_TINTA = "0F172A"
_GRIS = "64748B"

_PREFIJOS_PELIGROSOS = ("=", "+", "-", "@")


def _celda(valor):
    """Valor seguro para una celda. Los números se conservan numéricos."""
    if valor is None:
        return ""
    if isinstance(valor, str):
        texto = valor
        if texto.startswith(_PREFIJOS_PELIGROSOS):
            # Se escribe como texto literal, nunca como fórmula.
            texto = "'" + texto
        return texto
    return valor


def _fecha_corta(iso) -> str:
    from datetime import datetime

    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(iso) if iso else "—"


def _ancho(ws, columnas: int, ancho: float = 18) -> None:
    for i in range(1, columnas + 1):
        ws.column_dimensions[get_column_letter(i)].width = ancho


def _titulo_hoja(ws, texto: str, columnas: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columnas)
    celda = ws.cell(row=1, column=1, value=texto)
    celda.font = Font(bold=True, size=14, color=_VERDE)
    celda.alignment = Alignment(vertical="center")


def _subtitulo(ws, fila: int, texto: str, columnas: int) -> None:
    celda = ws.cell(row=fila, column=1, value=texto)
    celda.font = Font(bold=True, size=11, color=_TINTA)
    celda.fill = PatternFill("solid", fgColor=_FONDO)
    if columnas > 1:
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=columnas)


def _cabecera(ws, fila: int, encabezados: list[str]) -> None:
    for col, texto in enumerate(encabezados, start=1):
        celda = ws.cell(row=fila, column=col, value=texto)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=_VERDE)
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _escribir_fila(ws, fila: int, valores: list) -> None:
    for col, valor in enumerate(valores, start=1):
        ws.cell(row=fila, column=col, value=_celda(valor))


# ══════════════════════════════════════
# Hojas
# ══════════════════════════════════════
def _hoja_resumen(wb: Workbook, resumen: dict, filtros: dict[str, str]) -> None:
    from app.services.reportes_resumen_service import ETIQUETAS_KPI, KPIS

    ws = wb.active
    ws.title = "Resumen"
    _ancho(ws, 3, 32)
    ws.column_dimensions["C"].width = 46

    _titulo_hoja(ws, "SESAES — Reporte de atenciones e inasistencias", 3)
    periodo = resumen["periodo"]
    ws.cell(row=2, column=1, value=(
        f"Período: {_fecha_corta(periodo['fecha_inicio'])} al "
        f"{_fecha_corta(periodo['fecha_fin'])}"
    ))
    activos = [f"{k}: {v}" for k, v in filtros.items() if v]
    ws.cell(row=3, column=1, value="Filtros: " + (", ".join(activos) if activos else "ninguno"))
    ws.cell(row=4, column=1, value=(
        "Una atención es una cita completada; las citas canceladas o "
        "pendientes no se cuentan como atenciones."
    ))

    fila = 6
    _subtitulo(ws, fila, "Indicadores", 3)
    fila += 1
    _cabecera(ws, fila, ["Indicador", "Valor", "Variación vs. período anterior"])
    fila += 1
    for clave in KPIS:
        kpi = resumen["kpis"][clave]
        variacion = kpi["variacion_pct"]
        _escribir_fila(ws, fila, [
            ETIQUETAS_KPI[clave],
            kpi["valor"],
            "Sin datos comparables" if variacion is None else f"{variacion:+.1f}%",
        ])
        fila += 1

    fila += 1
    _subtitulo(ws, fila, "Tasa de inasistencia", 3)
    fila += 1
    _cabecera(ws, fila, ["Métrica", "Valor", "Definición"])
    fila += 1
    inas = resumen["inasistencia"]
    tasa = inas["tasa_pct"]
    _escribir_fila(ws, fila, ["Inasistencias", inas["inasistencias"], "Citas marcadas como inasistencia"])
    ws.cell(row=fila, column=2).number_format = "0"
    fila += 1
    _escribir_fila(ws, fila, ["Atenciones", inas["atenciones"], "Citas efectivamente completadas"])
    ws.cell(row=fila, column=2).number_format = "0"
    fila += 1
    _escribir_fila(ws, fila, ["Citas resueltas", inas["citas_resueltas"], "Completadas + inasistencias"])
    ws.cell(row=fila, column=2).number_format = "0"
    fila += 1
    _escribir_fila(ws, fila, [
        "Tasa de inasistencia",
        "Sin datos" if tasa is None else tasa / 100,
        "Inasistencias / citas resueltas. Pendientes y canceladas no entran en el denominador.",
    ])
    if tasa is not None:
        ws.cell(row=fila, column=2).number_format = "0.0%"
    fila += 2

    _subtitulo(ws, fila, "Citas por estado", 3)
    fila += 1
    _cabecera(ws, fila, ["Estado", "Cantidad", ""])
    fila += 1
    for estado, cantidad in resumen["citas_por_estado"].items():
        _escribir_fila(ws, fila, [estado.capitalize(), cantidad, ""])
        fila += 1


def _hoja_profesionales(wb: Workbook, resumen: dict) -> None:
    ws = wb.create_sheet("Profesionales")
    _cabecera(ws, 1, [
        "Profesional", "Especialidad", "Atenciones", "Citas", "Canceladas",
        "Inasistencias", "Tasa inasistencia", "Sobrecupos", "Urgentes",
    ])
    for fila, p in enumerate(resumen["profesionales"], start=2):
        tasa = p.get("tasa_inasistencia_pct")
        _escribir_fila(ws, fila, [
            p["profesional"], p["especialidad"], p["atenciones"], p["citas"],
            p["canceladas"], p["inasistencias"],
            "—" if tasa is None else tasa / 100,
            p["sobrecupos"], p["urgentes"],
        ])
        if tasa is not None:
            ws.cell(row=fila, column=7).number_format = "0.0%"
    for col, ancho in enumerate([34, 26, 12, 10, 12, 14, 16, 12, 11], start=1):
        ws.column_dimensions[get_column_letter(col)].width = ancho
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _hoja_semanas(wb: Workbook, resumen: dict) -> None:
    ws = wb.create_sheet("Evolución semanal")
    _cabecera(ws, 1, ["Semana (inicio)", "Total citas", "Completadas", "Canceladas"])
    for fila, s in enumerate(resumen["evolucion_semanal"], start=2):
        _escribir_fila(ws, fila, [
            _fecha_corta(s["semana_inicio"]), s["total"], s["completadas"], s["canceladas"],
        ])
    _ancho(ws, 4, 18)
    ws.freeze_panes = "A2"


def _hoja_inasistencias(wb: Workbook, resumen: dict) -> None:
    ws = wb.create_sheet("Inasistencias")
    inas = resumen["inasistencia"]
    _titulo_hoja(ws, "Inasistencias del período", 3)
    ws.cell(row=2, column=1, value="Total de inasistencias")
    ws.cell(row=2, column=2, value=_celda(inas["inasistencias"]))
    ws.cell(row=3, column=1, value="Citas resueltas")
    ws.cell(row=3, column=2, value=_celda(inas["citas_resueltas"]))
    ws.cell(row=4, column=1, value="Tasa de inasistencia")
    if inas["tasa_pct"] is None:
        ws.cell(row=4, column=2, value="Sin datos")
    else:
        ws.cell(row=4, column=2, value=inas["tasa_pct"] / 100)
        ws.cell(row=4, column=2).number_format = "0.0%"

    _cabecera(ws, 6, ["Fecha", "Inasistencias"])
    for fila, item in enumerate(resumen["jornada"]["inasistencias_evolucion"], start=7):
        _escribir_fila(ws, fila, [_fecha_corta(item["fecha"]), item["cantidad"]])
    _ancho(ws, 2, 20)
    ws.column_dimensions["B"].width = 16


def _hoja_ultimas(wb: Workbook, resumen: dict) -> None:
    ws = wb.create_sheet("Últimas atenciones")
    _cabecera(ws, 1, [
        "Fecha", "Hora", "Estudiante", "Profesional", "Especialidad",
        "Estado", "Urgente", "Sobrecupo",
    ])
    for fila, a in enumerate(resumen["ultimas_atenciones"], start=2):
        _escribir_fila(ws, fila, [
            _fecha_corta(a["fecha"]), a["hora"], a["estudiante"], a["profesional"],
            a["especialidad"], a["estado"],
            "Sí" if a["urgente"] else "No",
            "Sí" if a["sobrecupo"] else "No",
        ])
    for col, ancho in enumerate([13, 9, 28, 28, 24, 12, 9, 11], start=1):
        ws.column_dimensions[get_column_letter(col)].width = ancho
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _hoja_agregados(wb: Workbook, resumen: dict) -> None:
    ws = wb.create_sheet("Especialidades y carreras")
    fila = 1
    for titulo, clave, campo, etiqueta in (
        ("Atenciones por especialidad", "por_especialidad", "especialidad", "Especialidad"),
        ("Atenciones por carrera", "por_carrera", "carrera", "Carrera"),
        ("Sobrecupos por especialidad", "sobrecupos_por_especialidad", "especialidad", "Especialidad"),
    ):
        _subtitulo(ws, fila, titulo, 2)
        fila += 1
        _cabecera(ws, fila, [etiqueta, "Cantidad"])
        fila += 1
        for item in resumen[clave]:
            _escribir_fila(ws, fila, [item[campo], item["cantidad"]])
            fila += 1
        fila += 1
    _ancho(ws, 2, 34)
    ws.column_dimensions["B"].width = 14


# ══════════════════════════════════════
# API pública
# ══════════════════════════════════════
def renderizar_excel(resumen: dict, filtros: dict[str, str]) -> bytes:
    """Devuelve los bytes de un .xlsx real con el resumen ya calculado."""
    wb = Workbook()
    _hoja_resumen(wb, resumen, filtros)
    _hoja_profesionales(wb, resumen)
    _hoja_semanas(wb, resumen)
    _hoja_inasistencias(wb, resumen)
    _hoja_ultimas(wb, resumen)
    _hoja_agregados(wb, resumen)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
