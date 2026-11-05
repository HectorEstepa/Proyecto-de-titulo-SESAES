# -*- coding: utf-8 -*-
"""
SESAES — SA-11.2: endpoint de capacidades clínicas efectivas.

Expone exclusivamente las capacidades del PROFESIONAL autenticado.
Identidad efectiva SIEMPRE resuelta desde current_user (JWT validado
por get_current_user) + Profesional.usuario_id — nunca se acepta un
profesional_id provisto por el frontend para determinar identidad.

ADMIN y SUPERADMIN no obtienen capacidades clínicas por jerarquía: se
exige rol == "profesional" explícitamente (defensa en profundidad,
mismo criterio que verificar_acceso_profesional en auth_dependencies.py
desde Fase 3.5F: ningún helper de este tipo debe tener un bypass de rol
"admin").

Fuera de alcance de SA-11.2 (ver entrega): no se integra con
cita.medicamento, /citas/{id}/pdf, recetas, justificativos, órdenes ni
certificados. Este endpoint solo informa QUÉ puede hacer el profesional
en principio.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth_dependencies import get_current_user, verificar_rol
from app.database import get_db
from app.models.profesional import Profesional
from app.services.capacidades_por_defecto import capacidades_efectivas_profesional

router = APIRouter()


def _resolver_profesional_propio(current_user: dict, db: Session) -> Profesional | None:
    """
    Resuelve el (único) Profesional asociado al Usuario autenticado.

    Fail-closed ante ambigüedad: NO se usa .first() para "elegir una
    fila cualquiera" cuando hay más de un Profesional con el mismo
    usuario_id. Hoy no existe una restricción unique=True sobre
    Profesional.usuario_id (y SA-11.2 deliberadamente no la agrega ni
    hace una migración destructiva para forzarla), así que ese estado
    puede existir en datos reales o de prueba. Ante esa ambigüedad, no
    hay forma segura de saber cuál fila es "la correcta": se trata como
    ausencia de configuración válida, igual que 0 filas.

      0 filas Profesional   -> None (capacidades vacías)
      exactamente 1 fila    -> esa fila
      2+ filas              -> None (capacidades vacías, fail-closed)
    """
    profesionales = (
        db.query(Profesional)
        .filter(Profesional.usuario_id == current_user["id"])
        .all()
    )
    if len(profesionales) != 1:
        return None
    return profesionales[0]


@router.get("/profesional/capacidades-clinicas")
def obtener_mis_capacidades_clinicas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Devuelve {"capacidades": [...]} con las capacidades clínicas
    efectivas del profesional autenticado, según su especialidad y las
    reglas activas de EspecialidadCapability.

    Decisión de diseño documentada: tanto la ausencia de una fila
    Profesional asociada como la existencia de más de una (asociación
    ambigua) responden {"capacidades": []} en vez de 404/500. Es
    fail-closed y evita filtrar detalle de un estado interno
    inconsistente; si el negocio prefiere un error explícito acá, es
    una decisión pendiente para quien la apruebe.
    """
    verificar_rol(current_user, ["profesional"])

    profesional = _resolver_profesional_propio(current_user, db)
    if profesional is None:
        return {"capacidades": []}

    capacidades = capacidades_efectivas_profesional(profesional.especialidad, db)
    return {"capacidades": capacidades}
