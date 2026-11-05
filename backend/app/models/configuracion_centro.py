from sqlalchemy import Column, Integer, String
from app.database import Base


class ConfiguracionCentro(Base):
    __tablename__ = "configuracion_centro"

    id = Column(Integer, primary_key=True, index=True)
    nombre_centro = Column(String, default="SESAES")
    direccion = Column(String, default="José Pedro Alessandri 1200, Ñuñoa")
    telefono = Column(String, default="")
    correo_contacto = Column(String, default="")
    horario_atencion = Column(String, default="Lunes a Viernes 08:00–18:00")
    foto_admin_url = Column(String, nullable=True)
    nombre_admin = Column(String, default="Admin SESAES")
