# -*- coding: utf-8 -*-
"""
SESAES — SA-11.2: tests de la infraestructura de capacidades clínicas.

Usa SQLite en memoria con los modelos reales del proyecto (mismo patrón
que test_rbac_fase3_5f_historial.py): los filtros de SQLAlchemy corren
de verdad, no se simulan con un FakeDB.

No toca cita.medicamento, /citas/{id}/pdf, recetas, justificativos,
órdenes, certificados, frontend, ni RBAC existente (fuera de alcance de
SA-11.2).
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.usuario import Usuario
from app.models.profesional import Profesional
from app.models.especialidad_capability import EspecialidadCapability
from app.rbac.clinical_capabilities import (
    ClinicalCapability,
    es_capability_valida,
    normalizar_especialidad,
)
from app.rbac.permissions import Permission
from app.services.clinical_capabilities_service import resolver_capacidades_efectivas
from app.routers import capacidades_clinicas as m
from app.auth_dependencies import get_current_user as real_get_current_user


# ══════════════════════════════════════════════════════════════════
# DB real en memoria (SQLite)
# ══════════════════════════════════════════════════════════════════
@pytest.fixture()
def db():
    # StaticPool mantiene una única conexión SQLite en memoria durante
    # cada test y hace el fixture robusto aunque futuras pruebas ejecuten
    # código a través de otro hilo.
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


def _regla(db, especialidad_normalizada, capability, activo=True):
    r = EspecialidadCapability(
        especialidad_normalizada=especialidad_normalizada,
        capability=capability,
        activo=activo,
    )
    db.add(r)
    db.commit()
    return r


def _usuario_profesional(db, usuario_id=10, rol="profesional", activo=True):
    u = Usuario(id=usuario_id, correo=f"u{usuario_id}@utem.cl", password="x", rol=rol, activo=activo)
    db.add(u)
    db.commit()
    return u


def _profesional(db, prof_id, usuario_id, especialidad):
    p = Profesional(id=prof_id, usuario_id=usuario_id, nombre="Prof", especialidad=especialidad)
    db.add(p)
    db.commit()
    return p


# ══════════════════════════════════════════════════════════════════
# A. normalizar_especialidad
# ══════════════════════════════════════════════════════════════════
def test_normalizacion_none():
    assert normalizar_especialidad(None) is None


def test_normalizacion_vacia_o_solo_espacios():
    assert normalizar_especialidad("") is None
    assert normalizar_especialidad("   ") is None


def test_normalizacion_case_y_tildes_equivalentes():
    assert normalizar_especialidad("Odontología") == normalizar_especialidad("odontologia")
    assert normalizar_especialidad("  Medicina General  ") == normalizar_especialidad("medicina general")


def test_normalizacion_colapsa_espacios_internos():
    assert normalizar_especialidad("Medicina    General") == normalizar_especialidad("Medicina General")


# ══════════════════════════════════════════════════════════════════
# B. catálogo / es_capability_valida
# ══════════════════════════════════════════════════════════════════
def test_capability_valida_reconoce_catalogo():
    assert es_capability_valida(ClinicalCapability.EMITIR_RECETA.value) is True


def test_capability_invalida_desconocida():
    assert es_capability_valida("capability_que_no_existe") is False


def test_no_existen_permisos_clinicos_nuevos_en_permission():
    """
    Ningún value de ClinicalCapability puede colarse dentro del enum
    Permission (RBAC global). Son catálogos deliberadamente separados.
    """
    valores_permission = {p.value for p in Permission}
    for cap in ClinicalCapability:
        assert cap.value not in valores_permission


# ══════════════════════════════════════════════════════════════════
# C. resolver_capacidades_efectivas
# ══════════════════════════════════════════════════════════════════
def test_especialidad_con_regla_valida_recibe_capability(db):
    _regla(db, "odontologia", ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value)
    resultado = resolver_capacidades_efectivas("Odontología", db)
    assert resultado == [ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value]


def test_especialidad_sin_regla_devuelve_lista_vacia(db):
    _regla(db, "odontologia", ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value)
    assert resolver_capacidades_efectivas("Kinesiología", db) == []


def test_especialidad_none_devuelve_lista_vacia(db):
    assert resolver_capacidades_efectivas(None, db) == []


def test_regla_inactiva_no_se_concede(db):
    _regla(db, "psicologia", ClinicalCapability.EMITIR_CERTIFICADO.value, activo=False)
    assert resolver_capacidades_efectivas("Psicología", db) == []


def test_capability_desconocida_en_bd_es_fail_closed(db):
    _regla(db, "medicina general", "capability_inventada_por_error")
    assert resolver_capacidades_efectivas("Medicina General", db) == []


def test_capability_desconocida_no_bloquea_las_demas_reglas_validas(db):
    _regla(db, "medicina general", "capability_inventada_por_error")
    _regla(db, "medicina general", ClinicalCapability.EMITIR_RECETA.value)
    assert resolver_capacidades_efectivas("Medicina General", db) == [ClinicalCapability.EMITIR_RECETA.value]


def test_orden_de_capacidades_es_deterministico_por_capability(db):
    # Se insertan deliberadamente en un orden que NO coincide con el
    # orden alfabético de `capability` (ni, por lo tanto, con el orden
    # de creación/IDs): EMITIR_RECETA primero, luego EMITIR_CERTIFICADO,
    # luego EMITIR_ORDEN_EXAMEN. Si el resultado dependiera del orden de
    # inserción (IDs) o de un plan de consulta no determinista, este
    # test lo detectaría — el resultado debe depender únicamente del
    # contenido (`capability` ASC), no de cuándo se creó cada regla.
    _regla(db, "medicina general", ClinicalCapability.EMITIR_RECETA.value)
    _regla(db, "medicina general", ClinicalCapability.EMITIR_CERTIFICADO.value)
    _regla(db, "medicina general", ClinicalCapability.EMITIR_ORDEN_EXAMEN.value)

    esperado = sorted([
        ClinicalCapability.EMITIR_RECETA.value,
        ClinicalCapability.EMITIR_CERTIFICADO.value,
        ClinicalCapability.EMITIR_ORDEN_EXAMEN.value,
    ])
    assert esperado == [
        ClinicalCapability.EMITIR_CERTIFICADO.value,
        ClinicalCapability.EMITIR_ORDEN_EXAMEN.value,
        ClinicalCapability.EMITIR_RECETA.value,
    ]  # confirma que el orden de inserción difiere del alfabético esperado

    # Se repite la llamada varias veces: el orden no debe variar entre
    # invocaciones (si dependiera de un plan de consulta no determinista,
    # una corrida aislada podría no detectarlo).
    for _ in range(3):
        assert resolver_capacidades_efectivas("Medicina General", db) == esperado


def test_activo_no_tiene_default_y_debe_indicarse_explicitamente(db):
    # Regresión directa del punto "activo sin default=True": si alguien
    # reintrodujera un default a nivel de columna, este test seguiría
    # pasando (porque _regla siempre pasa `activo` explícito) — por eso
    # se valida además a nivel de esquema, con un INSERT que omite el
    # campo a propósito, esperando que la BD rechace la fila en vez de
    # concederla implícitamente como activa.
    from sqlalchemy.exc import IntegrityError

    regla_incompleta = EspecialidadCapability(
        especialidad_normalizada="medicina general",
        capability=ClinicalCapability.EMITIR_RECETA.value,
        # `activo` deliberadamente omitido
    )
    db.add(regla_incompleta)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ══════════════════════════════════════════════════════════════════
# D. Endpoint — identidad efectiva y jerarquía de roles
# ══════════════════════════════════════════════════════════════════
def test_profesional_obtiene_solo_sus_propias_capacidades(db):
    _usuario_profesional(db, usuario_id=10)
    _profesional(db, prof_id=5, usuario_id=10, especialidad="Enfermería")
    _regla(db, "enfermeria", ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value)

    # otro profesional, otra especialidad — no debe filtrarse
    _usuario_profesional(db, usuario_id=11)
    _profesional(db, prof_id=6, usuario_id=11, especialidad="Psicología")
    _regla(db, "psicologia", ClinicalCapability.EMITIR_CERTIFICADO.value)

    resultado = m.obtener_mis_capacidades_clinicas(
        db=db,
        current_user={"id": 10, "rol": "profesional"},
    )
    assert resultado == {"capacidades": [ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value]}


def test_endpoint_nunca_acepta_profesional_id_externo():
    """
    El endpoint no declara ningún parámetro profesional_id: la identidad
    se resuelve exclusivamente desde current_user + Profesional.usuario_id.
    """
    firma = inspect.signature(m.obtener_mis_capacidades_clinicas)
    assert "profesional_id" not in firma.parameters


def test_admin_no_obtiene_capacidades_por_jerarquia(db):
    with pytest.raises(HTTPException) as exc:
        m.obtener_mis_capacidades_clinicas(
            db=db,
            current_user={"id": 999, "rol": "admin"},
        )
    assert exc.value.status_code == 403


def test_superadmin_no_obtiene_capacidades_por_jerarquia(db):
    with pytest.raises(HTTPException) as exc:
        m.obtener_mis_capacidades_clinicas(
            db=db,
            current_user={"id": 998, "rol": "superadmin"},
        )
    assert exc.value.status_code == 403


def test_admin_no_se_transforma_en_profesional_por_coincidencia_de_id(db):
    """
    Un ADMIN cuyo Usuario.id coincide numéricamente con el usuario_id de
    un Profesional real NO debe heredar sus capacidades: el rol se exige
    primero (verificar_rol), antes de siquiera consultar Profesional.
    """
    _usuario_profesional(db, usuario_id=10, rol="profesional")
    _profesional(db, prof_id=5, usuario_id=10, especialidad="Odontología")
    _regla(db, "odontologia", ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value)

    with pytest.raises(HTTPException) as exc:
        m.obtener_mis_capacidades_clinicas(
            db=db,
            current_user={"id": 10, "rol": "admin"},
        )
    assert exc.value.status_code == 403


def test_endpoint_depende_de_get_current_user_real_no_lo_reimplementa():
    """
    SA-11.2 no introduce un mecanismo de autenticación paralelo: el
    endpoint depende exactamente de app.auth_dependencies.get_current_user
    (la misma dependencia que ya valida JWT + usuario.activo + rol
    actual de BD, ver SA-3). Esto garantiza que un JWT viejo o una
    cuenta desactivada siguen bloqueados por esa protección existente,
    sin que SA-11.2 la duplique ni la debilite.
    """
    firma = inspect.signature(m.obtener_mis_capacidades_clinicas)
    dependencia_current_user = firma.parameters["current_user"].default
    assert dependencia_current_user.dependency is real_get_current_user


def test_profesional_sin_fila_profesional_asociada_es_fail_closed(db):
    _usuario_profesional(db, usuario_id=20, rol="profesional")
    resultado = m.obtener_mis_capacidades_clinicas(
        db=db,
        current_user={"id": 20, "rol": "profesional"},
    )
    assert resultado == {"capacidades": []}


def test_profesional_con_exactamente_una_asociacion_resuelve_normalmente(db):
    _usuario_profesional(db, usuario_id=30, rol="profesional")
    _profesional(db, prof_id=40, usuario_id=30, especialidad="Enfermería")
    _regla(db, "enfermeria", ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value)

    resultado = m.obtener_mis_capacidades_clinicas(
        db=db,
        current_user={"id": 30, "rol": "profesional"},
    )
    assert resultado == {"capacidades": [ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value]}


def test_profesional_con_dos_filas_asociadas_al_mismo_usuario_es_fail_closed(db):
    """
    Regresión obligatoria (corrección solicitada): si Profesional.usuario_id
    no es único a nivel de esquema y existen dos filas para el mismo
    Usuario, NO se debe elegir una arbitrariamente vía .first() — el
    resultado debe ser fail-closed ([]), nunca una capability concedida
    "por casualidad" según cuál fila haya devuelto la BD primero.
    """
    _usuario_profesional(db, usuario_id=50, rol="profesional")
    _profesional(db, prof_id=60, usuario_id=50, especialidad="Odontología")
    _profesional(db, prof_id=61, usuario_id=50, especialidad="Psicología")
    _regla(db, "odontologia", ClinicalCapability.GESTIONAR_FICHA_ODONTOLOGICA.value)
    _regla(db, "psicologia", ClinicalCapability.EMITIR_CERTIFICADO.value)

    resultado = m.obtener_mis_capacidades_clinicas(
        db=db,
        current_user={"id": 50, "rol": "profesional"},
    )
    assert resultado == {"capacidades": []}
