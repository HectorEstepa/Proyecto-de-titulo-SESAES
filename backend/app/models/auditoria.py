from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Auditoria(Base):
    __tablename__ = "auditoria"

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuario.id"))
    actor_rol   = Column(String, nullable=True)   # SA-2: nullable por compatibilidad histórica
    accion      = Column(String)
    resultado   = Column(String, nullable=False, server_default="exito")  # SA-2: "exito" | "denegado" | "error"
    detalle     = Column(String)
    entidad     = Column(String)    # 'cita', 'profesional', 'configuracion', etc.
    entidad_id  = Column(Integer)   # id del registro afectado
    fecha       = Column(DateTime, server_default=func.now())
