# -*- coding: utf-8 -*-
"""
SESAES — A.3: prueba de integración REAL contra PostgreSQL.

Los tests de test_a3_concurrencia.py corren contra SQLite (como el
resto del proyecto) y por eso el dialecto "sqlite" en
adquirir_lock_agenda_profesional_fecha() es un no-op explícito — SQLite
no ofrece la garantía transaccional que A.3 necesita, así que ningún
test SQLite puede probarla de verdad, por más que "pase".

Este archivo es la única prueba que ejercita el pg_advisory_xact_lock
REAL: dos conexiones/sesiones independientes, sincronizadas con una
barrera para maximizar la ventana de carrera, intentando reservar el
mismo profesional+fecha+hora (ver docstring del test para por qué el
mismo slot, y no dos horas distintas que se solapen, es el escenario
correcto para ejercitar la garantía TRANSACCIONAL bajo concurrencia
real). Se espera:
  - exactamente una operación exitosa;
  - exactamente una rechazada (motivo de ocupación, equivalente al 409
    que devolvería el endpoint HTTP);
  - al final, una sola cita activa ocupando ese intervalo.

Requiere una base PostgreSQL de test real, indicada en la variable de
entorno TEST_POSTGRES_URL (p. ej.
"postgresql+psycopg2://user:pass@localhost:5432/sesaes_test"). Si no
está definida, o si no se puede conectar, el test se salta
explícitamente (@pytest.mark.postgres + skip) — NUNCA se simula ni se
da por buena la garantía sin haberla ejercitado contra Postgres real.

Cómo correrlo:
    TEST_POSTGRES_URL="postgresql+psycopg2://..." \
        pytest tests/test_a3_concurrencia_postgres.py -m postgres -q

No se registró la marca "postgres" en un pytest.ini propio (el
proyecto no tiene ninguno) — sin --strict-markers esto solo emite un
PytestUnknownMarkWarning, no falla la suite; se deja como nota para
quien agregue tooling de configuración de pytest más adelante.
"""

from __future__ import annotations

import os
import threading
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.postgres

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

if not TEST_POSTGRES_URL:
    pytest.skip(
        "A.3: TEST_POSTGRES_URL no está definida — la garantía "
        "transaccional real de pg_advisory_xact_lock NO se validó "
        "contra PostgreSQL en esta ejecución. Los tests SQLite de "
        "test_a3_concurrencia.py solo prueban el contrato de la "
        "función (qué SQL construye, en qué orden se llama), no la "
        "concurrencia real. Define TEST_POSTGRES_URL apuntando a un "
        "Postgres de test para ejercitar esta garantía.",
        allow_module_level=True,
    )

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

from app.database import Base
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import admin, citas
from app.schemas import CitaCreate
from app.services.agenda_disponibilidad_service import (
    adquirir_lock_agenda_profesional_fecha,
    canonicalizar_fecha_valida,
    evaluar_disponibilidad_slot,
)


def _fecha_sin_ceros(fecha_iso: str) -> str:
    """Misma fecha real que `fecha_iso` ("YYYY-MM-DD"), pero escrita
    sin ceros de relleno en mes/día (p. ej. "2026-09-01" ->
    "2026-9-1") — la variante que _parsear_fecha acepta vía strptime y
    que antes de A.3 (v3) podía tomar un advisory lock/consultar
    ocupación con una clave distinta a la de la forma canónica."""
    anio, mes, dia = fecha_iso.split("-")
    return f"{int(anio)}-{int(mes)}-{int(dia)}"


def _dia_habil_futuro(dias_calendario: int = 1) -> str:
    fecha = date.today() + timedelta(days=dias_calendario)
    while fecha.weekday() >= 5:
        fecha += timedelta(days=1)
    return fecha.isoformat()


@pytest.fixture(scope="module")
def engine_postgres():
    try:
        engine = create_engine(TEST_POSTGRES_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depende del entorno
        pytest.skip(
            f"A.3: no se pudo conectar a TEST_POSTGRES_URL ({exc!r}). "
            f"La garantía transaccional real quedó sin validar en esta "
            f"ejecución — no se simula el resultado."
        )
        return
    assert engine.dialect.name == "postgresql", (
        "TEST_POSTGRES_URL no apunta a un dialecto postgresql; este "
        "test existe específicamente para ejercitar "
        "pg_advisory_xact_lock real, no para correr sobre otro motor."
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def datos_base(engine_postgres):
    """Profesional + 2 estudiantes + 1 actor administrativo real
    (Usuario.rol == "superadmin") de este test run, limpiados al final
    (best-effort) para no ensuciar la base de test entre corridas.

    A.3 (v3) — corrección de identidad: el actor administrativo del
    canal /admin/citas/urgente debe ser una fila Usuario real cuyo rol
    en BD coincida con el rol del `current_user` que se le pasa al
    router (rol="superadmin" en ambos lados) — nunca el id de un
    estudiante de prueba con un rol fabricado en el dict que no
    corresponde a su fila real."""
    SessionLocal = sessionmaker(bind=engine_postgres, autoflush=False, autocommit=False)
    setup = SessionLocal()
    sufijo = threading.get_ident()  # solo para correos únicos por corrida
    prof = Profesional(
        nombre="A3 Postgres IT", especialidad="Nutrición", iniciales="A3",
        estado="activo", horario_inicio="09:00", horario_fin="17:00",
        duracion_min=45,
    )
    est_a = Usuario(
        correo=f"a3-postgres-a-{sufijo}@sesaes.cl", password="x",
        rol="estudiante", nombre="A3 A", rut=f"a3-pg-a-{sufijo}", activo=True,
    )
    est_b = Usuario(
        correo=f"a3-postgres-b-{sufijo}@sesaes.cl", password="x",
        rol="estudiante", nombre="A3 B", rut=f"a3-pg-b-{sufijo}", activo=True,
    )
    actor_superadmin = Usuario(
        correo=f"a3-postgres-superadmin-{sufijo}@sesaes.cl", password="x",
        rol="superadmin", nombre="A3 Superadmin", rut=f"a3-pg-sa-{sufijo}", activo=True,
    )
    setup.add_all([prof, est_a, est_b, actor_superadmin])
    setup.commit()
    setup.refresh(prof)
    setup.refresh(est_a)
    setup.refresh(est_b)
    setup.refresh(actor_superadmin)
    ids = {
        "profesional_id": prof.id,
        "estudiante_a_id": est_a.id,
        "estudiante_b_id": est_b.id,
        "actor_superadmin_id": actor_superadmin.id,
    }
    setup.close()

    yield ids

    limpieza = SessionLocal()
    try:
        limpieza.query(Cita).filter(Cita.profesional_id == ids["profesional_id"]).delete()
        limpieza.query(Profesional).filter(Profesional.id == ids["profesional_id"]).delete()
        limpieza.query(Usuario).filter(
            Usuario.id.in_([
                ids["estudiante_a_id"],
                ids["estudiante_b_id"],
                ids["actor_superadmin_id"],
            ])
        ).delete(synchronize_session=False)
        limpieza.commit()
    except Exception:
        limpieza.rollback()
    finally:
        limpieza.close()


def _intentar_reservar(
    *,
    engine,
    profesional_id: int,
    estudiante_id: int,
    fecha: str,
    hora: str,
    barrera: threading.Barrier,
    resultado: dict,
):
    """Réplica mínima, con las piezas REALES de A.3 (sin mockear nada),
    de la sección crítica de POST /citas: lock -> re-evaluar -> insertar
    si libre. Cada llamada usa su propia Session/conexión, como haría
    cada request HTTP real."""
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        barrera.wait(timeout=15)

        # 1. Lock — bloquea aquí si la otra sesión ya lo tiene para la
        #    misma (profesional_id, fecha); se libera solo al hacer
        #    commit/rollback de esa otra transacción.
        adquirir_lock_agenda_profesional_fecha(
            session, profesional_id=profesional_id, fecha=fecha,
        )

        # 2. Re-evaluación DENTRO del lock — para cuando la segunda
        #    sesión llega hasta acá, ya ve el commit de la primera.
        disponibilidad = evaluar_disponibilidad_slot(
            session, profesional_id=profesional_id, fecha=fecha, hora=hora,
        )

        if not disponibilidad.disponible:
            session.rollback()
            resultado.update(
                ok=False,
                status_equivalente=409 if disponibilidad.motivo == "slot_ocupado" else 400,
                motivo=disponibilidad.motivo,
            )
            return

        # 3. Insertar solo si sigue libre.
        nueva = Cita(
            estudiante_id=estudiante_id, profesional_id=profesional_id,
            fecha=fecha, hora=hora, estado="pendiente",
        )
        session.add(nueva)
        session.commit()  # 4. libera el lock
        resultado.update(ok=True, cita_id=nueva.id)
    except Exception as exc:  # pragma: no cover - diagnóstico de fallos reales
        session.rollback()
        resultado.update(ok=False, error=repr(exc))
    finally:
        session.close()


def test_dos_conexiones_concurrentes_al_mismo_slot_solo_una_gana(
    engine_postgres, datos_base,
):
    """A y B piden EXACTAMENTE el mismo profesional+fecha+hora,
    disparadas lo más simultáneamente posible con una barrera —
    ejemplo primario de A.3 (dos operaciones concurrentes sobre el
    mismo horario). Nota sobre por qué el mismo slot y no dos horas
    distintas que se solapen: con duracion_min fijo, dos horas de
    inicio DISTINTAS que ambas pertenezcan a la grilla real
    (evaluar_disponibilidad_slot exige que el inicio esté alineado a
    la grilla) nunca se solapan entre sí — la grilla parte el día en
    bloques exactos de esa duración. La superposición por duración con
    horas de inicio distintas (A.2C) ya se prueba de forma aislada,
    sin concurrencia real, en test_a3_concurrencia.py — acá lo que se
    ejercita es la garantía TRANSACCIONAL real (el advisory lock de
    PostgreSQL), para lo cual pedir el mismo slot es la carrera más
    directa y no requiere ningún atajo sobre la validación de grilla.

    Exactamente una debe ganar; la otra debe ver slot_ocupado
    (equivalente al 409 HTTP); al final debe existir una sola cita
    activa en ese horario."""
    fecha = _dia_habil_futuro()
    profesional_id = datos_base["profesional_id"]
    hora = "10:15"  # bloque real de la grilla (duracion_min=45 desde 08:00)

    barrera = threading.Barrier(2)
    resultado_a: dict = {}
    resultado_b: dict = {}

    hilo_a = threading.Thread(
        target=_intentar_reservar,
        kwargs=dict(
            engine=engine_postgres,
            profesional_id=profesional_id,
            estudiante_id=datos_base["estudiante_a_id"],
            fecha=fecha,
            hora=hora,
            barrera=barrera,
            resultado=resultado_a,
        ),
    )
    hilo_b = threading.Thread(
        target=_intentar_reservar,
        kwargs=dict(
            engine=engine_postgres,
            profesional_id=profesional_id,
            estudiante_id=datos_base["estudiante_b_id"],
            fecha=fecha,
            hora=hora,
            barrera=barrera,
            resultado=resultado_b,
        ),
    )

    hilo_a.start()
    hilo_b.start()
    hilo_a.join(timeout=30)
    hilo_b.join(timeout=30)

    assert not hilo_a.is_alive() and not hilo_b.is_alive(), (
        "Uno de los dos hilos no terminó — posible deadlock real del "
        "advisory lock, a diferenciar de una carrera resuelta."
    )

    resultados = [resultado_a, resultado_b]
    exitosas = [r for r in resultados if r.get("ok")]
    rechazadas = [r for r in resultados if not r.get("ok")]

    assert len(exitosas) == 1, f"se esperaba exactamente 1 éxito, se obtuvo: {resultados}"
    assert len(rechazadas) == 1, f"se esperaba exactamente 1 rechazo, se obtuvo: {resultados}"
    assert rechazadas[0].get("motivo") == "slot_ocupado"
    assert rechazadas[0].get("status_equivalente") == 409

    SessionLocal = sessionmaker(bind=engine_postgres, autoflush=False, autocommit=False)
    verificacion = SessionLocal()
    try:
        activas = (
            verificacion.query(Cita)
            .filter(
                Cita.profesional_id == profesional_id,
                Cita.fecha == fecha,
                Cita.estado.in_(("pendiente", "completada")),
            )
            .all()
        )
        assert len(activas) == 1, (
            f"debía quedar exactamente una cita activa ocupando el "
            f"intervalo, se encontraron {len(activas)}"
        )
    finally:
        verificacion.close()


# ══════════════════════════════════════════════════════════
# A.3 (v3) — misma carrera, pero A y B escriben la MISMA fecha real
# con DOS representaciones de string distintas ("2026-9-1" vs
# "2026-09-01"). Antes de la corrección de canonicalización, esto ya
# tomaba el MISMO advisory lock (adquirir_lock_agenda_profesional_
# fecha ya canonicalizaba internamente su clave), pero la fila
# insertada por el ganador podía quedar con el string CRUDO de
# entrada — dejando abierta la posibilidad de que una consulta
# posterior con la otra representación no la encontrara. Este test
# ejercita el flujo REAL de los routers (canonicalizar una vez,
# reutilizar para lock + re-evaluación + INSERT) contra PostgreSQL
# real, con dos sesiones/transacciones independientes.
# ══════════════════════════════════════════════════════════

def _intentar_reservar_v3(
    *,
    engine,
    profesional_id: int,
    estudiante_id: int,
    fecha: str,
    hora: str,
    barrera: threading.Barrier,
    resultado: dict,
):
    """Réplica mínima de la sección crítica YA CORREGIDA (A.3 v3) de
    los routers: canonicalizar_fecha_valida() UNA sola vez, y
    reutilizar esa misma forma canónica para el lock, la
    re-evaluación DENTRO del lock y el INSERT — nunca el string crudo
    de `fecha` recibido por parámetro."""
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        barrera.wait(timeout=15)

        fecha_canon = canonicalizar_fecha_valida(fecha)

        adquirir_lock_agenda_profesional_fecha(
            session, profesional_id=profesional_id, fecha=fecha_canon,
        )

        disponibilidad = evaluar_disponibilidad_slot(
            session, profesional_id=profesional_id, fecha=fecha_canon, hora=hora,
        )

        if not disponibilidad.disponible:
            session.rollback()
            resultado.update(
                ok=False,
                status_equivalente=409 if disponibilidad.motivo == "slot_ocupado" else 400,
                motivo=disponibilidad.motivo,
            )
            return

        nueva = Cita(
            estudiante_id=estudiante_id, profesional_id=profesional_id,
            fecha=fecha_canon, hora=hora, estado="pendiente",
        )
        session.add(nueva)
        session.commit()
        resultado.update(ok=True, cita_id=nueva.id, fecha_guardada=fecha_canon)
    except Exception as exc:  # pragma: no cover - diagnóstico de fallos reales
        session.rollback()
        resultado.update(ok=False, error=repr(exc))
    finally:
        session.close()


def test_dos_representaciones_de_fecha_mismo_slot_solo_una_gana(
    engine_postgres, datos_base,
):
    """A: fecha "2026-9-1" (sin ceros de relleno). B: fecha
    "2026-09-01" (forma canónica) — la MISMA fecha real. Mismo
    profesional, mismo slot, dos sesiones/transacciones
    independientes, disparadas lo más simultáneamente posible con una
    barrera. Ambas deben canonicalizar ANTES de construir la clave del
    advisory lock, así que deben tomar el MISMO lock. Se espera:
    exactamente 1 éxito, exactamente 1 conflicto (slot_ocupado,
    equivalente a 409), exactamente 1 cita activa al final, y esa fila
    con Cita.fecha almacenada en su forma canónica — nunca el string
    crudo con el que llegó cualquiera de las dos peticiones."""
    fecha_canonica = _dia_habil_futuro()
    fecha_sin_ceros = _fecha_sin_ceros(fecha_canonica)
    assert fecha_sin_ceros != fecha_canonica  # strings distintos, misma fecha real

    profesional_id = datos_base["profesional_id"]
    hora = "10:15"  # bloque real de la grilla (duracion_min=45 desde 08:00)

    barrera = threading.Barrier(2)
    resultado_a: dict = {}
    resultado_b: dict = {}

    hilo_a = threading.Thread(
        target=_intentar_reservar_v3,
        kwargs=dict(
            engine=engine_postgres,
            profesional_id=profesional_id,
            estudiante_id=datos_base["estudiante_a_id"],
            fecha=fecha_sin_ceros,
            hora=hora,
            barrera=barrera,
            resultado=resultado_a,
        ),
    )
    hilo_b = threading.Thread(
        target=_intentar_reservar_v3,
        kwargs=dict(
            engine=engine_postgres,
            profesional_id=profesional_id,
            estudiante_id=datos_base["estudiante_b_id"],
            fecha=fecha_canonica,
            hora=hora,
            barrera=barrera,
            resultado=resultado_b,
        ),
    )

    hilo_a.start()
    hilo_b.start()
    hilo_a.join(timeout=30)
    hilo_b.join(timeout=30)

    assert not hilo_a.is_alive() and not hilo_b.is_alive(), (
        "Uno de los dos hilos no terminó — posible deadlock real del "
        "advisory lock, a diferenciar de una carrera resuelta."
    )

    resultados = [resultado_a, resultado_b]
    exitosas = [r for r in resultados if r.get("ok")]
    rechazadas = [r for r in resultados if not r.get("ok")]

    assert len(exitosas) == 1, f"se esperaba exactamente 1 éxito, se obtuvo: {resultados}"
    assert len(rechazadas) == 1, f"se esperaba exactamente 1 rechazo, se obtuvo: {resultados}"
    assert rechazadas[0].get("motivo") == "slot_ocupado"
    assert rechazadas[0].get("status_equivalente") == 409
    assert exitosas[0].get("fecha_guardada") == fecha_canonica

    SessionLocal = sessionmaker(bind=engine_postgres, autoflush=False, autocommit=False)
    verificacion = SessionLocal()
    try:
        activas = (
            verificacion.query(Cita)
            .filter(
                Cita.profesional_id == profesional_id,
                Cita.fecha == fecha_canonica,
                Cita.hora == hora,
                Cita.estado.in_(("pendiente", "completada")),
            )
            .all()
        )
        assert len(activas) == 1, (
            f"debía quedar exactamente una cita activa ocupando ese "
            f"horario, se encontraron {len(activas)}"
        )
        assert activas[0].fecha == fecha_canonica, (
            "la fila ganadora debe quedar guardada con Cita.fecha "
            "canónico, sin importar con qué representación de fecha "
            "haya llegado la petición ganadora"
        )
    finally:
        verificacion.close()


# ══════════════════════════════════════════════════════════
# Cross-channel real: POST /citas (estudiante) vs.
# POST /admin/citas/urgente (admin), mismo profesional+fecha+slot.
# ══════════════════════════════════════════════════════════
#
# A diferencia del test anterior (que ejercita directamente
# adquirir_lock_agenda_profesional_fecha + evaluar_disponibilidad_slot,
# las mismas piezas que usan los routers), este invoca los routers
# REALES citas.crear_cita() y admin.crear_cita_urgente() sin mockear
# nada: ni RBAC ni alcance administrativo. Esto fue posible sin
# mocking desproporcionado gracias a que:
#   - el canal /citas usa un estudiante reservando para sí mismo
#     (ownership trivial, sin necesitar agenda.gestionar);
#   - el canal /admin/citas/urgente usa como actor un Usuario REAL con
#     rol="superadmin" en BD (ver `actor_superadmin_id` en
#     datos_base) — no el id de un estudiante de prueba con un rol
#     "superadmin" fabricado únicamente en el dict current_user. La
#     fila real y el current_user pasado al router representan la
#     MISMA identidad/rol; obtener_alcance_administrativo_efectivo()
#     ya otorga alcance institucional a rol="superadmin" por un camino
#     de código real y ya existente (ver
#     app/rbac/admin_authorization.py) a partir del rol declarado en
#     current_user — sin necesitar filas de AccesoAdministrativo ni
#     parchear el resolver de permisos. La dependencia de FastAPI
#     require_effective_permission(...) del endpoint urgente no se
#     ejecuta al llamar la función directamente (no vía HTTP), igual
#     que en los tests unitarios de routers ya existentes en el
#     proyecto (ver test_sa9_cita_urgente_alcance.py). El estudiante B
#     sigue siendo, en este test, únicamente el PACIENTE de la cita
#     urgente (payload_kwargs.estudiante_id) — nunca el actor.
# Si esto no hubiera sido posible sin mocks pesados, este test no se
# habría agregado — se habría reportado la limitación y conservado
# solo la combinación de unit tests de routers (test_a3_concurrencia.py)
# + esta integración real de un solo canal (test anterior).


def _worker_router_normal(engine, payload_kwargs, current_user, barrera, resultado):
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        barrera.wait(timeout=15)
        payload = CitaCreate(**payload_kwargs)
        respuesta = citas.crear_cita(cita=payload, db=session, current_user=current_user)
        resultado.update(ok=True, respuesta=respuesta)
    except HTTPException as exc:
        resultado.update(ok=False, status_equivalente=exc.status_code, detail=exc.detail)
    except Exception as exc:  # pragma: no cover - diagnóstico de fallos reales
        resultado.update(ok=False, error=repr(exc))
    finally:
        session.close()


def _worker_router_urgente(engine, payload_kwargs, current_user, barrera, resultado):
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        barrera.wait(timeout=15)
        payload = CitaCreate(**payload_kwargs)
        respuesta = admin.crear_cita_urgente(cita=payload, db=session, current_user=current_user)
        resultado.update(ok=True, respuesta=respuesta)
    except HTTPException as exc:
        resultado.update(ok=False, status_equivalente=exc.status_code, detail=exc.detail)
    except Exception as exc:  # pragma: no cover - diagnóstico de fallos reales
        resultado.update(ok=False, error=repr(exc))
    finally:
        session.close()


def test_cross_channel_citas_vs_urgente_mismo_slot_solo_uno_gana(
    engine_postgres, datos_base,
):
    """Operación A: POST /citas (estudiante reservando para sí mismo).
    Operación B: POST /admin/citas/urgente. Mismo profesional+fecha+
    hora, disparadas lo más simultáneamente posible con una barrera.
    Exactamente una debe quedar creada; la otra debe fallar con 409;
    al final debe existir una sola cita activa en ese horario."""
    fecha = _dia_habil_futuro()
    profesional_id = datos_base["profesional_id"]
    hora = "10:15"  # bloque real de la grilla (duracion_min=45 desde 08:00)

    barrera = threading.Barrier(2)
    resultado_normal: dict = {}
    resultado_urgente: dict = {}

    hilo_normal = threading.Thread(
        target=_worker_router_normal,
        kwargs=dict(
            engine=engine_postgres,
            payload_kwargs=dict(
                estudiante_id=datos_base["estudiante_a_id"],
                profesional_id=profesional_id,
                fecha=fecha,
                hora=hora,
            ),
            current_user={"id": datos_base["estudiante_a_id"], "rol": "estudiante"},
            barrera=barrera,
            resultado=resultado_normal,
        ),
    )
    hilo_urgente = threading.Thread(
        target=_worker_router_urgente,
        kwargs=dict(
            engine=engine_postgres,
            payload_kwargs=dict(
                estudiante_id=datos_base["estudiante_b_id"],
                profesional_id=profesional_id,
                fecha=fecha,
                hora=hora,
            ),
            current_user={"id": datos_base["actor_superadmin_id"], "rol": "superadmin"},
            barrera=barrera,
            resultado=resultado_urgente,
        ),
    )

    hilo_normal.start()
    hilo_urgente.start()
    hilo_normal.join(timeout=30)
    hilo_urgente.join(timeout=30)

    assert not hilo_normal.is_alive() and not hilo_urgente.is_alive(), (
        "uno de los dos hilos no terminó — posible deadlock real del "
        "advisory lock, a diferenciar de una carrera resuelta."
    )

    resultados = [resultado_normal, resultado_urgente]
    exitosas = [r for r in resultados if r.get("ok")]
    rechazadas = [r for r in resultados if not r.get("ok")]

    assert len(exitosas) == 1, f"se esperaba exactamente 1 éxito, se obtuvo: {resultados}"
    assert len(rechazadas) == 1, f"se esperaba exactamente 1 rechazo, se obtuvo: {resultados}"
    assert rechazadas[0].get("status_equivalente") == 409, (
        f"la petición perdedora debía equivaler a 409, se obtuvo: {rechazadas[0]}"
    )

    SessionLocal = sessionmaker(bind=engine_postgres, autoflush=False, autocommit=False)
    verificacion = SessionLocal()
    try:
        activas = (
            verificacion.query(Cita)
            .filter(
                Cita.profesional_id == profesional_id,
                Cita.fecha == fecha,
                Cita.hora == hora,
                Cita.estado.in_(("pendiente", "completada")),
            )
            .all()
        )
        assert len(activas) == 1, (
            f"debía quedar exactamente una cita activa ocupando ese "
            f"horario, se encontraron {len(activas)}"
        )
    finally:
        verificacion.close()
