from sqlalchemy import create_engine, inspect, text
import pytest

from app.models.usuario import Usuario
from scripts.migrar_acceso_administrativo_sa8 import (
    MigracionAccesoAdministrativoError,
    migrar_acceso_administrativo_sa8,
)


def _engine_sqlite():
    return create_engine("sqlite:///:memory:")


def test_migracion_sa8_crea_las_dos_tablas_y_no_inserta_datos():
    engine = _engine_sqlite()

    try:
        Usuario.__table__.create(bind=engine)

        migrar_acceso_administrativo_sa8(
            bind=engine,
            emitir_mensaje=False,
        )

        inspector = inspect(engine)

        assert "acceso_administrativo" in inspector.get_table_names()
        assert "acceso_admin_especialidad" in inspector.get_table_names()

        with engine.connect() as conn:
            total_accesos = conn.execute(
                text(
                    "SELECT COUNT(*) "
                    "FROM acceso_administrativo"
                )
            ).scalar_one()

            total_especialidades = conn.execute(
                text(
                    "SELECT COUNT(*) "
                    "FROM acceso_admin_especialidad"
                )
            ).scalar_one()

        assert total_accesos == 0
        assert total_especialidades == 0
    finally:
        engine.dispose()


def test_migracion_sa8_es_idempotente():
    engine = _engine_sqlite()

    try:
        Usuario.__table__.create(bind=engine)

        migrar_acceso_administrativo_sa8(
            bind=engine,
            emitir_mensaje=False,
        )

        migrar_acceso_administrativo_sa8(
            bind=engine,
            emitir_mensaje=False,
        )

        inspector = inspect(engine)

        assert inspector.get_table_names().count(
            "acceso_administrativo"
        ) == 1

        assert inspector.get_table_names().count(
            "acceso_admin_especialidad"
        ) == 1
    finally:
        engine.dispose()


def test_migracion_sa8_falla_cerrado_si_tabla_existente_es_incompleta():
    engine = _engine_sqlite()

    try:
        Usuario.__table__.create(bind=engine)

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE acceso_administrativo (
                        id INTEGER PRIMARY KEY,
                        usuario_id INTEGER,
                        perfil VARCHAR,
                        tipo_alcance VARCHAR
                    )
                    """
                )
            )

        with pytest.raises(
            MigracionAccesoAdministrativoError
        ):
            migrar_acceso_administrativo_sa8(
                bind=engine,
                emitir_mensaje=False,
            )
    finally:
        engine.dispose()


def test_init_db_registra_modelos_sa8_en_metadata():
    import app.init_db  # noqa: F401
    from app.database import Base

    assert "acceso_administrativo" in Base.metadata.tables
    assert "acceso_admin_especialidad" in Base.metadata.tables
