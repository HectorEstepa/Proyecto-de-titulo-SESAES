from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.database import Base


class DiaCerrado(Base):
    """
    Un día en que el centro completo permanece cerrado (ningún profesional
    atiende), decidido manualmente por el admin — ej. un feriado
    irrenunciable, un cierre por fuerza mayor, etc.

    Al crear uno, se cancelan automáticamente todas las citas pendientes
    de ese día (de cualquier profesional) y se notifica a cada estudiante
    afectado para que reagende.
    """
    __tablename__ = "dia_cerrado"

    id             = Column(Integer, primary_key=True, index=True)
    fecha          = Column(String, unique=True, nullable=False, index=True)  # YYYY-MM-DD
    motivo         = Column(String, nullable=True)
    creado_por     = Column(Integer, ForeignKey("usuario.id"), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
