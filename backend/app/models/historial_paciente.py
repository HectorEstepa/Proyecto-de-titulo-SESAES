from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON, String, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class HistorialPaciente(Base):
    """
    Ficha de antecedentes de un estudiante para UN profesional en particular.
    Cada profesional tiene su propia ficha del mismo estudiante, independiente
    de las de otros profesionales — no se comparte entre ellos.
    """
    __tablename__ = "historial_paciente"

    id             = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesional.id"), nullable=False, index=True)
    estudiante_id  = Column(Integer, ForeignKey("usuario.id"), nullable=False, index=True)

    # { "<pregunta_id>": "<respuesta>" }
    respuestas = Column(JSON, default=dict)

    completado_por           = Column(String, nullable=True)      # "estudiante" | "profesional"
    revisado_por_profesional = Column(Boolean, default=False, nullable=False)

    fecha_creacion    = Column(DateTime(timezone=True), server_default=func.now())
    fecha_modificacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    profesional = relationship("Profesional")
    estudiante  = relationship("Usuario")