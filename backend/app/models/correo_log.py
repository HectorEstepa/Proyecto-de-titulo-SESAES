from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class CorreoLog(Base):
    __tablename__ = "correo_log"

    id             = Column(Integer, primary_key=True, index=True)
    destinatario   = Column(String)
    asunto         = Column(String)
    cuerpo         = Column(String)
    enviado        = Column(Boolean, default=False)
    error_envio    = Column(String, nullable=True)   # detalle del error SMTP, si falló
    fecha          = Column(DateTime, server_default=func.now())
    tipo           = Column(String, nullable=True)   # cancelacion, reagenda, urgente
    referencia_id  = Column(Integer, nullable=True)  # id de la cita relacionada