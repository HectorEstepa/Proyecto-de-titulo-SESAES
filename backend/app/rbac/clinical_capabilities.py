# -*- coding: utf-8 -*-
"""
SESAES — SA-11.2: catálogo estable de capacidades clínicas.

Este módulo es la ÚNICA fuente de verdad para los identificadores de
capacidad clínica usados en todo el proyecto. Ningún otro módulo debe
declarar strings de capacidad "sueltos": siempre se importa
ClinicalCapability desde acá.

Decisiones de diseño (ver entrega SA-11.2):
  - Las capacidades clínicas NO son permisos RBAC. Viven en un catálogo
    separado de app.rbac.permissions.Permission y nunca se agregan a ese
    enum. RBAC sigue respondiendo "¿puede este rol operar el módulo
    clínico en general?"; este catálogo responde "¿qué puede hacer,
    específicamente, un PROFESIONAL con una especialidad dada?".
  - El catálogo es intencionalmente pequeño y estable: agregar una nueva
    capacidad es un cambio explícito y revisado acá, nunca un string
    libre inventado en un router o en una fila de configuración.
  - Cualquier valor que no sea un miembro de este enum se considera
    inválido/desconocido y debe tratarse como fail-closed (se descarta,
    nunca se concede "por si acaso").
"""

from __future__ import annotations

import unicodedata
from enum import Enum


class ClinicalCapability(str, Enum):
    """
    Identificadores estables de capacidad clínica.

    El valor string (no el nombre del miembro) es lo que se persiste en
    EspecialidadCapability.capability y lo que viaja en las respuestas de
    API — por eso son minúsculas y en snake_case, pensados para vivir
    tal cual en una columna de BD y no cambiar de valor una vez usados
    en datos reales (renombrar el VALOR de un miembro existente es un
    cambio incompatible con las reglas ya persistidas).
    """

    # NOTA (decisión de negocio resuelta en SA-11.3B, ver auditoría
    # SA-11.3): se confirmó que Cita.medicamento representa
    # exclusivamente "medicamento suministrado durante la atención", NO
    # una receta, prescripción ni indicación previa (ver
    # app/routers/profesionales.py:completar_cita y el PDF de
    # resumen de atención en app/routers/citas.py). El miembro se
    # renombró de REGISTRAR_INDICACION_MEDICAMENTO a este nombre para
    # reflejar esa semántica real. Este rename es seguro porque SA-11.2
    # no sembró reglas ni tuvo consumidores productivos de este valor
    # (ver auditoría SA-11.3): no hay filas persistidas en
    # EspecialidadCapability con el string antiguo que deban migrarse,
    # y por eso tampoco se agrega un alias silencioso. Si en el futuro
    # se confirma la necesidad de una prescripción formal distinta de
    # lo suministrado, esa sería una capability nueva y separada (p.ej.
    # `prescribir_medicamento`), no una reinterpretación de esta.
    REGISTRAR_MEDICAMENTO_SUMINISTRADO = "registrar_medicamento_suministrado"
    EMITIR_RECETA = "emitir_receta"
    EMITIR_JUSTIFICATIVO = "emitir_justificativo"
    EMITIR_ORDEN_EXAMEN = "emitir_orden_examen"
    EMITIR_CERTIFICADO = "emitir_certificado"
    GESTIONAR_FICHA_ODONTOLOGICA = "gestionar_ficha_odontologica"


_VALORES_VALIDOS = {c.value for c in ClinicalCapability}


def es_capability_valida(valor: str) -> bool:
    """
    True solo si `valor` coincide EXACTAMENTE con el value de un miembro
    de ClinicalCapability. Cualquier otra cosa (typo, capability
    eliminada, dato corrupto en BD) es inválida y debe descartarse por
    quien la use — nunca lanzar excepción acá: la responsabilidad de
    fail-closed es de quien resuelve capacidades, no de esta función.
    """
    return valor in _VALORES_VALIDOS


def normalizar_especialidad(especialidad: str | None) -> str | None:
    """
    Normaliza `Profesional.especialidad` (string libre) a una forma
    canónica y estable usada como clave de configuración:
      1. None o vacío/solo espacios -> None (sin especialidad válida).
      2. strip() de espacios al inicio/fin.
      3. minúsculas.
      4. se eliminan tildes/diacríticos (NFKD + descarte de
         combining marks), para que "Odontología" y "odontologia"
         resuelvan a la misma clave.
      5. espacios internos múltiples se colapsan a uno solo.

    Esta normalización es la ÚNICA permitida para resolver reglas
    especialidad → capability. Nunca debe reimplementarse ad-hoc en
    otro módulo: si se necesita en otro lugar, se importa esta función.

    No interpreta prefijos de tratamiento ("Dr.", "Dra.", "Psic.", etc.)
    porque esos NO forman parte de Profesional.especialidad (viven en el
    campo separado `tratamiento`); si en el futuro apareciera un dato de
    especialidad con prefijo mezclado, esta función NO lo separa
    automáticamente — eso sería inventar una regla de negocio no
    definida (ver "decisiones pendientes" en la entrega).
    """
    if especialidad is None:
        return None

    valor = especialidad.strip()
    if not valor:
        return None

    valor = valor.lower()
    valor = "".join(
        ch for ch in unicodedata.normalize("NFKD", valor)
        if not unicodedata.combining(ch)
    )
    valor = " ".join(valor.split())

    return valor or None
