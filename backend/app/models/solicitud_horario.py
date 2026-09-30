from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class SolicitudHorario(Base):
    __tablename__ = "solicitud_horario"

    id = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesional.id"), nullable=False)
    tipo = Column(String, nullable=False)          # "colacion" | "jornada" | "bloques"
    # Para tipo "colacion"/"jornada" (legado): un único rango horario.
    # Para tipo "bloques": estos dos quedan igual (se guarda el rango del
    # primer bloque solo como referencia de listado); el detalle real vive
    # en bloques_json.
    hora_inicio = Column(String, nullable=False)
    hora_fin = Column(String, nullable=False)
    # Para tipo "bloques": JSON con la lista completa de bloques solicitados,
    # ej. '[{"dia_semana":0,"hora_inicio":"09:00","hora_fin":"13:00","tipo":"disponible"}, ...]'
    bloques_json = Column(String, nullable=True)
    estado = Column(String, default="pendiente")    # "pendiente" | "aprobado" | "rechazado"
    motivo_rechazo = Column(String, nullable=True)
    fecha_solicitud = Column(DateTime(timezone=True), server_default=func.now())
    fecha_resolucion = Column(DateTime(timezone=True), nullable=True)

    profesional = relationship("Profesional", back_populates="solicitudes_horario")