# -*- coding: utf-8 -*-
"""
SESAES — Inicio institucional de SUPERADMIN: endpoints de resumen.

Solo información administrativa AGREGADA. No expone datos clínicos,
correos, RUT ni contenido de fichas: únicamente conteos, series y listas
cortas de nombre/rol/estado.

── Autorización (fail-closed, sin permiso nuevo) ──

No se agrega ningún permiso al catálogo. Cada endpoint exige una
COMBINACIÓN de permisos ya existentes, resuelta con
`tiene_permiso_efectivo` (misma fuente que el resto de SA-9):

  · ROLES_GESTIONAR es la pieza institucional: pertenece a
    PERMISOS_RESERVADOS_SUPERADMIN, así que ningún perfil ADMIN puede
    recibirlo (ver app.rbac.admin_access). Es el mismo permiso que abre
    la sección "Administradores".
  · A eso se suma el permiso de DOMINIO del dato que se entrega
    (reportes.ver, usuarios.ver, agenda.gestionar), para que el endpoint
    nunca conceda por una vía nueva algo que el dominio no concede.
  · Además se exige alcance institucional: aquí no hay variante por
    especialidad, así que un alcance limitado falla cerrado.

No existe ningún atajo `if rol == superadmin`: SUPERADMIN pasa solo
porque ROLE_DEFAULT_PERMISSIONS lo lista explícitamente.

── Definiciones de métricas (documentadas, no inferidas) ──

  · "Cita contada": estado `pendiente` o `completada` (mismo criterio que
    /admin/graficos/especialidad y /admin/estadisticas). Excluye
    canceladas e inasistencias.
  · Citas este mes / por mes: por `Cita.fecha` (fecha de la cita, no de
    creación); incluye citas programadas y atendidas del mes.
  · Citas por mes: los últimos 12 meses calendario incluyendo el actual;
    los meses sin citas se devuelven con 0.
  · Profesionales más solicitados: top 5 por cantidad de citas contadas
    con fecha dentro de los últimos 90 días (hoy incluido). Empate: orden
    alfabético por nombre.
  · Especialidades: cantidad de valores DISTINTOS de
    Profesional.especialidad tras normalizar (no existe tabla de
    especialidades; el campo es texto libre).
  · Estudiantes registrados: cuentas con rol `estudiante`.
  · Profesionales activos: Profesional.estado == "activo".
  · Solicitudes pendientes: SolicitudHorario.estado == "pendiente".
  · Incidencias: eventos de auditoría con resultado `denegado` o `error`
    en los últimos 30 días. NO es un módulo formal de incidencias. Solo
    se calcula si el actor además tiene AUDITORIA_VER; si no, es null.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, null
from sqlalchemy.orm import Session

from app.auth_dependencies import get_current_user
from app.database import get_db
from app.models.auditoria import Auditoria
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.solicitud_horario import SolicitudHorario
from app.models.usuario import Usuario
from app.rbac.admin_access import normalizar_especialidad
from app.rbac.admin_authorization import (
    obtener_alcance_administrativo_efectivo,
    tiene_permiso_efectivo,
)
from app.rbac.permissions import Permission

router = APIRouter(prefix="/admin/inicio", tags=["administrador"])

# ── Parámetros de las métricas (ver docstring del módulo) ─────────
ESTADOS_CITA_CONTADOS = ("pendiente", "completada")
MESES_SERIE = 12
DIAS_TOP_PROFESIONALES = 90
TOP_PROFESIONALES = 5
DIAS_INCIDENCIAS = 30
RESULTADOS_INCIDENCIA = ("denegado", "error")
LIMITE_LISTAS = 5

# ── Combinaciones de permisos por endpoint ───────────────────────
PERMISOS_RESUMEN: tuple[Permission, ...] = (
    Permission.ROLES_GESTIONAR,
    Permission.REPORTES_VER,
)
PERMISOS_GESTION: tuple[Permission, ...] = (
    Permission.ROLES_GESTIONAR,
    Permission.USUARIOS_VER,
    # Igual que GET /admin/solicitudes-horario: leer solicitudes de
    # horario exige AGENDA_GESTIONAR, no basta con verlas.
    Permission.AGENDA_GESTIONAR,
)


def requerir_permisos_institucionales(
    *permisos: Permission,
) -> Callable[..., dict]:
    """
    Dependencia FastAPI: exige TODOS los `permisos` (autorización
    efectiva SA-9) y además alcance administrativo institucional.
    """

    def _dependency(
        current_user: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        for permiso in permisos:
            if not tiene_permiso_efectivo(db, current_user, permiso):
                raise HTTPException(
                    status_code=403,
                    detail="No tienes permiso para acceder a este recurso.",
                )

        alcance = obtener_alcance_administrativo_efectivo(db, current_user)

        if alcance is None or not alcance.institucional:
            raise HTTPException(
                status_code=403,
                detail="No tienes acceso al alcance solicitado.",
            )

        return current_user

    return _dependency


# ── Helpers de fechas ────────────────────────────────────────────
def _primer_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _sumar_meses(primer_dia: date, meses: int) -> date:
    """Suma `meses` a una fecha que ya es el día 1 de un mes."""
    total = primer_dia.year * 12 + (primer_dia.month - 1) + meses
    return date(total // 12, total % 12 + 1, 1)


def _iso(momento: Optional[datetime]) -> Optional[str]:
    return momento.isoformat() if momento else None


# ── Construcción de payloads (puras: fecha/hora inyectables) ─────
def _contar_especialidades(db: Session) -> int:
    claves: set[str] = set()

    for (especialidad,) in db.query(Profesional.especialidad).distinct().all():
        try:
            claves.add(normalizar_especialidad(especialidad).normalizada)
        except ValueError:
            # Vacía o no textual: no cuenta como especialidad.
            continue

    return len(claves)


def _citas_por_mes(db: Session, hoy: date) -> dict:
    ultimo = _primer_dia_mes(hoy)
    primero = _sumar_meses(ultimo, -(MESES_SERIE - 1))
    limite_exclusivo = _sumar_meses(ultimo, 1)

    mes_expr = func.substr(Cita.fecha, 1, 7)

    # Una sola consulta agrupada. Cita.fecha es texto ISO (YYYY-MM-DD),
    # por lo que la comparación lexicográfica equivale a la de fechas.
    filas = (
        db.query(mes_expr, func.count(Cita.id))
        .filter(
            Cita.fecha >= primero.isoformat(),
            Cita.fecha < limite_exclusivo.isoformat(),
            Cita.estado.in_(ESTADOS_CITA_CONTADOS),
        )
        .group_by(mes_expr)
        .all()
    )
    por_mes = {mes: cantidad for mes, cantidad in filas}

    meses = []
    cursor = primero
    for _ in range(MESES_SERIE):
        clave = cursor.strftime("%Y-%m")
        meses.append({"mes": clave, "cantidad": int(por_mes.get(clave, 0))})
        cursor = _sumar_meses(cursor, 1)

    return {
        "desde": meses[0]["mes"],
        "hasta": meses[-1]["mes"],
        "meses": meses,
    }


def _profesionales_mas_solicitados(db: Session, hoy: date) -> dict:
    desde = hoy - timedelta(days=DIAS_TOP_PROFESIONALES - 1)
    cantidad = func.count(Cita.id)

    filas = (
        db.query(
            Profesional.id,
            Profesional.nombre,
            Profesional.tratamiento,
            Profesional.especialidad,
            cantidad.label("cantidad"),
        )
        .join(Cita, Cita.profesional_id == Profesional.id)
        .filter(
            Cita.estado.in_(ESTADOS_CITA_CONTADOS),
            Cita.fecha >= desde.isoformat(),
            Cita.fecha <= hoy.isoformat(),
        )
        .group_by(
            Profesional.id,
            Profesional.nombre,
            Profesional.tratamiento,
            Profesional.especialidad,
        )
        .order_by(cantidad.desc(), Profesional.nombre.asc(), Profesional.id.asc())
        .limit(TOP_PROFESIONALES)
        .all()
    )

    return {
        "desde": desde.isoformat(),
        "hasta": hoy.isoformat(),
        "dias": DIAS_TOP_PROFESIONALES,
        "items": [
            {
                "profesional_id": f.id,
                "nombre": f.nombre,
                "tratamiento": f.tratamiento,
                "especialidad": f.especialidad,
                "cantidad": int(f.cantidad),
            }
            for f in filas
        ],
    }


def construir_resumen(
    db: Session,
    *,
    hoy: date,
    ahora: datetime,
    incluir_incidencias: bool,
) -> dict:
    desde_incidencias = ahora - timedelta(days=DIAS_INCIDENCIAS)

    # Los cuatro conteos simples viajan en UNA sola consulta (subconsultas
    # escalares): un round-trip en vez de uno por tarjeta.
    estudiantes = (
        db.query(func.count(Usuario.id))
        .filter(Usuario.rol == "estudiante")
        .scalar_subquery()
    )
    profesionales_activos = (
        db.query(func.count(Profesional.id))
        .filter(Profesional.estado == "activo")
        .scalar_subquery()
    )
    solicitudes_pendientes = (
        db.query(func.count(SolicitudHorario.id))
        .filter(SolicitudHorario.estado == "pendiente")
        .scalar_subquery()
    )
    incidencias = (
        db.query(func.count(Auditoria.id))
        .filter(
            Auditoria.resultado.in_(RESULTADOS_INCIDENCIA),
            Auditoria.fecha >= desde_incidencias,
        )
        .scalar_subquery()
        if incluir_incidencias
        else null()
    )

    fila = db.query(
        estudiantes,
        profesionales_activos,
        solicitudes_pendientes,
        incidencias,
    ).one()

    citas_por_mes = _citas_por_mes(db, hoy)

    return {
        "generado_en": ahora.isoformat(),
        "kpis": {
            "estudiantes_registrados": int(fila[0] or 0),
            "profesionales_activos": int(fila[1] or 0),
            # El mes en curso es el último de la serie: no se repite
            # la consulta.
            "citas_mes": citas_por_mes["meses"][-1]["cantidad"],
            "especialidades": _contar_especialidades(db),
            "solicitudes_pendientes": int(fila[2] or 0),
            "incidencias": (
                {"total": int(fila[3] or 0), "dias": DIAS_INCIDENCIAS}
                if incluir_incidencias
                else None
            ),
        },
        "citas_por_mes": citas_por_mes,
        "profesionales_mas_solicitados": _profesionales_mas_solicitados(db, hoy),
    }


def construir_gestion(db: Session) -> dict:
    ultimos = (
        db.query(
            Usuario.id,
            Usuario.nombre,
            Usuario.rol,
            Usuario.fecha_creacion,
        )
        # Los ids son monótonos: orden fiable incluso para cuentas
        # históricas sin fecha_creacion.
        .order_by(Usuario.id.desc())
        .limit(LIMITE_LISTAS)
        .all()
    )

    total_pendientes = (
        db.query(func.count(SolicitudHorario.id))
        .filter(SolicitudHorario.estado == "pendiente")
        .scalar()
        or 0
    )

    # Un solo JOIN: sin consultar el profesional fila por fila (N+1).
    pendientes = (
        db.query(SolicitudHorario, Profesional.nombre, Profesional.especialidad)
        .join(Profesional, Profesional.id == SolicitudHorario.profesional_id)
        .filter(SolicitudHorario.estado == "pendiente")
        .order_by(
            SolicitudHorario.fecha_solicitud.desc(),
            SolicitudHorario.id.desc(),
        )
        .limit(LIMITE_LISTAS)
        .all()
    )

    return {
        "ultimos_usuarios": [
            {
                "id": u.id,
                "nombre": u.nombre,
                "rol": u.rol,
                "fecha_creacion": _iso(u.fecha_creacion),
            }
            for u in ultimos
        ],
        "solicitudes_pendientes": {
            "total": int(total_pendientes),
            "items": [
                {
                    "id": s.id,
                    "profesional_id": s.profesional_id,
                    "profesional_nombre": nombre,
                    "especialidad": especialidad,
                    "tipo": s.tipo,
                    "hora_inicio": s.hora_inicio,
                    "hora_fin": s.hora_fin,
                    "estado": s.estado,
                    "fecha_solicitud": _iso(s.fecha_solicitud),
                }
                for s, nombre, especialidad in pendientes
            ],
        },
    }


# ── Endpoints ────────────────────────────────────────────────────
@router.get("/resumen")
def get_resumen_inicio(
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        requerir_permisos_institucionales(*PERMISOS_RESUMEN)
    ),
):
    return construir_resumen(
        db,
        hoy=date.today(),
        ahora=datetime.now(),
        incluir_incidencias=tiene_permiso_efectivo(
            db, current_user, Permission.AUDITORIA_VER
        ),
    )


@router.get("/gestion")
def get_gestion_inicio(
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        requerir_permisos_institucionales(*PERMISOS_GESTION)
    ),
):
    return construir_gestion(db)
