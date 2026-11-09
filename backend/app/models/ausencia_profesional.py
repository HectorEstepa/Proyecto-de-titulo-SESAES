from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.database import Base


class AusenciaProfesional(Base):
    """
    Ausencia de día completo de un profesional, para una fecha exacta.

    Se crea junto con reportar_ausencia(tipo="dia_completo") en
    routers/profesionales.py. A diferencia de HistorialEstadoProfesional
    (que solo deja registro/auditoría), esta tabla SÍ se consulta en
    horarios.py:get_disponibilidad y citas.py:crear_cita para impedir que
    se agenden citas NUEVAS en esa fecha — no solo cancelar las que ya
    existían al momento de reportar la ausencia.
    """
    __tablename__ = "ausencia_profesional"

    id             = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesional.id"), nullable=False, index=True)
    fecha          = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    motivo         = Column(String, nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
