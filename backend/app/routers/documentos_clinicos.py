# -*- coding: utf-8 -*-
"""
SESAES — Documentos clínicos (receta médica y justificativo médico).

Los documentos se EMITEN al completar la atención
(PATCH /profesional/{prof_id}/citas/{cita_id}/completar, ver profesionales.py).
Este router solo los consulta, descarga, anula y valida:

  GET  /documentos/cita/{cita_id}        lista los documentos de una atención
  GET  /documentos/{id}/pdf              descarga el PDF
  POST /documentos/{id}/anular           anula (solo el profesional emisor)
  GET  /documentos/validar/{codigo}      PÚBLICO, sin sesión, con límite de uso
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session
from typing import Annotated

from app.auditoria import registrar_evento_auditoria
from app.auth_dependencies import get_current_user
from app.database import get_db
from app.models.cita import Cita
from app.models.documento_clinico import DocumentoClinico
from app.models.notificacion import Notificacion
from app.rate_limiter import limiter
from app.rbac.permissions import Permission
from app.routers.citas import _verificar_acceso_a_cita
from app.routers.profesionales import _exigir_permiso_y_ownership_propio
from app.services import documento_clinico_service as svc

router = APIRouter(tags=["documentos-clinicos"])


class AnularIn(BaseModel):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]


def _doc_o_404(doc_id: int, db: Session) -> DocumentoClinico:
    doc = db.query(DocumentoClinico).filter(DocumentoClinico.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return doc


def _cita_de(doc: DocumentoClinico, db: Session) -> Cita:
    cita = db.query(Cita).filter(Cita.id == doc.cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return cita


# ── PÚBLICO ──────────────────────────────────────────────────────────
# Declarado antes de las rutas con /{doc_id} para que "validar" no se
# interprete como un id.
@router.get("/documentos/validar/{codigo}")
@limiter.limit("20/minute")
def validar_documento(request: Request, codigo: str, db: Session = Depends(get_db)):
    """
    Sin autenticación: lo usa la pantalla pública "Validar documento" y el
    QR del PDF. Responde siempre 200 con {valido, estado, ...}; solo expone
    tipo, profesional, fecha y nombre enmascarado (ver
    documento_clinico_service.validar_publicamente).
    """
    return svc.validar_publicamente(db, codigo)


# ── CON SESIÓN ───────────────────────────────────────────────────────
@router.get("/documentos/profesional/{prof_id}/hoy")
def resumen_documentos_hoy(
    prof_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cuántos documentos vigentes emitió el profesional hoy (solo el propio profesional)."""
    _exigir_permiso_y_ownership_propio(current_user, prof_id, db, Permission.ATENCIONES_REGISTRAR)
    return svc.contar_documentos_del_dia(db, prof_id)


@router.get("/documentos/cita/{cita_id}")
def listar_documentos_de_cita(
    cita_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cita = db.query(Cita).filter(Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    _verificar_acceso_a_cita(cita, current_user, db)
    return svc.documentos_por_citas(db, [cita_id]).get(cita_id, [])


@router.get("/documentos/{doc_id}/pdf")
def descargar_documento_pdf(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    doc = _doc_o_404(doc_id, db)
    _verificar_acceso_a_cita(_cita_de(doc, db), current_user, db)
    return Response(
        content=svc.renderizar_pdf(doc),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.folio}.pdf"'},
    )


@router.post("/documentos/{doc_id}/anular")
def anular_documento(
    doc_id: int,
    body: AnularIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    doc = _doc_o_404(doc_id, db)
    # Solo el profesional que emitió el documento (permiso + ownership).
    _exigir_permiso_y_ownership_propio(current_user, doc.profesional_id, db, Permission.ATENCIONES_REGISTRAR)

    svc.anular_documento(doc, body.motivo)
    registrar_evento_auditoria(
        db, current_user, "Profesional anuló documento clínico",
        entidad="documento_clinico", entidad_id=doc.id,
        detalle=f"{svc.resumen_documento(doc)['nombre_tipo']} {doc.folio}",
    )
    db.add(Notificacion(
        usuario_id=doc.estudiante_id,
        mensaje=f"Tu profesional anuló un documento de tu atención (folio {doc.folio}).",
        tipo="advertencia",
    ))
    db.commit()
    return {"message": "Documento anulado", "estado": doc.estado}
