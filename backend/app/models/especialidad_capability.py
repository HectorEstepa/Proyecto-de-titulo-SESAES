# -*- coding: utf-8 -*-
"""
SESAES — SA-11.2: tabla NUEVA y aditiva `especialidad_capability`.

Persiste la relación configurable especialidad → capability clínica.
Deliberadamente NO reemplaza ni modifica ninguna tabla existente
(Profesional.especialidad se mantiene como está, como fuente libre de
la especialidad real del profesional).

Cada fila es una regla independiente: (especialidad_normalizada,
capability) es única. Desactivar una capability para una especialidad
es un UPDATE de `activo`, no un DELETE — se conserva el registro para
auditoría/histórico, igual criterio que el resto del proyecto (ver
decisiones de SA-2 sobre no ocultar historial).

Este modelo debe importarse explícitamente en algún punto cargado antes
de `Base.metadata.create_all(bind=engine)` (init_db.py y/o
app/models/init.py, según el patrón ya usado por el resto de modelos)
para que SQLAlchemy registre la tabla. No se detectó Alembic propio en
el proyecto (solo create_all), así que esta tabla se crea de forma
aditiva la primera vez que corra init_db() contra una BD que no la
tenga — no se requiere migración destructiva ni recrear tablas
existentes.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, func

from app.database import Base


class EspecialidadCapability(Base):
    __tablename__ = "especialidad_capability"

    id = Column(Integer, primary_key=True, index=True)

    # Clave de configuración: SIEMPRE la salida de
    # app.rbac.clinical_capabilities.normalizar_especialidad(). Nunca se
    # guarda el string crudo de Profesional.especialidad acá.
    especialidad_normalizada = Column(String, nullable=False, index=True)

    # Value de un miembro de ClinicalCapability (string). No se usa una
    # FK/enum de BD a propósito: el catálogo válido vive en código
    # (app.rbac.clinical_capabilities) y se valida en el servicio de
    # resolución, no a nivel de esquema — así agregar una capability al
    # catálogo no exige una migración de constraint de BD.
    capability = Column(String, nullable=False)

    # Fail-closed por diseño: una regla con activo=False NUNCA concede
    # la capability, aunque exista la fila. No hay estado "pendiente"
    # ni "heredado"; es binario.
    #
    # Deliberadamente SIN default=True (ni default a nivel de columna ni
    # server_default): quien crea una regla debe decidir explícitamente
    # si nace activa o no. Un default=True aquí habría significado que
    # cualquier inserción futura que "se olvide" el campo activa una
    # capability por omisión — exactamente el comportamiento fail-open
    # que SA-11.2 busca evitar. Como no hay seed real (ver punto 6 de
    # la entrega), esto no afecta ninguna fila existente; solo obliga a
    # que todo INSERT futuro sea explícito.
    activo = Column(Boolean, nullable=False)

    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "especialidad_normalizada", "capability",
            name="uq_especialidad_capability_regla",
        ),
    )
