from sqlalchemy import Column, Integer, Text, ForeignKey

from app.database import Base


class SolicitudBloques(Base):
    """
    Detalle de una SolicitudHorario de tipo "bloques": la lista completa de
    bloques pedidos, en JSON. Vive en una tabla aparte para no modificar
    solicitud_horario: asi la tabla se crea sola al arrancar el backend
    (create_all) y no hace falta ninguna migracion manual.

    bloques_json: '[{"dia_semana":0,"hora_inicio":"09:00","hora_fin":"13:00","tipo":"disponible"}, ...]'
    """
    __tablename__ = "solicitud_horario_bloques"

    solicitud_id = Column(
        Integer, ForeignKey("solicitud_horario.id", ondelete="CASCADE"), primary_key=True,
    )
    bloques_json = Column(Text, nullable=False)
