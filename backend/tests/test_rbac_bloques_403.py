# -*- coding: utf-8 -*-
"""
RBAC estricto a nivel HTTP: un token de ESTUDIANTE no puede ejecutar las
operaciones de anulación/gestión de bloques y agenda del ADMINISTRADOR.

A diferencia de test_rbac_fase3_5f_solicitudes_horario.py (que llama a las
funciones de endpoint con current_user inyectado a mano), esta suite cruza
la cadena completa:

    JWT firmado -> HTTPBearer -> get_current_user (firma + expiración +
    re-resolución del rol ACTUAL en BD) -> require_effective_permission /
    ownership -> 403

Por eso no se sobrescribe `get_current_user`: solo se sustituye `get_db`
para usar una SQLite en memoria compartida entre el hilo del TestClient y
la suite (StaticPool + check_same_thread=False).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.init  # noqa: F401 — registra TODOS los modelos productivos

from app.database import Base, get_db
from app.main import app
from app.models.profesional import Profesional
from app.models.solicitud_horario import SolicitudHorario
from app.models.usuario import Usuario
from app.security import JWT_ALGORITHM, create_access_token


# ══════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════

@pytest.fixture()
def entorno():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _get_db_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db_override
    client = TestClient(app)

    db = SessionLocal()
    try:
        yield client, db
    finally:
        db.close()
        client.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _usuario(db, *, correo, rol, rut):
    usuario = Usuario(
        correo=correo,
        password="hash-no-usado-en-esta-suite",
        rol=rol,
        nombre=f"Usuario {rol}",
        rut=rut,
        activo=True,
    )
    db.add(usuario)
    db.flush()
    return usuario


def _token(usuario):
    return create_access_token(
        {"id": usuario.id, "rol": usuario.rol, "correo": usuario.correo}
    )


def _headers(usuario):
    return {"Authorization": f"Bearer {_token(usuario)}"}


# Endpoints administrativos de anulación/gestión de agenda y bloques.
# Todos deben responder 403 a un Estudiante autenticado.
ENDPOINTS_ADMIN = [
    ("PATCH", "/admin/citas/1/cancelar", {"motivo": "prueba"}),
    ("PATCH", "/admin/citas/1/prioridad", {"urgente": True}),
    ("POST", "/admin/dias-cerrados", {"fecha": "2030-01-01", "motivo": "prueba"}),
    ("DELETE", "/admin/dias-cerrados/1", None),
    ("PATCH", "/admin/solicitudes-horario/1/aprobar", None),
    ("PATCH", "/admin/solicitudes-horario/1/rechazar", {"motivo": "prueba"}),
    ("DELETE", "/admin/profesionales/1", None),
    ("PATCH", "/admin/profesionales/1/estado", {"estado": "inactivo"}),
    ("POST", "/admin/citas/urgente", {
        "estudiante_id": 1,
        "profesional_id": 1,
        "fecha": "2030-01-01",
        "hora": "09:00",
        "motivo": "prueba",
    }),
    ("GET", "/admin/reportes/resumen/pdf", None),
    ("GET", "/admin/reportes/resumen/excel", None),
    ("GET", "/admin/exportar/cgr/datos?anio=2030", None),
]


# ══════════════════════════════════════════════════════════
# 1) Estudiante -> 403 en TODOS los endpoints del administrador
# ══════════════════════════════════════════════════════════

@pytest.mark.parametrize("metodo,ruta,body", ENDPOINTS_ADMIN)
def test_estudiante_recibe_403_en_endpoints_admin(entorno, metodo, ruta, body):
    client, db = entorno
    est = _usuario(
        db, correo="est-rbac-http@utem.cl", rol="estudiante", rut="rbac-1"
    )
    db.commit()

    respuesta = (
        client.request(metodo, ruta, json=body, headers=_headers(est))
        if body is not None
        else client.request(metodo, ruta, headers=_headers(est))
    )

    assert respuesta.status_code == 403, (
        f"{metodo} {ruta} devolvió {respuesta.status_code}: {respuesta.text}"
    )
    assert respuesta.json()["detail"] == (
        "No tienes permiso para acceder a este recurso."
    )


# ══════════════════════════════════════════════════════════
# 2) Profesional -> también 403 (no hay bypass por ownership/rol)
# ══════════════════════════════════════════════════════════

def test_profesional_no_hereda_permisos_del_admin(entorno):
    client, db = entorno
    prof_user = _usuario(
        db, correo="prof-rbac-http@utem.cl", rol="profesional", rut="rbac-2"
    )
    db.commit()

    respuesta = client.patch(
        "/admin/citas/1/cancelar",
        json={"motivo": "prueba"},
        headers=_headers(prof_user),
    )

    assert respuesta.status_code == 403


def test_superadmin_puede_descargar_el_excel_de_reportes(entorno):
    """La ruta existe y devuelve un .xlsx real cuando el rol lo permite."""
    client, db = entorno
    sa = _usuario(
        db, correo="sa-reportes-http@utem.cl", rol="superadmin", rut="rbac-10"
    )
    db.commit()

    respuesta = client.get(
        "/admin/reportes/resumen/excel", headers=_headers(sa)
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert respuesta.content[:2] == b"PK"


# ══════════════════════════════════════════════════════════
# 3) Autenticación: sin token / token con firma inválida -> 401
#     (401 y 403 son estados distintos: no autenticado vs sin permiso)
# ══════════════════════════════════════════════════════════

def test_sin_token_es_401_no_403(entorno):
    client, _ = entorno
    respuesta = client.patch("/admin/citas/1/cancelar", json={"motivo": "x"})
    assert respuesta.status_code == 401


def test_token_con_firma_invalida_es_401(entorno):
    client, db = entorno
    est = _usuario(
        db, correo="est-firma@utem.cl", rol="estudiante", rut="rbac-3"
    )
    db.commit()

    token_falso = jwt.encode(
        {"id": est.id, "rol": est.rol, "correo": est.correo},
        "clave-que-no-es-la-del-servidor",
        algorithm=JWT_ALGORITHM,
    )

    respuesta = client.patch(
        "/admin/citas/1/cancelar",
        json={"motivo": "x"},
        headers={"Authorization": f"Bearer {token_falso}"},
    )

    assert respuesta.status_code == 401


# ══════════════════════════════════════════════════════════
# 4) Endpoint self-service del profesional: el permiso se exige
#     ANTES de consultar la fila (403, nunca 404 por enumeración)
# ══════════════════════════════════════════════════════════

def test_estudiante_recibe_403_antes_de_404_en_solicitud_ajena(entorno):
    client, db = entorno
    prof_user = _usuario(
        db, correo="prof-dueno@utem.cl", rol="profesional", rut="rbac-4"
    )
    est = _usuario(
        db, correo="est-ajeno@utem.cl", rol="estudiante", rut="rbac-5"
    )
    prof = Profesional(
        nombre="Profesional Dueño",
        especialidad="Nutrición",
        iniciales="PDU",
        estado="activo",
        usuario_id=prof_user.id,
    )
    db.add(prof)
    db.flush()
    solicitud = SolicitudHorario(
        profesional_id=prof.id,
        tipo="colacion",
        hora_inicio="13:00",
        hora_fin="14:00",
        estado="pendiente",
    )
    db.add(solicitud)
    db.commit()

    # Existe la fila: debe ser 403, no un 404 que confirme autoría ajena.
    existente = client.delete(
        f"/solicitudes-horario/{solicitud.id}", headers=_headers(est)
    )
    assert existente.status_code == 403

    # No existe la fila: el estudiante tampoco puede distinguirlo.
    inexistente = client.delete(
        "/solicitudes-horario/999999", headers=_headers(est)
    )
    assert inexistente.status_code == 403


def test_profesional_dueno_conserva_su_endpoint_self_service(entorno):
    """La corrección no debe bloquear al dueño legítimo."""
    client, db = entorno
    prof_user = _usuario(
        db, correo="prof-ok@utem.cl", rol="profesional", rut="rbac-6"
    )
    prof = Profesional(
        nombre="Profesional OK",
        especialidad="Nutrición",
        iniciales="POK",
        estado="activo",
        usuario_id=prof_user.id,
    )
    db.add(prof)
    db.flush()
    solicitud = SolicitudHorario(
        profesional_id=prof.id,
        tipo="colacion",
        hora_inicio="13:00",
        hora_fin="14:00",
        estado="pendiente",
    )
    db.add(solicitud)
    db.commit()

    respuesta = client.delete(
        f"/solicitudes-horario/{solicitud.id}", headers=_headers(prof_user)
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["message"] == "Solicitud eliminada correctamente"


# ══════════════════════════════════════════════════════════
# 5) No sobre-bloquear: el estudiante conserva su propio acceso
# ══════════════════════════════════════════════════════════

def test_estudiante_conserva_acceso_a_sus_propias_citas(entorno):
    client, db = entorno
    est = _usuario(
        db, correo="est-propio@utem.cl", rol="estudiante", rut="rbac-7"
    )
    db.commit()

    respuesta = client.get(
        f"/citas/estudiante/{est.id}", headers=_headers(est)
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_estudiante_no_puede_ver_citas_de_otro_estudiante(entorno):
    client, db = entorno
    est = _usuario(
        db, correo="est-uno@utem.cl", rol="estudiante", rut="rbac-8"
    )
    otro = _usuario(
        db, correo="est-dos@utem.cl", rol="estudiante", rut="rbac-9"
    )
    db.commit()

    respuesta = client.get(
        f"/citas/estudiante/{otro.id}", headers=_headers(est)
    )

    assert respuesta.status_code == 403
