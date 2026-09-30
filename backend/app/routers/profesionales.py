from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from pydantic import BaseModel

from app.database import get_db
from app.security import (
    PASSWORD_POLICY_MESSAGE,
    hash_password,
    password_cumple_politica,
    verify_password,
)
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.models.notificacion import Notificacion
from app.models.bloque_horario_semanal import BloqueHorarioSemanal
from app.routers.correos import simular_envio_correo
from app.auth_dependencies import get_current_user, verificar_acceso_profesional
from app.rbac.permissions import Permission, has_permission
from app.rbac.admin_authorization import (
    tiene_permiso_admin_en_especialidad,
)
from app.rbac.clinical_capabilities import ClinicalCapability
from app.services.clinical_capabilities_service import resolver_capacidades_efectivas
from app.schemas import CompletarCitaBody
from app.auditoria import registrar_evento_auditoria
from app import reglas_horario

router = APIRouter(tags=["profesionales"])


class CambiarPasswordProfesionalIn(BaseModel):
    contrasena_actual: str
    contrasena_nueva: str

# SA-2: el helper local registrar_auditoria(...) se eliminó. Este router
# usa ahora app.auditoria.registrar_evento_auditoria, que deriva el actor
# (usuario_id, actor_rol) EXCLUSIVAMENTE de current_user y nunca hace
# commit/rollback por sí mismo — ver docstring de app/auditoria.py.


def _exigir_permiso_y_ownership_propio(
    current_user: dict, prof_id: int, db, permission: Permission
) -> None:
    """
    RBAC + ownership para endpoints "propios" del profesional (Fase 3.5F).

    Exige explícitamente:
      - que el usuario autenticado tenga `permission` (has_permission), Y
      - que sea el profesional dueño de `prof_id` (verificar_acceso_profesional,
        sin bypass admin/superadmin — ver auth_dependencies.py).

    Un profesional sin `permission` recibe 403 aunque sea dueño del recurso.
    Un profesional con `permission` pero sobre un prof_id ajeno también
    recibe 403. Ningún rol tiene atajo aquí: ROLE + PERMISSION + OWNERSHIP.
    """
    if not has_permission(current_user, permission):
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso.")
    verificar_acceso_profesional(current_user, prof_id, db, roles_permitidos=["profesional"])


def _notificar_con_agenda_gestionar(
    db,
    especialidad: str,
    mensaje: str,
    tipo: str = "info",
    email_asunto: str = None,
    email_cuerpo: str = None,
    email_referencia_id: int = None,
) -> None:
    """
    Notifica a usuarios administrativos activos con capacidad real
    agenda.gestionar para la especialidad del evento.

    ADMIN requiere configuracion valida, permiso persistido y alcance.
    SUPERADMIN conserva su permiso explicito definido por rol.
    """
    for u in db.query(Usuario).all():
        if not getattr(u, "activo", True):
            continue

        if u.rol == "admin":
            autorizado = tiene_permiso_admin_en_especialidad(
                db,
                u.id,
                Permission.AGENDA_GESTIONAR,
                especialidad,
            )
        else:
            autorizado = has_permission(
                u.rol,
                Permission.AGENDA_GESTIONAR,
            )

        if not autorizado:
            continue

        db.add(
            Notificacion(
                usuario_id=u.id,
                mensaje=mensaje,
                tipo=tipo,
            )
        )

        if email_asunto:
            simular_envio_correo(
                db,
                destinatario=u.correo or "",
                asunto=email_asunto,
                cuerpo=email_cuerpo or mensaje,
                tipo=tipo,
                referencia_id=email_referencia_id,
            )


# ══════════════════════════════════════
# ENDPOINT PÚBLICO — lista para estudiantes
# ══════════════════════════════════════

@router.get("/profesionales")
def get_profesionales(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # dias_con_bloque_disponible: un solo query para TODOS los
    # profesionales, agrupado por profesional_id — evita N+1 (un query
    # de BloqueHorarioSemanal por profesional dentro del for de abajo).
    dias_por_profesional: dict[int, set[int]] = {}
    for bloque in (
        db.query(BloqueHorarioSemanal)
        .filter(BloqueHorarioSemanal.tipo == "disponible")
        .all()
    ):
        dias_por_profesional.setdefault(bloque.profesional_id, set()).add(bloque.dia_semana)

    return [
        {
            "id":           p.id,
            "nombre":       p.nombre,
            "especialidad": p.especialidad,
            "iniciales":    p.iniciales,
            "descripcion":  p.descripcion,
            "foto_url":     p.foto_url,
            "duracion_min": p.duracion_min,
            "estado":       p.estado or "activo",
            # Días de semana (0=Lunes...4=Viernes) en que el profesional
            # ofrece horas — para que el estudiante no pueda ni
            # seleccionar en el calendario un día que este profesional
            # no atiende (ver app.reglas_horario.calcular_dias_disponibles).
            # None si el profesional no tiene ningún horario configurado
            # todavía (no bloquear de más algo que no se ha cargado).
            "dias_disponibles": reglas_horario.calcular_dias_disponibles(
                dias_por_profesional.get(p.id, set()),
                tiene_jornada_simple=bool(p.horario_inicio and p.horario_fin),
            ),
            # Fase 3.5F: correo y usuario_id ya no se exponen en este catálogo
            # autenticado. El login resuelve el profesional vía
            # /profesional/buscar-por-usuario/{usuario_id} (ownership estricto).
        }
        for p in db.query(Profesional).filter(Profesional.estado == "activo").all()
    ]


# ══════════════════════════════════════
# BUSCAR PROFESIONAL POR USUARIO_ID (para login)
# ══════════════════════════════════════

@router.get("/profesional/buscar-por-usuario/{usuario_id}")
def buscar_profesional_por_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Fase 3.5F: ownership estricto, sin bypass administrativo inline.
    if current_user["id"] != usuario_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso.")
    prof = db.query(Profesional).filter(Profesional.usuario_id == usuario_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    return {
        "id":           prof.id,
        "nombre":       prof.nombre,
        "especialidad": prof.especialidad,
        "estado":       prof.estado or "activo",
        "correo":       prof.correo,
        "usuario_id":   prof.usuario_id
    }
# ══════════════════════════════════════
# PERFIL DEL PROFESIONAL
# ══════════════════════════════════════
@router.get("/profesional/{prof_id}/perfil")
def get_perfil(
    prof_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    verificar_acceso_profesional(current_user, prof_id, db)
    prof = db.query(Profesional).filter(Profesional.id == prof_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    usuario = db.query(Usuario).filter(Usuario.id == prof.usuario_id).first()
    return {
        "id":           prof.id,
        "nombre":       prof.nombre,
        "especialidad": prof.especialidad,
        "iniciales":    prof.iniciales,
        "descripcion":  prof.descripcion,
        "correo":       prof.correo,
        "rut":          prof.rut,
        "estado":       prof.estado or "activo",
        "foto_url":     prof.foto_url,
        "duracion_min": prof.duracion_min,
        "tema_oscuro":  usuario.tema_oscuro if usuario else False,
        "usuario_id":   prof.usuario_id,
        "hora_almuerzo_inicio": prof.hora_almuerzo_inicio,
        "hora_almuerzo_fin":    prof.hora_almuerzo_fin,
        "horario_inicio": prof.horario_inicio,
        "horario_fin":    prof.horario_fin,
        # Agenda semanal por bloques ya APROBADA (no la solicitud
        # pendiente, que se obtiene aparte vía GET
        # /profesional/{id}/solicitudes-horario) — para que el
        # frontend precargue la grilla de bloques con lo que ya está
        # vigente en vez de partir siempre en blanco.
        "bloques_semanales": [
            {"dia_semana": b.dia_semana, "hora_inicio": b.hora_inicio,
             "hora_fin": b.hora_fin, "tipo": b.tipo}
            for b in db.query(BloqueHorarioSemanal)
                .filter(BloqueHorarioSemanal.profesional_id == prof_id)
                .all()
        ],
    }

@router.patch("/profesional/{prof_id}/perfil")
def actualizar_perfil(
    prof_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    verificar_acceso_profesional(current_user, prof_id, db)
    prof = db.query(Profesional).filter(Profesional.id == prof_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")

    if "nombre" in body:
        prof.nombre = body["nombre"]
    if "descripcion" in body:
        prof.descripcion = body["descripcion"]
    if "foto_url" in body:
        prof.foto_url = body["foto_url"]
    if "tema_oscuro" in body:
        usuario = db.query(Usuario).filter(Usuario.id == prof.usuario_id).first()
        if usuario:
            usuario.tema_oscuro = body["tema_oscuro"]

    registrar_evento_auditoria(db, current_user, "Profesional actualizó su perfil",
                                entidad="profesional", entidad_id=prof_id)
    db.commit()
    return {"message": "Perfil actualizado correctamente"}

@router.patch("/profesional/{prof_id}/cambiar-password")
def cambiar_password(
    prof_id: int,
    body: CambiarPasswordProfesionalIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    verificar_acceso_profesional(current_user, prof_id, db)
    prof = db.query(Profesional).filter(Profesional.id == prof_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")

    usuario = db.query(Usuario).filter(Usuario.id == prof.usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # FastAPI entrega CambiarPasswordProfesionalIn; se tolera dict en llamadas
    # directas de tests unitarios antiguos para no romper cobertura de ownership.
    if isinstance(body, dict):
        contrasena_actual = body.get("contrasena_actual")
        contrasena_nueva = body.get("contrasena_nueva")
    else:
        contrasena_actual = body.contrasena_actual
        contrasena_nueva = body.contrasena_nueva

    if not contrasena_actual or not contrasena_nueva:
        raise HTTPException(
            status_code=400,
            detail="Debes ingresar la contraseña actual y la nueva.",
        )

    if not password_cumple_politica(contrasena_nueva):
        raise HTTPException(
            status_code=400,
            detail=PASSWORD_POLICY_MESSAGE,
        )

    if not verify_password(contrasena_actual, usuario.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña actual es incorrecta.",
        )

    if verify_password(contrasena_nueva, usuario.password):
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña debe ser diferente a la actual.",
        )

    usuario.password = hash_password(contrasena_nueva)
    usuario.debe_cambiar_password = False
    db.commit()
    return {"message": "Contraseña actualizada correctamente"}


# ══════════════════════════════════════
# ESTADÍSTICAS DEL DÍA
# ══════════════════════════════════════

@router.get("/profesional/{prof_id}/estadisticas-dia")
def get_estadisticas_dia(
    prof_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_permiso_y_ownership_propio(current_user, prof_id, db, Permission.AGENDA_VER_PROFESIONAL)
    hoy = date.today().isoformat()
    citas_hoy = db.query(Cita).filter(Cita.profesional_id == prof_id, Cita.fecha == hoy).all()
    return {
        "total_hoy":     len(citas_hoy),
        "completadas":   len([c for c in citas_hoy if c.estado == "completada"]),
        "pendientes":    len([c for c in citas_hoy if c.estado == "pendiente"]),
        "inasistencias": len([c for c in citas_hoy if c.estado == "inasistencia"])
    }


# ══════════════════════════════════════
# CITAS SIN CERRAR (fecha ya pasó y siguen "pendiente" — nadie las marcó
# como completada ni como inasistencia). El profesional ve un aviso al
# entrar para que las cierre, en vez de quedar colgadas para siempre.
# ══════════════════════════════════════

@router.get("/profesional/{prof_id}/citas-sin-cerrar")
def get_citas_sin_cerrar(
    prof_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_permiso_y_ownership_propio(current_user, prof_id, db, Permission.AGENDA_VER_PROFESIONAL)
    hoy = date.today().isoformat()
    citas = db.query(Cita).filter(
        Cita.profesional_id == prof_id,
        Cita.estado == "pendiente",
        Cita.fecha < hoy
    ).order_by(Cita.fecha.desc()).all()

    resultado = []
    for c in citas:
        est = db.query(Usuario).filter(Usuario.id == c.estudiante_id).first()
        resultado.append({
            "id":          c.id,
            "estudiante":  est.nombre if est else "—",
            "rut":         est.rut if est else "—",
            "fecha":       c.fecha,
            "hora":        c.hora,
        })
    return resultado


# ══════════════════════════════════════
# CITAS DEL PROFESIONAL
# ══════════════════════════════════════

@router.get("/profesional/{prof_id}/citas")
def get_citas_profesional(
    prof_id: int,
    fecha: str = None,
    estado: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_permiso_y_ownership_propio(current_user, prof_id, db, Permission.ATENCIONES_VER_ASIGNADAS)
    query = db.query(Cita).filter(Cita.profesional_id == prof_id)
    if fecha:  query = query.filter(Cita.fecha == fecha)
    if estado: query = query.filter(Cita.estado == estado)
    citas = query.order_by(Cita.fecha, Cita.hora).all()
    result = []
    for c in citas:
        est = db.query(Usuario).filter(Usuario.id == c.estudiante_id).first()
        result.append({
            "id":                     c.id,
            "estudiante":             est.nombre  if est else "—",
            "estudiante_id":          c.estudiante_id,
            "rut":                    est.rut     if est else "—",
            "carrera":                est.carrera if est else "—",
            "correo_est":             est.correo  if est else "—",
            "foto_url":               est.foto_url if est else None,
            "fecha":                  c.fecha,
            "hora":                   c.hora,
            "estado":                 c.estado,
            "urgente":                c.urgente or False,
            "sobrecupo":              c.sobrecupo or False,
            "observaciones":          c.observaciones,
            "medicamento":            c.medicamento,
            "observaciones_atencion": c.observaciones_atencion
        })
    return result


# ══════════════════════════════════════
# COMPLETAR CITA
# ══════════════════════════════════════

@router.patch("/profesional/{prof_id}/citas/{cita_id}/completar")
def completar_cita(
    prof_id: int,
    cita_id: int,
    body: CompletarCitaBody,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Orden obligatorio (SA-11.3B): autenticación (get_current_user, ya
    # resuelta por la dependencia) -> ATENCIONES_REGISTRAR -> ownership
    # -> normalizar body -> si hay medicamento real, resolver capability
    # -> si falta la capability, 403 SIN mutar la cita -> recién ahí se
    # modifica `cita` -> commit. No debe existir ninguna asignación a
    # cita.estado/medicamento/observaciones_atencion antes de superar el
    # chequeo de capability.
    _exigir_permiso_y_ownership_propio(current_user, prof_id, db, Permission.ATENCIONES_REGISTRAR)
    cita = db.query(Cita).filter(Cita.id == cita_id, Cita.profesional_id == prof_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if cita.fecha > date.today().isoformat():
        raise HTTPException(status_code=400, detail="No puedes completar una cita que todavía no ocurre")

    # Normalización (SA-11.3B): None, "" y strings de solo espacios se
    # tratan como "sin medicamento" tanto para decidir si se exige la
    # capability como para lo que finalmente se persiste — un valor de
    # solo espacios NUNCA debe esquivar el chequeo ni quedar guardado
    # tal cual en Cita.medicamento. `observaciones_atencion` conserva el
    # mismo criterio de compatibilidad que ya tenía el `dict.get(...) or
    # None` anterior (ya trataba "" como None); acá se extiende el mismo
    # strip() por consistencia, sin agregar ninguna regla de negocio
    # nueva (p.ej. longitudes máximas siguen fuera de alcance).
    medicamento = body.medicamento.strip() if body.medicamento else None
    medicamento = medicamento or None
    observaciones_atencion = body.observaciones_atencion.strip() if body.observaciones_atencion else None
    observaciones_atencion = observaciones_atencion or None

    if medicamento is not None:
        prof = db.query(Profesional).filter(Profesional.id == prof_id).first()
        especialidad = prof.especialidad if prof else None
        capacidades = resolver_capacidades_efectivas(especialidad, db)
        if ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO.value not in capacidades:
            raise HTTPException(
                status_code=403,
                detail="No tienes la capacidad clínica para registrar medicamento suministrado.",
            )

    cita.estado                 = "completada"
    cita.medicamento            = medicamento
    cita.observaciones_atencion = observaciones_atencion
    est = db.query(Usuario).filter(Usuario.id == cita.estudiante_id).first()
    registrar_evento_auditoria(db, current_user, "Profesional completó cita",
                                entidad="cita", entidad_id=cita_id,
                                detalle=f"Estudiante: {est.nombre if est else '—'} — {cita.fecha} {cita.hora}")
    db.commit()
    return {"message": "Cita marcada como completada"}


# ══════════════════════════════════════
# INASISTENCIA
# ══════════════════════════════════════

@router.patch("/profesional/{prof_id}/citas/{cita_id}/inasistencia")
def marcar_inasistencia(
    prof_id: int,
    cita_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_permiso_y_ownership_propio(current_user, prof_id, db, Permission.AGENDA_GESTIONAR_PROPIA)
    prof = (
        db.query(Profesional)
        .filter(
            Profesional.id == prof_id
        )
        .first()
    )

    if not prof:
        raise HTTPException(
            status_code=404,
            detail="Profesional no encontrado",
        )

    cita = db.query(Cita).filter(Cita.id == cita_id, Cita.profesional_id == prof_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if cita.fecha > date.today().isoformat():
        raise HTTPException(status_code=400, detail="No puedes marcar inasistencia de una cita que todavía no ocurre")
    est = db.query(Usuario).filter(Usuario.id == cita.estudiante_id).first()
    cita.estado = "inasistencia"
    _notificar_con_agenda_gestionar(
        db,
        prof.especialidad,
        mensaje=f"Inasistencia: {est.nombre if est else '—'} no asistió a su cita del {cita.fecha} a las {cita.hora}.",
        tipo="info",
    )
    registrar_evento_auditoria(db, current_user, "Profesional marcó inasistencia",
                                entidad="cita", entidad_id=cita_id,
                                detalle=f"Estudiante: {est.nombre if est else '—'} — {cita.fecha} {cita.hora}")
    db.commit()
    return {"message": "Inasistencia registrada"}


# ══════════════════════════════════════
# ACEPTAR / RECHAZAR CITA PENDIENTE
# ══════════════════════════════════════
#
# "Aceptar" y "rechazar" son sobre la CITA (el compromiso de horario),
# no sobre la ATENCIÓN — por eso no tocan completar_cita/marcar_inasistencia
# más arriba, que sí son sobre lo clínico. Aceptar es deliberadamente
# "manso": solo confirma y notifica, NO cambia cita.estado — sigue
# "pendiente" hasta el día de la atención, respetando la regla
# "Cita ≠ Atención" del Documento Maestro (una cita aceptada todavía
# tiene que pasar por completar/inasistencia ese día). Rechazar sí
# muta el estado: reutiliza "cancelada" + el flag
# rechazada_por_profesional, para no inventar un 5º estado con color
# propio — mismo patrón que cancelada_por_admin.

@router.patch("/profesional/{prof_id}/citas/{cita_id}/aceptar")
def aceptar_cita(
    prof_id: int,
    cita_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_permiso_y_ownership_propio(current_user, prof_id, db, Permission.AGENDA_GESTIONAR_PROPIA)
    cita = db.query(Cita).filter(Cita.id == cita_id, Cita.profesional_id == prof_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if cita.estado != "pendiente":
        raise HTTPException(status_code=400, detail="Solo se puede aceptar una cita pendiente")

    est = db.query(Usuario).filter(Usuario.id == cita.estudiante_id).first()
    if est:
        db.add(Notificacion(
            usuario_id=est.id,
            mensaje=f"Tu cita del {cita.fecha} a las {cita.hora} fue confirmada por el profesional.",
            tipo="info",
        ))
    registrar_evento_auditoria(db, current_user, "Profesional aceptó cita",
                                entidad="cita", entidad_id=cita_id,
                                detalle=f"Estudiante: {est.nombre if est else '—'} — {cita.fecha} {cita.hora}")
    db.commit()
    return {"message": "Cita aceptada y confirmada"}


@router.patch("/profesional/{prof_id}/citas/{cita_id}/rechazar")
def rechazar_cita(
    prof_id: int,
    cita_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _exigir_permiso_y_ownership_propio(current_user, prof_id, db, Permission.AGENDA_GESTIONAR_PROPIA)
    cita = db.query(Cita).filter(Cita.id == cita_id, Cita.profesional_id == prof_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if cita.estado != "pendiente":
        raise HTTPException(status_code=400, detail="Solo se puede rechazar una cita pendiente")

    motivo = (body or {}).get("motivo")
    if not motivo:
        raise HTTPException(status_code=400, detail="Debes indicar un motivo de rechazo")

    cita.estado = "cancelada"
    cita.rechazada_por_profesional = True
    cita.motivo_cancelacion = motivo

    est = db.query(Usuario).filter(Usuario.id == cita.estudiante_id).first()
    if est:
        db.add(Notificacion(
            usuario_id=est.id,
            mensaje=f"Tu cita del {cita.fecha} a las {cita.hora} fue rechazada por el profesional. Motivo: {motivo}",
            tipo="advertencia",
        ))
    prof = db.query(Profesional).filter(Profesional.id == prof_id).first()
    _notificar_con_agenda_gestionar(
        db,
        prof.especialidad if prof else None,
        mensaje=f"{est.nombre if est else '—'}: cita del {cita.fecha} {cita.hora} fue rechazada por el profesional. Motivo: {motivo}",
        tipo="info",
    )
    registrar_evento_auditoria(db, current_user, "Profesional rechazó cita",
                                entidad="cita", entidad_id=cita_id,
                                detalle=f"Estudiante: {est.nombre if est else '—'} — {cita.fecha} {cita.hora} — Motivo: {motivo}")
    db.commit()
    return {"message": "Cita rechazada"}



# ══════════════════════════════════════
# NOTIFICACIONES DEL PROFESIONAL
# ══════════════════════════════════════

@router.get("/profesional/{prof_id}/notificaciones")
def get_notificaciones_profesional(
    prof_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    verificar_acceso_profesional(current_user, prof_id, db)
    prof = db.query(Profesional).filter(Profesional.id == prof_id).first()
    if not prof or not prof.usuario_id:
        return []
    notifs = db.query(Notificacion).filter(
        Notificacion.usuario_id == prof.usuario_id
    ).order_by(Notificacion.fecha_creacion.desc()).limit(50).all()
    return [
        {
            "id":             n.id,
            "mensaje":        n.mensaje,
            "tipo":           n.tipo,
            "leida":          n.leida,
            "fecha_creacion": n.fecha_creacion.isoformat() if n.fecha_creacion else None
        }
        for n in notifs
    ]
