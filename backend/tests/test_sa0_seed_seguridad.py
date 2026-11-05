"""
SESAES — Fase SA-0: seguridad del seed / init_db().

Cubre exclusivamente el alcance autorizado para SA-0:
  - El seed de datos demo NO se ejecuta por defecto.
  - Solo se activa con SEED_DEMO_DATA=true (comparación normalizada).
  - Requiere SEED_DEMO_PASSWORD explícita; si falta, falla seguro
    (SeedConfigError) sin tocar la base de datos.
  - Las contraseñas sembradas quedan hasheadas (bcrypt), nunca en texto plano.
  - Idempotencia: una segunda ejecución no duplica usuarios.
  - Base.metadata.create_all() se sigue ejecutando siempre (A y B separados).

Sigue la convención del proyecto: unittest de la biblioteca estándar
(pytest no está declarado como dependencia). Ejecutar desde backend/:

    python -m unittest tests.test_sa0_seed_seguridad -v
"""

import os
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import init_db as init_db_module
from app.database import Base
from app.init_db import init_db, SeedConfigError
from app.models.usuario import Usuario
from app.security import is_legacy_plaintext, verify_password


def _nueva_bd_en_memoria():
    """
    Crea un engine SQLite en memoria aislado por test (StaticPool para que
    la misma conexión/BD persista entre las distintas sesiones que abre
    init_db() dentro de una misma prueba) y crea el esquema en él.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal


class SA0SeedSeguridadTests(unittest.TestCase):
    def setUp(self):
        # Cada test corre contra su propia BD en memoria, aislada de las
        # demás, y con SEED_DEMO_DATA / SEED_DEMO_PASSWORD limpias salvo
        # que el propio test las fije explícitamente.
        self.engine, self.SessionLocal = _nueva_bd_en_memoria()

        self._engine_patch = mock.patch.object(init_db_module, "engine", self.engine)
        self._session_patch = mock.patch.object(init_db_module, "SessionLocal", self.SessionLocal)
        self._engine_patch.start()
        self._session_patch.start()

        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("SEED_DEMO_DATA", None)
        os.environ.pop("SEED_DEMO_PASSWORD", None)

    def tearDown(self):
        self._engine_patch.stop()
        self._session_patch.stop()
        self._env_patch.stop()
        self.engine.dispose()

    def _contar_usuarios(self):
        db = self.SessionLocal()
        try:
            return db.query(Usuario).count()
        finally:
            db.close()

    def _tablas_existentes(self):
        from sqlalchemy import inspect
        return set(inspect(self.engine).get_table_names())

    # ── Caso 1: BD vacía, SEED_DEMO_DATA ausente ──────────────────
    def test_seed_ausente_no_crea_cuentas_demo(self):
        init_db()
        self.assertEqual(self._contar_usuarios(), 0)

    # ── Caso 2: BD vacía, SEED_DEMO_DATA=false ────────────────────
    def test_seed_false_no_crea_cuentas_demo(self):
        os.environ["SEED_DEMO_DATA"] = "false"
        init_db()
        self.assertEqual(self._contar_usuarios(), 0)

    def test_seed_valor_no_reconocido_no_crea_cuentas_demo(self):
        for valor in ("0", "no", "TRUEISH", "", "  ", "verdadero"):
            with self.subTest(valor=valor):
                self.engine, self.SessionLocal = _nueva_bd_en_memoria()
                with mock.patch.object(init_db_module, "engine", self.engine), \
                     mock.patch.object(init_db_module, "SessionLocal", self.SessionLocal):
                    os.environ["SEED_DEMO_DATA"] = valor
                    init_db()
                    self.assertEqual(self._contar_usuarios(), 0)

    # ── create_all sigue funcionando aunque el seed esté desactivado ──
    def test_create_all_sigue_ejecutandose_con_seed_desactivado(self):
        init_db()
        tablas = self._tablas_existentes()
        self.assertIn("usuario", tablas)

    # ── Caso 3: BD vacía, SEED_DEMO_DATA=true, config válida ──────
    def test_seed_true_con_password_crea_seed_esperado(self):
        os.environ["SEED_DEMO_DATA"] = "TrUe"  # normalización lower/strip
        os.environ["SEED_DEMO_PASSWORD"] = "clave-demo-de-prueba"
        init_db()
        self.assertEqual(self._contar_usuarios(), 11)

    # ── Caso 4: seed habilitado pero falta SEED_DEMO_PASSWORD ─────
    def test_seed_true_sin_password_falla_seguro(self):
        os.environ["SEED_DEMO_DATA"] = "true"
        with self.assertRaises(SeedConfigError) as ctx:
            init_db()
        # No debe haberse escrito nada en la BD.
        self.assertEqual(self._contar_usuarios(), 0)
        # El mensaje de error no debe filtrar ningún secreto (no hay
        # password que filtrar en este caso, pero validamos que el texto
        # del error no incluya valores de entorno sensibles arbitrarios).
        self.assertNotIn("SEED_DEMO_PASSWORD=", str(ctx.exception))

    def test_seed_true_con_password_vacia_falla_seguro(self):
        os.environ["SEED_DEMO_DATA"] = "true"
        os.environ["SEED_DEMO_PASSWORD"] = "   "
        with self.assertRaises(SeedConfigError):
            init_db()
        self.assertEqual(self._contar_usuarios(), 0)

    # ── Caso 5: contraseñas sembradas quedan hasheadas ────────────
    def test_passwords_sembradas_quedan_hasheadas(self):
        os.environ["SEED_DEMO_DATA"] = "true"
        os.environ["SEED_DEMO_PASSWORD"] = "clave-demo-de-prueba"
        init_db()

        db = self.SessionLocal()
        try:
            usuarios = db.query(Usuario).all()
            self.assertEqual(len(usuarios), 11)
            for u in usuarios:
                self.assertFalse(
                    is_legacy_plaintext(u.password),
                    f"la contraseña de {u.correo} no quedó hasheada",
                )
                self.assertNotEqual(u.password, "clave-demo-de-prueba")
                self.assertTrue(verify_password("clave-demo-de-prueba", u.password))
        finally:
            db.close()

    # ── Caso 6: segunda ejecución no duplica usuarios ─────────────
    def test_segunda_ejecucion_no_duplica_usuarios(self):
        os.environ["SEED_DEMO_DATA"] = "true"
        os.environ["SEED_DEMO_PASSWORD"] = "clave-demo-de-prueba"
        init_db()
        primer_conteo = self._contar_usuarios()

        init_db()
        segundo_conteo = self._contar_usuarios()

        self.assertEqual(primer_conteo, segundo_conteo)

    # ── Caso nuevo: BD ya inicializada + SEED_DEMO_PASSWORD ausente ──
    # No debe exigirse la contraseña demo cuando no se va a crear ningún
    # usuario: si la BD ya tiene al menos un Usuario, init_db() debe
    # retornar normalmente sin siquiera evaluar SEED_DEMO_PASSWORD.
    def test_bd_ya_inicializada_no_exige_password_ni_duplica(self):
        # Preparamos manualmente una BD "ya inicializada" con un usuario
        # cualquiera, sin pasar por el seed (para no depender de él acá).
        Base.metadata.create_all(bind=self.engine)
        db = self.SessionLocal()
        try:
            db.add(Usuario(correo="ya.existente@utem.cl", password="hash-preexistente", rol="admin"))
            db.commit()
        finally:
            db.close()

        os.environ["SEED_DEMO_DATA"] = "true"
        os.environ.pop("SEED_DEMO_PASSWORD", None)  # deliberadamente ausente

        try:
            init_db()  # NO debe lanzar SeedConfigError
        except SeedConfigError:
            self.fail(
                "init_db() exigió SEED_DEMO_PASSWORD aunque la BD ya "
                "tenía usuarios y no se iba a sembrar nada."
            )

        self.assertEqual(self._contar_usuarios(), 1)  # no duplicó nada

    # ── Caso 3 (extendido): cada hash bcrypt es distinto (salt aleatorio) ──
    def test_hashes_de_password_son_distintos_entre_si(self):
        os.environ["SEED_DEMO_DATA"] = "true"
        os.environ["SEED_DEMO_PASSWORD"] = "clave-demo-de-prueba"
        init_db()

        db = self.SessionLocal()
        try:
            hashes = [u.password for u in db.query(Usuario).all()]
            self.assertEqual(len(hashes), 11)
            self.assertEqual(len(set(hashes)), 11, "los 11 hashes deberían ser distintos entre sí")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
