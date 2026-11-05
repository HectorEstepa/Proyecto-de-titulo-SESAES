# -*- coding: utf-8 -*-
"""
SESAES — Capacidades clínicas que trae CADA ESPECIALIDAD de fábrica.

Un profesional no necesita que el superadmin le "dé permiso" para hacer lo
propio de su profesión: un médico receta, emite justificativos y registra el
medicamento que suministra desde el primer día. Las reglas por especialidad en
base de datos (EspecialidadCapability, SA-11.2) quedan solo para AUTORIZACIONES
ADICIONALES y supervisadas — por ejemplo, enfermería, que no trae nada de
fábrica y requiere que un administrador lo autorice.

No todos los profesionales recetan: lo que se concede depende de la
especialidad, comparando el nombre normalizado (sin tildes ni mayúsculas) por
fragmentos, para cubrir variantes como "Medicina General" o "Medicina Interna".
Una especialidad que no calza con ninguna regla no recibe nada (fail-closed).

Para ajustar quién puede qué, se edita ÚNICAMENTE esta tabla.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.rbac.clinical_capabilities import ClinicalCapability, normalizar_especialidad
from app.services.clinical_capabilities_service import resolver_capacidades_efectivas

_COMPLETAS = frozenset({
    ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO.value,
    ClinicalCapability.EMITIR_RECETA.value,
    ClinicalCapability.EMITIR_JUSTIFICATIVO.value,
})
_SOLO_JUSTIFICATIVO = frozenset({ClinicalCapability.EMITIR_JUSTIFICATIVO.value})

# (fragmentos del nombre normalizado de la especialidad, capacidades que trae)
_REGLAS: tuple[tuple[tuple[str, ...], frozenset[str]], ...] = (
    # Prescriben medicamentos.
    (("medicina", "medico", "odontolog", "dental", "otorrino", "psiquiatr", "pediatr",
      "ginecolog", "dermatolog", "traumatolog", "cardiolog", "oftalmolog", "urolog",
      "neurolog", "gastroenterolog", "endocrinolog", "reumatolog", "geriatr"), _COMPLETAS),
    # No prescriben, pero sí certifican su atención.
    (("psicolog", "kinesiolog", "nutri", "fonoaudiolog", "terapia ocupacional",
      "podolog", "matron", "trabajo social"), _SOLO_JUSTIFICATIVO),
    # Enfermería y cualquier otra especialidad: nada de fábrica.
)


def capacidades_por_defecto(especialidad: str | None) -> frozenset[str]:
    clave = normalizar_especialidad(especialidad)
    if not clave:
        return frozenset()
    for fragmentos, capacidades in _REGLAS:
        if any(f in clave for f in fragmentos):
            return capacidades
    return frozenset()


def capacidades_efectivas_profesional(especialidad: str | None, db: Session) -> list[str]:
    """Lo que trae la especialidad de fábrica + las autorizaciones adicionales vigentes."""
    return sorted(capacidades_por_defecto(especialidad) | set(resolver_capacidades_efectivas(especialidad, db)))
