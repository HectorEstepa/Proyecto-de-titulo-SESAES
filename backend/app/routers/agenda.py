"""
Fase 3.5F — endpoint ADMINISTRATIVO/OPERACIONAL de agenda, separado del
endpoint CLÍNICO que usa el dashboard del profesional
(GET /profesional/{prof_id}/citas en profesionales.py).

Este módulo es exclusivamente para el rol administrativo: exige
Permission.AGENDA_VER (no AGENDA_VER_PROFESIONAL ni ownership de
profesional) y devuelve solo los campos operacionales necesarios para
que Admin/Superadmin vean el horario de un profesional — nunca datos
clínicos (medicamento, observaciones_atencion, ficha, anamnesis,
cuestionario, diagnóstico, etc.).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rbac.dependencies import require_effective_permission
from app.rbac.permissions import Permission
from app.rbac.admin_authorization import (
    obtener_alcance_administrativo_efectivo,
    especialidad_permitida_por_alcance,
)
from app.services.agenda_disponibilidad_service import (
    listar_disponibilidad_rango,
    ParametrosRangoInvalidosError,
    ProfesionalNoEncontradoError,
)

router = APIRouter(prefix="/agenda", tags=["agenda"])


@router.get("/profesionales")
def listar_profesionales_agenda(
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_effective_permission(
            Permission.AGENDA_VER
        )
    ),
):
    """
    Catálogo operacional mínimo para seleccionar profesionales en Agenda.

    Requiere agenda.ver y respeta el alcance administrativo efectivo.
    No reutiliza /admin/profesionales porque esa ruta pertenece al módulo
    de Profesionales y exige profesionales.ver.
    """
    alcance = obtener_alcance_administrativo_efectivo(
        db,
        current_user,
    )

    if alcance is None:
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso al alcance solicitado.",
        )

    profesionales = [
        profesional
        for profesional in db.query(Profesional).all()
        if especialidad_permitida_por_alcance(
            alcance,
            profesional.especialidad,
        )
    ]

    return [
        {
            "id": profesional.id,
            "nombre": profesional.nombre,
            "tratamiento": profesional.tratamiento,
            "especialidad": profesional.especialidad,
            "iniciales": profesional.iniciales,
            "duracion_min": profesional.duracion_min,
            "estado": profesional.estado or "activo",
            "color_identificador": profesional.color_identificador,
        }
        for profesional in profesionales
    ]


@router.get("/citas")
def listar_citas_admin(
    estudiante: str | None = None,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
    estado: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_effective_permission(
            Permission.AGENDA_VER
        )
    ),
):
    """
    Listado administrativo/operacional de citas.

    Requiere agenda.ver y respeta el alcance administrativo efectivo.
    No reutiliza /admin/historial porque esa ruta pertenece a
    reporter?a y exige reportes.ver.

    Expone solamente datos operacionales necesarios para Agenda/Citas.
    Nunca expone campos cl?nicos.
    """
    alcance = obtener_alcance_administrativo_efectivo(
        db,
        current_user,
    )

    if alcance is None:
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso al alcance solicitado.",
        )

    ids_profesionales: list[int] | None = None

    if not alcance.institucional:
        ids_profesionales = [
            profesional.id
            for profesional in db.query(Profesional).all()
            if especialidad_permitida_por_alcance(
                alcance,
                profesional.especialidad,
            )
        ]

        if not ids_profesionales:
            return []

    query = db.query(Cita)

    # El alcance se aplica antes que cualquier filtro solicitado.
    if ids_profesionales is not None:
        query = query.filter(
            Cita.profesional_id.in_(
                ids_profesionales
            )
        )

    if estudiante and estudiante.strip():
        patron = f"%{estudiante.strip()}%"

        query = (
            query
            .join(
                Usuario,
                Cita.estudiante_id == Usuario.id,
            )
            .filter(
                Usuario.nombre.ilike(patron)
                | Usuario.rut.ilike(patron)
            )
        )

    if fecha_inicio:
        query = query.filter(
            Cita.fecha >= fecha_inicio
        )

    if fecha_fin:
        query = query.filter(
            Cita.fecha <= fecha_fin
        )

    if estado:
        query = query.filter(
            Cita.estado == estado
        )

    citas = (
        query
        .order_by(
            Cita.fecha.desc(),
            Cita.hora.desc(),
        )
        .all()
    )

    resultado = []

    for cita in citas:
        profesional = (
            db.query(Profesional)
            .filter(
                Profesional.id == cita.profesional_id
            )
            .first()
        )

        estudiante_obj = (
            db.query(Usuario)
            .filter(
                Usuario.id == cita.estudiante_id
            )
            .first()
        )

        resultado.append({
            "id": cita.id,
            "estudiante": (
                estudiante_obj.nombre
                if estudiante_obj
                else "?"
            ),
            "estudiante_id": cita.estudiante_id,
            "rut": (
                estudiante_obj.rut
                if estudiante_obj
                else "?"
            ),
            # Se conserva el contrato visual que hoy consume
            # AdminCitasComponent.
            "iniciales": (
                profesional.iniciales
                if profesional
                else "??"
            ),
            "especialidad": (
                profesional.especialidad
                if profesional
                else "?"
            ),
            "profesional": (
                profesional.nombre
                if profesional
                else "?"
            ),
            "profesional_id": cita.profesional_id,
            "fecha": cita.fecha,
            "hora": cita.hora,
            "estado": cita.estado,
            "urgente": cita.urgente or False,
            "sobrecupo": cita.sobrecupo or False,
        })

    return resultado


@router.get("/profesional/{prof_id}/citas")
def get_citas_profesional_admin(
    prof_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_effective_permission(Permission.AGENDA_VER)),
):
    """
    Vista administrativa/operacional de la agenda de un profesional.

    Requiere Permission.AGENDA_VER (no ownership del profesional:
    esto es para Admin/Superadmin con lectura administrativa, no para el
    profesional dueño — ese caso ya está cubierto por su propio endpoint
    clínico protegido en profesionales.py).

    Devuelve exclusivamente campos operacionales: id, estudiante,
    estudiante_id, especialidad, fecha, hora, estado, urgente, sobrecupo.
    NO expone campos clínicos.
    """
    prof = db.query(Profesional).filter(Profesional.id == prof_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")

    alcance = obtener_alcance_administrativo_efectivo(
        db,
        current_user,
    )

    if (
        alcance is None
        or not especialidad_permitida_por_alcance(
            alcance,
            prof.especialidad,
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="El profesional esta fuera de tu alcance administrativo.",
        )

    citas = db.query(Cita).filter(Cita.profesional_id == prof_id).order_by(Cita.fecha, Cita.hora).all()

    result = []
    for c in citas:
        est = db.query(Usuario).filter(Usuario.id == c.estudiante_id).first()
        result.append({
            "id":            c.id,
            "estudiante":    est.nombre if est else "—",
            "estudiante_id": c.estudiante_id,
            "especialidad":  prof.especialidad,
            "fecha":         c.fecha,
            "hora":          c.hora,
            "estado":        c.estado,
            "urgente":       c.urgente or False,
            "sobrecupo":     c.sobrecupo or False,
        })
    return result


@router.get("/profesional/{profesional_id}/disponibilidad")
def get_disponibilidad_rango_admin(
    profesional_id: int,
    fecha_inicio: str,
    fecha_fin: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_effective_permission(Permission.AGENDA_VER)),
):
    """
    A.2B — disponibilidad real de un profesional, día por día, para un
    rango [fecha_inicio, fecha_fin] (YYYY-MM-DD, inclusive, máximo
    definido por agenda_disponibilidad_service.MAX_DIAS_RANGO_DISPONIBILIDAD
    días). Genérico por diseño: hoy lo consume la vista Semana de Agenda
    Admin, pero no está acoplado a 7 días — Día/Mes podrán reutilizarlo
    sin un endpoint nuevo.

    Requiere Permission.AGENDA_VER y respeta el alcance administrativo
    efectivo, igual que el resto de este router: el profesional
    solicitado se valida contra el alcance (institucional o por
    especialidad) SIN confiar en el profesional_id que envía el
    frontend. SUPERADMIN tiene alcance institucional administrativo,
    pero eso no le da acceso clínico universal — esto solo expone
    disponibilidad operacional (nunca datos clínicos).

    La evaluación de cada slot vive en
    app.services.agenda_disponibilidad_service.listar_disponibilidad_rango,
    que comparte núcleo con evaluar_disponibilidad_slot() (el que valida
    POST /citas). Este endpoint no reimplementa esa lógica: solo aplica
    RBAC/scope y adapta errores de dominio a HTTP.
    """
    profesional = (
        db.query(Profesional)
        .filter(Profesional.id == profesional_id)
        .first()
    )
    if not profesional:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")

    alcance = obtener_alcance_administrativo_efectivo(db, current_user)

    if (
        alcance is None
        or not especialidad_permitida_por_alcance(alcance, profesional.especialidad)
    ):
        raise HTTPException(
            status_code=403,
            detail="El profesional está fuera de tu alcance administrativo.",
        )

    try:
        return listar_disponibilidad_rango(
            db,
            profesional_id=profesional_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
    except ParametrosRangoInvalidosError as exc:
        raise HTTPException(status_code=400, detail=exc.mensaje)
    except ProfesionalNoEncontradoError:
        # Defensivo: ya se validó arriba, pero si el registro se borra
        # entre ambas consultas (carrera infrecuente), fail-closed igual.
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
