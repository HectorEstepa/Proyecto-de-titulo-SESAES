# -*- coding: utf-8 -*-
"""
SESAES — Documentos clínicos emitidos (receta médica y justificativo médico).

Cada fila es un documento emitido al completar una atención. El contenido
se guarda como instantánea (snapshot) JSON: si después cambia el nombre del
profesional o la carrera del estudiante, el documento ya emitido no cambia.

`huella_sha256` cubre tipo + folio + cita + contenido. La validación pública
la recalcula: si no coincide, el documento se reporta como "modificado".

Los documentos nunca se borran: se anulan (estado="anulado") para que el
folio siga siendo verificable y diga la verdad.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

TIPO_RECETA = "receta"
TIPO_JUSTIFICATIVO = "justificativo"
TIPOS_VALIDOS = (TIPO_RECETA, TIPO_JUSTIFICATIVO)

ESTADO_VIGENTE = "vigente"
ESTADO_ANULADO = "anulado"


class DocumentoClinico(Base):
    __tablename__ = "documento_clinico"

    id             = Column(Integer, primary_key=True, index=True)
    tipo           = Column(String, nullable=False)                    # receta | justificativo
    folio          = Column(String, unique=True, index=True, nullable=False)  # SES-XXXX-XXXX-XXXX (también es el código de verificación)
    cita_id        = Column(Integer, ForeignKey("cita.id"), nullable=False, index=True)
    profesional_id = Column(Integer, ForeignKey("profesional.id"), nullable=False, index=True)
    estudiante_id  = Column(Integer, ForeignKey("usuario.id"), nullable=False, index=True)

    contenido      = Column(JSON, nullable=False)
    huella_sha256  = Column(String(64), nullable=False)

    estado            = Column(String, nullable=False, default=ESTADO_VIGENTE)
    motivo_anulacion  = Column(String, nullable=True)
    emitido_en        = Column(DateTime(timezone=True), server_default=func.now())
    anulado_en        = Column(DateTime(timezone=True), nullable=True)

    cita        = relationship("Cita")
    profesional = relationship("Profesional")
    estudiante  = relationship("Usuario", foreign_keys=[estudiante_id])
