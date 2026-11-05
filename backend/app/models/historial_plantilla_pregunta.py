from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base


class HistorialPlantillaPregunta(Base):
    """
    Preguntas del cuestionario de antecedentes.

    Cada profesional tiene su propio set de preguntas (profesional_id).
    Las filas con profesional_id = NULL son plantillas "legacy" por
    especialidad (de antes de este cambio), que se usan como punto de
    partida la primera vez que un profesional de esa especialidad
    necesita su propia plantilla — ver _asegurar_plantilla_base()
    en routers/historial_clinico.py.
    """
    __tablename__ = "historial_plantilla_pregunta"

    id             = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, index=True, nullable=True)  # None = plantilla legacy por especialidad
    especialidad   = Column(String, index=True, nullable=False)
    etiqueta       = Column(String, nullable=False)          # ej. "¿Es alérgico a algún medicamento?"
    tipo           = Column(String, default="texto")         # texto | numero | si_no | textarea
    orden          = Column(Integer, default=0)
    activa         = Column(Boolean, default=True)           # soft-delete: no se borra, se desactiva