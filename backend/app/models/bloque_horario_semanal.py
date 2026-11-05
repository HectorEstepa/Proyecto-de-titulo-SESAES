from sqlalchemy import Column, Integer, String, ForeignKey

from app.database import Base


class BloqueHorarioSemanal(Base):
    """
    Un bloque recurrente de la agenda semanal APROBADA de un profesional.

    dia_semana: 0=Lunes ... 4=Viernes.
    tipo: "disponible" (atiende) o "colacion" (almuerzo, no se agenda).

    Si un profesional tiene al menos un bloque, esta agenda reemplaza a
    horario_inicio/horario_fin y hora_almuerzo_* como fuente de verdad. Un
    profesional sin bloques sigue funcionando con su jornada simple.
    """
    __tablename__ = "bloque_horario_semanal"

    id = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("profesional.id"), nullable=False, index=True)
    dia_semana = Column(Integer, nullable=False)
    hora_inicio = Column(String, nullable=False)
    hora_fin = Column(String, nullable=False)
    tipo = Column(String, nullable=False, default="disponible")
