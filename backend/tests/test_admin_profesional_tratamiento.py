"""
Tests del campo `tratamiento` en Profesional.

NOTA IMPORTANTE SOBRE ESTOS TESTS:
No tuve acceso a `app/main.py`, `app/database.py`, `app/rbac/dependencies.py`
ni a ningún `conftest.py`/carpeta `tests/` existente del proyecto, así que no
pude "seguir el patrón actual del repositorio" como se pidió — no sé qué
patrón usan. Para no fabricar un test que aparente pasar sin probar nada
real, estos tests:

  1. Llaman directamente a las funciones del router (`crear_profesional`,
     `actualizar_profesional`, `get_profesionales_admin`, `get_resumen_dia`)
     como funciones Python normales, con una sesión SQLAlchemy real sobre
     SQLite en memoria. Esto ejercita la lógica real de negocio (incluida
     la distinción model_fields_set) sin necesitar saber cómo el proyecto
     resuelve `require_permission` vía HTTP.
  2. Por eso NO cubren "las restricciones de permisos existentes no
     cambian" vía HTTP real (ver test marcado como `skip` al final, con la
     razón exacta de qué archivos necesito para escribirlo de verdad).

Si el proyecto ya tiene un `conftest.py` con un fixture de TestClient
autenticado (ej. `client_admin`), lo ideal es adaptar estos tests para usar
ese fixture y probar los endpoints vía HTTP end-to-end. Compárteme ese
conftest y te entrego la versión ajustada.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

# Registra todos los modelos y relaciones SQLAlchemy antes de create_all().
# Mismo patrón usado por los tests RBAC existentes de SESAES.
import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base

from app.models.profesional import Profesional
from app.schemas import ProfesionalCreate, ProfesionalUpdate, COLORES_PERMITIDOS
from app.routers.admin import (
    crear_profesional,
    actualizar_profesional,
    get_profesionales_admin,
    get_resumen_dia,
)

# Estos tests llaman directamente las funciones del router y,
# como explica la cabecera del archivo, NO prueban RBAC.
# Usamos un contexto institucional para no introducir bypasses
# de autorizaci?n en producci?n.
FAKE_ADMIN = {"id": -1, "rol": "superadmin"}


@pytest.fixture()
def db_session():
    """Sesión real sobre SQLite en memoria, con todas las tablas del
    proyecto creadas a partir del mismo Base declarativo que usa la app."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ══════════════════════════════════════
# 1. Creación de profesional CON tratamiento
# ══════════════════════════════════════

def test_crear_profesional_con_tratamiento(db_session):
    datos = ProfesionalCreate(
        nombre="Eduardo Carvajal",
        tratamiento="Dr.",
        especialidad="Medicina General",
        correo="eduardo.carvajal@utem.cl",
    )
    creado = crear_profesional(datos, db_session, FAKE_ADMIN)

    assert creado.tratamiento == "Dr."
    guardado = db_session.query(Profesional).filter(Profesional.id == creado.id).first()
    assert guardado.tratamiento == "Dr."


# ══════════════════════════════════════
# 2. Creación de profesional SIN tratamiento sigue funcionando
# ══════════════════════════════════════

def test_crear_profesional_sin_tratamiento(db_session):
    datos = ProfesionalCreate(
        nombre="Carlos Muñoz",
        especialidad="Nutrición",
        correo="carlos.munoz@utem.cl",
    )
    creado = crear_profesional(datos, db_session, FAKE_ADMIN)

    assert creado.tratamiento is None
    assert creado.nombre == "Carlos Muñoz"
    guardado = db_session.query(Profesional).filter(Profesional.id == creado.id).first()
    assert guardado.tratamiento is None


# ══════════════════════════════════════
# 3. Actualización del tratamiento (profesional ya existente, dato NULL)
# ══════════════════════════════════════

def test_actualizar_tratamiento_de_profesional_existente(db_session):
    creado = crear_profesional(
        ProfesionalCreate(nombre="Rodrigo Céspedes", especialidad="Kinesiología", correo="rodrigo@utem.cl"),
        db_session, FAKE_ADMIN
    )
    assert creado.tratamiento is None  # estado inicial: sin tratamiento, como los datos reales hoy

    actualizado = actualizar_profesional(
        creado.id, ProfesionalUpdate(tratamiento="Dr."), db_session, FAKE_ADMIN
    )

    assert actualizado.tratamiento == "Dr."


# ══════════════════════════════════════
# 4. Limpieza explícita del tratamiento (PATCH con tratamiento: null)
# ══════════════════════════════════════

def test_limpiar_tratamiento_explicitamente(db_session):
    creado = crear_profesional(
        ProfesionalCreate(nombre="Ana Martínez", tratamiento="Dra.", especialidad="Psicología", correo="ana@utem.cl"),
        db_session, FAKE_ADMIN
    )
    assert creado.tratamiento == "Dra."

    # tratamiento=None enviado EXPLÍCITAMENTE (queda en model_fields_set)
    limpiado = actualizar_profesional(
        creado.id, ProfesionalUpdate(tratamiento=None), db_session, FAKE_ADMIN
    )
    assert limpiado.tratamiento is None


def test_no_tocar_tratamiento_si_no_se_envia(db_session):
    """Si `tratamiento` no viene en el payload, debe conservar su valor
    actual (regresión del bug 'is not None' que impedía limpiar, pero
    aplicada al revés: tampoco debe borrar sin querer)."""
    creado = crear_profesional(
        ProfesionalCreate(nombre="Diego Soto", tratamiento="Dr.", especialidad="Kinesiología", correo="diego@utem.cl"),
        db_session, FAKE_ADMIN
    )
    assert creado.tratamiento == "Dr."

    # Solo se envía duracion_min; tratamiento NO se toca.
    actualizado = actualizar_profesional(
        creado.id, ProfesionalUpdate(duracion_min=30), db_session, FAKE_ADMIN
    )
    assert actualizado.tratamiento == "Dr."


def test_tratamiento_acepta_valor_historico_libre_por_compatibilidad(db_session):
    """`tratamiento` es texto libre a nivel de backend (sin enum/validación,
    a diferencia de color_identificador) por compatibilidad con datos
    históricos que pudieran tener otros prefijos. La interfaz actual, sin
    embargo, solo ofrece Sin prefijo/Dr./Dra. — esto no es una opción que
    el admin pueda elegir hoy desde el formulario, es una garantía de que
    no se rompen filas antiguas."""
    creado = crear_profesional(
        ProfesionalCreate(nombre="Roberto Fuentes", tratamiento="Psic.", especialidad="Psicología", correo="roberto@utem.cl"),
        db_session, FAKE_ADMIN
    )
    assert creado.tratamiento == "Psic."


# ══════════════════════════════════════
# 5. /admin/resumen-dia devuelve tratamiento
# ══════════════════════════════════════

def test_resumen_dia_incluye_tratamiento_y_color(db_session):
    crear_profesional(
        ProfesionalCreate(nombre="Eduardo Carvajal", tratamiento="Dr.", especialidad="Medicina General",
                           correo="eduardo2@utem.cl", color_identificador="#4F8EF7"),
        db_session, FAKE_ADMIN
    )
    crear_profesional(
        ProfesionalCreate(nombre="Carlos Muñoz", especialidad="Nutrición", correo="carlos2@utem.cl"),
        db_session, FAKE_ADMIN
    )

    resumen = get_resumen_dia(
        db_session,
        {"id": -1, "rol": "superadmin"},
    )

    por_nombre = {r["nombre"]: r for r in resumen}
    assert por_nombre["Eduardo Carvajal"]["tratamiento"] == "Dr."
    assert por_nombre["Eduardo Carvajal"]["color_identificador"] == "#4F8EF7"
    assert por_nombre["Carlos Muñoz"]["tratamiento"] is None
    assert por_nombre["Carlos Muñoz"]["color_identificador"] is None


def test_listado_profesionales_incluye_tratamiento(db_session):
    crear_profesional(
        ProfesionalCreate(nombre="Ana Martínez", tratamiento="Dra.", especialidad="Psicología", correo="ana2@utem.cl"),
        db_session, FAKE_ADMIN
    )

    listado = get_profesionales_admin(
        db_session,
        {"id": -1, "rol": "superadmin"},
    )

    assert listado[0]["tratamiento"] == "Dra."


# ══════════════════════════════════════
# 6. Permisos — PENDIENTE, requiere archivos que no tengo
# ══════════════════════════════════════

@pytest.mark.skip(
    reason=(
        "No tengo acceso a app/rbac/dependencies.py (implementación real de "
        "require_permission) ni a app/main.py, así que no puedo construir un "
        "TestClient con override de autenticación fiel al mecanismo real del "
        "proyecto. Comparte esos dos archivos (y el conftest.py si existe) "
        "para escribir un test end-to-end que confirme que un usuario sin "
        "PROFESIONALES_GESTIONAR sigue recibiendo 403 en estos endpoints."
    )
)
def test_permisos_profesionales_gestionar_sin_cambios():
    pass


# ══════════════════════════════════════
# 7. color_identificador — creación, actualización, limpieza, validación
# ══════════════════════════════════════

def test_crear_profesional_con_color_valido(db_session):
    color = next(iter(COLORES_PERMITIDOS))
    creado = crear_profesional(
        ProfesionalCreate(nombre="Joaquín Rodríguez", especialidad="Medicina General",
                           correo="joaquin@utem.cl", color_identificador=color),
        db_session, FAKE_ADMIN
    )
    assert creado.color_identificador == color
    guardado = db_session.query(Profesional).filter(Profesional.id == creado.id).first()
    assert guardado.color_identificador == color


def test_crear_profesional_sin_color(db_session):
    creado = crear_profesional(
        ProfesionalCreate(nombre="Diego Soto", especialidad="Kinesiología", correo="diego3@utem.cl"),
        db_session, FAKE_ADMIN
    )
    assert creado.color_identificador is None


def test_actualizar_color_de_profesional_existente(db_session):
    creado = crear_profesional(
        ProfesionalCreate(nombre="Ana Martínez", especialidad="Psicología", correo="ana3@utem.cl"),
        db_session, FAKE_ADMIN
    )
    assert creado.color_identificador is None

    nuevo_color = "#4F8EF7"
    actualizado = actualizar_profesional(
        creado.id, ProfesionalUpdate(color_identificador=nuevo_color), db_session, FAKE_ADMIN
    )
    assert actualizado.color_identificador == nuevo_color


def test_limpiar_color_explicitamente(db_session):
    creado = crear_profesional(
        ProfesionalCreate(nombre="Carlos Muñoz", especialidad="Nutrición", correo="carlos3@utem.cl",
                           color_identificador="#D96C8A"),
        db_session, FAKE_ADMIN
    )
    assert creado.color_identificador == "#D96C8A"

    limpiado = actualizar_profesional(
        creado.id, ProfesionalUpdate(color_identificador=None), db_session, FAKE_ADMIN
    )
    assert limpiado.color_identificador is None


def test_no_tocar_color_si_no_se_envia(db_session):
    creado = crear_profesional(
        ProfesionalCreate(nombre="Rodrigo Céspedes", especialidad="Kinesiología", correo="rodrigo2@utem.cl",
                           color_identificador="#D9A441"),
        db_session, FAKE_ADMIN
    )
    assert creado.color_identificador == "#D9A441"

    actualizado = actualizar_profesional(
        creado.id, ProfesionalUpdate(duracion_min=30), db_session, FAKE_ADMIN
    )
    assert actualizado.color_identificador == "#D9A441"


def test_color_invalido_es_rechazado_en_creacion_con_http_400(db_session):
    """La validación real ocurre en el router (crear_profesional), no en el
    schema — por eso el resultado es HTTPException(400), no un 422 de
    Pydantic. ProfesionalCreate en sí acepta cualquier string en este
    campo; es admin.py quien decide rechazarlo."""
    for valor_invalido in ["red", "url(javascript:alert(1))", "var(--admin-primary)", "#FFFFFF", "#4f8ef7"]:
        datos = ProfesionalCreate(nombre="X", especialidad="Y", correo="x@utem.cl", color_identificador=valor_invalido)
        with pytest.raises(HTTPException) as exc_info:
            crear_profesional(datos, db_session, FAKE_ADMIN)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Color identificador no permitido"


def test_color_invalido_es_rechazado_en_actualizacion_con_http_400(db_session):
    creado = crear_profesional(
        ProfesionalCreate(nombre="Diego Soto", especialidad="Kinesiología", correo="diego4@utem.cl"),
        db_session, FAKE_ADMIN
    )
    datos = ProfesionalUpdate(color_identificador="not-a-color")
    with pytest.raises(HTTPException) as exc_info:
        actualizar_profesional(creado.id, datos, db_session, FAKE_ADMIN)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Color identificador no permitido"

    # Confirma que el rechazo no alcanzó a mutar el profesional.
    guardado = db_session.query(Profesional).filter(Profesional.id == creado.id).first()
    assert guardado.color_identificador is None


def test_listado_profesionales_incluye_color(db_session):
    crear_profesional(
        ProfesionalCreate(nombre="Eduardo Carvajal", especialidad="Medicina General", correo="eduardo3@utem.cl",
                           color_identificador="#4F8EF7"),
        db_session, FAKE_ADMIN
    )
    listado = get_profesionales_admin(
        db_session,
        {"id": -1, "rol": "superadmin"},
    )
    assert listado[0]["color_identificador"] == "#4F8EF7"
