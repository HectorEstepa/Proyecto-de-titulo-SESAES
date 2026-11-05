# -*- coding: utf-8 -*-
"""
SESAES — SA-11.2: resolución de capacidades clínicas efectivas.

Único punto donde se traduce "especialidad de un Profesional" en
"capacidades clínicas efectivas". Nadie más debe consultar
EspecialidadCapability directamente ni reimplementar esta lógica.

Regla central (fail-closed):
    sin especialidad normalizable       -> []
    especialidad sin ninguna regla      -> []
    regla con capability desconocida    -> se descarta esa fila (no todo)
    regla inactiva (activo=False)       -> se descarta esa fila
    en cualquier otro caso              -> se concede la capability

Este módulo NO resuelve todavía ownership ni relación clínica concreta
(eso es la capa siguiente del pipeline RBAC → capability → ownership/
relación clínica → acceso, fuera de alcance de SA-11.2). Tampoco decide
qué hacer con `cita.medicamento`, recetas, justificativos, órdenes o
certificados: SA-11.2 solo expone QUÉ puede hacer un profesional en
principio, según su especialidad.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.especialidad_capability import EspecialidadCapability
from app.rbac.clinical_capabilities import es_capability_valida, normalizar_especialidad


def resolver_capacidades_efectivas(especialidad: str | None, db: Session) -> list[str]:
    """
    Devuelve la lista de valores de ClinicalCapability efectivamente
    concedidos para la especialidad dada, según las reglas activas
    persistidas en EspecialidadCapability.

    - `especialidad` es el string libre tal como está en
      Profesional.especialidad (puede ser None).
    - Se normaliza acá mismo (single source of truth de normalización:
      app.rbac.clinical_capabilities.normalizar_especialidad).
    - El orden de retorno es determinista: se ordena explícitamente por
      `EspecialidadCapability.capability` ascendente (orden alfabético
      del valor de la capability), vía `ORDER BY` en la consulta — no
      se depende del orden físico/no garantizado que devolvería la BD
      sin cláusula de orden explícita, ni del orden histórico de
      inserción/IDs: el resultado depende únicamente del contenido de
      la configuración vigente (qué capabilities están activas para la
      especialidad), no de cuándo se creó cada regla.
    """
    especialidad_normalizada = normalizar_especialidad(especialidad)
    if not especialidad_normalizada:
        return []

    reglas = (
        db.query(EspecialidadCapability)
        .filter(
            EspecialidadCapability.especialidad_normalizada == especialidad_normalizada,
            EspecialidadCapability.activo.is_(True),
        )
        .order_by(EspecialidadCapability.capability.asc())
        .all()
    )

    capacidades: list[str] = []
    for regla in reglas:
        if not es_capability_valida(regla.capability):
            # Fail-closed: una fila corrupta/obsoleta no invalida las
            # demás, simplemente no se concede esa capability puntual.
            continue
        if regla.capability not in capacidades:
            capacidades.append(regla.capability)

    return capacidades
