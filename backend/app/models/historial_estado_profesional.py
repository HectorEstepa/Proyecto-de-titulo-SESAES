from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class HistorialEstadoProfesional(Base):
    __tablename__ = "historial_estado_profesional"

    id               = Column(Integer, primary_key=True, index=True)
    profesional_id   = Column(Integer, ForeignKey("profesional.id"))
    estado_anterior  = Column(String, nullable=True)
    estado_nuevo     = Column(String)
    motivo           = Column(String, nullable=True)
    fecha            = Column(DateTime, default=datetime.now)
    registrado_por   = Column(Integer, ForeignKey("usuario.id"), nullable=True)

    profesional  = relationship("Profesional", foreign_keys=[profesional_id])
    registrador  = relationship("Usuario", foreign_keys=[registrado_por])