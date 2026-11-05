# -*- coding: utf-8 -*-
"""
SESAES — Cuestionario de antecedentes OPCIONAL.

El profesional decide si el estudiante debe responder el cuestionario previo:

  - CuestionarioConfig: ajuste general del profesional (enviar por defecto o no).
    Sin fila = no enviar (el cuestionario es opcional).
  - CuestionarioEnvio: decisión puntual para UN estudiante, que tiene prioridad
    sobre el ajuste general (solicitado=True lo envía; solicitado=False lo omite
    aunque el ajuste general esté activo).
"""

from sqlalchemy import Column, Integer, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class CuestionarioConfig(Base):
    __tablename__ = "cuestionario_config"

    profesional_id    = Column(Integer, ForeignKey("profesional.id"), primary_key=True)
    enviar_por_defecto = Column(Boolean, nullable=False, default=False)


class CuestionarioEnvio(Base):
    __tablename__ = "cuestionario_envio"
    __table_args__ = (
        UniqueConstraint("profesional_id", "estudiante_id", name="uq_cuestionario_envio_par"),
    )

    id             = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesional.id"), nullable=False, index=True)
    estudiante_id  = Column(Integer, ForeignKey("usuario.id"), nullable=False, index=True)
    solicitado     = Column(Boolean, nullable=False, default=True)
    decidido_en    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
