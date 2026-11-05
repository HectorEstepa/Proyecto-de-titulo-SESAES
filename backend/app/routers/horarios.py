from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db
from app.models.dia_cerrado import DiaCerrado
from app.auth_dependencies import get_current_user
from app.services.agenda_disponibilidad_service import listar_horas_disponibles

router = APIRouter(tags=["horarios"])


@router.get("/dias-cerrados")
def listar_dias_cerrados_publico(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Versión de solo-lectura, accesible para cualquier usuario logueado
    (no solo admin) — la usan estudiante y profesional para bloquear/marcar
    esas fechas en sus propios calendarios.
    """
    dias = db.query(DiaCerrado).filter(DiaCerrado.fecha >= date.today().isoformat()).order_by(DiaCerrado.fecha).all()
    return [{"fecha": d.fecha, "motivo": d.motivo} for d in dias]


@router.get("/disponibilidad/{profesional_id}")
def get_disponibilidad(
    profesional_id: int,
    fecha: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Devuelve las horas disponibles para un profesional en una fecha específica.
    fecha: string en formato YYYY-MM-DD

    No es un endpoint "sensible" (no expone datos de ningún paciente puntual,
    solo qué horas están libres), así que cualquier usuario autenticado
    (estudiante, profesional o admin) puede consultarlo — es lo que necesita
    el estudiante para agendar.

    A.2 — la lógica de negocio vive ahora en
    app.services.agenda_disponibilidad_service.listar_horas_disponibles,
    compartida con la validación de POST /citas. Este endpoint solo
    adapta esa función al contrato HTTP existente (sin cambios de shape).
    """
    horas, mensaje = listar_horas_disponibles(
        db,
        profesional_id=profesional_id,
        fecha=fecha,
    )
    return {"horas": horas, "mensaje": mensaje}
