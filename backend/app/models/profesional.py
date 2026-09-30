from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Profesional(Base):
    __tablename__ = "profesional"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String)
    tratamiento = Column(String, nullable=True)  # Prefijo profesional. La interfaz actual solo permite asignar "Dr." o "Dra." (o ninguno); el campo queda como texto libre en BD por compatibilidad con datos históricos que pudieran traer otros prefijos (p.ej. "Psic.", "Klgo.").
    color_identificador = Column(String, nullable=True)  # hex de una paleta cerrada (ver COLORES_PERMITIDOS en schemas.py). Nullable: no rompe filas existentes.
    especialidad = Column(String)
    iniciales = Column(String(5))
    descripcion = Column(String, nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuario.id"), nullable=True)
    duracion_min = Column(Integer, default=45)
    estado = Column(String, default="activo")
    correo = Column(String, nullable=True)
    rut = Column(String, nullable=True)
    foto_url = Column(String, nullable=True)
    hora_almuerzo_inicio = Column(String, nullable=True)
    hora_almuerzo_fin = Column(String, nullable=True)
    horario_inicio = Column(String, nullable=True)
    horario_fin = Column(String, nullable=True)

    horarios = relationship("HorarioDisponible", back_populates="profesional")
    citas = relationship("Cita", back_populates="profesional")
    solicitudes_horario = relationship("SolicitudHorario", back_populates="profesional")
    # Agenda semanal APROBADA por bloques (día + rango + tipo). Reemplaza,
    # para el profesional que la tenga, la pareja horario_inicio/horario_fin
    # + hora_almuerzo_* de arriba. Ver app.reglas_horario y
    # app.models.bloque_horario_semanal para el detalle.
    bloques_semanales = relationship("BloqueHorarioSemanal", back_populates="profesional")