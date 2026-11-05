"""
Reglas de horario del centro para la agenda por bloques.

Horario institucional de atencion (el profesional solo puede ofrecer horas
dentro de el):
    Lunes a Jueves : 09:00 a 17:30
    Viernes        : 09:00 a 16:30
    Sabado/Domingo : sin atencion

Este modulo solo contiene datos y validaciones puras (sin base de datos).
El frontend replica el mismo rango en `slotsDelDia` de dashboard-profesional.ts;
si uno cambia, deben cambiar juntos.
"""
from __future__ import annotations

from datetime import time

NOMBRES_DIA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

TIPOS_BLOQUE = ("disponible", "colacion")

# dia_semana (0=Lunes ... 6=Domingo) -> (inicio, fin) | None si no se atiende
RANGO_INSTITUCIONAL: dict[int, tuple[time, time] | None] = {
    0: (time(9, 0), time(17, 30)),
    1: (time(9, 0), time(17, 30)),
    2: (time(9, 0), time(17, 30)),
    3: (time(9, 0), time(17, 30)),
    4: (time(9, 0), time(16, 30)),
    5: None,
    6: None,
}


def rango_institucional_dia(dia_semana: int) -> tuple[time, time] | None:
    return RANGO_INSTITUCIONAL.get(dia_semana)


def parsear_hora(valor: str | None) -> time | None:
    """'HH:MM' -> time, o None si no es una hora valida."""
    try:
        h, m = str(valor).strip().split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, TypeError):
        return None


def validar_bloque(dia_semana: int, hora_inicio: str, hora_fin: str) -> str | None:
    """
    Devuelve un mensaje de error si el bloque no cabe en el horario
    institucional de ese dia, o None si es valido.
    """
    rango = rango_institucional_dia(dia_semana)
    if rango is None:
        return "El centro no atiende ese día."
    ini, fin = parsear_hora(hora_inicio), parsear_hora(hora_fin)
    if ini is None or fin is None or ini >= fin:
        return "Rango de horas inválido."
    if ini < rango[0] or fin > rango[1]:
        return (
            f"El horario institucional es de {rango[0].strftime('%H:%M')} "
            f"a {rango[1].strftime('%H:%M')}."
        )
    return None
