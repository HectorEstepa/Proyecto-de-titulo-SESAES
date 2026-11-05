"""
SESAES — Fase SA-1: bootstrap controlado del primer SUPERADMIN.

Sigue la misma convención y el mismo patrón de aislamiento con SQLite en
memoria que backend/tests/test_sa0_seed_seguridad.py: unittest de la
biblioteca estándar (pytest no está declarado como dependencia).

Ejecutar desde backend/:
    python -m unittest tests.test_sa1_bootstrap_superadmin -v
"""

import contextlib
import io
import os
import unittest
from unittest import mock

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import bootstrap_superadmin as bootstrap_module
from app.bootstrap_superadmin import bootstrap_superadmin, main, BootstrapError
from app.database import Base
from app.models.usuario import Usuario
from app.rbac.roles import Role
from app.security import is_legacy_plaintext, verify_password

VALID_EMAIL = "SuperAdmin.Inicial@utem.cl"          # con mayúsculas/espacio a propósito
VALID_EMAIL_NORMALIZADO = "superadmin.inicial@utem.cl"
VALID_PASSWORD = "Sup3r$eguro!"                     # cumple la política de fortaleza
VALID_NAME = "Superadministrador Inicial"


def _nueva_bd_en_memoria():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)  # el bootstrap asume el esquema ya creado
    return engine, SessionLocal


class SA1BootstrapSuperadminTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.SessionLocal = _nueva_bd_en_memoria()
        self._session_patch = mock.patch.object(bootstrap_module, "SessionLocal", self.SessionLocal)
        self._session_patch.start()

        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        for var in ("SUPERADMIN_BOOTSTRAP_EMAIL", "SUPERADMIN_BOOTSTRAP_PASSWORD", "SUPERADMIN_BOOTSTRAP_NAME"):
            os.environ.pop(var, None)
        # SA-1 no debe depender de las variables de SA-0.
        os.environ.pop("SEED_DEMO_DATA", None)
        os.environ.pop("SEED_DEMO_PASSWORD", None)

    def tearDown(self):
        self._session_patch.stop()
        self._env_patch.stop()
        self.engine.dispose()

    def _fijar_config_valida(self):
        os.environ["SUPERADMIN_BOOTSTRAP_EMAIL"] = VALID_EMAIL
        os.environ["SUPERADMIN_BOOTSTRAP_PASSWORD"] = VALID_PASSWORD
        os.environ["SUPERADMIN_BOOTSTRAP_NAME"] = VALID_NAME

    def _todos_los_usuarios(self):
        db = self.SessionLocal()
        try:
            return db.query(Usuario).all()
        finally:
            db.close()

    def _agregar_usuario(self, **kwargs):
        db = self.SessionLocal()
        try:
            u = Usuario(**kwargs)
            db.add(u)
            db.commit()
            db.refresh(u)
            return u.id
        finally:
            db.close()

    # ── 1-6: creación exitosa del primer SUPERADMIN ───────────────
    def test_crea_primer_superadmin_cuando_no_existe_ninguno(self):
        self._fijar_config_valida()
        creado = bootstrap_superadmin()

        usuarios = self._todos_los_usuarios()
        self.assertEqual(len(usuarios), 1)
        u = usuarios[0]

        self.assertEqual(u.rol, Role.SUPERADMIN.value)          # 2
        self.assertTrue(u.activo)                                 # 3
        self.assertFalse(is_legacy_plaintext(u.password))         # 4: hasheada
        self.assertNotEqual(u.password, VALID_PASSWORD)           # 5: no plaintext
        self.assertTrue(verify_password(VALID_PASSWORD, u.password))
        self.assertEqual(u.correo, VALID_EMAIL_NORMALIZADO)       # 6: normalizado
        self.assertEqual(creado.correo, VALID_EMAIL_NORMALIZADO)

    # ── 7: falta email -> falla antes de escribir ─────────────────
    def test_falta_email_falla_antes_de_escribir(self):
        os.environ["SUPERADMIN_BOOTSTRAP_PASSWORD"] = VALID_PASSWORD
        with self.assertRaises(BootstrapError):
            bootstrap_superadmin()
        self.assertEqual(len(self._todos_los_usuarios()), 0)

    # ── 8: falta password -> falla antes de escribir ──────────────
    def test_falta_password_falla_antes_de_escribir(self):
        os.environ["SUPERADMIN_BOOTSTRAP_EMAIL"] = VALID_EMAIL
        with self.assertRaises(BootstrapError):
            bootstrap_superadmin()
        self.assertEqual(len(self._todos_los_usuarios()), 0)

    # ── 9: password vacía / débil -> falla ────────────────────────
    def test_password_vacia_o_debil_falla(self):
        os.environ["SUPERADMIN_BOOTSTRAP_EMAIL"] = VALID_EMAIL
        for password_invalida in ("", "   ", "corta1!", "todominusculas1!", "SINNUMERO!", "SinEspecial1"):
            with self.subTest(password=password_invalida):
                os.environ["SUPERADMIN_BOOTSTRAP_PASSWORD"] = password_invalida
                with self.assertRaises(BootstrapError):
                    bootstrap_superadmin()
        self.assertEqual(len(self._todos_los_usuarios()), 0)

    # ── 10: correo duplicado de otro rol -> falla ─────────────────
    def test_correo_duplicado_de_otro_rol_falla(self):
        self._agregar_usuario(correo=VALID_EMAIL_NORMALIZADO, password="lo-que-sea-ya-hasheado", rol="estudiante")
        self._fijar_config_valida()

        with self.assertRaises(BootstrapError):
            bootstrap_superadmin()

        usuarios = self._todos_los_usuarios()
        self.assertEqual(len(usuarios), 1)  # sigue solo el estudiante preexistente
        self.assertEqual(usuarios[0].rol, "estudiante")  # no se le cambió el rol

    # ── 11: ya existe SUPERADMIN activo -> no crea otro ───────────
    def test_ya_existe_superadmin_activo_no_crea_otro(self):
        self._agregar_usuario(correo="ya.superadmin@utem.cl", password="hash-x", rol=Role.SUPERADMIN.value, activo=True)
        self._fijar_config_valida()

        with self.assertRaises(BootstrapError):
            bootstrap_superadmin()

        self.assertEqual(len(self._todos_los_usuarios()), 1)

    # ── 12: ya existe SUPERADMIN inactivo -> tampoco crea otro ────
    def test_ya_existe_superadmin_inactivo_no_crea_otro(self):
        self._agregar_usuario(correo="viejo.superadmin@utem.cl", password="hash-x", rol=Role.SUPERADMIN.value, activo=False)
        self._fijar_config_valida()

        with self.assertRaises(BootstrapError):
            bootstrap_superadmin()

        self.assertEqual(len(self._todos_los_usuarios()), 1)

    # ── Nuevo: SUPERADMIN existente + SUPERADMIN_BOOTSTRAP_EMAIL/PASSWORD
    #    ausentes -> falla por "ya existe SUPERADMIN", NO por config
    #    faltante. El bootstrap queda cerrado incluso sin variables en
    #    el entorno. Parametrizado para activo=True y activo=False.
    def test_superadmin_existente_sin_config_falla_por_ya_existe_no_por_config(self):
        for activo in (True, False):
            with self.subTest(activo=activo):
                engine, SessionLocal = _nueva_bd_en_memoria()
                with mock.patch.object(bootstrap_module, "SessionLocal", SessionLocal):
                    db = SessionLocal()
                    try:
                        db.add(Usuario(
                            correo=f"existente-{activo}@utem.cl",
                            password="hash-x",
                            rol=Role.SUPERADMIN.value,
                            activo=activo,
                        ))
                        db.commit()
                    finally:
                        db.close()

                    # Deliberadamente ausentes: no deben ni exigirse ni leerse.
                    os.environ.pop("SUPERADMIN_BOOTSTRAP_EMAIL", None)
                    os.environ.pop("SUPERADMIN_BOOTSTRAP_PASSWORD", None)

                    with self.assertRaises(BootstrapError) as ctx:
                        bootstrap_superadmin()

                    self.assertIn("ya existe un", str(ctx.exception).lower())
                    self.assertNotIn("SUPERADMIN_BOOTSTRAP_EMAIL", str(ctx.exception))
                    self.assertNotIn("SUPERADMIN_BOOTSTRAP_PASSWORD", str(ctx.exception))

                    db = SessionLocal()
                    try:
                        self.assertEqual(db.query(Usuario).count(), 1)  # no duplicó
                    finally:
                        db.close()
                engine.dispose()

    # ── 13: tener ADMIN existentes no impide crear el primer SUPERADMIN ──
    def test_admin_existente_no_impide_crear_primer_superadmin(self):
        self._agregar_usuario(correo="admin.real@utem.cl", password="hash-x", rol="admin", activo=True)
        self._fijar_config_valida()

        bootstrap_superadmin()

        usuarios = self._todos_los_usuarios()
        self.assertEqual(len(usuarios), 2)
        roles = {u.rol for u in usuarios}
        self.assertEqual(roles, {"admin", Role.SUPERADMIN.value})
        # el admin preexistente sigue siendo admin, no fue tocado/promovido
        admin_preexistente = next(u for u in usuarios if u.correo == "admin.real@utem.cl")
        self.assertEqual(admin_preexistente.rol, "admin")

    # ── 14: error de commit -> rollback, no queda cuenta parcial ──
    def test_error_de_commit_hace_rollback(self):
        self._fijar_config_valida()

        with mock.patch("sqlalchemy.orm.Session.commit", side_effect=SQLAlchemyError("boom")):
            with self.assertRaises(SQLAlchemyError):
                bootstrap_superadmin()

        self.assertEqual(len(self._todos_los_usuarios()), 0)

    # ── 15: no modifica usuarios existentes ───────────────────────
    def test_no_modifica_usuarios_existentes(self):
        id_estudiante = self._agregar_usuario(
            correo="estudiante.existente@utem.cl", password="hash-original", rol="estudiante",
            nombre="Alguien", activo=True,
        )
        self._fijar_config_valida()
        bootstrap_superadmin()

        db = self.SessionLocal()
        try:
            estudiante = db.query(Usuario).filter(Usuario.id == id_estudiante).first()
            self.assertEqual(estudiante.rol, "estudiante")
            self.assertEqual(estudiante.password, "hash-original")
            self.assertEqual(estudiante.nombre, "Alguien")
        finally:
            db.close()

    # ── 16: no depende de SEED_DEMO_DATA ───────────────────────────
    def test_no_depende_de_seed_demo_data(self):
        os.environ["SEED_DEMO_DATA"] = "false"  # explícitamente deshabilitado
        self._fijar_config_valida()

        bootstrap_superadmin()  # debe funcionar igual, sin importar SEED_DEMO_DATA

        self.assertEqual(len(self._todos_los_usuarios()), 1)

    # ── 17: no introduce permisos clínicos / no altera RBAC ───────
    def test_no_introduce_permisos_clinicos(self):
        from app.rbac.permissions import ROLE_DEFAULT_PERMISSIONS, Permission

        antes = dict(ROLE_DEFAULT_PERMISSIONS)  # copia superficial para comparar

        self._fijar_config_valida()
        bootstrap_superadmin()

        self.assertEqual(ROLE_DEFAULT_PERMISSIONS, antes)
        permisos_superadmin = ROLE_DEFAULT_PERMISSIONS.get(Role.SUPERADMIN, frozenset())
        permisos_clinicos = {
            p for p in Permission
            if p.name in (
                "FICHA_VER_ASIGNADA", "FICHA_EDITAR_ASIGNADA",
                "ATENCIONES_REGISTRAR", "ATENCIONES_VER_ASIGNADAS",
            )
        }
        self.assertEqual(permisos_superadmin & permisos_clinicos, set())

    # ── 18: ejecución repetida -> segunda ejecución falla / no duplica ──
    def test_ejecucion_repetida_falla_y_no_duplica(self):
        self._fijar_config_valida()
        bootstrap_superadmin()
        self.assertEqual(len(self._todos_los_usuarios()), 1)

        with self.assertRaises(BootstrapError):
            bootstrap_superadmin()

        self.assertEqual(len(self._todos_los_usuarios()), 1)


class SA1BootstrapSuperadminCLITests(unittest.TestCase):
    """
    Códigos de salida de `python -m app.bootstrap_superadmin` (main() -> int).
    Mismo aislamiento con SQLite en memoria que la clase anterior; main()
    solo envuelve bootstrap_superadmin(), así que se reutiliza el mismo
    patrón de setUp/tearDown.
    """

    def setUp(self):
        self.engine, self.SessionLocal = _nueva_bd_en_memoria()
        self._session_patch = mock.patch.object(bootstrap_module, "SessionLocal", self.SessionLocal)
        self._session_patch.start()

        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        for var in ("SUPERADMIN_BOOTSTRAP_EMAIL", "SUPERADMIN_BOOTSTRAP_PASSWORD", "SUPERADMIN_BOOTSTRAP_NAME"):
            os.environ.pop(var, None)
        os.environ.pop("SEED_DEMO_DATA", None)
        os.environ.pop("SEED_DEMO_PASSWORD", None)

    def tearDown(self):
        self._session_patch.stop()
        self._env_patch.stop()
        self.engine.dispose()

    def _fijar_config_valida(self):
        os.environ["SUPERADMIN_BOOTSTRAP_EMAIL"] = VALID_EMAIL
        os.environ["SUPERADMIN_BOOTSTRAP_PASSWORD"] = VALID_PASSWORD
        os.environ["SUPERADMIN_BOOTSTRAP_NAME"] = VALID_NAME

    # ── A: creación exitosa -> main() == 0 ─────────────────────────
    def test_main_devuelve_0_en_creacion_exitosa(self):
        self._fijar_config_valida()
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = main()
        self.assertEqual(codigo, 0)

    # ── B: BootstrapError -> main() == 1 (config inválida) ─────────
    def test_main_devuelve_1_por_config_invalida(self):
        # SUPERADMIN_BOOTSTRAP_EMAIL / _PASSWORD deliberadamente ausentes.
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = main()
        self.assertEqual(codigo, 1)

    # ── B: BootstrapError -> main() == 1 (ya existe SUPERADMIN) ─────
    def test_main_devuelve_1_si_ya_existe_superadmin(self):
        db = self.SessionLocal()
        try:
            db.add(Usuario(
                correo="ya.superadmin@utem.cl",
                password="hash-x",
                rol=Role.SUPERADMIN.value,
                activo=True,
            ))
            db.commit()
        finally:
            db.close()

        self._fijar_config_valida()
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = main()
        self.assertEqual(codigo, 1)

    # ── C: la salida de la CLI nunca contiene la contraseña ni el hash ──
    def test_salida_cli_no_contiene_password_ni_hash(self):
        self._fijar_config_valida()
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            main()
        texto = salida.getvalue()

        self.assertNotIn(VALID_PASSWORD, texto)

        db = self.SessionLocal()
        try:
            creado = db.query(Usuario).filter(Usuario.correo == VALID_EMAIL_NORMALIZADO).first()
            self.assertIsNotNone(creado)
            self.assertNotIn(creado.password, texto)  # el hash tampoco se imprime
        finally:
            db.close()

    # ── C (caso de error): la salida tampoco contiene password/hash ────
    def test_salida_cli_no_contiene_password_ni_hash_en_error(self):
        os.environ["SUPERADMIN_BOOTSTRAP_EMAIL"] = VALID_EMAIL
        os.environ["SUPERADMIN_BOOTSTRAP_PASSWORD"] = VALID_PASSWORD
        os.environ["SUPERADMIN_BOOTSTRAP_PASSWORD"] = "corta1!"  # inválida -> BootstrapError

        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = main()

        self.assertEqual(codigo, 1)
        texto = salida.getvalue()
        self.assertNotIn("corta1!", texto)
        self.assertNotIn(VALID_PASSWORD, texto)


if __name__ == "__main__":
    unittest.main()
