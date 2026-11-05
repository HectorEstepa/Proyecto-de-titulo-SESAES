from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base


class Auditoria(Base):
    __tablename__ = "auditoria"
    # Índice compuesto de consulta: el historial de un registro concreto
    # (p. ej. todas las acciones sobre una cita) filtra por entidad +
    # entidad_id y ordena por fecha. En bases ya desplegadas se crea con
    # backend/scripts/migrar_auditoria_agenda.py (idempotente).
    __table_args__ = (
        Index(
            "ix_auditoria_entidad_entidad_id_fecha",
            "entidad", "entidad_id", "fecha",
        ),
    )

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuario.id"))
    actor_rol   = Column(String, nullable=True)   # SA-2: nullable por compatibilidad histórica
    accion      = Column(String)
    resultado   = Column(String, nullable=False, server_default="exito")  # SA-2: "exito" | "denegado" | "error"
    detalle     = Column(String)
    entidad     = Column(String)    # 'cita', 'profesional', 'configuracion', etc.
    entidad_id  = Column(Integer)   # id del registro afectado
    fecha       = Column(DateTime, server_default=func.now())
