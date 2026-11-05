# -*- coding: utf-8 -*-
"""
SESAES — Administración de capacidades clínicas por especialidad.

Es la contraparte de administración de SA-11.2: define QUÉ documentos y
registros puede emitir un profesional según su especialidad (receta,
justificativo, medicamento suministrado...). Quien lo gestiona es quien
tiene el permiso `configuracion.gestionar` (hoy, SUPERADMIN).

  GET /admin/capacidades-clinicas            catálogo + especialidades + reglas vigentes
  PUT /admin/capacidades-clinicas/{clave}    reemplaza las capacidades de UNA especialidad

Cada especialidad trae de fábrica lo propio de su profesión (ver
capacidades_por_defecto.py): un médico no necesita autorización. Esta pantalla
sirve para las AUTORIZACIONES ADICIONALES y supervisadas (por ejemplo,
enfermería). Lo que viene de fábrica se muestra como "incluida" y no se edita.

Reglas (las mismas de SA-11.2, fail-closed):
  - la clave de especialidad es SIEMPRE la normalizada (normalizar_especialidad);
  - solo se aceptan capacidades del catálogo ClinicalCapability;
  - una capacidad desmarcada queda como regla inactiva (no se borra la fila),
    así queda el historial de que existió.
"""

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auditoria import registrar_evento_auditoria
from app.auth_dependencies import get_current_user
from app.database import get_db
from app.models.especialidad_capability import EspecialidadCapability
from app.models.profesional import Profesional
from app.rbac.clinical_capabilities import (
    ClinicalCapability,
    es_capability_valida,
    normalizar_especialidad,
)
from app.rbac.permissions import Permission, has_permission
from app.services.capacidades_por_defecto import capacidades_efectivas_profesional, capacidades_por_defecto
from app.services.clinical_capabilities_service import resolver_capacidades_efectivas

router = APIRouter(prefix="/admin/capacidades-clinicas", tags=["admin-capacidades-clinicas"])

# Texto para la pantalla de administración. `activa_en_sistema` indica si hoy
# alguna pantalla usa la capacidad; las demás existen en el catálogo pero
# todavía no cambian nada, y la pantalla las muestra como "próximamente"
# para no dar a entender que hacen algo.
_CATALOGO = [
    (ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO, "Medicamento suministrado",
     "Registrar el medicamento entregado durante la atención.", True),
    (ClinicalCapability.EMITIR_RECETA, "Receta médica",
     "Emitir recetas con folio y código de verificación.", True),
    (ClinicalCapability.EMITIR_JUSTIFICATIVO, "Justificativo médico",
     "Emitir justificativos de atención y reposo (sin diagnóstico).", True),
    (ClinicalCapability.EMITIR_ORDEN_EXAMEN, "Orden de examen",
     "Emitir órdenes de examen.", False),
    (ClinicalCapability.EMITIR_CERTIFICADO, "Certificado",
     "Emitir certificados médicos.", False),
    (ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA, "Ficha odontológica",
     "Gestionar la ficha odontológica.", False),
]


class CapacidadesIn(BaseModel):
    capacidades: list[str]


def _exigir_gestion(current_user: dict) -> None:
    if not has_permission(current_user, Permission.CONFIGURACION_GESTIONAR):
        raise HTTPException(status_code=403, detail="No tienes permiso para administrar las capacidades clínicas.")


def _especialidades(db: Session) -> list[dict]:
    """Une las especialidades de los profesionales con las que ya tienen reglas."""
    nombres: dict[str, Counter] = {}
    conteo: Counter = Counter()
    for (esp,) in db.query(Profesional.especialidad).all():
        clave = normalizar_especialidad(esp)
        if not clave:
            continue
        nombres.setdefault(clave, Counter())[(esp or "").strip()] += 1
        conteo[clave] += 1
    for (clave,) in db.query(EspecialidadCapability.especialidad_normalizada).distinct().all():
        nombres.setdefault(clave, Counter())

    salida = []
    for clave in sorted(nombres):
        visible = nombres[clave].most_common(1)[0][0] if nombres[clave] else clave.title()
        salida.append({
            "clave": clave,
            "nombre": visible,
            "profesionales": conteo.get(clave, 0),
            "incluidas": sorted(capacidades_por_defecto(clave)),     # de fábrica, no editables
            "capacidades": capacidades_efectivas_profesional(clave, db),
        })
    return salida


@router.get("")
def listar_capacidades(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_gestion(current_user)
    return {
        "catalogo": [
            {"valor": c.value, "nombre": n, "descripcion": d, "activa_en_sistema": activa}
            for c, n, d, activa in _CATALOGO
        ],
        "especialidades": _especialidades(db),
    }


@router.put("/{clave}")
def actualizar_capacidades(
    clave: str,
    datos: CapacidadesIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_gestion(current_user)

    if normalizar_especialidad(clave) != clave:
        raise HTTPException(status_code=400, detail="Especialidad no válida.")
    deseadas = set(datos.capacidades)
    desconocidas = sorted(c for c in deseadas if not es_capability_valida(c))
    if desconocidas:
        raise HTTPException(status_code=400, detail=f"Capacidad desconocida: {', '.join(desconocidas)}.")

    # Lo que la especialidad ya trae de fábrica no se guarda como regla: solo
    # se persisten las autorizaciones adicionales.
    de_fabrica = capacidades_por_defecto(clave)
    deseadas = deseadas - de_fabrica
    antes = set(resolver_capacidades_efectivas(clave, db))
    reglas = {
        r.capability: r
        for r in db.query(EspecialidadCapability).filter(EspecialidadCapability.especialidad_normalizada == clave).all()
    }
    for c in ClinicalCapability:
        quiere = c.value in deseadas
        regla = reglas.get(c.value)
        if regla:
            regla.activo = quiere
        elif quiere:
            db.add(EspecialidadCapability(especialidad_normalizada=clave, capability=c.value, activo=True))

    otorgadas = sorted(deseadas - antes)
    retiradas = sorted(antes - deseadas)
    registrar_evento_auditoria(
        db, current_user, "Administrador cambió autorizaciones clínicas adicionales",
        entidad="especialidad_capability", entidad_id=None,
        detalle=f"{clave}: +[{', '.join(otorgadas)}] -[{', '.join(retiradas)}]",
    )
    db.commit()
    return next(e for e in _especialidades(db) if e["clave"] == clave)
