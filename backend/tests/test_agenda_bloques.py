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
from app.models.cita import Cita
from app.models.notificacion import Notificacion
from app.models.profesional import Profesional
from app.models.solicitud_bloques import SolicitudBloques
from app.models.solicitud_horario import SolicitudHorario
from app.models.usuario import Usuario
from app.rbac.admin_authorization import AlcanceAdministrativoEfectivo
from app.routers import admin, profesionales, solicitudes_horario
from app.schemas import CitaCreate
from app.services.agenda_disponibilidad_service import (
    evaluar_disponibilidad_slot,
    listar_disponibilidad_rango,
    listar_horas_disponibles,
    validar_horario_aprobado_slot,
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
    # El acuerdo por bloques aprobado es bloqueo estricto: ni el
    # sobrecupo lo puede forzar (antes era True y el admin podia
    # agendar encima de la colacion aprobada).
    assert r.overridable_con_sobrecupo is False
    assert "colación aprobada" in r.mensaje and "13:00" in r.mensaje


def test_hora_fuera_de_los_bloques_es_bloqueo_absoluto(db):
    prof = _profesional(db)
    dia = _lunes_a_jueves_futuro().weekday()
    _bloque(db, prof, dia, "09:00", "12:00")
    db.commit()
    r = evaluar_disponibilidad_slot(
        db, profesional_id=prof.id, fecha=_lunes_a_jueves_futuro().isoformat(), hora="15:00",
    )
    assert r.disponible is False and r.motivo == "fuera_de_jornada"
    assert r.overridable_con_sobrecupo is False
    assert "horario semanal aprobado" in r.mensaje


def test_dia_sin_atencion_se_distingue_de_hora_fuera_del_bloque(db):
    """El mensaje del 400 debe detallar el motivo: no es lo mismo "no
    trabaja ese día" que "esa hora queda fuera de sus bloques"."""
    prof = _profesional(db)
    fecha = _lunes_a_jueves_futuro()
    otro_dia = (fecha.weekday() + 1) % 4
    _bloque(db, prof, otro_dia, "09:00", "17:00")
    db.commit()
    r = evaluar_disponibilidad_slot(
        db, profesional_id=prof.id, fecha=fecha.isoformat(), hora="10:00",
    )
    assert r.disponible is False and r.motivo == "fuera_de_jornada"
    assert r.overridable_con_sobrecupo is False
    assert "no trabaja ese día" in r.mensaje


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
    assert slots["09:00"]["bloqueado_por_horario_aprobado"] is False
    assert slots["11:00"]["disponible"] is False
    assert slots["11:00"]["motivo"] == "fuera_de_jornada"
    # Las 3 agendas pintan y deshabilitan a partir de este flag.
    assert slots["11:00"]["bloqueado_por_horario_aprobado"] is True


def test_el_rango_marca_la_colacion_aprobada_como_bloqueada(db):
    prof = _profesional(db)
    fecha = _lunes_a_jueves_futuro()
    _bloque(db, prof, fecha.weekday(), "09:00", "13:00")
    _bloque(db, prof, fecha.weekday(), "13:00", "14:00", tipo="colacion")
    _bloque(db, prof, fecha.weekday(), "14:00", "17:00")
    db.commit()
    res = listar_disponibilidad_rango(
        db, profesional_id=prof.id,
        fecha_inicio=fecha.isoformat(), fecha_fin=fecha.isoformat(),
    )
    slots = {s["hora"]: s for s in res["dias"][0]["slots"]}
    assert slots["13:00"]["motivo"] == "en_colacion"
    assert slots["13:00"]["bloqueado_por_horario_aprobado"] is True
    assert slots["14:00"]["bloqueado_por_horario_aprobado"] is False


def _proximo_dia_semana(dia: int) -> date:
    f = date.today() + timedelta(days=1)
    while f.weekday() != dia:
        f += timedelta(days=1)
    return f


def test_el_flag_no_marca_el_fin_de_semana_como_bloqueo_del_profesional(db):
    """El analizador agrega un conflicto de bloques también un sábado (día
    sin atención), pero la celda debe seguir siendo 'centro cerrado'."""
    prof = _profesional(db)
    _bloque(db, prof, 0, "09:00", "17:00")
    sabado = _proximo_dia_semana(5)
    db.commit()
    res = listar_disponibilidad_rango(
        db, profesional_id=prof.id,
        fecha_inicio=sabado.isoformat(), fecha_fin=sabado.isoformat(),
    )
    slots = res["dias"][0]["slots"]
    assert slots and all(s["motivo"] == "fin_de_semana" for s in slots)
    assert all(s["bloqueado_por_horario_aprobado"] is False for s in slots)


def test_el_flag_no_marca_un_dia_cerrado_del_centro(db):
    from app.models.dia_cerrado import DiaCerrado

    prof = _profesional(db)
    fecha = _lunes_a_jueves_futuro()
    _bloque(db, prof, fecha.weekday(), "09:00", "17:00")
    db.add(DiaCerrado(fecha=fecha.isoformat(), motivo="Feriado"))
    db.commit()
    res = listar_disponibilidad_rango(
        db, profesional_id=prof.id,
        fecha_inicio=fecha.isoformat(), fecha_fin=fecha.isoformat(),
    )
    slots = res["dias"][0]["slots"]
    assert slots and all(s["motivo"] == "dia_cerrado" for s in slots)
    assert all(s["bloqueado_por_horario_aprobado"] is False for s in slots)


def test_sin_bloques_el_flag_no_marca_la_jornada_simple_como_bloqueada(db):
    """La jornada simple conserva su política (overridable con sobrecupo):
    el flag es exclusivo del acuerdo por bloques aprobado."""
    prof = _profesional(db, horario_inicio="09:00", horario_fin="12:00")
    db.commit()
    fecha = _lunes_a_jueves_futuro()
    res = listar_disponibilidad_rango(
        db, profesional_id=prof.id,
        fecha_inicio=fecha.isoformat(), fecha_fin=fecha.isoformat(),
    )
    slots = {s["hora"]: s for s in res["dias"][0]["slots"]}
    assert slots["15:00"]["disponible"] is False
    assert slots["15:00"]["bloqueado_por_horario_aprobado"] is False
    assert slots["15:00"]["overridable_con_sobrecupo"] is True


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


# ════════════════════════════════════════════════════════════
# Horario aprobado = bloqueo estricto (400 con motivo concreto)
# ════════════════════════════════════════════════════════════
#
# validar_horario_aprobado_slot() es la regla que aplica
# POST /admin/citas/urgente, el único canal que no pasa por
# evaluar_disponibilidad_slot(). La jornada simple queda fuera:
# mantiene su política anterior (overridable con sobrecupo).

def test_validar_horario_sin_bloques_no_impone_nada(db):
    prof = _profesional(db, horario_inicio="09:00", horario_fin="17:00")
    db.commit()
    fecha = _lunes_a_jueves_futuro().isoformat()
    assert validar_horario_aprobado_slot(db, profesional=prof, fecha=fecha, hora="08:00") is None
    assert validar_horario_aprobado_slot(db, profesional=prof, fecha=fecha, hora="12:00") is None


def test_validar_horario_dentro_de_un_bloque_es_valido(db):
    prof = _profesional(db)
    dia = _lunes_a_jueves_futuro().weekday()
    _bloque(db, prof, dia, "09:00", "13:00")
    db.commit()
    fecha = _lunes_a_jueves_futuro().isoformat()
    # 12:30 + 30 min termina justo al borde del bloque: válido.
    assert validar_horario_aprobado_slot(db, profesional=prof, fecha=fecha, hora="12:30") is None


def test_validar_horario_dia_sin_atencion_detalla_el_motivo(db):
    prof = _profesional(db)
    fecha = _lunes_a_jueves_futuro()
    otro_dia = (fecha.weekday() + 1) % 4
    _bloque(db, prof, otro_dia, "09:00", "17:00")
    db.commit()
    mensaje = validar_horario_aprobado_slot(
        db, profesional=prof, fecha=fecha.isoformat(), hora="10:00",
    )
    assert mensaje == "El profesional no trabaja ese día según su horario semanal aprobado."


def test_validar_horario_fuera_de_bloque_detalla_el_motivo(db):
    prof = _profesional(db)
    dia = _lunes_a_jueves_futuro().weekday()
    _bloque(db, prof, dia, "09:00", "12:00")
    db.commit()
    mensaje = validar_horario_aprobado_slot(
        db, profesional=prof, fecha=_lunes_a_jueves_futuro().isoformat(), hora="15:00",
    )
    assert mensaje == "La hora solicitada está fuera del horario semanal aprobado del profesional."


def test_validar_horario_en_colacion_incluye_el_rango_aprobado(db):
    prof = _profesional(db)
    dia = _lunes_a_jueves_futuro().weekday()
    _bloque(db, prof, dia, "09:00", "17:00")
    _bloque(db, prof, dia, "13:00", "14:00", tipo="colacion")
    db.commit()
    mensaje = validar_horario_aprobado_slot(
        db, profesional=prof, fecha=_lunes_a_jueves_futuro().isoformat(), hora="13:00",
    )
    assert mensaje == (
        "La hora solicitada se superpone con la colación aprobada "
        "del profesional (13:00–14:00)."
    )


def test_validar_horario_ignora_entradas_no_interpretables(db):
    """Formato inválido no es responsabilidad de esta regla: la cita
    urgente ya lo rechaza con 400 vía hay_solapamiento_con_cita_activa."""
    prof = _profesional(db)
    _bloque(db, prof, _lunes_a_jueves_futuro().weekday(), "09:00", "17:00")
    db.commit()
    assert validar_horario_aprobado_slot(
        db, profesional=prof, fecha="no-es-fecha", hora="10:00",
    ) is None
    assert validar_horario_aprobado_slot(
        db, profesional=prof, fecha=_lunes_a_jueves_futuro().isoformat(), hora="xx",
    ) is None


# ----------------------------------------- POST /admin/citas/urgente

def _estudiante_urgente(db, correo="urg-bloques@sesaes.cl"):
    u = Usuario(correo=correo, password="x", rol="estudiante",
                nombre="Estudiante Urgente", rut="urg-1", activo=True)
    db.add(u)
    db.flush()
    return u


def _alcance_institucional(monkeypatch):
    monkeypatch.setattr(
        admin, "obtener_alcance_administrativo_efectivo",
        lambda db, u: AlcanceAdministrativoEfectivo(
            institucional=True, especialidades_normalizadas=frozenset(),
        ),
    )


def test_urgente_rechaza_con_400_un_dia_sin_atencion_aprobado(db, monkeypatch):
    fecha = _lunes_a_jueves_futuro()
    prof = _profesional(db)
    otro_dia = (fecha.weekday() + 1) % 4
    _bloque(db, prof, otro_dia, "09:00", "17:00")
    est = _estudiante_urgente(db)
    db.commit()
    _alcance_institucional(monkeypatch)

    payload = CitaCreate(
        estudiante_id=est.id, profesional_id=prof.id,
        fecha=fecha.isoformat(), hora="10:00",
    )
    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(cita=payload, db=db, current_user={"id": 999, "rol": "admin"})

    assert exc.value.status_code == 400
    assert "no trabaja ese día" in exc.value.detail
    assert db.query(Cita).count() == 0


def test_urgente_rechaza_con_400_la_colacion_aprobada_aunque_sea_admin(db, monkeypatch):
    """Ni Admin ni Super Admin pueden forzar la colación con una
    urgencia: es un bloqueo absoluto, no un sobrecupo."""
    fecha = _lunes_a_jueves_futuro()
    prof = _profesional(db)
    dia = fecha.weekday()
    _bloque(db, prof, dia, "09:00", "17:00")
    _bloque(db, prof, dia, "13:00", "14:00", tipo="colacion")
    est = _estudiante_urgente(db, correo="urg-colacion@sesaes.cl")
    db.commit()
    _alcance_institucional(monkeypatch)

    payload = CitaCreate(
        estudiante_id=est.id, profesional_id=prof.id,
        fecha=fecha.isoformat(), hora="13:00",
    )
    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(cita=payload, db=db, current_user={"id": 999, "rol": "admin"})

    assert exc.value.status_code == 400
    assert "colación aprobada" in exc.value.detail
    assert "13:00–14:00" in exc.value.detail
    assert db.query(Cita).count() == 0


def test_urgente_sigue_funcionando_dentro_del_bloque_aprobado(db, monkeypatch):
    fecha = _lunes_a_jueves_futuro()
    prof = _profesional(db)
    _bloque(db, prof, fecha.weekday(), "09:00", "17:00")
    est = _estudiante_urgente(db, correo="urg-ok@sesaes.cl")
    db.commit()
    _alcance_institucional(monkeypatch)

    payload = CitaCreate(
        estudiante_id=est.id, profesional_id=prof.id,
        fecha=fecha.isoformat(), hora="10:00",
    )
    resultado = admin.crear_cita_urgente(
        cita=payload, db=db, current_user={"id": 999, "rol": "admin"},
    )
    assert resultado["urgente"] is True and resultado["hora"] == "10:00"
    assert db.query(Cita).count() == 1


# --------------------------------- GET /admin/profesionales (agenda admin)

def test_profesionales_admin_expone_los_bloques_aprobados(db, monkeypatch):
    """La agenda administrativa dibuja la colación y los días de atención con
    los bloques aprobados del profesional: si el endpoint no los entrega, la
    pantalla solo puede caer en hora_almuerzo_*, que es la colación de la
    jornada simple y no la de la agenda por bloques."""
    prof = _profesional(db)
    prof.hora_almuerzo_inicio = "13:00"
    prof.hora_almuerzo_fin = "14:00"
    _bloque(db, prof, 0, "09:00", "12:00")
    _bloque(db, prof, 0, "12:00", "13:00", tipo="colacion")
    _bloque(db, prof, 0, "13:00", "17:30")
    sin_bloques = _profesional(db, horario_inicio="10:00", horario_fin="12:00")
    db.commit()
    _alcance_institucional(monkeypatch)

    filas = admin.get_profesionales_admin(
        db=db, current_user={"id": 999, "rol": "admin"},
    )
    por_id = {fila["id"]: fila for fila in filas}

    assert por_id[prof.id]["bloques_semanales"] == [
        {"dia_semana": 0, "hora_inicio": "09:00", "hora_fin": "12:00", "tipo": "disponible"},
        {"dia_semana": 0, "hora_inicio": "12:00", "hora_fin": "13:00", "tipo": "colacion"},
        {"dia_semana": 0, "hora_inicio": "13:00", "hora_fin": "17:30", "tipo": "disponible"},
    ]
    # Sin bloques aprobados la lista va vacía: la agenda usa la jornada simple.
    assert por_id[sin_bloques.id]["bloques_semanales"] == []
