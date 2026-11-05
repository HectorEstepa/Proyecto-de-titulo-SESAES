from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Notificacion(Base):
    __tablename__ = "notificacion"

    id             = Column(Integer, primary_key=True, index=True)
    usuario_id     = Column(Integer, ForeignKey("usuario.id"))
    mensaje        = Column(String)
    tipo           = Column(String)   # info, advertencia, cancelacion, reagenda
    leida          = Column(Boolean, default=False)
    fecha_creacion = Column(DateTime, default=datetime.now)

    usuario = relationship("Usuario", foreign_keys=[usuario_id])