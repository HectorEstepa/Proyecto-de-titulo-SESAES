from sqlalchemy import Column, Integer, Boolean
from app.database import Base

class ConfiguracionSistema(Base):
    __tablename__ = "configuracion_sistema"

    id                         = Column(Integer, primary_key=True, index=True)
    duracion_turno_min         = Column(Integer, default=20)
    agendamiento_por_pacientes = Column(Boolean, default=True)
    cancelacion_instantanea    = Column(Boolean, default=False)
    sobreturnos_habilitados    = Column(Boolean, default=True)
    cupos_por_turno            = Column(Integer, default=4)