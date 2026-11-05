from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.correo_log import CorreoLog
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.rbac.dependencies import require_effective_permission
from app.rbac.admin_authorization import (
    obtener_alcance_administrativo_efectivo,
    especialidad_permitida_por_alcance,
)
from app.rbac.permissions import Permission

import smtplib
import ssl
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

router = APIRouter(prefix="/correos", tags=["correos"])

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL


def _enviar_smtp(destinatario: str, asunto: str, cuerpo: str) -> tuple[bool, str | None]:
    """
    Intenta enviar el correo de verdad vía Gmail SMTP.
    Devuelve (exito: bool, error: str | None).

    Si las variables de entorno SMTP_EMAIL / SMTP_APP_PASSWORD no están
    configuradas, no lo intenta y devuelve un error descriptivo — así el
    sistema sigue funcionando sin romperse mientras alguien configura las
    credenciales (ver .env.example).
    """
    smtp_email        = os.getenv("SMTP_EMAIL")
    smtp_app_password = os.getenv("SMTP_APP_PASSWORD")
    nombre_remitente   = os.getenv("SMTP_NOMBRE_REMITENTE", "SESAES")

    if not smtp_email or not smtp_app_password:
        return False, "SMTP no configurado (faltan SMTP_EMAIL / SMTP_APP_PASSWORD en el .env)"
    if not destinatario:
        return False, "Sin destinatario"

    try:
        mensaje = MIMEMultipart()
        mensaje["From"]    = f"{nombre_remitente} <{smtp_email}>"
        mensaje["To"]      = destinatario
        mensaje["Subject"] = asunto
        mensaje.attach(MIMEText(cuerpo, "plain", "utf-8"))

        contexto = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=contexto, timeout=10) as servidor:
            servidor.login(smtp_email, smtp_app_password)
            servidor.sendmail(smtp_email, destinatario, mensaje.as_string())
        return True, None
    except Exception as e:
        # Nunca dejamos que un problema de correo (credenciales vencidas,
        # Gmail bloqueando el envío, sin internet, etc.) tumbe la acción
        # principal que lo disparó (agendar, cancelar, cerrar un día...).
        return False, str(e)[:500]


def simular_envio_correo(
    db: Session,
    destinatario: str,
    asunto: str,
    cuerpo: str,
    tipo: str = "info",
    referencia_id: int = None
):
    """
    Envía el correo de verdad por Gmail SMTP (si las credenciales están
    configuradas en el .env) y siempre deja registro en correo_log —
    tanto si se envió con éxito como si falló, para que quede visible en
    el panel de admin ("Correos").

    El nombre de la función se mantiene por compatibilidad con las
    llamadas existentes en el resto del backend (antes solo simulaba el
    envío guardando el registro; ahora también lo manda de verdad).
    """
    exito, error = _enviar_smtp(destinatario, asunto, cuerpo)

    log = CorreoLog(
        destinatario  = destinatario,
        asunto        = asunto,
        cuerpo        = cuerpo,
        enviado       = exito,
        error_envio   = error,
        tipo          = tipo,
        referencia_id = referencia_id
    )
    db.add(log)
    # No hace commit aquí — el caller lo hace


def _ids_profesionales_en_alcance(
    db: Session,
    alcance,
) -> list[int]:
    """
    IDs de profesionales visibles para un alcance limitado.

    El alcance institucional no necesita lista de IDs.
    """
    if alcance is None or alcance.institucional:
        return []

    return [
        profesional.id
        for profesional in db.query(Profesional).all()
        if especialidad_permitida_por_alcance(
            alcance,
            profesional.especialidad,
        )
    ]


@router.get("")
def get_correos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_effective_permission(
            Permission.REPORTES_VER
        )
    ),
):
    """
    Lista los ?ltimos 100 correos visibles para el alcance
    administrativo efectivo.

    En alcance limitado solo se muestran registros que puedan
    vincularse de forma demostrable a una Cita cuyo profesional
    pertenezca al scope. Los registros sin referencia de cita se
    ocultan para evitar exposici?n cruzada.
    """
    alcance = obtener_alcance_administrativo_efectivo(
        db,
        current_user,
    )

    if alcance is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="No tienes acceso al alcance solicitado.",
        )

    if alcance.institucional:
        query = db.query(CorreoLog)
    else:
        ids_profesionales = _ids_profesionales_en_alcance(
            db,
            alcance,
        )

        if not ids_profesionales:
            return []

        query = (
            db.query(CorreoLog)
            .join(
                Cita,
                CorreoLog.referencia_id == Cita.id,
            )
            .filter(
                Cita.profesional_id.in_(
                    ids_profesionales
                )
            )
        )

    correos = (
        query
        .order_by(CorreoLog.fecha.desc())
        .limit(100)
        .all()
    )

    return [
        {
            "id": c.id,
            "destinatario": c.destinatario,
            "asunto": c.asunto,
            "cuerpo": c.cuerpo,
            "enviado": c.enviado,
            "error_envio": c.error_envio,
            "fecha": (
                c.fecha.isoformat()
                if c.fecha
                else None
            ),
            "tipo": c.tipo,
            "referencia_id": c.referencia_id,
        }
        for c in correos
    ]
