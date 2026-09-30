from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.models.historial_plantilla_pregunta import HistorialPlantillaPregunta
from app.models.historial_paciente import HistorialPaciente
from app.auth_dependencies import get_current_user, verificar_acceso_profesional
from app.rbac.permissions import Permission, has_permission

router = APIRouter(prefix="/historial-clinico", tags=["historial-clinico"])


# ══════════════════════════════════════
# Preguntas por defecto para especialidades nuevas
# (se crean solo la primera vez que una especialidad pide su plantilla)
# ══════════════════════════════════════
PREGUNTAS_BASE = [
    {"etiqueta": "Edad",                                              "tipo": "numero"},
    {"etiqueta": "¿Es alérgico a algún medicamento o sustancia?",     "tipo": "si_no"},
    {"etiqueta": "Detalle de la alergia (si aplica)",                 "tipo": "texto"},
    {"etiqueta": "¿Algún padre o familiar directo tiene una enfermedad genética o crónica?", "tipo": "textarea"},
    {"etiqueta": "¿Fuma?",                                            "tipo": "si_no"},
    {"etiqueta": "¿Consume alcohol?",                                 "tipo": "si_no"},
    {"etiqueta": "Observaciones adicionales",                         "tipo": "textarea"},
]


# ══════════════════════════════════════
# Schemas
# ══════════════════════════════════════
class PreguntaIn(BaseModel):
    id: Optional[int] = None   # None = pregunta nueva
    etiqueta: str
    tipo: str = "texto"        # texto | numero | si_no | textarea
    orden: int = 0


class PlantillaUpdateIn(BaseModel):
    preguntas: list[PreguntaIn]


class HistorialGuardarIn(BaseModel):
    respuestas: dict


# ══════════════════════════════════════
# Helpers
# ══════════════════════════════════════
def _get_profesional_o_404(profesional_id: int, db: Session) -> Profesional:
    prof = db.query(Profesional).filter(Profesional.id == profesional_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    return prof


# Estados de Cita que constituyen una relación clínica vigente entre un
# profesional y un estudiante. "cancelada" e "inasistencia" NO cuentan:
# nunca llegó a existir un vínculo clínico real por esa cita.
_ESTADOS_RELACION_VALIDA = ("pendiente", "completada")


def _tiene_relacion_clinica(profesional_id: int, estudiante_id: int, db: Session) -> bool:
    """
    Determina si existe una RELACIÓN CLÍNICA CONCRETA entre este profesional
    y este estudiante (Prioridad 1, Fase 3.5F).

    Existe relación válida si:
      1. ya existe una HistorialPaciente para ese par profesional+estudiante
         (ficha ya iniciada, sin importar el estado de las citas actuales), O
      2. existe al menos una Cita entre ese profesional y ese estudiante con
         estado "pendiente" o "completada".

    Una cita "cancelada" o "inasistencia" NUNCA crea relación por sí sola.
    No se autoriza por especialidad, por nombre, ni porque otro profesional
    haya atendido al mismo estudiante — la relación es siempre el par
    (profesional_id, estudiante_id) concreto.
    """
    from app.models.cita import Cita

    ficha = db.query(HistorialPaciente).filter(
        HistorialPaciente.profesional_id == profesional_id,
        HistorialPaciente.estudiante_id == estudiante_id,
    ).first()
    if ficha:
        return True

    cita_valida = db.query(Cita).filter(
        Cita.profesional_id == profesional_id,
        Cita.estudiante_id == estudiante_id,
        Cita.estado.in_(_ESTADOS_RELACION_VALIDA),
    ).first()
    return cita_valida is not None


def _exigir_acceso_clinico(
    current_user: dict, profesional_id: int, estudiante_id: int, db: Session, permission: Permission
) -> None:
    """
    Acceso a un recurso clínico concreto (ficha de UN estudiante) exige las
    tres condiciones a la vez (Prioridad 1, Fase 3.5F):

      PERMISSION + OWNERSHIP PROFESIONAL + RELACIÓN CLÍNICA CONCRETA = ACCESO

    Si falta cualquiera de las tres: 403. Sin bypass para ADMIN ni
    SUPERADMIN — ninguno de los dos recibe permisos clínicos por defecto
    (ver ROLE_DEFAULT_PERMISSIONS) y verificar_acceso_profesional exige
    además rol "profesional" + ownership real.
    """
    if not has_permission(current_user, permission):
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso.")
    verificar_acceso_profesional(current_user, profesional_id, db, roles_permitidos=["profesional"])
    if not _tiene_relacion_clinica(profesional_id, estudiante_id, db):
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso.")


def _asegurar_plantilla_base(prof: Profesional, db: Session) -> None:
    """
    Garantiza que el profesional tenga su propio set de preguntas.

    Si nunca ha tenido preguntas propias, se le da un punto de partida:
      1. Si existen preguntas "legacy" de su especialidad (de antes de este
         cambio, cuando las preguntas se compartían por especialidad), se
         las copia — así ningún profesional amanece con el cuestionario
         en blanco el día que se activa este cambio.
      2. Si no hay legacy (especialidad nueva, o profesional nuevo sin
         historial), se usan las PREGUNTAS_BASE genéricas.
    A partir de ahí, cada profesional edita su propia copia libremente,
    sin afectar a otros profesionales de la misma especialidad.
    """
    existe = db.query(HistorialPlantillaPregunta).filter(
        HistorialPlantillaPregunta.profesional_id == prof.id
    ).first()
    if existe:
        return

    legacy = db.query(HistorialPlantillaPregunta).filter(
        HistorialPlantillaPregunta.especialidad == prof.especialidad,
        HistorialPlantillaPregunta.profesional_id.is_(None)
    ).order_by(HistorialPlantillaPregunta.orden).all()

    fuente = (
        [{"etiqueta": p.etiqueta, "tipo": p.tipo} for p in legacy]
        if legacy else PREGUNTAS_BASE
    )

    for i, p in enumerate(fuente):
        db.add(HistorialPlantillaPregunta(
            profesional_id=prof.id, especialidad=prof.especialidad,
            etiqueta=p["etiqueta"], tipo=p["tipo"], orden=i, activa=True
        ))
    db.commit()


# ══════════════════════════════════════
# Plantilla de preguntas (propia de cada profesional)
# ══════════════════════════════════════
@router.get("/plantilla/{profesional_id}")
def obtener_plantilla(
    profesional_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    verificar_acceso_profesional(current_user, profesional_id, db)
    prof = _get_profesional_o_404(profesional_id, db)
    _asegurar_plantilla_base(prof, db)

    preguntas = db.query(HistorialPlantillaPregunta).filter(
        HistorialPlantillaPregunta.profesional_id == profesional_id,
        HistorialPlantillaPregunta.activa == True  # noqa: E712
    ).order_by(HistorialPlantillaPregunta.orden).all()

    return {
        "especialidad": prof.especialidad,
        "preguntas": [
            {"id": p.id, "etiqueta": p.etiqueta, "tipo": p.tipo, "orden": p.orden}
            for p in preguntas
        ]
    }


@router.put("/plantilla/{profesional_id}")
def actualizar_plantilla(
    profesional_id: int,
    datos: PlantillaUpdateIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Reemplaza el set de preguntas propias de este profesional. Las preguntas
    que ya no vienen en la lista se desactivan (no se borran, para no perder
    las respuestas ya guardadas por pacientes anteriores con esa pregunta).
    """
    verificar_acceso_profesional(current_user, profesional_id, db)
    prof = _get_profesional_o_404(profesional_id, db)
    _asegurar_plantilla_base(prof, db)

    existentes = db.query(HistorialPlantillaPregunta).filter(
        HistorialPlantillaPregunta.profesional_id == profesional_id
    ).all()
    ids_recibidos = {p.id for p in datos.preguntas if p.id is not None}

    # Desactiva las que ya no vienen
    for e in existentes:
        e.activa = e.id in ids_recibidos

    # Actualiza o crea
    for i, p in enumerate(datos.preguntas):
        if p.id is not None:
            existente = next((e for e in existentes if e.id == p.id), None)
            if existente:
                existente.etiqueta = p.etiqueta
                existente.tipo     = p.tipo
                existente.orden    = i
                existente.activa   = True
                continue
        db.add(HistorialPlantillaPregunta(
            profesional_id=profesional_id, especialidad=prof.especialidad,
            etiqueta=p.etiqueta, tipo=p.tipo, orden=i, activa=True
        ))

    db.commit()
    return {"message": "Plantilla actualizada correctamente"}


# ══════════════════════════════════════
# CUESTIONARIO RESPONDIDO POR EL ESTUDIANTE (primera atención)
# ══════════════════════════════════════
# Un estudiante debe responder el cuestionario de un profesional SOLO la
# primera vez que lo verá (es decir: mientras no exista todavía una fila en
# HistorialPaciente para ese par profesional+estudiante). No se guarda un
# flag aparte para esto — se calcula al vuelo comprobando si la ficha existe,
# así nunca puede quedar desincronizado.

class RespuestasEstudianteIn(BaseModel):
    respuestas: dict


@router.get("/cuestionarios-pendientes/{estudiante_id}")
def cuestionarios_pendientes(
    estudiante_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista los profesionales con quienes el estudiante tiene AL MENOS UNA
    cita (pendiente o ya completada) y todavía no tiene ficha de
    antecedentes. Cubre tanto el caso normal (recién agendó por primera
    vez) como el retroactivo: pacientes que ya se atendieron varias veces
    antes de que existiera este cuestionario y nunca lo respondieron.
    El dashboard del estudiante usa esto para mostrar la tarea pendiente.
    """
    # Fase 3.5F (corrección final): recurso propio del estudiante dentro
    # del dominio clínico — mismo criterio de ownership estricto que
    # estudiante.py. Se retira "admin" de roles_permitidos por defensa en
    # profundidad (verificar_acceso ya exige current_user["id"] ==
    # estudiante_id, así que un ADMIN/SUPERADMIN solo podía "colarse" si
    # su propio Usuario.id coincidiera por accidente con el
    # estudiante_id solicitado). Acceso administrativo a este dato, si
    # corresponde, se resuelve con un permiso RBAC explícito en un
    # endpoint dedicado, nunca como atajo de rol dentro de este helper
    # de ownership.
    from app.auth_dependencies import verificar_acceso
    verificar_acceso(current_user, id_esperado=estudiante_id, roles_permitidos=["estudiante"])

    from app.models.cita import Cita

    todas_las_citas = db.query(Cita).filter(
        Cita.estudiante_id == estudiante_id,
        Cita.estado.in_(["pendiente", "completada"])
    ).order_by(Cita.fecha.desc()).all()

    if not todas_las_citas:
        return []

    profesional_ids = {c.profesional_id for c in todas_las_citas}
    fichas_existentes = db.query(HistorialPaciente.profesional_id).filter(
        HistorialPaciente.estudiante_id == estudiante_id,
        HistorialPaciente.profesional_id.in_(profesional_ids)
    ).all()
    ids_con_ficha = {f[0] for f in fichas_existentes}

    pendientes = []
    vistos = set()
    for c in todas_las_citas:
        if c.profesional_id in ids_con_ficha or c.profesional_id in vistos:
            continue
        vistos.add(c.profesional_id)
        prof = db.query(Profesional).filter(Profesional.id == c.profesional_id).first()
        if not prof:
            continue
        pendientes.append({
            "profesional_id": prof.id,
            "profesional_nombre": prof.nombre,
            "especialidad": prof.especialidad,
            "cita_id": c.id,
            "fecha": c.fecha,
            "hora": c.hora,
        })
    return pendientes


@router.get("/cuestionario-estudiante/{profesional_id}")
def obtener_cuestionario_para_estudiante(
    profesional_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """El propio estudiante consulta las preguntas de un profesional para responderlas."""
    from app.auth_dependencies import verificar_rol
    verificar_rol(current_user, roles_permitidos=["estudiante"])

    prof = _get_profesional_o_404(profesional_id, db)
    estudiante_id = current_user["id"]

    from app.models.cita import Cita
    tiene_cita = db.query(Cita).filter(
        Cita.profesional_id == profesional_id,
        Cita.estudiante_id == estudiante_id,
        Cita.estado.in_(_ESTADOS_RELACION_VALIDA),
    ).first()
    if not tiene_cita:
        raise HTTPException(status_code=403, detail="Solo puedes responder el cuestionario de un profesional con el que tengas una cita.")

    ya_existe = db.query(HistorialPaciente).filter(
        HistorialPaciente.profesional_id == profesional_id,
        HistorialPaciente.estudiante_id  == estudiante_id
    ).first()
    if ya_existe:
        raise HTTPException(status_code=400, detail="Ya respondiste este cuestionario anteriormente. Cualquier actualización la revisa tu profesional en la consulta.")

    _asegurar_plantilla_base(prof, db)
    preguntas = db.query(HistorialPlantillaPregunta).filter(
        HistorialPlantillaPregunta.profesional_id == profesional_id,
        HistorialPlantillaPregunta.activa == True  # noqa: E712
    ).order_by(HistorialPlantillaPregunta.orden).all()

    return {
        "profesional_nombre": prof.nombre,
        "especialidad": prof.especialidad,
        "preguntas": [
            {"id": p.id, "etiqueta": p.etiqueta, "tipo": p.tipo, "orden": p.orden}
            for p in preguntas
        ]
    }


@router.post("/cuestionario-estudiante/{profesional_id}")
def responder_cuestionario_estudiante(
    profesional_id: int,
    datos: RespuestasEstudianteIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    El estudiante envía sus respuestas por primera vez. Crea la ficha con
    completado_por='estudiante' y revisado_por_profesional=False, para que
    el profesional vea que está pendiente de su revisión en la consulta.
    """
    from app.auth_dependencies import verificar_rol
    verificar_rol(current_user, roles_permitidos=["estudiante"])

    _get_profesional_o_404(profesional_id, db)
    estudiante_id = current_user["id"]

    from app.models.cita import Cita
    tiene_cita = db.query(Cita).filter(
        Cita.profesional_id == profesional_id,
        Cita.estudiante_id == estudiante_id,
        Cita.estado.in_(_ESTADOS_RELACION_VALIDA),
    ).first()
    if not tiene_cita:
        raise HTTPException(status_code=403, detail="Solo puedes responder el cuestionario de un profesional con el que tengas una cita.")

    ya_existe = db.query(HistorialPaciente).filter(
        HistorialPaciente.profesional_id == profesional_id,
        HistorialPaciente.estudiante_id  == estudiante_id
    ).first()
    if ya_existe:
        raise HTTPException(status_code=400, detail="Ya respondiste este cuestionario anteriormente.")

    historial = HistorialPaciente(
        profesional_id=profesional_id,
        estudiante_id=estudiante_id,
        respuestas=datos.respuestas,
        completado_por="estudiante",
        revisado_por_profesional=False,
    )
    db.add(historial)
    db.commit()
    return {"message": "Cuestionario enviado correctamente. Tu profesional lo revisará en tu consulta."}


@router.get("/{profesional_id}/pacientes")
def listar_pacientes_atendidos(
    profesional_id: int,
    anio: Optional[int] = None,
    busqueda: Optional[str] = None,   # nombre o RUT
    carrera: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista los estudiantes que este profesional ha atendido (según sus citas),
    junto con si ya tienen ficha de antecedentes creada, cuántas veces han
    venido y hace cuánto fue su última visita.

    Filtros opcionales:
      - anio: solo pacientes con al menos una cita en ese año
      - busqueda: coincidencia parcial en nombre o RUT
      - carrera: coincidencia parcial en carrera
    """
    if not has_permission(current_user, Permission.FICHA_VER_ASIGNADA):
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso.")
    verificar_acceso_profesional(current_user, profesional_id, db, roles_permitidos=["profesional"])
    from app.models.cita import Cita
    from datetime import date as date_cls

    # Solo citas que constituyen relación clínica vigente (pendiente o
    # completada) determinan qué estudiantes aparecen en este listado —
    # una cancelada o una inasistencia no crean, por sí solas, un
    # "paciente" del profesional. Se incluyen pendientes para que el
    # profesional pueda prepararse antes de la consulta.
    query_citas = db.query(Cita).filter(
        Cita.profesional_id == profesional_id,
        Cita.estado.in_(_ESTADOS_RELACION_VALIDA),
    )
    if anio:
        query_citas = query_citas.filter(Cita.fecha.startswith(str(anio)))
    todas_las_citas = query_citas.all()

    # Agrupamos en Python (el volumen esperado por profesional es bajo,
    # no justifica una query agregada más compleja).
    citas_por_estudiante: dict[int, list] = {}
    for c in todas_las_citas:
        citas_por_estudiante.setdefault(c.estudiante_id, []).append(c)

    estudiantes_ids = list(citas_por_estudiante.keys())
    if not estudiantes_ids:
        return []

    query_est = db.query(Usuario).filter(Usuario.id.in_(estudiantes_ids))
    if busqueda:
        like = f"%{busqueda}%"
        query_est = query_est.filter(
            (Usuario.nombre.ilike(like)) | (Usuario.rut.ilike(like))
        )
    if carrera:
        query_est = query_est.filter(Usuario.carrera.ilike(f"%{carrera}%"))
    estudiantes = query_est.all()

    fichas = db.query(HistorialPaciente).filter(
        HistorialPaciente.profesional_id == profesional_id,
        HistorialPaciente.estudiante_id.in_(estudiantes_ids)
    ).all()
    ids_con_ficha = {f.estudiante_id for f in fichas}
    ids_pendiente_revision = {f.estudiante_id for f in fichas if not f.revisado_por_profesional}

    hoy = date_cls.today()
    resultado = []
    for e in estudiantes:
        citas = citas_por_estudiante.get(e.id, [])
        # Métricas de "atención" cuentan SOLO citas completadas: una
        # pendiente todavía no ocurrió, así que no suma atención ni
        # mueve la última visita. total_atenciones cuenta TODAS las
        # completadas aunque alguna tenga fecha inválida/legacy — sigue
        # siendo una atención real, solo que no aporta a ultima_visita.
        citas_completadas = [c for c in citas if c.estado == "completada"]
        fechas_completadas = []
        for c in citas_completadas:
            try:
                fechas_completadas.append(datetime.strptime(c.fecha, "%Y-%m-%d").date())
            except (ValueError, TypeError):
                continue

        ultima_visita = max(fechas_completadas).isoformat() if fechas_completadas else None
        dias_desde_ultima = (hoy - max(fechas_completadas)).days if fechas_completadas else None

        resultado.append({
            "estudiante_id":          e.id,
            "nombre":                 e.nombre,
            "rut":                    e.rut,
            "correo":                 e.correo,
            "carrera":                e.carrera,
            "foto_url":               e.foto_url,
            "tiene_ficha":            e.id in ids_con_ficha,
            "pendiente_revision":     e.id in ids_pendiente_revision,
            "total_atenciones":       len(citas_completadas),
            "ultima_visita":          ultima_visita,
            "dias_desde_ultima_visita": dias_desde_ultima,
        })

    resultado.sort(key=lambda r: r["ultima_visita"] or "", reverse=True)
    return resultado


# ══════════════════════════════════════
# Ficha del paciente (por profesional + estudiante)
# ══════════════════════════════════════
@router.get("/{profesional_id}/{estudiante_id}")
def obtener_historial(
    profesional_id: int,
    estudiante_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_acceso_clinico(current_user, profesional_id, estudiante_id, db, Permission.FICHA_VER_ASIGNADA)
    prof = _get_profesional_o_404(profesional_id, db)
    estudiante = db.query(Usuario).filter(Usuario.id == estudiante_id).first()
    if not estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    _asegurar_plantilla_base(prof, db)
    preguntas = db.query(HistorialPlantillaPregunta).filter(
        HistorialPlantillaPregunta.profesional_id == profesional_id,
        HistorialPlantillaPregunta.activa == True  # noqa: E712
    ).order_by(HistorialPlantillaPregunta.orden).all()

    historial = db.query(HistorialPaciente).filter(
        HistorialPaciente.profesional_id == profesional_id,
        HistorialPaciente.estudiante_id  == estudiante_id
    ).first()

    # Todas las citas que este estudiante ha tenido con este profesional
    # (para la vista "ver todas sus atenciones" al hacer clic en el paciente).
    # Se muestran TODAS (incluidas canceladas/inasistencia) como registro
    # informativo, pero las MÉTRICAS de abajo (total_atenciones, última
    # visita, etc.) cuentan únicamente citas "completada": solo una
    # atención realmente ocurrida cuenta como atención.
    from app.models.cita import Cita
    citas = db.query(Cita).filter(
        Cita.profesional_id == profesional_id,
        Cita.estudiante_id  == estudiante_id
    ).order_by(Cita.fecha.desc(), Cita.hora.desc()).all()

    # total_atenciones cuenta TODAS las citas completadas, aunque alguna
    # tenga una fecha inválida/legacy que no se pueda parsear — sigue
    # siendo una atención real. fechas_completadas (para ultima_visita y
    # dias_desde_ultima_visita) solo puede usar las fechas que sí se
    # lograron convertir.
    citas_completadas = [c for c in citas if c.estado == "completada"]
    fechas_completadas = []
    for c in citas_completadas:
        try:
            fechas_completadas.append(datetime.strptime(c.fecha, "%Y-%m-%d").date())
        except (ValueError, TypeError):
            continue

    return {
        "existe": historial is not None,
        "estudiante_nombre": estudiante.nombre,
        "estudiante_rut":     estudiante.rut,
        "estudiante_carrera": estudiante.carrera,
        "estudiante_correo":  estudiante.correo,
        "estudiante_foto_url": estudiante.foto_url,
        "preguntas": [
            {"id": p.id, "etiqueta": p.etiqueta, "tipo": p.tipo, "orden": p.orden}
            for p in preguntas
        ],
        "respuestas": historial.respuestas if historial else {},
        "fecha_creacion":     historial.fecha_creacion if historial else None,
        "fecha_modificacion": historial.fecha_modificacion if historial else None,
        "completado_por":            historial.completado_por if historial else None,
        "revisado_por_profesional":  historial.revisado_por_profesional if historial else True,
        "citas": [
            {
                "id":                     c.id,
                "fecha":                  c.fecha,
                "hora":                   c.hora,
                "estado":                 c.estado,
                "motivo_consulta":        c.observaciones,
                "medicamento":            c.medicamento,
                "observaciones_atencion": c.observaciones_atencion,
                "motivo_cancelacion":     c.motivo_cancelacion,
            }
            for c in citas
        ],
        "total_atenciones":         len(citas_completadas),
        "ultima_visita":            max(fechas_completadas).isoformat() if fechas_completadas else None,
        "dias_desde_ultima_visita": (datetime.now().date() - max(fechas_completadas)).days if fechas_completadas else None,
    }


@router.put("/{profesional_id}/{estudiante_id}")
def guardar_historial(
    profesional_id: int,
    estudiante_id: int,
    datos: HistorialGuardarIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_acceso_clinico(current_user, profesional_id, estudiante_id, db, Permission.FICHA_EDITAR_ASIGNADA)
    prof = _get_profesional_o_404(profesional_id, db)
    estudiante = db.query(Usuario).filter(Usuario.id == estudiante_id).first()
    if not estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    historial = db.query(HistorialPaciente).filter(
        HistorialPaciente.profesional_id == profesional_id,
        HistorialPaciente.estudiante_id  == estudiante_id
    ).first()

    if historial:
        historial.respuestas = datos.respuestas
        historial.revisado_por_profesional = True   # el profesional acaba de editar/confirmar
    else:
        historial = HistorialPaciente(
            profesional_id=profesional_id, estudiante_id=estudiante_id,
            respuestas=datos.respuestas, completado_por="profesional",
            revisado_por_profesional=True
        )
        db.add(historial)

    db.commit()
    return {"message": "Ficha guardada correctamente"}


