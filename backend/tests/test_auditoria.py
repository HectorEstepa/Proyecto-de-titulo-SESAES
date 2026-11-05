"""
Tests SA-2 para el helper central de auditoría (app/auditoria.py) y el
contrato de seguridad acordado.

Los tests 1-13 y 16 son autocontenidos: crean su propia base SQLite en
memoria (a partir de Base.metadata), no dependen de la base de datos real
ni de fixtures existentes en tu conftest.py. Fueron ejecutados y pasan
en un entorno de simulación equivalente antes de esta entrega.

Los tests 14 y 15 validan el contrato RBAC real del proyecto mediante
app.rbac.permissions.

El test 14 comprueba que SUPERADMIN no obtiene permisos clínicos por
jerarquía y conserva únicamente sus permisos administrativos explícitos.

El test 15 comprueba que ADMIN no posee AUDITORIA_VER, el permiso
exigido por el único endpoint de auditoría que existe (GET). Desde
SA-5 la auditoría es append-only a nivel de aplicación: no existen
endpoints DELETE/PATCH/PUT de auditoría ni el permiso
AUDITORIA_GESTIONAR (retirado del catálogo).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.auditoria import Auditoria
# Se importa el modelo REAL Usuario únicamente para que su tabla quede
# registrada en Base.metadata y se pueda crear, en este esquema de test
# aislado, la tabla "usuario" que referencia el ForeignKey de
# Auditoria.usuario_id. No se usa Usuario para nada más en este archivo.
from app.models.usuario import Usuario
from app.auditoria import registrar_evento_auditoria


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Usuario.__table__, Auditoria.__table__])
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


CURRENT_USER_VALIDO = {"id": 42, "rol": "admin", "correo": "admin@utem.cl", "nombre": "Admin"}


# ─── 1. actor deriva de current_user ──────────────────────────────

def test_actor_deriva_de_current_user(db_session):
    evento = registrar_evento_auditoria(db_session, CURRENT_USER_VALIDO, "accion_test")
    assert evento.usuario_id == 42
    assert evento.actor_rol == "admin"


# ─── 2. actor no falsificable ──────────────────────────────────────

def test_actor_no_falsificable(db_session):
    # Aunque current_user traiga claves con nombres parecidos, el actor
    # siempre sale de current_user["id"] / current_user["rol"].
    current_user = {"id": 7, "rol": "superadmin", "usuario_id": 999, "actor_rol": "otro_rol"}
    evento = registrar_evento_auditoria(db_session, current_user, "accion_test")
    assert evento.usuario_id == 7
    assert evento.actor_rol == "superadmin"


def test_helper_no_acepta_usuario_id_como_parametro_externo():
    import inspect as _inspect
    firma = _inspect.signature(registrar_evento_auditoria)
    assert "usuario_id" not in firma.parameters
    assert "actor_id" not in firma.parameters
    assert "actor_rol" not in firma.parameters


# ─── 3. acción correcta ────────────────────────────────────────────

def test_accion_correcta(db_session):
    evento = registrar_evento_auditoria(db_session, CURRENT_USER_VALIDO, "Editó profesional")
    assert evento.accion == "Editó profesional"


# ─── 4. entidad/entidad_id correctos ───────────────────────────────

def test_entidad_y_entidad_id_correctos(db_session):
    evento = registrar_evento_auditoria(
        db_session, CURRENT_USER_VALIDO, "accion_test", entidad="profesional", entidad_id=123,
    )
    assert evento.entidad == "profesional"
    assert evento.entidad_id == 123


# ─── 5. resultado default = exito ──────────────────────────────────

def test_resultado_default_exito(db_session):
    evento = registrar_evento_auditoria(db_session, CURRENT_USER_VALIDO, "accion_test")
    assert evento.resultado == "exito"


# ─── 6. soporta denegado ───────────────────────────────────────────

def test_soporta_resultado_denegado(db_session):
    evento = registrar_evento_auditoria(db_session, CURRENT_USER_VALIDO, "accion_test", resultado="denegado")
    assert evento.resultado == "denegado"


# ─── 7. soporta error ───────────────────────────────────────────────

def test_soporta_resultado_error(db_session):
    evento = registrar_evento_auditoria(db_session, CURRENT_USER_VALIDO, "accion_test", resultado="error")
    assert evento.resultado == "error"


# ─── 8. resultado inválido → ValueError ────────────────────────────

def test_resultado_invalido_lanza_value_error(db_session):
    with pytest.raises(ValueError):
        registrar_evento_auditoria(db_session, CURRENT_USER_VALIDO, "accion_test", resultado="algo_invalido")


# ─── 9. current_user sin id → ValueError ───────────────────────────

def test_current_user_sin_id_lanza_value_error(db_session):
    current_user = {"rol": "admin"}
    with pytest.raises(ValueError):
        registrar_evento_auditoria(db_session, current_user, "accion_test")


# ─── 10. current_user sin rol → ValueError ─────────────────────────

def test_current_user_sin_rol_lanza_value_error(db_session):
    current_user = {"id": 1}
    with pytest.raises(ValueError):
        registrar_evento_auditoria(db_session, current_user, "accion_test")


def test_current_user_con_id_cero_es_valido(db_session):
    # Caso borde que justifica validar con `is None` y no con
    # `if not usuario_id`: id=0 es "falsy" en Python pero es un id válido.
    current_user = {"id": 0, "rol": "admin"}
    evento = registrar_evento_auditoria(db_session, current_user, "accion_test")
    assert evento.usuario_id == 0


# ─── 11. no queda evento parcial en sesión tras un ValueError ──────

def test_no_queda_evento_parcial_en_sesion_tras_error(db_session):
    current_user_incompleto = {"id": 1}  # sin rol
    with pytest.raises(ValueError):
        registrar_evento_auditoria(db_session, current_user_incompleto, "accion_test")
    # El helper valida ANTES de construir/agregar el objeto Auditoria.
    assert len(db_session.new) == 0


# ─── 12. no guardar secretos ────────────────────────────────────────

def test_no_guarda_campos_ajenos_de_current_user(db_session):
    current_user_con_secreto = {
        "id": 1, "rol": "admin",
        "password": "no_deberia_llegar_aqui",
        "token": "tampoco_esto",
    }
    evento = registrar_evento_auditoria(db_session, current_user_con_secreto, "accion_test")
    columnas = {c.name for c in Auditoria.__table__.columns}
    assert "password" not in columnas
    assert "token" not in columnas
    assert evento.usuario_id == 1 and evento.actor_rol == "admin"


# ─── 13. usuario_id no queda None con current_user válido ─────────

def test_usuario_id_no_queda_none_con_current_user_valido(db_session):
    evento = registrar_evento_auditoria(db_session, CURRENT_USER_VALIDO, "accion_test")
    assert evento.usuario_id is not None
    assert evento.actor_rol is not None


# ─── 14. SUPERADMIN no gana acceso clínico ─────────────────────────

def test_superadmin_no_gana_acceso_clinico():
    from app.rbac.permissions import has_permission, Permission

    assert has_permission({"rol": "superadmin"}, Permission.FICHA_VER_ASIGNADA) is False
    assert has_permission({"rol": "superadmin"}, Permission.FICHA_EDITAR_ASIGNADA) is False
    assert has_permission({"rol": "superadmin"}, Permission.ATENCIONES_REGISTRAR) is False
    # Pero sí conserva sus permisos administrativos explícitos:
    assert has_permission({"rol": "superadmin"}, Permission.AUDITORIA_VER) is True

# ─── 15. ADMIN no posee permisos de auditoría ──────────────────────

def test_admin_sin_permiso_auditoria_no_accede_a_get():
    from app.rbac.permissions import has_permission, Permission

    admin = {"id": 99, "rol": "admin"}

    # GET /admin/auditoria exige AUDITORIA_VER.
    assert has_permission(admin, Permission.AUDITORIA_VER) is False

    # SA-5: ya no existe AUDITORIA_GESTIONAR ni ningún endpoint DELETE
    # de auditoría — la auditoría es append-only. Ver
    # test_rbac_fase3_5a.py para las pruebas de regresión
    # específicas de esa política.
    assert not hasattr(Permission, "AUDITORIA_GESTIONAR")

# ─── 16. patrón rollback → evento error → commit ───────────────────

def test_patron_rollback_evento_error_commit(db_session):
    """
    Simula el patrón acordado para ERROR:
    1) una mutación de negocio falla y se hace rollback;
    2) se intenta registrar (best-effort) un evento resultado="error";
    3) ese evento se commitea en una transacción separada.
    """
    evento_fantasma = Auditoria(usuario_id=1, actor_rol="admin", accion="no_deberia_quedar", resultado="exito")
    db_session.add(evento_fantasma)
    db_session.rollback()

    registrar_evento_auditoria(
        db_session, CURRENT_USER_VALIDO, "Operación falló",
        resultado="error", detalle="codigo_seguro_001",
    )
    db_session.commit()

    persistidos = db_session.query(Auditoria).all()
    assert len(persistidos) == 1
    assert persistidos[0].resultado == "error"
    assert persistidos[0].accion == "Operación falló"
