# -*- coding: utf-8 -*-
"""
Registro de auditoría de la agenda médica.

Cubre el requisito de tesis: toda cita deja constancia automática de
QUIÉN la crea, modifica o anula (usuario_id + actor_rol derivados de
current_user) y CUÁNDO (Auditoria.fecha, DEFAULT now() del motor).

Se apoya en el helper central ya existente (app.auditoria) y en la
tabla `auditoria` (SA-2). No se crea un segundo sistema de auditoría:
el historial de una cita se reconstruye filtrando
entidad="cita" + entidad_id=<id>.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401 — registra TODOS los modelos productivos
import app.models.solicitud_horario  # noqa: F401 — igual que test_a3/a4_1

from app.database import Base
from app.models.auditoria import Auditoria
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.auditoria import registrar_evento_cita
from app.routers import admin, citas
from app.schemas import CitaCreate


# ══════════════════════════════════════════════════════════
# Fixtures / helpers (mismo estilo que test_a4_1_trazabilidad.py)
# ══════════════════════════════════════════════════════════

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _dia_habil_futuro(dias_calendario: int = 1) -> str:
    fecha = date.today() + timedelta(days=dias_calendario)
    while fecha.weekday() >= 5:
        fecha += timedelta(days=1)
    return fecha.isoformat()


def _profesional(db, *, estado="activo"):
    prof = Profesional(
        nombre="Profesional Test Auditoría",
        especialidad="Nutrición",
        iniciales="PAU",
        estado=estado,
        horario_inicio="09:00",
        horario_fin="17:00",
        duracion_min=45,
    )
    db.add(prof)
    db.flush()
    return prof


def _usuario(db, *, correo, rol, rut):
    usuario = Usuario(
        correo=correo, password="hash-auditoria", rol=rol,
        nombre="Usuario Test Auditoría", rut=rut, activo=True,
    )
    db.add(usuario)
    db.flush()
    return usuario


def _current_user(usuario):
    return {"id": usuario.id, "rol": usuario.rol}


def _eventos_de_cita(db, cita_id):
    return (
        db.query(Auditoria)
        .filter(Auditoria.entidad == "cita", Auditoria.entidad_id == cita_id)
        .order_by(Auditoria.id)
        .all()
    )


# ══════════════════════════════════════════════════════════
# 1) CREACIÓN — actor + timestamp exacto
# ══════════════════════════════════════════════════════════

def test_crear_cita_registra_actor_id_y_timestamp(db_session):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session)
    est = _usuario(
        db_session, correo="est-crea-aud@sesaes.cl",
        rol="estudiante", rut="aud-1",
    )
    db_session.commit()

    citas.crear_cita(
        cita=CitaCreate(
            estudiante_id=est.id, profesional_id=prof.id,
            fecha=fecha, hora="09:30",
        ),
        db=db_session,
        current_user=_current_user(est),
    )

    creada = db_session.query(Cita).one()
    eventos = _eventos_de_cita(db_session, creada.id)
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.accion == "Creó cita"
    # El actor es el usuario autenticado, no el paciente del body.
    assert evento.usuario_id == est.id
    assert evento.actor_rol == "estudiante"
    assert evento.resultado == "exito"
    # Timestamp exacto persistido por el DEFAULT del motor.
    assert isinstance(evento.fecha, datetime)
    assert f"Estudiante id {est.id}" in evento.detalle


def test_crear_cita_admin_registra_al_admin_no_al_paciente(db_session):
    """Un admin agendando a nombre de un estudiante deja como actor al
    admin — exactamente el mismo criterio que creado_por_usuario_id."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session)
    est = _usuario(
        db_session, correo="est-agenda-admin-aud@sesaes.cl",
        rol="estudiante", rut="aud-2",
    )
    sa = _usuario(
        db_session, correo="sa-agenda-aud@sesaes.cl",
        rol="superadmin", rut="aud-3",
    )
    db_session.commit()

    citas.crear_cita(
        cita=CitaCreate(
            estudiante_id=est.id, profesional_id=prof.id,
            fecha=fecha, hora="10:15",
        ),
        db=db_session,
        current_user=_current_user(sa),
    )

    creada = db_session.query(Cita).one()
    evento = _eventos_de_cita(db_session, creada.id)[0]
    assert evento.usuario_id == sa.id
    assert evento.actor_rol == "superadmin"
    assert evento.accion == "Creó cita"


# ══════════════════════════════════════════════════════════
# 2) ANULACIÓN — DELETE /citas/{id}
# ══════════════════════════════════════════════════════════

def test_cancelar_cita_registra_actor_id_y_timestamp(db_session):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session)
    est = _usuario(
        db_session, correo="est-cancela-aud@sesaes.cl",
        rol="estudiante", rut="aud-4",
    )
    db_session.commit()

    citas.crear_cita(
        cita=CitaCreate(
            estudiante_id=est.id, profesional_id=prof.id,
            fecha=fecha, hora="11:00",
        ),
        db=db_session,
        current_user=_current_user(est),
    )
    creada = db_session.query(Cita).one()

    citas.cancelar_cita(
        cita_id=creada.id,
        db=db_session,
        current_user=_current_user(est),
    )

    eventos = _eventos_de_cita(db_session, creada.id)
    assert [e.accion for e in eventos] == ["Creó cita", "Canceló cita"]
    anulacion = eventos[-1]
    assert anulacion.usuario_id == est.id
    assert anulacion.actor_rol == "estudiante"
    assert isinstance(anulacion.fecha, datetime)
    assert "pendiente → cancelada" in anulacion.detalle
    assert db_session.query(Cita).filter(Cita.id == creada.id).one().estado == "cancelada"


# ══════════════════════════════════════════════════════════
# 3) ANULACIÓN MASIVA — cierre de día: una fila POR CITA
# ══════════════════════════════════════════════════════════

def test_cierre_de_dia_registra_un_evento_por_cita(db_session, monkeypatch):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session)
    est1 = _usuario(
        db_session, correo="est1-cierre-aud@sesaes.cl",
        rol="estudiante", rut="aud-5",
    )
    est2 = _usuario(
        db_session, correo="est2-cierre-aud@sesaes.cl",
        rol="estudiante", rut="aud-6",
    )
    sa = _usuario(
        db_session, correo="sa-cierre-aud@sesaes.cl",
        rol="superadmin", rut="aud-7",
    )
    cita1 = Cita(estudiante_id=est1.id, profesional_id=prof.id,
                 fecha=fecha, hora="09:00", estado="pendiente")
    cita2 = Cita(estudiante_id=est2.id, profesional_id=prof.id,
                 fecha=fecha, hora="10:00", estado="pendiente")
    db_session.add_all([cita1, cita2])
    db_session.commit()

    # El envío de correo no es parte de lo que este test verifica y no
    # debe intentar red real durante la suite.
    monkeypatch.setattr(admin, "simular_envio_correo", lambda *a, **k: None)

    admin.crear_dia_cerrado(
        body={"fecha": fecha, "motivo": "Cierre de prueba"},
        db=db_session,
        current_user=_current_user(sa),
    )

    for cita in (cita1, cita2):
        eventos = _eventos_de_cita(db_session, cita.id)
        assert len(eventos) == 1
        evento = eventos[0]
        assert evento.accion == "Canceló cita"
        assert evento.usuario_id == sa.id
        assert evento.actor_rol == "superadmin"
        assert isinstance(evento.fecha, datetime)
        assert "centro cerrado" in evento.detalle


# ══════════════════════════════════════════════════════════
# 4) CONSULTA — historial completo de una cita
# ══════════════════════════════════════════════════════════

def test_evento_de_cita_sin_id_falla_cerrado(db_session):
    """Nunca se persiste un evento de cita con entidad_id=NULL: si el
    call-site olvidó el flush previo, la auditoría falla explícitamente
    en vez de quedar huérfana."""

    class CitaSinId:
        id = None
        estudiante_id = 1
        profesional_id = 2
        fecha = "2026-01-01"
        hora = "09:00"

    with pytest.raises(ValueError):
        registrar_evento_cita(
            db_session,
            {"id": 1, "rol": "admin"},
            "Creó cita",
            cita=CitaSinId(),
        )
    assert db_session.query(Auditoria).count() == 0


def test_historial_de_una_cita_se_filtra_por_entidad_y_entidad_id(db_session):
    otra = Auditoria(
        usuario_id=None, actor_rol="superadmin",
        accion="Eliminó profesional", entidad="profesional", entidad_id=99,
        fecha=datetime.now(),
    )
    eventos_cita = [
        Auditoria(
            usuario_id=None, actor_rol="estudiante",
            accion="Creó cita", entidad="cita", entidad_id=42,
            fecha=datetime.now(),
        ),
        Auditoria(
            usuario_id=None, actor_rol="admin",
            accion="Canceló cita", entidad="cita", entidad_id=42,
            fecha=datetime.now(),
        ),
    ]
    db_session.add_all([otra, *eventos_cita])
    db_session.commit()

    resultado = admin.get_auditoria(
        db=db_session,
        current_user={"id": 1, "rol": "superadmin"},
        entidad="cita",
        entidad_id=42,
    )

    assert [r["accion"] for r in resultado] == ["Canceló cita", "Creó cita"]
    assert all(r["entidad"] == "cita" and r["entidad_id"] == 42 for r in resultado)
    assert all(r["fecha"] is not None for r in resultado)
