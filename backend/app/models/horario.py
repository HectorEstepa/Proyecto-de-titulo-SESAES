from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class HorarioDisponible(Base):
    __tablename__ = "horario_disponible"

    id             = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesional.id"))
    dia_nombre     = Column(String)   # LUN, MAR, MIÉ, JUE, VIE
    dia_num        = Column(Integer)
    fecha          = Column(String)   # YYYY-MM-DD
    hora           = Column(String)   # HH:MM AM/PM
    estado         = Column(String, default="disponible")  # disponible, reservado, bloqueado

    profesional = relationship("Profesional", back_populates="horarios")