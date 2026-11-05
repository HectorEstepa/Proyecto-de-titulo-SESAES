# -*- coding: utf-8 -*-
"""
SESAES — SA-11.3B: integración clínica real de "medicamento suministrado".

Cubre exclusivamente lo descrito en la entrega SA-11.3B:
  1. Rename REGISTRAR_INDICACION_MEDICAMENTO -> REGISTRAR_MEDICAMENTO_SUMINISTRADO
     en app/rbac/clinical_capabilities.py.
  2. Integración condicional de esa capability en
     app/routers/profesionales.py::completar_cita — SOLO exigida cuando
     `medicamento` trae contenido real (no None, no "", no solo espacios).
  3. Schema explícito CompletarCitaBody (app/schemas.py) reemplazando el
     `body: dict` anterior.
  4. Encabezado del PDF ("Indicaciones Médicas" -> "Registro de atención"),
     conservando "SESAES - Resumen de Atención" y "Medicamento suministrado".

Usa DB real en SQLite en memoria (mismo patrón que
test_sa11_2_capacidades_clinicas.py): los filtros de SQLAlchemy y el
fail-closed de resolver_capacidades_efectivas corren de verdad, sin
FakeDB. No toca recetas, justificativos, órdenes, certificados, CGR,
frontend, Agenda, seeds ni permisos RBAC nuevos.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.init  # noqa: F401 — registra todas las relaciones SQLAlchemy
import app.models.solicitud_horario  # noqa: F401 — referenciado por Profesional

from app.database import Base
from app.models.usuario import Usuario
from app.models.profesional import Profesional
from app.models.cita import Cita
from app.models.especialidad_capability import EspecialidadCapability
from app.rbac.clinical_capabilities import ClinicalCapability, normalizar_especialidad
from app.rbac.permissions import Permission
from app.schemas import CompletarCitaBody
from app.routers import profesionales as m
from app.routers import citas as citas_router


# ══════════════════════════════════════════════════════════════════
# DB real en memoria (SQLite) — StaticPool para una sola conexión viva
# durante todo el test.
# ══════════════════════════════════════════════════════════════════
@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ══════════════════════════════════════════════════════════════════
# Helpers de fixtures de datos
# ══════════════════════════════════════════════════════════════════
def _usuario(db, id_, rol, activo=True, nombre="—"):
    u = Usuario(id=id_, correo=f"u{id_}@utem.cl", password="x", rol=rol, activo=activo, nombre=nombre)
    db.add(u)
    db.commit()
    return u


def _profesional(db, id_, usuario_id, especialidad):
    p = Profesional(id=id_, usuario_id=usuario_id, nombre="Dra. Owner", especialidad=especialidad, iniciales="DO")
    db.add(p)
    db.commit()
    return p


def _cita(db, id_, profesional_id, estudiante_id, estado="pendiente", fecha="2020-01-01", hora="09:00"):
    c = Cita(id=id_, profesional_id=profesional_id, estudiante_id=estudiante_id, estado=estado, fecha=fecha, hora=hora)
    db.add(c)
    db.commit()
    return c


def _regla(db, especialidad_normalizada, capability, activo=True):
    r = EspecialidadCapability(especialidad_normalizada=especialidad_normalizada, capability=capability, activo=activo)
    db.add(r)
    db.commit()
    return r


PROF_ID = 5
USUARIO_PROF_ID = 10
ESTUDIANTE_ID = 99
CITA_ID = 7
CURRENT_USER = {"id": USUARIO_PROF_ID, "rol": "profesional"}


def _setup_basico(db, especialidad="Enfermería", estado_cita="pendiente"):
    """Profesional dueño + estudiante + cita pendiente del día anterior."""
    _usuario(db, USUARIO_PROF_ID, "profesional")
    _usuario(db, ESTUDIANTE_ID, "estudiante", nombre="Ana")
    _profesional(db, PROF_ID, USUARIO_PROF_ID, especialidad)
    return _cita(db, CITA_ID, PROF_ID, ESTUDIANTE_ID, estado=estado_cita)


# ══════════════════════════════════════════════════════════════════
# 1. Rename del catálogo (ClinicalCapability)
# ══════════════════════════════════════════════════════════════════
def test_capability_renombrada_existe_y_la_antigua_no():
    assert ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO.value == "registrar_medicamento_suministrado"
    assert not hasattr(ClinicalCapability, "REGISTRAR_INDICACION_MEDICAMENTO")
    valores = {c.value for c in ClinicalCapability}
    assert "registrar_indicacion_medicamento" not in valores
    assert "registrar_medicamento_suministrado" in valores


def test_clinical_capability_no_contamina_permission():
    """
    ClinicalCapability vive en un catálogo separado de Permission y
    nunca debe mezclarse con él (ver docstring de
    app/rbac/clinical_capabilities.py). Ningún value de
    ClinicalCapability debe aparecer como Permission, y viceversa.
    """
    valores_capability = {c.value for c in ClinicalCapability}
    valores_permission = {p.value for p in Permission}
    assert valores_capability.isdisjoint(valores_permission)
    assert not hasattr(Permission, "REGISTRAR_MEDICAMENTO_SUMINISTRADO")
    assert "registrar_medicamento_suministrado" not in valores_permission


# ══════════════════════════════════════════════════════════════════
# 2. Casos funcionales de completar_cita + capability condicional
# ══════════════════════════════════════════════════════════════════
def test_orden_obligatorio_no_hay_mutacion_antes_de_capability():
    """
    Verifica estáticamente que, en el código fuente de completar_cita,
    la resolución de capability ocurre antes de cualquier asignación a
    cita.estado / cita.medicamento / cita.observaciones_atencion (no
    solo que el resultado final sea correcto).
    """
    source = inspect.getsource(m.completar_cita)
    idx_capability = source.index("capacidades_efectivas_profesional")
    idx_estado = source.index('cita.estado                 = "completada"')
    idx_medicamento = source.index("cita.medicamento            = medicamento")
    assert idx_capability < idx_estado
    assert idx_capability < idx_medicamento


def test_caso_1_dueno_capability_activa_medicamento_200_y_persistido(db):
    _setup_basico(db)
    _regla(db, normalizar_especialidad("Enfermería"), ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO.value)

    resultado = m.completar_cita(
        prof_id=PROF_ID, cita_id=CITA_ID,
        body=CompletarCitaBody(medicamento="Paracetamol 500mg", observaciones_atencion="Reposo 24h"),
        db=db, current_user=CURRENT_USER,
    )

    cita = db.query(Cita).filter(Cita.id == CITA_ID).first()
    assert resultado == {"message": "Cita marcada como completada"}
    assert cita.estado == "completada"
    assert cita.medicamento == "Paracetamol 500mg"
    assert cita.observaciones_atencion == "Reposo 24h"


def test_caso_2_dueno_permiso_sin_capability_medicamento_403(db):
    _setup_basico(db)
    # Sin ninguna regla EspecialidadCapability -> resolver_capacidades_efectivas([]) fail-closed.
    with pytest.raises(HTTPException) as exc:
        m.completar_cita(
            prof_id=PROF_ID, cita_id=CITA_ID,
            body=CompletarCitaBody(medicamento="Ibuprofeno"),
            db=db, current_user=CURRENT_USER,
        )
    assert exc.value.status_code == 403


def test_caso_3_tras_403_cita_y_medicamento_no_cambian(db):
    cita = _setup_basico(db)
    estado_previo = cita.estado
    medicamento_previo = cita.medicamento
    observaciones_previas = cita.observaciones_atencion

    with pytest.raises(HTTPException):
        m.completar_cita(
            prof_id=PROF_ID, cita_id=CITA_ID,
            body=CompletarCitaBody(medicamento="Ibuprofeno", observaciones_atencion="algo"),
            db=db, current_user=CURRENT_USER,
        )

    db.expire_all()
    cita_recargada = db.query(Cita).filter(Cita.id == CITA_ID).first()
    assert cita_recargada.estado == estado_previo
    assert cita_recargada.medicamento == medicamento_previo
    assert cita_recargada.observaciones_atencion == observaciones_previas


def test_caso_4_dueno_permiso_sin_capability_medicamento_none_completa(db):
    _setup_basico(db)
    resultado = m.completar_cita(
        prof_id=PROF_ID, cita_id=CITA_ID,
        body=CompletarCitaBody(medicamento=None),
        db=db, current_user=CURRENT_USER,
    )
    cita = db.query(Cita).filter(Cita.id == CITA_ID).first()
    assert resultado == {"message": "Cita marcada como completada"}
    assert cita.estado == "completada"
    assert cita.medicamento is None


def test_caso_5_dueno_permiso_sin_capability_medicamento_omitido_completa(db):
    _setup_basico(db)
    resultado = m.completar_cita(
        prof_id=PROF_ID, cita_id=CITA_ID,
        body=CompletarCitaBody(),  # campo omitido -> default None
        db=db, current_user=CURRENT_USER,
    )
    cita = db.query(Cita).filter(Cita.id == CITA_ID).first()
    assert resultado == {"message": "Cita marcada como completada"}
    assert cita.estado == "completada"
    assert cita.medicamento is None


def test_caso_6_capability_inactiva_medicamento_403(db):
    _setup_basico(db)
    _regla(db, normalizar_especialidad("Enfermería"), ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO.value, activo=False)
    with pytest.raises(HTTPException) as exc:
        m.completar_cita(
            prof_id=PROF_ID, cita_id=CITA_ID,
            body=CompletarCitaBody(medicamento="Paracetamol"),
            db=db, current_user=CURRENT_USER,
        )
    assert exc.value.status_code == 403


def test_caso_7_especialidad_sin_configuracion_medicamento_403(db):
    _setup_basico(db, especialidad="Especialidad Sin Reglas")
    with pytest.raises(HTTPException) as exc:
        m.completar_cita(
            prof_id=PROF_ID, cita_id=CITA_ID,
            body=CompletarCitaBody(medicamento="Paracetamol"),
            db=db, current_user=CURRENT_USER,
        )
    assert exc.value.status_code == 403


def test_caso_8_profesional_ajeno_bloqueado_aunque_tenga_capability(db):
    _setup_basico(db)
    _regla(db, normalizar_especialidad("Enfermería"), ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO.value)
    otro_usuario = {"id": 999, "rol": "profesional"}
    with pytest.raises(HTTPException) as exc:
        m.completar_cita(
            prof_id=PROF_ID, cita_id=CITA_ID,
            body=CompletarCitaBody(medicamento="Paracetamol"),
            db=db, current_user=otro_usuario,
        )
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_caso_9_admin_superadmin_no_obtienen_acceso_por_coincidencia_de_id(db, rol):
    _setup_basico(db)
    _regla(db, normalizar_especialidad("Enfermería"), ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO.value)
    # Mismo id que Profesional.usuario_id, pero rol no autorizado por
    # verificar_acceso_profesional (roles_permitidos=["profesional"]).
    current_user = {"id": USUARIO_PROF_ID, "rol": rol}
    with pytest.raises(HTTPException) as exc:
        m.completar_cita(
            prof_id=PROF_ID, cita_id=CITA_ID,
            body=CompletarCitaBody(medicamento="Paracetamol"),
            db=db, current_user=current_user,
        )
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# Medicamento vacío / solo espacios — no exige capability y no
# persiste el string tal cual (se normaliza a None).
# ══════════════════════════════════════════════════════════════════
def test_medicamento_string_vacio_no_exige_capability_y_persiste_none(db):
    _setup_basico(db)
    # Sin ninguna regla de capability configurada a propósito: si el
    # endpoint exigiera la capability acá, esto fallaría con 403.
    resultado = m.completar_cita(
        prof_id=PROF_ID, cita_id=CITA_ID,
        body=CompletarCitaBody(medicamento=""),
        db=db, current_user=CURRENT_USER,
    )
    cita = db.query(Cita).filter(Cita.id == CITA_ID).first()
    assert resultado == {"message": "Cita marcada como completada"}
    assert cita.medicamento is None


def test_medicamento_solo_espacios_no_exige_capability_y_persiste_none(db):
    _setup_basico(db)
    resultado = m.completar_cita(
        prof_id=PROF_ID, cita_id=CITA_ID,
        body=CompletarCitaBody(medicamento="   "),
        db=db, current_user=CURRENT_USER,
    )
    cita = db.query(Cita).filter(Cita.id == CITA_ID).first()
    assert resultado == {"message": "Cita marcada como completada"}
    assert cita.medicamento is None


def test_medicamento_con_espacios_al_borde_se_persiste_stripeado(db):
    _setup_basico(db)
    _regla(db, normalizar_especialidad("Enfermería"), ClinicalCapability.REGISTRAR_MEDICAMENTO_SUMINISTRADO.value)
    m.completar_cita(
        prof_id=PROF_ID, cita_id=CITA_ID,
        body=CompletarCitaBody(medicamento="  Paracetamol 500mg  "),
        db=db, current_user=CURRENT_USER,
    )
    cita = db.query(Cita).filter(Cita.id == CITA_ID).first()
    assert cita.medicamento == "Paracetamol 500mg"


def test_observaciones_atencion_vacia_o_espacios_persiste_none(db):
    _setup_basico(db)
    resultado = m.completar_cita(
        prof_id=PROF_ID, cita_id=CITA_ID,
        body=CompletarCitaBody(observaciones_atencion="   "),
        db=db, current_user=CURRENT_USER,
    )
    cita = db.query(Cita).filter(Cita.id == CITA_ID).first()
    assert resultado == {"message": "Cita marcada como completada"}
    assert cita.observaciones_atencion is None


# ══════════════════════════════════════════════════════════════════
# 10. Schema Pydantic — rechaza tipos no string
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("valor", [123, 1.5, True, ["a"], {"a": 1}, ("a",)])
def test_schema_rechaza_medicamento_no_string(valor):
    with pytest.raises(ValidationError):
        CompletarCitaBody(medicamento=valor)


@pytest.mark.parametrize("valor", [123, 1.5, True, ["a"], {"a": 1}, ("a",)])
def test_schema_rechaza_observaciones_no_string(valor):
    with pytest.raises(ValidationError):
        CompletarCitaBody(observaciones_atencion=valor)


def test_schema_acepta_string_y_none_y_omitido():
    assert CompletarCitaBody(medicamento="x").medicamento == "x"
    assert CompletarCitaBody(medicamento=None).medicamento is None
    assert CompletarCitaBody().medicamento is None
    assert CompletarCitaBody().observaciones_atencion is None


def test_endpoint_usa_schema_explicito_no_dict():
    """El parámetro `body` de completar_cita ya no es un `dict` sin tipar."""
    sig = inspect.signature(m.completar_cita)
    anotacion = sig.parameters["body"].annotation
    assert anotacion is CompletarCitaBody


# ══════════════════════════════════════════════════════════════════
# 11. PDF — sigue siendo Resumen de Atención, encabezado corregido
# ══════════════════════════════════════════════════════════════════
def test_pdf_usa_registro_de_atencion_y_no_indicaciones_medicas():
    source = inspect.getsource(citas_router.descargar_pdf_cita)
    assert "Registro de atención" in source
    assert "Indicaciones Médicas" not in source
    assert "SESAES - Resumen de Atención" in source
    assert "Medicamento suministrado" in source


def test_pdf_no_se_convierte_en_receta():
    source = inspect.getsource(citas_router.descargar_pdf_cita)
    # No se agregó ningún encabezado/rótulo de "receta" al documento.
    assert "Receta" not in source
    assert "RECETA" not in source
