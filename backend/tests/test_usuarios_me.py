"""
Tests de GET/PATCH /usuarios/me (SA-1.2 — Mi Perfil sobre Usuario).

Sigue exactamente el mismo patrón que
backend/tests/test_admin_profesional_tratamiento.py: SQLite en memoria,
`app.models.init` importado para registrar todos los modelos contra el
mismo `Base` declarativo antes de `create_all()`, y llamado DIRECTO a
las funciones del router (`obtener_mi_perfil`, `actualizar_mi_perfil`)
como funciones Python normales — current_user se pasa como dict plano
(FAKE_ADMIN / FAKE_SUPERADMIN), igual que FAKE_ADMIN en ese archivo.

No se usa TestClient ni ningún fixture `client`: no existe conftest.py
en el proyecto (confirmado en el ZIP de contexto real) y no hay evidencia
de que la suite use HTTP end-to-end en ningún test existente — inventar
un fixture así habría sido fabricar infraestructura que no existe.

Por el mismo motivo que test_admin_profesional_tratamiento.py deja un
test marcado @pytest.mark.skip para lo que no puede probar sin
app/rbac/dependencies.py, este archivo prueba la lógica de negocio real
del router (aislamiento entre usuarios, rechazo de campos sensibles,
independencia de ConfiguracionCentro, no exposición de password) sin
pasar por la capa HTTP de FastAPI. `verificar_rol` sí se ejecuta tal
cual (se importa del auth_dependencies.py real), así que el chequeo de
rol queda cubierto de verdad, no simulado.
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

# Registra todos los modelos y relaciones SQLAlchemy antes de create_all().
# Mismo patrón usado por test_admin_profesional_tratamiento.py.
import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401
from app.database import Base
from app.models.usuario import Usuario
from app.schemas import UsuarioMeUpdate, UsuarioMeOut
from app.security import hash_password
from app.routers.usuarios import obtener_mi_perfil, actualizar_mi_perfil

FAKE_ADMIN_ROL = "admin"
FAKE_SUPERADMIN_ROL = "superadmin"


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


def _crear_usuario(db_session, *, correo, nombre, rol, telefono=None, foto_url=None, activo=True):
    usuario = Usuario(
        correo=correo,
        password=hash_password("Password123!"),
        rol=rol,
        nombre=nombre,
        telefono=telefono,
        foto_url=foto_url,
        activo=activo,
        debe_cambiar_password=False,
    )
    db_session.add(usuario)
    db_session.commit()
    db_session.refresh(usuario)
    return usuario


def _current_user_de(usuario: Usuario) -> dict:
    """Payload equivalente al que produce create_access_token()/
    get_current_user() para este usuario (id + rol, mínimo exigido por
    verificar_rol y por _obtener_usuario_actual)."""
    return {"id": usuario.id, "rol": usuario.rol, "correo": usuario.correo}


# ══════════════════════════════════════
# 1-2. GET /usuarios/me — ADMIN y SUPERADMIN obtienen su propio perfil
# ══════════════════════════════════════

def test_admin_obtiene_su_propio_perfil(db_session):
    admin = _crear_usuario(db_session, correo="admin1@utem.cl", nombre="Admin Uno", rol=FAKE_ADMIN_ROL, telefono="+56911111111")

    resultado = obtener_mi_perfil(db_session, _current_user_de(admin))

    assert resultado.id == admin.id
    assert resultado.nombre == "Admin Uno"
    assert resultado.correo == "admin1@utem.cl"
    assert resultado.telefono == "+56911111111"
    assert resultado.rol == FAKE_ADMIN_ROL


def test_superadmin_obtiene_su_propio_perfil(db_session):
    superadmin = _crear_usuario(db_session, correo="super1@utem.cl", nombre="Super Uno", rol=FAKE_SUPERADMIN_ROL)

    resultado = obtener_mi_perfil(db_session, _current_user_de(superadmin))

    assert resultado.id == superadmin.id
    assert resultado.rol == FAKE_SUPERADMIN_ROL


# ══════════════════════════════════════
# 3-6. PATCH /usuarios/me — campos editables
# ══════════════════════════════════════

def test_admin_cambia_su_nombre(db_session):
    admin = _crear_usuario(db_session, correo="admin2@utem.cl", nombre="Nombre Viejo", rol=FAKE_ADMIN_ROL)

    actualizado = actualizar_mi_perfil(UsuarioMeUpdate(nombre="Nombre Nuevo"), db_session, _current_user_de(admin))

    assert actualizado.nombre == "Nombre Nuevo"
    guardado = db_session.query(Usuario).filter(Usuario.id == admin.id).first()
    assert guardado.nombre == "Nombre Nuevo"


def test_superadmin_cambia_su_nombre(db_session):
    superadmin = _crear_usuario(db_session, correo="super2@utem.cl", nombre="Nombre Viejo", rol=FAKE_SUPERADMIN_ROL)

    actualizado = actualizar_mi_perfil(UsuarioMeUpdate(nombre="Nombre Nuevo Super"), db_session, _current_user_de(superadmin))

    assert actualizado.nombre == "Nombre Nuevo Super"


def test_admin_cambia_su_foto_url(db_session):
    admin = _crear_usuario(db_session, correo="admin3@utem.cl", nombre="Admin Tres", rol=FAKE_ADMIN_ROL)

    actualizado = actualizar_mi_perfil(
        UsuarioMeUpdate(foto_url="data:image/png;base64,ABC"), db_session, _current_user_de(admin)
    )

    assert actualizado.foto_url == "data:image/png;base64,ABC"
    guardado = db_session.query(Usuario).filter(Usuario.id == admin.id).first()
    assert guardado.foto_url == "data:image/png;base64,ABC"


def test_admin_cambia_su_telefono(db_session):
    admin = _crear_usuario(db_session, correo="admin4@utem.cl", nombre="Admin Cuatro", rol=FAKE_ADMIN_ROL)

    actualizado = actualizar_mi_perfil(
        UsuarioMeUpdate(telefono="+56922223333"), db_session, _current_user_de(admin)
    )

    assert actualizado.telefono == "+56922223333"


# ══════════════════════════════════════
# 7 y 14. Aislamiento entre usuarios / identidades independientes
# ══════════════════════════════════════

def test_usuario_a_no_modifica_usuario_b(db_session):
    admin_a = _crear_usuario(db_session, correo="a@utem.cl", nombre="Admin A", rol=FAKE_ADMIN_ROL)
    admin_b = _crear_usuario(db_session, correo="b@utem.cl", nombre="Admin B", rol=FAKE_ADMIN_ROL)

    actualizar_mi_perfil(UsuarioMeUpdate(nombre="A Modificado"), db_session, _current_user_de(admin_a))

    db_session.refresh(admin_a)
    db_session.refresh(admin_b)
    assert admin_a.nombre == "A Modificado"
    assert admin_b.nombre == "Admin B"  # intacto


def test_admin_y_superadmin_mantienen_identidades_independientes(db_session):
    admin = _crear_usuario(db_session, correo="indep1@utem.cl", nombre="Independiente Uno", rol=FAKE_ADMIN_ROL)
    superadmin = _crear_usuario(db_session, correo="indep2@utem.cl", nombre="Independiente Dos", rol=FAKE_SUPERADMIN_ROL)

    actualizar_mi_perfil(UsuarioMeUpdate(nombre="Cambiado Uno"), db_session, _current_user_de(admin))
    actualizar_mi_perfil(UsuarioMeUpdate(nombre="Cambiado Dos"), db_session, _current_user_de(superadmin))

    db_session.refresh(admin)
    db_session.refresh(superadmin)
    assert admin.nombre == "Cambiado Uno"
    assert superadmin.nombre == "Cambiado Dos"


# ══════════════════════════════════════
# 8-12. Campos sensibles -> 422 (ValidationError de Pydantic, extra="forbid")
# ══════════════════════════════════════
#
# UsuarioMeUpdate se valida en el borde HTTP real de FastAPI (el body
# JSON se parsea contra el schema antes de que el endpoint reciba
# control); llamando al router directamente como función Python, ese
# borde equivale a intentar construir UsuarioMeUpdate(**payload) — con
# extra="forbid" eso lanza pydantic.ValidationError, que es exactamente
# lo que FastAPI traduce a 422 en el endpoint real.

@pytest.mark.parametrize("campo,valor", [
    ("rol", "superadmin"),
    ("activo", False),
    ("correo", "otro@utem.cl"),
    ("password", "otra-clave"),
    ("debe_cambiar_password", True),
    ("usuario_id", 999),
    ("permisos", ["configuracion.gestionar"]),
])
def test_campos_sensibles_son_rechazados_por_el_schema(campo, valor):
    with pytest.raises(ValidationError):
        UsuarioMeUpdate(**{"nombre": "Nombre cualquiera", campo: valor})


def test_campo_sensible_no_altera_datos_aunque_venga_junto_a_uno_valido(db_session):
    """Confirma que la petición se rechaza COMPLETA: no se acepta el
    campo válido (nombre) descartando en silencio el sensible (rol)."""
    admin = _crear_usuario(db_session, correo="sensible@utem.cl", nombre="Admin Sensible", rol=FAKE_ADMIN_ROL)

    with pytest.raises(ValidationError):
        UsuarioMeUpdate(nombre="Nombre Colado", rol="superadmin")

    guardado = db_session.query(Usuario).filter(Usuario.id == admin.id).first()
    assert guardado.nombre == "Admin Sensible"  # no cambió
    assert guardado.rol == FAKE_ADMIN_ROL        # tampoco escaló su rol


# ══════════════════════════════════════
# 13. ConfiguracionCentro permanece independiente
# ══════════════════════════════════════

def test_configuracion_centro_no_cambia_al_guardar_mi_perfil(db_session):
    from app.models.configuracion_centro import ConfiguracionCentro

    admin = _crear_usuario(db_session, correo="centro@utem.cl", nombre="Admin Centro", rol=FAKE_ADMIN_ROL)

    config = ConfiguracionCentro(
        nombre_centro="SESAES", direccion="José Pedro Alessandri 1200, Ñuñoa",
        horario_atencion="Lunes a Viernes 08:00-18:00",
        nombre_admin="Admin SESAES", foto_admin_url=None,
    )
    db_session.add(config)
    db_session.commit()

    actualizar_mi_perfil(
        UsuarioMeUpdate(nombre="Admin Centro Modificado", foto_url="data:image/png;base64,XYZ"),
        db_session, _current_user_de(admin),
    )

    config_despues = db_session.query(ConfiguracionCentro).first()
    assert config_despues.nombre_admin == "Admin SESAES"       # intacto
    assert config_despues.foto_admin_url is None                 # intacto


# ══════════════════════════════════════
# 15. Usuario inexistente / inconsistencia de token -> falla seguro (404)
# ══════════════════════════════════════

def test_usuario_inexistente_falla_seguro(db_session):
    current_user_inexistente = {"id": 99999, "rol": FAKE_ADMIN_ROL, "correo": "fantasma@utem.cl"}

    with pytest.raises(HTTPException) as exc_info:
        obtener_mi_perfil(db_session, current_user_inexistente)
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        actualizar_mi_perfil(UsuarioMeUpdate(nombre="No importa"), db_session, current_user_inexistente)
    assert exc_info.value.status_code == 404


def test_rol_no_permitido_es_rechazado(db_session):
    estudiante = _crear_usuario(db_session, correo="estudiante@utem.cl", nombre="Estudiante", rol="estudiante")

    with pytest.raises(HTTPException) as exc_info:
        obtener_mi_perfil(db_session, _current_user_de(estudiante))
    assert exc_info.value.status_code == 403


# ══════════════════════════════════════
# 16. Ningún response expone password/hash
# ══════════════════════════════════════

def test_response_model_no_expone_password_ni_hash(db_session):
    """
    Llamar `obtener_mi_perfil`/`actualizar_mi_perfil` directamente (como
    en el resto de este archivo) devuelve el objeto ORM `Usuario` crudo,
    que SÍ tiene `.password` como atributo Python — eso es correcto y
    esperado, no una fuga: en la API real, FastAPI nunca serializa ese
    objeto tal cual, sino a través de `response_model=UsuarioMeOut`
    (ver app/routers/usuarios.py). Por eso esta prueba replica
    explícitamente ese paso de serialización (from_attributes=True) en
    vez de inspeccionar el objeto ORM, que sería la prueba equivocada.
    """
    admin = _crear_usuario(db_session, correo="passcheck@utem.cl", nombre="Admin Passcheck", rol=FAKE_ADMIN_ROL)

    resultado_orm = obtener_mi_perfil(db_session, _current_user_de(admin))
    serializado = UsuarioMeOut.model_validate(resultado_orm).model_dump()

    assert "password" not in serializado
    assert set(serializado.keys()) == {"id", "nombre", "correo", "telefono", "foto_url", "rol", "activo"}
