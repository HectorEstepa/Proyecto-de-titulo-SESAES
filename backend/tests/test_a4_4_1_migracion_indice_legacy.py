# -*- coding: utf-8 -*-
"""
SESAES — A.4.4.1: la migración manual que sanea el índice único
legacy sobre `cita` (incompatible con el sobrecupo de A.4.4) corre
contra un catálogo PostgreSQL real, es idempotente, y es fail-closed
ante cualquier índice que solo coincida en el nombre.

Igual que test_a4_3_migracion_permiso_sobrecupo.py, esto requiere una
base PostgreSQL de test real (TEST_POSTGRES_URL): el script consulta
pg_indexes y ejecuta DROP INDEX, catálogo y sintaxis específicos de
este motor — no tiene sentido ejercitarlo contra el SQLite que usa el
resto de la suite. Si TEST_POSTGRES_URL no está definida, el test se
salta explícitamente — nunca se simula "pasar" esta garantía sin una
base real.

── Por qué este módulo NO comparte la base de TEST_POSTGRES_URL ──

El índice legacy es:

    CREATE UNIQUE INDEX ux_cita_profesional_fecha_hora_pendiente
    ON public.cita USING btree (profesional_id, fecha, hora)
    WHERE ((estado)::text = 'pendiente'::text)

Esa sentencia barre TODA la tabla `cita` al crearse — no solo las
filas que este test module inserta. El resto de la suite Postgres
(test_a4_4_concurrencia_postgres.py, test_a4_4_sobrecupo_slot_ocupado
vía SQLite, etc.) EXISTE PRECISAMENTE para demostrar que A.4.4 permite
2 citas "pendiente" simultáneas sobre el mismo (profesional_id, fecha,
hora) — es decir, la operación normal de esos tests crea, por diseño,
las filas que hacen fallar un CREATE UNIQUE INDEX sobre esa tripleta.
Si este módulo reutilizara la misma base que TEST_POSTGRES_URL usa
para el resto de la suite, CREATE UNIQUE INDEX podría toparse en
cualquier momento con un duplicado dejado por OTRO módulo — sin que
eso implique ningún bug real de A.4.4.1 ni de A.4.4. Elegir
profesional_id/fecha/hora distintos para cada test NO resuelve esto:
la restricción es global a la tabla completa, no a las filas que un
test en particular tocó.

Por eso este módulo sigue la opción recomendada de aislamiento: cada
corrida crea una base PostgreSQL COMPLETAMENTE NUEVA y descartable
(mismo servidor/credenciales que TEST_POSTGRES_URL, nombre generado
con sufijo aleatorio), le aplica el esquema completo de la app, corre
todos los tests de este archivo ahí, y la destruye al final — ver
`_engine_a441_dedicado`. TEST_POSTGRES_URL en sí NUNCA recibe
TRUNCATE/DELETE/DDL destructivo desde este módulo: solo se usa su URL
para abrir una conexión administrativa a la base 'postgres' del mismo
servidor y emitir CREATE DATABASE / DROP DATABASE sobre la base
dedicada. Como salvaguarda adicional (fail-closed), si el nombre de la
base de TEST_POSTGRES_URL no contiene la palabra "test", este módulo
se niega a crear/destruir bases nuevas contra ese servidor en vez de
asumir que es seguro.

Además de los tests de la migración en sí, este archivo incluye la
regresión funcional completa de A.4.4 (POST /citas real, no una
reimplementación manual del flujo) para confirmar que, tras aplicar
A.4.4.1 sobre una base con el índice legacy:

  - una segunda cita con sobrecupo intencional válido sobre el mismo
    slot SE CREA (ya no la bloquea el índice legacy);
  - una tercera cita simultánea sigue viendo 409, pero por la política
    de capacidad de A.4.4 (analizador de intervalos +
    CAPACIDAD_MAXIMA_CITAS_SIMULTANEAS), NO por IntegrityError del
    índice legacy — se distingue explícitamente revisando el detail
    del 409 esperado en cada caso.

Cómo correrlo:
    TEST_POSTGRES_URL="postgresql+psycopg2://..." \\
        pytest tests/test_a4_4_1_migracion_indice_legacy.py -m postgres -q
"""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.postgres

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

if not TEST_POSTGRES_URL:
    pytest.skip(
        "A.4.4.1: TEST_POSTGRES_URL no está definida — el saneamiento "
        "del índice legacy (pg_indexes real + DROP INDEX) NO se validó "
        "contra Postgres real en esta ejecución. Define "
        "TEST_POSTGRES_URL apuntando a un Postgres de test DESECHABLE "
        "para ejercitar esta garantía — nunca contra una base "
        "productiva.",
        allow_module_level=True,
    )

from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.cita import Cita
from app.models.cita_sobrecupo import CitaSobrecupo
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import citas
from app.schemas import CitaCreate
from scripts.migrar_a4_4_1_eliminar_indice_unico_slot import (
    MigracionA441IncompletaError,
    MigracionA441RevisionManualError,
    migrar_a4_4_1_eliminar_indice_unico_slot,
)

_NOMBRE_INDICE = "ux_cita_profesional_fecha_hora_pendiente"

# El DDL EXACTO reportado en el diagnóstico real — usado tal cual para
# reconstruir el índice legacy en el fixture, sin "limpiarlo" a una
# forma más simple.
_DDL_INDICE_LEGACY = (
    f"CREATE UNIQUE INDEX {_NOMBRE_INDICE} "
    "ON public.cita USING btree (profesional_id, fecha, hora) "
    "WHERE ((estado)::text = 'pendiente'::text)"
)


def _dia_habil_futuro(dias_calendario: int = 1) -> str:
    fecha = date.today() + timedelta(days=dias_calendario)
    while fecha.weekday() >= 5:
        fecha += timedelta(days=1)
    return fecha.isoformat()


@pytest.fixture(scope="module")
def engine_postgres():
    """
    Base PostgreSQL COMPLETAMENTE NUEVA y descartable, dedicada
    exclusivamente a este módulo — ver la sección "Por qué este módulo
    NO comparte la base de TEST_POSTGRES_URL" en el docstring del
    archivo. Nunca ejecuta DDL/DML destructivo sobre la base que
    TEST_POSTGRES_URL nombra directamente: solo la usa para conectarse
    al servidor administrativo ('postgres') y crear/destruir esta base
    dedicada.
    """
    base_url = make_url(TEST_POSTGRES_URL)
    nombre_base_original = (base_url.database or "").strip()

    # Fail-closed: si no podemos confirmar, aunque sea por una señal
    # mínima, que el servidor detrás de TEST_POSTGRES_URL está pensado
    # para test, nos negamos a crear/destruir bases ahí. El propio
    # nombre de la variable de entorno ya es una señal fuerte, pero
    # además exigimos que el nombre de la base lo confirme.
    if "test" not in nombre_base_original.lower():
        pytest.skip(
            "A.4.4.1: TEST_POSTGRES_URL no aparenta apuntar a una base "
            f"de test (nombre de base {nombre_base_original!r} no "
            "contiene 'test') — por seguridad, este módulo se niega a "
            "crear/destruir bases nuevas en ese servidor. Define "
            "TEST_POSTGRES_URL con un nombre de base que incluya "
            "'test' para habilitar este módulo."
        )
        return

    nombre_base_dedicada = f"{nombre_base_original}_a441_{uuid.uuid4().hex[:10]}"
    admin_url = base_url.set(database="postgres")

    try:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{nombre_base_dedicada}"'))
    except Exception as exc:  # pragma: no cover - depende del entorno
        pytest.skip(
            "A.4.4.1: no se pudo crear la base dedicada de test "
            f"{nombre_base_dedicada!r} a partir del servidor de "
            f"TEST_POSTGRES_URL ({exc!r}). El rol necesita permiso "
            "CREATEDB para ejercitar este módulo con aislamiento real."
        )
        return

    dedicada_url = base_url.set(database=nombre_base_dedicada)
    eng = create_engine(dedicada_url, pool_pre_ping=True)
    assert eng.dialect.name == "postgresql", (
        "TEST_POSTGRES_URL no apunta a un dialecto postgresql; este "
        "test existe específicamente para ejercitar pg_indexes/DROP "
        "INDEX reales."
    )
    Base.metadata.create_all(bind=eng)

    try:
        yield eng
    finally:
        eng.dispose()
        with admin_engine.connect() as conn:
            # Cierra cualquier conexión residual a la base dedicada
            # antes del DROP — una conexión abierta (p. ej. por un
            # pool que no liberó a tiempo) haría fallar el DROP.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :nombre AND pid <> pg_backend_pid()"
                ),
                {"nombre": nombre_base_dedicada},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{nombre_base_dedicada}"'))
        admin_engine.dispose()


@pytest.fixture()
def sin_indice_legacy(engine_postgres):
    """Garantiza que la base parte SIN el índice legacy (estado
    'ya migrado' / base nueva) — caso base de idempotencia."""
    with engine_postgres.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))
    yield engine_postgres


@pytest.fixture()
def con_indice_legacy(engine_postgres):
    """Recrea el índice legacy EXACTO (mismo DDL que reportó el
    diagnóstico real) antes del test, y lo limpia después si el propio
    test no lo hizo (p. ej. un test que espera fail-closed y por lo
    tanto lo deja intacto)."""
    with engine_postgres.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))
        conn.execute(text(_DDL_INDICE_LEGACY))
    yield engine_postgres
    with engine_postgres.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))


def _existe_indice(engine, *, schema: str = "public", tabla: str = "cita") -> bool:
    inspector = inspect(engine)
    return any(
        idx.get("name") == _NOMBRE_INDICE
        for idx in inspector.get_indexes(tabla, schema=schema)
    )


# ──────────────────────────────────────────────────────────────────
# 1. Índice ausente → no-op
# ──────────────────────────────────────────────────────────────────

def test_indice_ausente_es_noop(sin_indice_legacy):
    assert not _existe_indice(sin_indice_legacy)
    # No debe lanzar ninguna excepción.
    migrar_a4_4_1_eliminar_indice_unico_slot(bind=sin_indice_legacy, emitir_mensaje=False)
    assert not _existe_indice(sin_indice_legacy)


# ──────────────────────────────────────────────────────────────────
# 2. Índice legacy exacto → se reconoce como eliminable
# ──────────────────────────────────────────────────────────────────

def test_indice_legacy_exacto_se_elimina(con_indice_legacy):
    assert _existe_indice(con_indice_legacy)
    migrar_a4_4_1_eliminar_indice_unico_slot(bind=con_indice_legacy, emitir_mensaje=False)
    assert not _existe_indice(con_indice_legacy)


# ──────────────────────────────────────────────────────────────────
# 3. Mismo nombre, columnas inesperadas → fail-closed
# ──────────────────────────────────────────────────────────────────

def test_mismo_nombre_columnas_inesperadas_fail_closed(engine_postgres):
    with engine_postgres.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))
        conn.execute(text(
            f"CREATE UNIQUE INDEX {_NOMBRE_INDICE} "
            "ON public.cita USING btree (profesional_id, fecha) "
            "WHERE ((estado)::text = 'pendiente'::text)"
        ))
    try:
        with pytest.raises(MigracionA441RevisionManualError, match="columnas"):
            migrar_a4_4_1_eliminar_indice_unico_slot(bind=engine_postgres, emitir_mensaje=False)
        # Fail-closed real: el índice sigue ahí, no se tocó.
        assert _existe_indice(engine_postgres)
    finally:
        with engine_postgres.begin() as conn:
            conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))


# ──────────────────────────────────────────────────────────────────
# 4. Mismo nombre, no unique → fail-closed
# ──────────────────────────────────────────────────────────────────

def test_mismo_nombre_no_unique_fail_closed(engine_postgres):
    with engine_postgres.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))
        conn.execute(text(
            f"CREATE INDEX {_NOMBRE_INDICE} "
            "ON public.cita USING btree (profesional_id, fecha, hora) "
            "WHERE ((estado)::text = 'pendiente'::text)"
        ))
    try:
        with pytest.raises(MigracionA441RevisionManualError, match="UNIQUE"):
            migrar_a4_4_1_eliminar_indice_unico_slot(bind=engine_postgres, emitir_mensaje=False)
        assert _existe_indice(engine_postgres)
    finally:
        with engine_postgres.begin() as conn:
            conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))


# ──────────────────────────────────────────────────────────────────
# 5. Mismo nombre, predicado distinto → fail-closed
# ──────────────────────────────────────────────────────────────────

def test_mismo_nombre_predicado_distinto_fail_closed(engine_postgres):
    with engine_postgres.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))
        conn.execute(text(
            f"CREATE UNIQUE INDEX {_NOMBRE_INDICE} "
            "ON public.cita USING btree (profesional_id, fecha, hora) "
            "WHERE ((estado)::text = 'completada'::text)"
        ))
    try:
        with pytest.raises(MigracionA441RevisionManualError, match="predicado"):
            migrar_a4_4_1_eliminar_indice_unico_slot(bind=engine_postgres, emitir_mensaje=False)
        assert _existe_indice(engine_postgres)
    finally:
        with engine_postgres.begin() as conn:
            conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))


def test_predicado_tolera_diferencias_de_representacion(engine_postgres):
    """El predicado EQUIVALENTE pero escrito distinto (sin casts
    explícitos, sin paréntesis extra) debe reconocerse como el mismo
    índice legacy — la tolerancia es sobre la FORMA, no sobre el
    contenido semántico."""
    with engine_postgres.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))
        conn.execute(text(
            f"CREATE UNIQUE INDEX {_NOMBRE_INDICE} "
            "ON public.cita USING btree (profesional_id, fecha, hora) "
            "WHERE (estado = 'pendiente')"
        ))
    try:
        migrar_a4_4_1_eliminar_indice_unico_slot(bind=engine_postgres, emitir_mensaje=False)
        assert not _existe_indice(engine_postgres)
    finally:
        with engine_postgres.begin() as conn:
            conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))


def test_mismo_nombre_tabla_distinta_fail_closed(engine_postgres):
    """Un índice con el mismo nombre pero en una tabla completamente
    distinta es una anomalía: fail-closed, no se ignora en silencio."""
    with engine_postgres.begin() as conn:
        conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))
        conn.execute(text("DROP TABLE IF EXISTS _a441_tabla_ajena;"))
        conn.execute(text(
            "CREATE TABLE _a441_tabla_ajena "
            "(profesional_id INTEGER, fecha VARCHAR, hora VARCHAR, estado VARCHAR);"
        ))
        conn.execute(text(
            f"CREATE UNIQUE INDEX {_NOMBRE_INDICE} "
            "ON _a441_tabla_ajena USING btree (profesional_id, fecha, hora) "
            "WHERE ((estado)::text = 'pendiente'::text)"
        ))
    try:
        with pytest.raises(MigracionA441RevisionManualError, match="_a441_tabla_ajena"):
            migrar_a4_4_1_eliminar_indice_unico_slot(bind=engine_postgres, emitir_mensaje=False)
    finally:
        with engine_postgres.begin() as conn:
            conn.execute(text(f'DROP INDEX IF EXISTS "{_NOMBRE_INDICE}";'))
            conn.execute(text("DROP TABLE IF EXISTS _a441_tabla_ajena;"))


# ──────────────────────────────────────────────────────────────────
# 6. Segunda ejecución → idempotente
# ──────────────────────────────────────────────────────────────────

def test_segunda_ejecucion_es_idempotente(con_indice_legacy):
    migrar_a4_4_1_eliminar_indice_unico_slot(bind=con_indice_legacy, emitir_mensaje=False)
    assert not _existe_indice(con_indice_legacy)
    # No debe lanzar ninguna excepción la segunda vez.
    migrar_a4_4_1_eliminar_indice_unico_slot(bind=con_indice_legacy, emitir_mensaje=False)
    assert not _existe_indice(con_indice_legacy)


# ──────────────────────────────────────────────────────────────────
# 7. El modelo SQLAlchemy vigente no declara la unicidad incompatible
# ──────────────────────────────────────────────────────────────────

def test_modelo_cita_no_declara_unicidad_incompatible_slot():
    """Confirma, contra la declaración real del modelo (no contra una
    base concreta), que Cita no define ningún UniqueConstraint/Index
    único sobre exactamente (profesional_id, fecha, hora) — si algún
    día alguien lo reintrodujera en el modelo, este test debe fallar
    antes de que llegue a una migración de esquema."""
    columnas_prohibidas = {"profesional_id", "fecha", "hora"}

    for constraint in Cita.__table__.constraints:
        if getattr(constraint, "columns", None) is None:
            continue
        nombres = {c.name for c in constraint.columns}
        if nombres == columnas_prohibidas:
            pytest.fail(
                f"Cita.__table__ declara un constraint sobre "
                f"{columnas_prohibidas!r}: {constraint!r} — esto es "
                "exactamente el error que A.4.4 evita (ver "
                "CAPACIDAD_MAXIMA_CITAS_SIMULTANEAS)."
            )

    for indice in Cita.__table__.indexes:
        nombres = {c.name for c in indice.columns}
        if indice.unique and nombres == columnas_prohibidas:
            pytest.fail(
                f"Cita.__table__ declara un índice único sobre "
                f"{columnas_prohibidas!r}: {indice!r} — esto es "
                "exactamente el error que A.4.4 evita (ver "
                "CAPACIDAD_MAXIMA_CITAS_SIMULTANEAS)."
            )


def test_rechaza_dialecto_no_postgres():
    from sqlalchemy import create_engine as _create_engine

    sqlite_engine = _create_engine("sqlite:///:memory:")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        migrar_a4_4_1_eliminar_indice_unico_slot(bind=sqlite_engine, emitir_mensaje=False)


# ──────────────────────────────────────────────────────────────────
# Regresión funcional A.4.4: tras migrar, el sobrecupo real sobre
# slot_ocupado ya NO lo bloquea el índice legacy, y el máximo 2 sigue
# vigente por la política de capacidad (no por IntegrityError).
# ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def datos_regresion(con_indice_legacy):
    """Profesional + actor SUPERADMIN + 3 estudiantes reales, sobre
    una base que TODAVÍA tiene el índice legacy (con_indice_legacy) —
    el propio test corre la migración A.4.4.1 en el momento que le
    corresponde dentro del escenario."""
    engine = con_indice_legacy
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = SessionLocal()
    sufijo = uuid.uuid4().hex[:12]
    prof = Profesional(
        nombre="A4.4.1 IT", especialidad="Nutrición", iniciales="A441",
        estado="activo", horario_inicio="09:00", horario_fin="18:00",
        duracion_min=45,
    )
    superadmin = Usuario(
        correo=f"a441-superadmin-{sufijo}@sesaes.cl", password="x",
        rol="superadmin", nombre="A4.4.1 Superadmin", rut=f"a441-sa-{sufijo}", activo=True,
    )
    estudiantes = [
        Usuario(
            correo=f"a441-est{i}-{sufijo}@sesaes.cl", password="x",
            rol="estudiante", nombre=f"A4.4.1 Est {i}", rut=f"a441-e{i}-{sufijo}", activo=True,
        )
        for i in range(3)
    ]
    setup.add_all([prof, superadmin, *estudiantes])
    setup.commit()
    setup.refresh(prof)
    setup.refresh(superadmin)
    for est in estudiantes:
        setup.refresh(est)
    ids = {
        "profesional_id": prof.id,
        "superadmin_id": superadmin.id,
        "estudiante_ids": [est.id for est in estudiantes],
    }
    setup.close()

    yield engine, ids

    limpieza = SessionLocal()
    try:
        limpieza.query(CitaSobrecupo).filter(
            CitaSobrecupo.cita_id.in_(
                limpieza.query(Cita.id).filter(Cita.profesional_id == ids["profesional_id"])
            )
        ).delete(synchronize_session=False)
        limpieza.query(Cita).filter(Cita.profesional_id == ids["profesional_id"]).delete()
        limpieza.query(Profesional).filter(Profesional.id == ids["profesional_id"]).delete()
        limpieza.query(Usuario).filter(
            Usuario.id.in_([ids["superadmin_id"], *ids["estudiante_ids"]])
        ).delete(synchronize_session=False)
        limpieza.commit()
    except Exception:
        limpieza.rollback()
    finally:
        limpieza.close()


def _crear_cita(*, engine, current_user, estudiante_id, profesional_id, fecha, hora,
                 sobrecupo=False, sobrecupo_motivo=None):
    """Réplica de una request HTTP real a POST /citas: llama
    directamente a citas.crear_cita() — mismo criterio que
    test_a4_4_concurrencia_postgres.py."""
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        payload = CitaCreate(
            estudiante_id=estudiante_id, profesional_id=profesional_id,
            fecha=fecha, hora=hora, sobrecupo=sobrecupo, sobrecupo_motivo=sobrecupo_motivo,
        )
        return citas.crear_cita(cita=payload, db=session, current_user=current_user)
    finally:
        session.close()


def test_regresion_a4_4_sobrecupo_tras_migracion_ya_no_lo_bloquea_el_indice_legacy(
    datos_regresion,
):
    engine, ids = datos_regresion
    fecha = _dia_habil_futuro()
    hora = "10:15"  # bloque real de la grilla (duracion_min=45 desde 09:00)

    current_user = {"id": ids["superadmin_id"], "rol": "superadmin"}
    est1, est2, est3 = ids["estudiante_ids"]

    # Confirma que, ANTES de migrar, el índice legacy efectivamente
    # reproduce el bug reportado (sobrecupo válido rechazado por
    # IntegrityError, no por política de capacidad).
    _crear_cita(
        engine=engine, current_user=current_user, estudiante_id=est1,
        profesional_id=ids["profesional_id"], fecha=fecha, hora=hora,
    )
    with pytest.raises(HTTPException) as exc_info:
        _crear_cita(
            engine=engine, current_user=current_user, estudiante_id=est2,
            profesional_id=ids["profesional_id"], fecha=fecha, hora=hora,
            sobrecupo=True, sobrecupo_motivo="urgencia",
        )
    assert exc_info.value.status_code == 409
    assert "reservada por otra persona" in exc_info.value.detail

    # A.4.4.1: sanea el esquema.
    migrar_a4_4_1_eliminar_indice_unico_slot(bind=engine, emitir_mensaje=False)
    assert not _existe_indice(engine)

    # Ahora el MISMO sobrecupo válido sobre el MISMO slot_ocupado SÍ
    # se crea — ya no lo bloquea el índice legacy.
    segunda = _crear_cita(
        engine=engine, current_user=current_user, estudiante_id=est2,
        profesional_id=ids["profesional_id"], fecha=fecha, hora=hora,
        sobrecupo=True, sobrecupo_motivo="urgencia",
    )
    assert segunda["id"] is not None

    # Una tercera cita simultánea sobre el mismo slot sigue prohibida
    # — pero por la política de capacidad de A.4.4 (máximo 2), NO por
    # IntegrityError del índice legacy (que ya no existe).
    with pytest.raises(HTTPException) as exc_info_tercera:
        _crear_cita(
            engine=engine, current_user=current_user, estudiante_id=est3,
            profesional_id=ids["profesional_id"], fecha=fecha, hora=hora,
            sobrecupo=True, sobrecupo_motivo="tercera",
        )
    assert exc_info_tercera.value.status_code == 409
    # El 409 de capacidad de A.4.4 usa un mensaje propio, distinto del
    # mensaje genérico de IntegrityError — confirma que el motivo del
    # rechazo cambió de mecanismo, no solo que "sigue dando 409".
    assert "reservada por otra persona" not in exc_info_tercera.value.detail

    engine_check = engine
    with engine_check.connect() as conn:
        activas = conn.execute(
            text(
                "SELECT COUNT(*) FROM cita WHERE profesional_id = :pid "
                "AND fecha = :fecha AND hora = :hora "
                "AND estado IN ('pendiente', 'completada')"
            ),
            {"pid": ids["profesional_id"], "fecha": fecha, "hora": hora},
        ).scalar_one()
    assert activas == 2, "nunca deben quedar 3 citas activas en el mismo slot"
