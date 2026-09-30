# -*- coding: utf-8 -*-
"""
SESAES — A.3: concurrencia / doble reserva.

Cubre, en app.services.agenda_disponibilidad_service:

  - adquirir_lock_agenda_profesional_fecha(): estrategia explícita por
    dialecto (postgresql real, sqlite no-op, cualquier otro dialecto
    falla). Construcción de claves int4 (profesional_id, YYYYMMDD) sin
    hash() de Python ni hashtext().
  - hay_solapamiento_con_cita_activa(): la pieza de ocupación/intervalos
    reutilizada por POST /admin/citas/urgente sin arrastrar
    jornada/colación/grilla/cierre de centro.

Y en los routers:

  - POST /citas adquiere el lock ANTES de re-evaluar disponibilidad
    (orden obligatorio de A.3), y un conflicto de ocupación (incluida
    la re-evaluación) responde 409, nunca se convierte en sobrecupo.
  - POST /admin/citas/urgente adquiere el mismo lock y ahora SÍ se
    protege de solapar una cita activa — hueco que tenía desde A.2 —
    sin tocar su semántica histórica de jornada/colación/grilla, que
    sigue sin evaluar (decisión que A.3 no amplía).

Los tests unitarios de esta suite corren contra SQLite (como el resto
del proyecto) y por lo tanto NO validan la garantía real de
concurrencia de PostgreSQL — solo el contrato de la función (qué SQL
construye, en qué orden se llama, qué endpoints la usan). La garantía
real se valida en test_a3_concurrencia_postgres.py, marcada
@pytest.mark.postgres y con skip si no hay Postgres de test disponible
(ver ese archivo).
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rbac.admin_authorization import AlcanceAdministrativoEfectivo
from app.routers import admin, citas
from app.schemas import CitaCreate
from app.models.dia_cerrado import DiaCerrado
from app.services.agenda_disponibilidad_service import (
    ResultadoDisponibilidad,
    SlotInvalidoError,
    adquirir_lock_agenda_profesional_fecha,
    canonicalizar_fecha_valida,
    evaluar_disponibilidad_slot,
    hay_solapamiento_con_cita_activa,
)


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


def _profesional(
    db,
    *,
    horario_inicio="09:00",
    horario_fin="17:00",
    hora_almuerzo_inicio=None,
    hora_almuerzo_fin=None,
    duracion_min=45,
    estado="activo",
):
    prof = Profesional(
        nombre="Profesional Test A3",
        especialidad="Nutrición",
        iniciales="PA3",
        estado=estado,
        horario_inicio=horario_inicio,
        horario_fin=horario_fin,
        hora_almuerzo_inicio=hora_almuerzo_inicio,
        hora_almuerzo_fin=hora_almuerzo_fin,
        duracion_min=duracion_min,
    )
    db.add(prof)
    db.flush()
    return prof


def _estudiante(db, *, correo, rut):
    usuario = Usuario(
        correo=correo, password="hash-a3", rol="estudiante",
        nombre="Estudiante Test A3", rut=rut, activo=True,
    )
    db.add(usuario)
    db.flush()
    return usuario


def _cita(db, *, estudiante_id, profesional_id, fecha, hora, estado="pendiente"):
    cita = Cita(
        estudiante_id=estudiante_id, profesional_id=profesional_id,
        fecha=fecha, hora=hora, estado=estado,
    )
    db.add(cita)
    db.flush()
    return cita


def _current_user_estudiante(est):
    return {"id": est.id, "rol": "estudiante"}


def _monkeypatch_admin_institucional(monkeypatch, modulo):
    """Alcance institucional total — usado para citas.py (que además
    resuelve permiso vía tiene_permiso_efectivo) y para admin.py (que
    solo llama a obtener_alcance_administrativo_efectivo dentro de
    crear_cita_urgente; el permiso en sí se resuelve como dependencia
    de FastAPI, fuera del cuerpo de la función, y no se ejecuta al
    llamarla directamente como en estos tests)."""
    if hasattr(modulo, "tiene_permiso_efectivo"):
        monkeypatch.setattr(modulo, "tiene_permiso_efectivo", lambda db, u, p: True)
    monkeypatch.setattr(
        modulo,
        "obtener_alcance_administrativo_efectivo",
        lambda db, u: AlcanceAdministrativoEfectivo(
            institucional=True, especialidades_normalizadas=frozenset(),
        ),
    )


# ══════════════════════════════════════════════════════════
# adquirir_lock_agenda_profesional_fecha() — estrategia por dialecto
# ══════════════════════════════════════════════════════════

def test_lock_postgresql_ejecuta_advisory_lock_con_claves_int4_correctas():
    """key1 = profesional_id, key2 = fecha como YYYYMMDD — sin hash()
    de Python ni hashtext()."""
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"

    adquirir_lock_agenda_profesional_fecha(db, profesional_id=42, fecha="2026-09-11")

    assert db.execute.called
    sql_arg, params_arg = db.execute.call_args[0]
    assert "pg_advisory_xact_lock" in str(sql_arg)
    assert params_arg == {"key1": 42, "key2": 20260911}


def test_lock_postgresql_fecha_invalida_usa_key2_cero_sin_reventar():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"

    adquirir_lock_agenda_profesional_fecha(db, profesional_id=7, fecha="no-es-una-fecha")

    _, params_arg = db.execute.call_args[0]
    assert params_arg == {"key1": 7, "key2": 0}


def test_lock_postgresql_no_normaliza_fecha_invalida_a_una_fecha_real():
    """Regresión explícita pedida: el helper del lock NUNCA debe
    intentar "adivinar"/normalizar una fecha inválida a una fecha real
    (p. ej. la de hoy) solo para poder construir la clave — eso
    ocultaría el error en vez de dejar que la validación normal de
    fecha (evaluar_disponibilidad_slot -> motivo "fecha_invalida") lo
    reporte. Cualquier fecha no parseable debe mapear siempre al mismo
    key2=0, sin importar cuál sea el string inválido ni la fecha real
    de hoy."""
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"

    for fecha_invalida in ("", "no-es-una-fecha", "2026/09/11", "2026-13-40", "hoy"):
        db.execute.reset_mock()
        adquirir_lock_agenda_profesional_fecha(db, profesional_id=1, fecha=fecha_invalida)
        _, params_arg = db.execute.call_args[0]
        assert params_arg["key2"] == 0, f"fecha={fecha_invalida!r} no debe generar otra key2"


def test_lock_sqlite_fecha_invalida_no_lanza_ni_ejecuta_sql():
    """Mismo caso que el anterior pero bajo el dialecto no-op: una
    fecha inválida tampoco debe intentar ejecutar SQL en SQLite, y
    sobre todo NO debe transformarse en un 500 — ver
    test_crear_cita_fecha_invalida_conserva_codigo_400_sin_convertirse_en_500
    para el mismo contrato a través del endpoint completo."""
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "sqlite"

    adquirir_lock_agenda_profesional_fecha(db, profesional_id=1, fecha="no-es-una-fecha")

    db.execute.assert_not_called()


def test_lock_real_sobre_sqlite_con_fecha_invalida_no_lanza(db_session):
    """Igual que test_lock_real_sobre_sqlite_de_test_no_lanza, pero con
    una fecha inválida — contra el motor SQLite real (no un mock)."""
    adquirir_lock_agenda_profesional_fecha(
        db_session, profesional_id=1, fecha="no-es-una-fecha",
    )


def test_lock_sqlite_es_no_op_explicito():
    """SQLite no ofrece la garantía real (ver docstring) — no debe
    intentar ejecutar SQL de PostgreSQL."""
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "sqlite"

    adquirir_lock_agenda_profesional_fecha(db, profesional_id=1, fecha="2026-09-11")

    db.execute.assert_not_called()


def test_lock_dialecto_desconocido_falla_explicitamente():
    """Nunca asumir en silencio que existe protección en un motor no
    contemplado — debe fallar ruidosamente, no ejecutar nada."""
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "mysql"

    with pytest.raises(RuntimeError):
        adquirir_lock_agenda_profesional_fecha(db, profesional_id=1, fecha="2026-09-11")

    db.execute.assert_not_called()


def test_lock_real_sobre_sqlite_de_test_no_lanza(db_session):
    """Integración mínima: contra el motor SQLite real que usan los
    tests (no un mock), adquirir el lock no debe lanzar ninguna
    excepción — es el no-op documentado."""
    adquirir_lock_agenda_profesional_fecha(
        db_session, profesional_id=1, fecha=_dia_habil_futuro(),
    )


# ══════════════════════════════════════════════════════════
# POST /citas — orden lock → re-evaluación, y 409 en conflicto
# ══════════════════════════════════════════════════════════

def test_crear_cita_adquiere_lock_antes_de_reevaluar_disponibilidad(db_session, monkeypatch):
    """Orden obligatorio de A.3: evaluar antes del lock y confiar en
    que el resultado siga vigente es exactamente la carrera que A.3
    existe para cerrar."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session)
    est = _estudiante(db_session, correo="orden-a3@sesaes.cl", rut="a3-1")
    db_session.commit()

    orden = []

    def fake_lock(db, *, profesional_id, fecha):
        orden.append("lock")

    def fake_evaluar(db, *, profesional_id, fecha, hora):
        orden.append("evaluar")
        return ResultadoDisponibilidad(
            disponible=True, motivo=None, mensaje=None,
            overridable_con_sobrecupo=False, profesional=prof,
        )

    monkeypatch.setattr(citas, "adquirir_lock_agenda_profesional_fecha", fake_lock)
    monkeypatch.setattr(citas, "evaluar_disponibilidad_slot", fake_evaluar)

    payload = CitaCreate(
        estudiante_id=est.id, profesional_id=prof.id, fecha=fecha, hora="09:30",
    )
    citas.crear_cita(cita=payload, db=db_session, current_user=_current_user_estudiante(est))

    assert orden == ["lock", "evaluar"]


def test_crear_cita_fecha_invalida_conserva_codigo_400_sin_convertirse_en_500(db_session):
    """Regresión explícita pedida junto con A.3: una `fecha` inválida
    debe seguir respondiendo exactamente igual que antes de A.3 —
    evaluar_disponibilidad_slot() ya devolvía motivo="fecha_invalida"
    (no overridable) desde A.2A, y eso sigue mapeando a 400 (el mismo
    "else 400" que todos los motivos que no son slot_ocupado; ver
    citas.py). El lock (adquirir_lock_agenda_profesional_fecha, que
    ahora se adquiere ANTES de esta evaluación) no debe alterar este
    resultado ni convertirlo en un 500 — su propio fallback interno
    (key2=0 para fecha no parseable, ver tests de la sección de
    arriba) existe precisamente para que una fecha inválida no rompa
    la adquisición del lock antes de que evaluar_disponibilidad_slot
    llegue a reportarla con su motivo real."""
    prof = _profesional(db_session)
    est = _estudiante(db_session, correo="fecha-invalida-a3@sesaes.cl", rut="a3-fecha-1")
    db_session.commit()

    payload = CitaCreate(
        estudiante_id=est.id, profesional_id=prof.id,
        fecha="no-es-una-fecha", hora="09:30",
    )

    with pytest.raises(HTTPException) as exc:
        citas.crear_cita(cita=payload, db=db_session, current_user=_current_user_estudiante(est))

    assert exc.value.status_code == 400
    assert exc.value.status_code != 500
    assert db_session.query(Cita).count() == 0


def test_crear_cita_conflicto_secuencial_responde_409_no_sobrecupo(db_session):
    """Sin ninguna carrera real (ambas peticiones secuenciales, no
    concurrentes): la segunda sigue viendo el slot ocupado tras la
    re-evaluación bajo lock, y debe recibir 409 — nunca insertarse
    como sobrecupo automático."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    ocupante = _estudiante(db_session, correo="ocupante-409@sesaes.cl", rut="a3-2")
    perdedor = _estudiante(db_session, correo="perdedor-409@sesaes.cl", rut="a3-3")
    _cita(db_session, estudiante_id=ocupante.id, profesional_id=prof.id, fecha=fecha, hora="11:00")
    db_session.commit()

    payload = CitaCreate(
        estudiante_id=perdedor.id, profesional_id=prof.id, fecha=fecha, hora="11:15",
    )

    with pytest.raises(HTTPException) as exc:
        citas.crear_cita(
            cita=payload, db=db_session,
            current_user=_current_user_estudiante(perdedor),
        )

    assert exc.value.status_code == 409
    creadas = db_session.query(Cita).all()
    assert len(creadas) == 1
    assert creadas[0].estudiante_id == ocupante.id  # ninguna cita nueva, ni sobrecupo


# ══════════════════════════════════════════════════════════
# Estados que ocupan (regresión explícita bajo el flujo con lock)
# ══════════════════════════════════════════════════════════

def test_cita_cancelada_no_bloquea_bajo_flujo_con_lock(db_session):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="cancelada-a3@sesaes.cl", rut="a3-4")
    nuevo = _estudiante(db_session, correo="nuevo-cancelada-a3@sesaes.cl", rut="a3-5")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="11:00", estado="cancelada")
    db_session.commit()

    payload = CitaCreate(estudiante_id=nuevo.id, profesional_id=prof.id, fecha=fecha, hora="11:15")
    resultado = citas.crear_cita(cita=payload, db=db_session, current_user=_current_user_estudiante(nuevo))

    assert resultado["estado"] == "pendiente"
    assert db_session.query(Cita).count() == 2


def test_cita_inasistencia_no_bloquea_bajo_flujo_con_lock(db_session):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="inasistencia-a3@sesaes.cl", rut="a3-6")
    nuevo = _estudiante(db_session, correo="nuevo-inasistencia-a3@sesaes.cl", rut="a3-7")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="11:00", estado="inasistencia")
    db_session.commit()

    payload = CitaCreate(estudiante_id=nuevo.id, profesional_id=prof.id, fecha=fecha, hora="11:15")
    resultado = citas.crear_cita(cita=payload, db=db_session, current_user=_current_user_estudiante(nuevo))

    assert resultado["estado"] == "pendiente"
    assert db_session.query(Cita).count() == 2


def test_cita_completada_bloquea_bajo_flujo_con_lock(db_session):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="completada-a3@sesaes.cl", rut="a3-8")
    nuevo = _estudiante(db_session, correo="nuevo-completada-a3@sesaes.cl", rut="a3-9")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="11:00", estado="completada")
    db_session.commit()

    payload = CitaCreate(estudiante_id=nuevo.id, profesional_id=prof.id, fecha=fecha, hora="11:15")

    with pytest.raises(HTTPException) as exc:
        citas.crear_cita(cita=payload, db=db_session, current_user=_current_user_estudiante(nuevo))

    assert exc.value.status_code == 409
    assert db_session.query(Cita).count() == 1


def test_cita_pendiente_bloquea_bajo_flujo_con_lock(db_session):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="pendiente-a3@sesaes.cl", rut="a3-10")
    nuevo = _estudiante(db_session, correo="nuevo-pendiente-a3@sesaes.cl", rut="a3-11")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="11:00", estado="pendiente")
    db_session.commit()

    payload = CitaCreate(estudiante_id=nuevo.id, profesional_id=prof.id, fecha=fecha, hora="11:15")

    with pytest.raises(HTTPException) as exc:
        citas.crear_cita(cita=payload, db=db_session, current_user=_current_user_estudiante(nuevo))

    assert exc.value.status_code == 409
    assert db_session.query(Cita).count() == 1


def test_solapamiento_parcial_por_duracion_bloquea_bajo_flujo_con_lock(db_session):
    """existente 11:00–11:45, nueva 10:30–11:15 (duración 45): mismo
    ejemplo de A.2C, ahora a través del flujo completo con lock."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="parcial-a3@sesaes.cl", rut="a3-12")
    nuevo = _estudiante(db_session, correo="nuevo-parcial-a3@sesaes.cl", rut="a3-13")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="11:00")
    db_session.commit()

    payload = CitaCreate(estudiante_id=nuevo.id, profesional_id=prof.id, fecha=fecha, hora="10:30")

    with pytest.raises(HTTPException) as exc:
        citas.crear_cita(cita=payload, db=db_session, current_user=_current_user_estudiante(nuevo))

    assert exc.value.status_code == 409
    assert db_session.query(Cita).count() == 1


# ══════════════════════════════════════════════════════════
# hay_solapamiento_con_cita_activa() — unidad, sin pasar por routers
# ══════════════════════════════════════════════════════════

def test_hay_solapamiento_ignora_cancelada_e_inasistencia(db_session):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="solap-cancel@sesaes.cl", rut="a3-14")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="10:00", estado="cancelada")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="11:00", estado="inasistencia")
    db_session.commit()

    assert hay_solapamiento_con_cita_activa(
        db_session, profesional=prof, fecha=fecha, hora="10:00",
    ) is False
    assert hay_solapamiento_con_cita_activa(
        db_session, profesional=prof, fecha=fecha, hora="11:00",
    ) is False


def test_hay_solapamiento_detecta_pendiente_y_completada(db_session):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="solap-activa@sesaes.cl", rut="a3-15")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="10:00", estado="pendiente")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="14:00", estado="completada")
    db_session.commit()

    assert hay_solapamiento_con_cita_activa(
        db_session, profesional=prof, fecha=fecha, hora="10:00",
    ) is True
    assert hay_solapamiento_con_cita_activa(
        db_session, profesional=prof, fecha=fecha, hora="14:00",
    ) is True


def test_hay_solapamiento_detecta_intervalo_parcial(db_session):
    """existente 10:00–10:45, consulta 09:30–10:15: se solapan aunque
    las horas de inicio sean distintas."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="solap-parcial@sesaes.cl", rut="a3-16")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha, hora="10:00")
    db_session.commit()

    assert hay_solapamiento_con_cita_activa(
        db_session, profesional=prof, fecha=fecha, hora="09:30",
    ) is True
    # Adyacente (termina justo cuando empieza la existente): no solapa.
    assert hay_solapamiento_con_cita_activa(
        db_session, profesional=prof, fecha=fecha, hora="09:15",
    ) is False


def test_hay_solapamiento_hora_invalida_lanza_slot_invalido_no_false(db_session):
    """A.3 (v2) — corrección de fail-open: antes esta función devolvía
    False ante una hora no parseable ("no hay solapamiento"), lo cual
    es peligroso para urgente (no pasa por evaluar_disponibilidad_slot,
    no hay otra red de validación de formato aguas arriba). Ahora debe
    lanzar SlotInvalidoError explícitamente — nunca un booleano para
    input inválido."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    db_session.commit()

    with pytest.raises(SlotInvalidoError):
        hay_solapamiento_con_cita_activa(
            db_session, profesional=prof, fecha=fecha, hora="no-es-una-hora",
        )


def test_hay_solapamiento_fecha_invalida_lanza_slot_invalido_no_false(db_session):
    """Misma corrección, para `fecha` — tampoco debe resolverse como
    False."""
    prof = _profesional(db_session, duracion_min=45)
    db_session.commit()

    with pytest.raises(SlotInvalidoError):
        hay_solapamiento_con_cita_activa(
            db_session, profesional=prof, fecha="no-es-una-fecha", hora="09:30",
        )


def test_hay_solapamiento_canonicaliza_fecha_antes_de_consultar(db_session):
    """A.3 (v2) — "2026-9-1" y "2026-09-01" son la MISMA fecha para
    _parsear_fecha (strptime acepta meses/días sin cero de relleno),
    pero son strings distintos en la columna String `Cita.fecha`. Si
    se consultara con el string crudo en vez de
    fecha_obj.isoformat(), una cita guardada en forma canónica
    ("2026-09-01") no se encontraría al pedir la hora con
    "2026-9-1" — un falso "no hay solapamiento"."""
    fecha_canonica = "2026-09-01"
    fecha_alternativa = "2026-9-1"  # misma fecha, sin cero de relleno
    assert fecha_canonica != fecha_alternativa  # strings distintos, misma fecha real

    prof = _profesional(db_session, duracion_min=45)
    otro = _estudiante(db_session, correo="canon-fecha@sesaes.cl", rut="a3-canon-1")
    _cita(db_session, estudiante_id=otro.id, profesional_id=prof.id, fecha=fecha_canonica, hora="10:00")
    db_session.commit()

    assert hay_solapamiento_con_cita_activa(
        db_session, profesional=prof, fecha=fecha_alternativa, hora="10:00",
    ) is True


# ══════════════════════════════════════════════════════════
# POST /admin/citas/urgente — hueco cerrado por A.3
# ══════════════════════════════════════════════════════════

def test_urgente_adquiere_lock_antes_de_comprobar_solapamiento(db_session, monkeypatch):
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session)
    est = _estudiante(db_session, correo="urgente-orden@sesaes.cl", rut="a3-17")
    db_session.commit()

    orden = []
    monkeypatch.setattr(
        admin, "adquirir_lock_agenda_profesional_fecha",
        lambda db, *, profesional_id, fecha: orden.append("lock"),
    )

    def fake_solapamiento(db, *, profesional, fecha, hora):
        orden.append("solapamiento")
        return False

    monkeypatch.setattr(admin, "hay_solapamiento_con_cita_activa", fake_solapamiento)
    _monkeypatch_admin_institucional(monkeypatch, admin)

    payload = CitaCreate(estudiante_id=est.id, profesional_id=prof.id, fecha=fecha, hora="09:30")
    admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert orden == ["lock", "solapamiento"]


def test_urgente_no_puede_solapar_cita_activa(db_session, monkeypatch):
    """Hallazgo del diagnóstico de A.3: antes de este cambio,
    crear_cita_urgente() nunca comprobaba ocupación (ni siquiera
    secuencialmente). Ahora debe rechazar con 409."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    ocupante = _estudiante(db_session, correo="urgente-ocupante@sesaes.cl", rut="a3-18")
    est_urgencia = _estudiante(db_session, correo="urgente-nuevo@sesaes.cl", rut="a3-19")
    _cita(db_session, estudiante_id=ocupante.id, profesional_id=prof.id, fecha=fecha, hora="10:00")
    db_session.commit()

    _monkeypatch_admin_institucional(monkeypatch, admin)

    payload = CitaCreate(
        estudiante_id=est_urgencia.id, profesional_id=prof.id, fecha=fecha, hora="10:00",
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert exc.value.status_code == 409
    assert db_session.query(Cita).count() == 1


def test_urgente_no_transforma_conflicto_en_sobrecupo(db_session, monkeypatch):
    """El conflicto detectado por urgente nunca debe insertarse como
    sobrecupo=True automático — de hecho crear_cita_urgente() ni
    siquiera lee cita.sobrecupo. Verificamos que, tras el 409, no
    exista ninguna fila nueva (con o sin sobrecupo)."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session, duracion_min=45)
    ocupante = _estudiante(db_session, correo="urgente-sobrecupo-ocupante@sesaes.cl", rut="a3-20")
    est_urgencia = _estudiante(db_session, correo="urgente-sobrecupo-nuevo@sesaes.cl", rut="a3-21")
    _cita(db_session, estudiante_id=ocupante.id, profesional_id=prof.id, fecha=fecha, hora="10:00")
    db_session.commit()

    _monkeypatch_admin_institucional(monkeypatch, admin)

    payload = CitaCreate(
        estudiante_id=est_urgencia.id, profesional_id=prof.id, fecha=fecha, hora="10:15",
        sobrecupo=True,  # ignorado por este endpoint; no debe colarse
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert exc.value.status_code == 409
    citas_bd = db_session.query(Cita).all()
    assert len(citas_bd) == 1
    assert citas_bd[0].sobrecupo is False


def test_urgente_hora_invalida_responde_400_no_inserta_nunca_500(db_session, monkeypatch):
    """A.3 (v2) — regresión explícita pedida: una `hora` no
    interpretable en POST /admin/citas/urgente debe responder 400
    (dato inválido), NUNCA 500, y NUNCA insertar la cita. Antes de esta
    corrección, hay_solapamiento_con_cita_activa() devolvía False ante
    una hora inválida ("no hay solapamiento"), y crear_cita_urgente()
    habría insertado la cita igual — fail-open real, porque este
    endpoint no pasa por evaluar_disponibilidad_slot()."""
    fecha = _dia_habil_futuro()
    prof = _profesional(db_session)
    est = _estudiante(db_session, correo="urgente-hora-invalida@sesaes.cl", rut="a3-23")
    db_session.commit()

    _monkeypatch_admin_institucional(monkeypatch, admin)

    payload = CitaCreate(
        estudiante_id=est.id, profesional_id=prof.id, fecha=fecha, hora="no-es-una-hora",
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert exc.value.status_code == 400
    assert exc.value.status_code != 500
    assert db_session.query(Cita).count() == 0


def test_urgente_fecha_invalida_responde_400_no_inserta_nunca_500(db_session, monkeypatch):
    """Misma regresión que la anterior, para `fecha` inválida."""
    prof = _profesional(db_session)
    est = _estudiante(db_session, correo="urgente-fecha-invalida@sesaes.cl", rut="a3-24")
    db_session.commit()

    _monkeypatch_admin_institucional(monkeypatch, admin)

    payload = CitaCreate(
        estudiante_id=est.id, profesional_id=prof.id, fecha="no-es-una-fecha", hora="09:30",
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert exc.value.status_code == 400
    assert exc.value.status_code != 500
    assert db_session.query(Cita).count() == 0


def test_urgente_conserva_semantica_de_jornada_colacion_sin_evaluar_disponibilidad_slot(db_session, monkeypatch):
    """A.3 NO amplía la decisión histórica de A.2: urgente sigue sin
    llamar a evaluar_disponibilidad_slot() (no evalúa jornada, colación,
    grilla ni cierre de centro) — solo se protege de solapar una cita
    ACTIVA. Fuera de jornada, sin ocupación real, debe seguir
    aceptándose exactamente igual que antes de A.3."""
    fecha = _dia_habil_futuro()
    # Jornada 09:00–13:00 — 20:00 está fuera de cualquier jornada real,
    # y ni siquiera pertenece a la grilla del centro (cierra a 18:00).
    prof = _profesional(db_session, horario_inicio="09:00", horario_fin="13:00")
    est = _estudiante(db_session, correo="urgente-legacy@sesaes.cl", rut="a3-22")
    db_session.commit()

    llamo_evaluar_disponibilidad = {"valor": False}

    def _fake_evaluar(*args, **kwargs):
        llamo_evaluar_disponibilidad["valor"] = True
        return evaluar_disponibilidad_slot(*args, **kwargs)

    # evaluar_disponibilidad_slot no está importado en admin.py; este
    # monkeypatch solo confirma que, si alguna vez se importara, no se
    # está llamando — lo dejamos como guard adicional sin afectar el
    # resultado si no existe el atributo.
    if hasattr(admin, "evaluar_disponibilidad_slot"):
        monkeypatch.setattr(admin, "evaluar_disponibilidad_slot", _fake_evaluar)

    _monkeypatch_admin_institucional(monkeypatch, admin)

    payload = CitaCreate(estudiante_id=est.id, profesional_id=prof.id, fecha=fecha, hora="20:00")
    resultado = admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert resultado["estado"] == "pendiente"
    assert llamo_evaluar_disponibilidad["valor"] is False
    assert db_session.query(Cita).count() == 1


# ══════════════════════════════════════════════════════════
# A.3 (v3) — hueco de canonicalización: DiaCerrado/lock/consulta de
# ocupación ya canonicalizaban internamente, pero ambos routers seguían
# guardando Cita.fecha con el string crudo de entrada. Ver
# canonicalizar_fecha_valida() en agenda_disponibilidad_service.py.
# ══════════════════════════════════════════════════════════

def _fecha_sin_ceros(fecha_iso: str) -> str:
    """Misma fecha real que `fecha_iso` ("YYYY-MM-DD"), pero escrita
    sin ceros de relleno en mes/día (p. ej. "2026-09-01" ->
    "2026-9-1") — la variante que _parsear_fecha acepta vía strptime y
    que antes de A.3 (v3) podía guardarse tal cual en Cita.fecha."""
    anio, mes, dia = fecha_iso.split("-")
    return f"{int(anio)}-{int(mes)}-{int(dia)}"


def test_crear_cita_guarda_fecha_canonica_aunque_llegue_sin_ceros(db_session):
    """1. POST /citas con "2026-9-1" (o cualquier fecha válida sin
    ceros de relleno) debe guardar Cita.fecha ya canonicalizada
    ("2026-09-01"), nunca el string crudo de entrada — es la MISMA
    forma que ya usan DiaCerrado, el lock y
    evaluar_disponibilidad_slot."""
    fecha_canonica = _dia_habil_futuro()
    fecha_cruda = _fecha_sin_ceros(fecha_canonica)
    assert fecha_cruda != fecha_canonica  # strings distintos, misma fecha real

    prof = _profesional(db_session, duracion_min=45)
    est = _estudiante(db_session, correo="canon-citas@sesaes.cl", rut="a3-canon-citas")
    db_session.commit()

    payload = CitaCreate(estudiante_id=est.id, profesional_id=prof.id, fecha=fecha_cruda, hora="09:00")
    resultado = citas.crear_cita(cita=payload, db=db_session, current_user=_current_user_estudiante(est))

    assert resultado["fecha"] == fecha_canonica
    guardada = db_session.query(Cita).one()
    assert guardada.fecha == fecha_canonica


def test_urgente_guarda_fecha_canonica_aunque_llegue_sin_ceros(db_session, monkeypatch):
    """2. POST /admin/citas/urgente con "2026-9-1" también debe guardar
    la fecha canónica, no el string crudo — mismo hueco que el punto
    anterior, en el otro canal de creación de citas."""
    fecha_canonica = _dia_habil_futuro()
    fecha_cruda = _fecha_sin_ceros(fecha_canonica)

    prof = _profesional(db_session, duracion_min=45)
    est = _estudiante(db_session, correo="canon-urgente@sesaes.cl", rut="a3-canon-urgente")
    db_session.commit()

    _monkeypatch_admin_institucional(monkeypatch, admin)

    payload = CitaCreate(estudiante_id=est.id, profesional_id=prof.id, fecha=fecha_cruda, hora="09:30")
    resultado = admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert resultado["estado"] == "pendiente"
    guardada = db_session.query(Cita).one()
    assert guardada.fecha == fecha_canonica


def test_urgente_dia_cerrado_canonico_bloquea_tambien_fecha_sin_ceros(db_session, monkeypatch):
    """3. Un DiaCerrado("2026-09-01") guardado en su forma canónica
    debe bloquear también una petición de urgente escrita como
    "2026-9-1" — antes de canonicalizar, la consulta de DiaCerrado en
    crear_cita_urgente() comparaba contra el string crudo y podía no
    encontrar el día cerrado real."""
    fecha_canonica = _dia_habil_futuro()
    fecha_cruda = _fecha_sin_ceros(fecha_canonica)

    prof = _profesional(db_session, duracion_min=45)
    est = _estudiante(db_session, correo="canon-diacerrado@sesaes.cl", rut="a3-canon-cerrado")
    db_session.add(DiaCerrado(fecha=fecha_canonica, motivo="Feriado de prueba", creado_por=1))
    db_session.commit()

    _monkeypatch_admin_institucional(monkeypatch, admin)

    payload = CitaCreate(estudiante_id=est.id, profesional_id=prof.id, fecha=fecha_cruda, hora="09:30")

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert exc.value.status_code == 400
    assert db_session.query(Cita).count() == 0


def test_helper_canonicalizar_fecha_valida_lanza_slot_invalido_para_fecha_no_interpretable():
    """canonicalizar_fecha_valida() nunca normaliza en silencio una
    fecha no interpretable (p. ej. a la fecha de hoy): debe lanzar
    SlotInvalidoError, para que quien llama la traduzca a 400 y no
    continúe."""
    with pytest.raises(SlotInvalidoError):
        canonicalizar_fecha_valida("no-es-una-fecha")


def test_helper_canonicalizar_fecha_valida_devuelve_forma_canonica():
    assert canonicalizar_fecha_valida("2026-9-1") == "2026-09-01"
    assert canonicalizar_fecha_valida("2026-09-01") == "2026-09-01"


# ══════════════════════════════════════════════════════════
# A.3 (v3) — precedencia RBAC: la canonicalización de fecha NUNCA debe
# adelantarse a una decisión de autorización ya existente. Un actor sin
# permiso/ownership debe seguir viendo 403 (o el 403 propio de
# alcance=None en urgente), incluso si además envía una fecha
# inválida — el orden exigido es
# autenticación/ownership/permiso-efectivo -> validación/canonicalización
# -> queries operativas, nunca al revés.
# ══════════════════════════════════════════════════════════

def test_crear_cita_actor_no_autorizado_es_rechazado_por_403_no_por_fecha(db_session):
    """POST /citas: un estudiante que intenta agendar para OTRO
    estudiante (sin agenda.gestionar) debe seguir recibiendo 403 por
    ownership, aunque la fecha del payload sea inválida. La
    canonicalización de A.3 (v3) no debe ejecutarse (ni fallar) antes
    de que _verificar_propietario_o_agenda() rechace el acceso."""
    dueno = _estudiante(db_session, correo="rbac-dueno@sesaes.cl", rut="a3-rbac-1")
    intruso = _estudiante(db_session, correo="rbac-intruso@sesaes.cl", rut="a3-rbac-2")
    prof = _profesional(db_session)
    db_session.commit()

    payload = CitaCreate(
        estudiante_id=dueno.id, profesional_id=prof.id,
        fecha="no-es-una-fecha", hora="09:30",
    )

    with pytest.raises(HTTPException) as exc:
        citas.crear_cita(
            cita=payload, db=db_session,
            current_user=_current_user_estudiante(intruso),
        )

    assert exc.value.status_code == 403
    assert db_session.query(Cita).count() == 0


def test_urgente_sin_alcance_es_rechazado_por_403_no_por_fecha(db_session, monkeypatch):
    """POST /admin/citas/urgente: si obtener_alcance_administrativo_efectivo()
    devuelve None (sin acceso al alcance solicitado), debe seguir
    respondiendo 403 aunque la fecha del payload sea inválida — el
    chequeo de alcance ocurre ANTES de canonicalizar_fecha_valida() en
    el cuerpo de la función (ver admin.py), y no debe alterarse ese
    orden."""
    prof = _profesional(db_session)
    est = _estudiante(db_session, correo="rbac-urgente@sesaes.cl", rut="a3-rbac-3")
    db_session.commit()

    monkeypatch.setattr(
        admin, "obtener_alcance_administrativo_efectivo",
        lambda db, u: None,
    )

    payload = CitaCreate(
        estudiante_id=est.id, profesional_id=prof.id,
        fecha="no-es-una-fecha", hora="09:30",
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_cita_urgente(cita=payload, db=db_session, current_user={"id": 999, "rol": "admin"})

    assert exc.value.status_code == 403
    assert db_session.query(Cita).count() == 0
