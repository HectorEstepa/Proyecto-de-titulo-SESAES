"""
Agenda semanal por bloques: reglas del horario institucional, efecto en la
disponibilidad (lo que ve el estudiante y el admin) y el flujo de solicitud
del profesional + aprobacion del admin.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401
from app import reglas_horario
from app.database import Base
from app.models.bloque_horario_semanal import BloqueHorarioSemanal
from app.models.notificacion import Notificacion
from app.models.profesional import Profesional
from app.models.solicitud_bloques import SolicitudBloques
from app.models.solicitud_horario import SolicitudHorario
from app.models.usuario import Usuario
from app.rbac.admin_authorization import AlcanceAdministrativoEfectivo
from app.routers import profesionales, solicitudes_horario
from app.services.agenda_disponibilidad_service import (
    evaluar_disponibilidad_slot,
    listar_disponibilidad_rango,
    listar_horas_disponibles,
)


# ---------------------------------------------------------------- reglas

@pytest.mark.parametrize("dia,ini,fin", [
    (0, "09:00", "13:00"), (3, "14:00", "17:30"), (4, "09:00", "16:30"),
])
def test_bloque_dentro_del_horario_institucional_es_valido(dia, ini, fin):
    assert reglas_horario.validar_bloque(dia, ini, fin) is None


@pytest.mark.parametrize("dia,ini,fin", [
    (0, "08:30", "13:00"),     # antes de las 09:00
    (0, "14:00", "18:00"),     # despues de las 17:30
    (4, "14:00", "17:00"),     # el viernes cierra 16:30
    (5, "09:00", "10:00"),     # sabado
    (0, "13:00", "09:00"),     # al reves
    (0, "xx", "10:00"),        # hora invalida
])
def test_bloque_fuera_del_horario_institucional_se_rechaza(dia, ini, fin):
    assert reglas_horario.validar_bloque(dia, ini, fin)


# ---------------------------------------------------------------- base

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _lunes_a_jueves_futuro() -> date:
    f = date.today() + timedelta(days=1)
    while f.weekday() >= 4:
        f += timedelta(days=1)
    return f


def _viernes_futuro() -> date:
    f = date.today() + timedelta(days=1)
    while f.weekday() != 4:
        f += timedelta(days=1)
    return f


def _profesional(db, *, con_usuario=False, horario_inicio="09:00", horario_fin="17:00"):
    usuario_id = None
    if con_usuario:
        u = Usuario(correo="prof-bloques@sesaes.cl", password="x", rol="profesional",
                    nombre="Profesional Bloques", rut="1-9", activo=True)
        db.add(u)
        db.flush()
        usuario_id = u.id
    p = Profesional(
        nombre="Profesional Bloques", especialidad="Nutrición", iniciales="PB",
        estado="activo", horario_inicio=horario_inicio, horario_fin=horario_fin,
        duracion_min=30, usuario_id=usuario_id,
    )
    db.add(p)
    db.flush()
    return p


def _bloque(db, prof, dia, ini, fin, tipo="disponible"):
    db.add(BloqueHorarioSemanal(
        profesional_id=prof.id, dia_semana=dia, hora_inicio=ini, hora_fin=fin, tipo=tipo,
    ))


# ----------------------------------------------------- efecto en disponibilidad

def test_sin_bloques_se_usa_la_jornada_simple_de_siempre(db):
    prof = _profesional(db, horario_inicio="10:00", horario_fin="12:00")
    db.commit()
    fecha = _lunes_a_jueves_futuro()
    horas, _ = listar_horas_disponibles(db, profesional_id=prof.id, fecha=fecha.isoformat())
    assert horas and min(horas) == "10:00" and max(horas) == "11:30"


def test_sin_jornada_aprobada_usa_el_horario_institucional_predeterminado(db):
    """Un profesional nuevo (sin bloques ni horario_inicio/fin) atiende
    Lun-Jue 09:00-17:30, no todo el horario operativo del centro."""
    prof = _profesional(db, horario_inicio=None, horario_fin=None)
    db.commit()
    fecha = _lunes_a_jueves_futuro()
    horas, _ = listar_horas_disponibles(db, profesional_id=prof.id, fecha=fecha.isoformat())
    assert horas and min(horas) == "09:00" and max(horas) == "17:00"  # 17:00-17:30
    assert "08:00" not in horas and "08:30" not in horas

    r = evaluar_disponibilidad_slot(
        db, profesional_id=prof.id, fecha=fecha.isoformat(), hora="08:00",
    )
    assert r.disponible is False and r.motivo == "fuera_de_jornada"


def test_viernes_predeterminado_cierra_a_las_1630(db):
    prof = _profesional(db, horario_inicio=None, horario_fin=None)
    db.commit()
    fecha = _viernes_futuro()
    horas, _ = listar_horas_disponibles(db, profesional_id=prof.id, fecha=fecha.isoformat())
    assert horas and max(horas) == "16:00"  # 16:00-16:30
    assert "16:30" not in horas

    r = evaluar_disponibilidad_slot(
        db, profesional_id=prof.id, fecha=fecha.isoformat(), hora="16:30",
    )
    assert r.disponible is False and r.motivo == "fuera_de_jornada"


def test_con_bloques_solo_se_ofrece_lo_que_esta_dentro_de_un_bloque_disponible(db):
    prof = _profesional(db)   # jornada simple 09:00-17:00, que los bloques reemplazan
    dia = _lunes_a_jueves_futuro().weekday()
    _bloque(db, prof, dia, "09:00", "13:00")
    _bloque(db, prof, dia, "14:00", "16:00")
    db.commit()
    horas, _ = listar_horas_disponibles(
        db, profesional_id=prof.id, fecha=_lunes_a_jueves_futuro().isoformat(),
    )
    assert "09:00" in horas and "12:30" in horas
    assert "13:00" not in horas and "13:30" not in horas      # hueco entre bloques
    assert "14:00" in horas and "15:30" in horas
    assert "16:00" not in horas                                # fin del ultimo bloque


def test_la_colacion_dentro_de_un_bloque_no_se_ofrece(db):
    prof = _profesional(db)
    dia = _lunes_a_jueves_futuro().weekday()
    _bloque(db, prof, dia, "09:00", "17:00")
    _bloque(db, prof, dia, "13:00", "14:00", tipo="colacion")
    db.commit()
    fecha = _lunes_a_jueves_futuro().isoformat()
    horas, _ = listar_horas_disponibles(db, profesional_id=prof.id, fecha=fecha)
    assert "12:30" in horas and "14:00" in horas
    assert "13:00" not in horas and "13:30" not in horas
    r = evaluar_disponibilidad_slot(db, profesional_id=prof.id, fecha=fecha, hora="13:00")
    assert r.disponible is False and r.motivo == "en_colacion"
    assert r.overridable_con_sobrecupo is True


def test_hora_fuera_de_los_bloques_es_fuera_de_jornada_y_overridable(db):
    prof = _profesional(db)
    dia = _lunes_a_jueves_futuro().weekday()
    _bloque(db, prof, dia, "09:00", "12:00")
    db.commit()
    r = evaluar_disponibilidad_slot(
        db, profesional_id=prof.id, fecha=_lunes_a_jueves_futuro().isoformat(), hora="15:00",
    )
    assert r.disponible is False and r.motivo == "fuera_de_jornada"
    assert r.overridable_con_sobrecupo is True


def test_un_dia_sin_bloques_dentro_de_una_agenda_por_bloques_no_atiende(db):
    prof = _profesional(db)
    fecha = _lunes_a_jueves_futuro()
    otro_dia = (fecha.weekday() + 1) % 4          # otro dia de Lun-Jue
    _bloque(db, prof, otro_dia, "09:00", "17:00")
    db.commit()
    horas, _ = listar_horas_disponibles(db, profesional_id=prof.id, fecha=fecha.isoformat())
    assert horas == []


def test_el_rango_de_la_agenda_admin_refleja_los_bloques(db):
    prof = _profesional(db)
    fecha = _lunes_a_jueves_futuro()
    _bloque(db, prof, fecha.weekday(), "09:00", "11:00")
    db.commit()
    res = listar_disponibilidad_rango(
        db, profesional_id=prof.id,
        fecha_inicio=fecha.isoformat(), fecha_fin=fecha.isoformat(),
    )
    slots = {s["hora"]: s for s in res["dias"][0]["slots"]}
    assert slots["09:00"]["disponible"] is True
    assert slots["11:00"]["disponible"] is False
    assert slots["11:00"]["motivo"] == "fuera_de_jornada"


# ---------------------------------------------------- solicitud y aprobacion

def _usuario_prof(prof):
    return {"id": prof.usuario_id, "rol": "profesional"}


def _bloques_validos():
    return [
        {"dia_semana": 0, "hora_inicio": "09:00", "hora_fin": "13:00", "tipo": "disponible"},
        {"dia_semana": 0, "hora_inicio": "13:00", "hora_fin": "14:00", "tipo": "colacion"},
        {"dia_semana": 0, "hora_inicio": "14:00", "hora_fin": "17:30", "tipo": "disponible"},
        {"dia_semana": 4, "hora_inicio": "09:00", "hora_fin": "16:30", "tipo": "disponible"},
    ]


def test_el_profesional_solicita_bloques_y_queda_pendiente(db):
    prof = _profesional(db, con_usuario=True)
    db.commit()
    r = solicitudes_horario.solicitar_bloques_horario(
        prof.id, {"bloques": _bloques_validos()}, db=db, current_user=_usuario_prof(prof),
    )
    assert len(r["bloques"]) == 4
    sol = db.query(SolicitudHorario).one()
    assert sol.tipo == "bloques" and sol.estado == "pendiente"
    assert (sol.hora_inicio, sol.hora_fin) == ("09:00", "17:30")      # resumen legible
    detalle = db.query(SolicitudBloques).one()
    assert len(json.loads(detalle.bloques_json)) == 4


def test_una_segunda_solicitud_pendiente_reemplaza_a_la_primera(db):
    prof = _profesional(db, con_usuario=True)
    db.commit()
    for _ in range(2):
        solicitudes_horario.solicitar_bloques_horario(
            prof.id, {"bloques": _bloques_validos()}, db=db, current_user=_usuario_prof(prof),
        )
    assert db.query(SolicitudHorario).count() == 1
    assert db.query(SolicitudBloques).count() == 1


@pytest.mark.parametrize("bloques", [
    [],
    [{"dia_semana": 5, "hora_inicio": "09:00", "hora_fin": "10:00", "tipo": "disponible"}],
    [{"dia_semana": 0, "hora_inicio": "08:00", "hora_fin": "10:00", "tipo": "disponible"}],
    [{"dia_semana": 4, "hora_inicio": "15:00", "hora_fin": "17:00", "tipo": "disponible"}],
    [{"dia_semana": 0, "hora_inicio": "09:00", "hora_fin": "10:00", "tipo": "otro"}],
    [{"dia_semana": 0, "hora_inicio": "13:00", "hora_fin": "14:00", "tipo": "colacion"}],  # sin disponibles
])
def test_solicitudes_de_bloques_invalidas_se_rechazan(db, bloques):
    prof = _profesional(db, con_usuario=True)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        solicitudes_horario.solicitar_bloques_horario(
            prof.id, {"bloques": bloques}, db=db, current_user=_usuario_prof(prof),
        )
    assert exc.value.status_code == 400
    assert db.query(SolicitudHorario).count() == 0


def test_un_profesional_ajeno_no_puede_solicitar_bloques(db):
    prof = _profesional(db, con_usuario=True)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        solicitudes_horario.solicitar_bloques_horario(
            prof.id, {"bloques": _bloques_validos()}, db=db,
            current_user={"id": 9999, "rol": "profesional"},
        )
    assert exc.value.status_code == 403


def _admin(monkeypatch):
    monkeypatch.setattr(
        solicitudes_horario, "obtener_alcance_administrativo_efectivo",
        lambda db, u: AlcanceAdministrativoEfectivo(
            institucional=True, especialidades_normalizadas=frozenset(),
        ),
    )
    return {"id": 99999, "rol": "admin"}


def test_el_admin_aprueba_y_la_agenda_por_bloques_reemplaza_a_la_anterior(db, monkeypatch):
    prof = _profesional(db, con_usuario=True)
    _bloque(db, prof, 2, "09:00", "10:00")            # agenda anterior, debe desaparecer
    db.commit()
    solicitudes_horario.solicitar_bloques_horario(
        prof.id, {"bloques": _bloques_validos()}, db=db, current_user=_usuario_prof(prof),
    )
    sol = db.query(SolicitudHorario).one()
    solicitudes_horario.aprobar_solicitud(sol.id, db=db, current_user=_admin(monkeypatch))

    db.expire_all()
    filas = db.query(BloqueHorarioSemanal).filter_by(profesional_id=prof.id).all()
    assert len(filas) == 4
    assert {f.dia_semana for f in filas} == {0, 4}
    assert db.query(SolicitudHorario).one().estado == "aprobado"
    assert db.query(Notificacion).filter(Notificacion.mensaje.like("%bloques%")).count() >= 1


def test_el_admin_rechaza_y_no_se_crean_bloques(db, monkeypatch):
    prof = _profesional(db, con_usuario=True)
    db.commit()
    solicitudes_horario.solicitar_bloques_horario(
        prof.id, {"bloques": _bloques_validos()}, db=db, current_user=_usuario_prof(prof),
    )
    sol = db.query(SolicitudHorario).one()
    solicitudes_horario.rechazar_solicitud(
        sol.id, {"motivo": "Faltan horas"}, db=db, current_user=_admin(monkeypatch),
    )
    assert db.query(BloqueHorarioSemanal).count() == 0
    assert db.query(SolicitudHorario).one().estado == "rechazado"


def test_los_listados_incluyen_el_detalle_de_los_bloques(db):
    prof = _profesional(db, con_usuario=True)
    db.commit()
    solicitudes_horario.solicitar_bloques_horario(
        prof.id, {"bloques": _bloques_validos()}, db=db, current_user=_usuario_prof(prof),
    )
    mis = solicitudes_horario.get_mis_solicitudes(prof.id, db=db, current_user=_usuario_prof(prof))
    assert len(mis[0]["bloques"]) == 4


def test_eliminar_una_solicitud_de_bloques_borra_tambien_su_detalle(db):
    prof = _profesional(db, con_usuario=True)
    db.commit()
    solicitudes_horario.solicitar_bloques_horario(
        prof.id, {"bloques": _bloques_validos()}, db=db, current_user=_usuario_prof(prof),
    )
    sol = db.query(SolicitudHorario).one()
    solicitudes_horario.eliminar_solicitud(sol.id, db=db, current_user=_usuario_prof(prof))
    assert db.query(SolicitudHorario).count() == 0
    assert db.query(SolicitudBloques).count() == 0


def test_el_perfil_del_profesional_trae_sus_bloques_aprobados(db):
    prof = _profesional(db, con_usuario=True)
    _bloque(db, prof, 0, "09:00", "13:00")
    _bloque(db, prof, 0, "13:00", "14:00", tipo="colacion")
    db.commit()
    perfil = profesionales.get_perfil(prof.id, db=db, current_user=_usuario_prof(prof))
    assert [b["tipo"] for b in perfil["bloques_semanales"]] == ["disponible", "colacion"]
