import pytest
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.models.usuario import Usuario
from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminPermiso,
)
from scripts.migrar_permisos_admin_sa9 import (
    MigracionPermisosAdminError,
    migrar_permisos_admin_sa9,
)


def _engine_con_sa8():
    engine = create_engine("sqlite:///:memory:")
    Usuario.__table__.create(engine)
    AccesoAdministrativo.__table__.create(engine)
    return engine


def test_migracion_crea_tabla_sin_datos():
    engine = _engine_con_sa8()

    migrar_permisos_admin_sa9(
        engine,
        emitir_mensaje=False,
    )

    inspector = inspect(engine)

    assert "acceso_admin_permiso" in inspector.get_table_names()

    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM acceso_admin_permiso")
        ).scalar_one()

    assert total == 0


def test_migracion_es_idempotente():
    engine = _engine_con_sa8()

    migrar_permisos_admin_sa9(
        engine,
        emitir_mensaje=False,
    )
    migrar_permisos_admin_sa9(
        engine,
        emitir_mensaje=False,
    )

    assert "acceso_admin_permiso" in inspect(engine).get_table_names()


def test_migracion_falla_si_sa8_no_existe():
    engine = create_engine("sqlite:///:memory:")
    Usuario.__table__.create(engine)

    with pytest.raises(MigracionPermisosAdminError):
        migrar_permisos_admin_sa9(
            engine,
            emitir_mensaje=False,
        )


def test_migracion_falla_cerrado_si_tabla_existente_es_incompleta():
    engine = _engine_con_sa8()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE acceso_admin_permiso (
                    id INTEGER PRIMARY KEY,
                    acceso_admin_id INTEGER NOT NULL
                )
                """
            )
        )

    with pytest.raises(MigracionPermisosAdminError):
        migrar_permisos_admin_sa9(
            engine,
            emitir_mensaje=False,
        )


def test_init_db_registra_tabla_sa9():
    import app.init_db  # noqa: F401

    assert "acceso_admin_permiso" in Base.metadata.tables


def test_fk_declara_cascade():
    engine = _engine_con_sa8()

    AccesoAdminPermiso.__table__.create(engine)

    fks = inspect(engine).get_foreign_keys("acceso_admin_permiso")

    assert len(fks) == 1
    assert fks[0]["constrained_columns"] == ["acceso_admin_id"]
    assert fks[0]["referred_table"] == "acceso_administrativo"
    assert (
        (fks[0].get("options") or {})
        .get("ondelete", "")
        .upper()
        == "CASCADE"
    )
