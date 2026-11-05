"""
SESAES — RBAC (Fase 3.2): tests con unittest (stdlib).

Continúa la migración de Fase 3.1: aplica require_permission a 4
endpoints administrativos que antes usaban verificar_rol(["admin"]).

Corrección post-revisión: los tests que "demostraban" el Permission
conectado a cada endpoint probando solo qué roles pasan/fallan no
distinguían nada, porque ADMIN y SUPERADMIN tienen tanto
AGENDA_GESTIONAR como REPORTES_VER, y PROFESIONAL no tiene ninguno de
los dos. Ahora `_permiso_de()` lee el Permission exacto capturado por
el closure de require_permission(...) vía inspect.getclosurevars(),
por nombre de variable (no por posición en __closure__), así que un
error de copy/paste entre AGENDA_GESTIONAR y REPORTES_VER sí rompe la
suite.

pytest NO está declarado en requirements.txt (mismo criterio que
test_rbac.py de Fase 3.1), así que estos tests usan exclusivamente
unittest de la biblioteca estándar. Tampoco se agrega ninguna
dependencia nueva (no httpx/TestClient): se llega a la dependencia
REAL conectada en la firma de cada endpoint productivo migrado, tal
como hace RequirePermissionDependencyTests en test_rbac.py.

Importar app.routers.solicitudes_horario / app.routers.correos exige
que exista DATABASE_URL (lo usa app.database al crear el engine, sin
necesidad de una conexión real para estos tests). Si el entorno no
trae un .env con DATABASE_URL configurada, se define un valor
provisional antes del import para que la suite sea ejecutable de
forma aislada — no reemplaza ninguna configuración real si ya existe.

Ejecutar desde backend/:
    python -m unittest discover -s tests -v
"""

import inspect
import os
import unittest

os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sesaes_test"
)

from fastapi import HTTPException

from app.rbac.permissions import Permission
from app.routers import correos, solicitudes_horario


def _dependencia_de(endpoint) -> callable:
    """
    Extrae la dependencia REAL conectada al parámetro `current_user`
    de un endpoint productivo (el closure devuelto por
    require_permission(...) que quedó en Depends(...) por defecto).
    """
    parametro = inspect.signature(endpoint).parameters["current_user"]
    return parametro.default.dependency


def _permiso_de(endpoint) -> Permission:
    """
    Extrae el Permission exacto capturado por el closure de
    require_permission(...) conectado a `endpoint`, inspeccionando sus
    variables de closure por NOMBRE (`permission`) en vez de por
    posición en `__closure__` — así el test no depende del orden en
    que `require_permission` capture sus variables libres.

    Esto es lo que distingue de verdad, por ejemplo, un endpoint
    conectado a AGENDA_GESTIONAR de uno conectado a REPORTES_VER: que
    ADMIN/SUPERADMIN pasen en ambos, o que PROFESIONAL falle en ambos,
    no lo demuestra (ambos roles comparten o carecen de los dos
    permisos) — solo leer el Permission capturado sí lo demuestra.
    """
    dependencia = _dependencia_de(endpoint)
    closure = inspect.getclosurevars(dependencia)
    return closure.nonlocals.get("permission")


class EndpointsMigradosUsanRequirePermissionTests(unittest.TestCase):
    """
    Confirma que los 4 endpoints de la slice de Fase 3.2 quedaron
    conectados a require_permission(Permission.X) con el Permission
    EXACTO esperado (leído del closure por nombre, no inferido por
    qué roles pasan/fallan), y ya no a verificar_rol(["admin"]).

    Un error de copy/paste que intercambiara AGENDA_GESTIONAR y
    REPORTES_VER entre estos 4 endpoints debe romper estos tests.
    """

    def test_get_solicitudes_admin_usa_agenda_gestionar(self):
        self.assertEqual(
            _permiso_de(solicitudes_horario.get_solicitudes_admin),
            Permission.AGENDA_GESTIONAR,
        )

    def test_aprobar_solicitud_usa_agenda_gestionar(self):
        self.assertEqual(
            _permiso_de(solicitudes_horario.aprobar_solicitud),
            Permission.AGENDA_GESTIONAR,
        )

    def test_rechazar_solicitud_usa_agenda_gestionar(self):
        self.assertEqual(
            _permiso_de(solicitudes_horario.rechazar_solicitud),
            Permission.AGENDA_GESTIONAR,
        )

    def test_get_correos_usa_reportes_ver(self):
        self.assertEqual(
            _permiso_de(correos.get_correos),
            Permission.REPORTES_VER,
        )

    def test_ningun_endpoint_migrado_referencia_verificar_rol(self):
        for modulo in (solicitudes_horario, correos):
            self.assertFalse(
                hasattr(modulo, "verificar_rol"),
                f"{modulo.__name__} todavía importa verificar_rol",
            )


class SolicitudesHorarioAdminAutorizacionTests(unittest.TestCase):
    """
    Desde SA-9.6A, las rutas administrativas de solicitudes de
    horario usan autorizaci?n efectiva.

    Un ADMIN ya no puede autorizarse correctamente a partir de un
    dict de rol aislado: su permiso efectivo depende de la BD, del
    perfil persistido y del alcance administrativo.

    Estos tests hist?ricos conservan su responsabilidad original:
    comprobar el Permission exacto conectado a los endpoints y que
    la dependencia ya usa el resolver efectivo.
    """

    def test_los_tres_endpoints_capturan_agenda_gestionar(self):
        for endpoint in (
            solicitudes_horario.get_solicitudes_admin,
            solicitudes_horario.aprobar_solicitud,
            solicitudes_horario.rechazar_solicitud,
        ):
            self.assertEqual(
                _permiso_de(endpoint),
                Permission.AGENDA_GESTIONAR,
            )

    def test_los_tres_endpoints_usan_autorizacion_efectiva(self):
        for endpoint in (
            solicitudes_horario.get_solicitudes_admin,
            solicitudes_horario.aprobar_solicitud,
            solicitudes_horario.rechazar_solicitud,
        ):
            dependencia = _dependencia_de(endpoint)

            self.assertIn(
                "tiene_permiso_efectivo",
                dependencia.__code__.co_names,
                (
                    f"{endpoint.__name__} no usa "
                    "autorizaci?n efectiva"
                ),
            )


class CorreosAdminAutorizacionTests(unittest.TestCase):
    """
    Desde SA-9.6B, GET /correos usa autorizaci?n efectiva.

    El Permission sigue siendo REPORTES_VER, pero un ADMIN ya
    no puede autorizarse correctamente usando solamente un dict
    con rol: el permiso depende de su configuraci?n persistida.
    """

    def test_get_correos_captura_reportes_ver(self):
        self.assertEqual(
            _permiso_de(correos.get_correos),
            Permission.REPORTES_VER,
        )

    def test_get_correos_usa_autorizacion_efectiva(self):
        dependencia = _dependencia_de(
            correos.get_correos
        )

        self.assertIn(
            "tiene_permiso_efectivo",
            dependencia.__code__.co_names,
        )


class EndpointsProfesionalSelfServiceIntactosTests(unittest.TestCase):
    """
    Fase 3.2: los endpoints self-service del profesional en
    solicitudes_horario.py no fueron tocados por ESA migración (seguían
    usando únicamente verificar_acceso_profesional).

    Actualización Fase 3.5F: estos 4 endpoints SÍ fueron modificados
    intencionalmente en esta fase posterior (tarea 4 del checklist) para
    exigir Permission.AGENDA_GESTIONAR_PROPIA además del ownership, vía
    el helper _exigir_agenda_gestionar_propia_y_ownership (que internamente
    sigue llamando a verificar_acceso_profesional — ver
    test_rbac_fase3_5f_solicitudes_horario.py para la cobertura de
    comportamiento completa de permiso + ownership). Se actualiza aquí
    solo la aserción de qué función envuelve la llamada, no el criterio
    de seguridad en sí.
    """

    def test_endpoints_profesional_usan_helper_agenda_gestionar_propia_y_ownership(self):
        endpoints_profesional = [
            solicitudes_horario.solicitar_colacion,
            solicitudes_horario.solicitar_jornada,
            solicitudes_horario.get_mis_solicitudes,
            solicitudes_horario.eliminar_solicitud,
        ]
        for endpoint in endpoints_profesional:
            codigo = endpoint.__code__.co_names
            self.assertIn(
                "_exigir_agenda_gestionar_propia_y_ownership",
                codigo,
                f"{endpoint.__name__} ya no invoca el helper de permiso + ownership (Fase 3.5F)",
            )

    def test_endpoints_profesional_no_usan_require_permission(self):
        endpoints_profesional = [
            solicitudes_horario.solicitar_colacion,
            solicitudes_horario.solicitar_jornada,
            solicitudes_horario.get_mis_solicitudes,
            solicitudes_horario.eliminar_solicitud,
        ]
        for endpoint in endpoints_profesional:
            parametro = inspect.signature(endpoint).parameters["current_user"]
            self.assertIs(parametro.default.dependency, __import__(
                "app.auth_dependencies", fromlist=["get_current_user"]
            ).get_current_user)


class PermissionCapturadoPorEndpointTests(unittest.TestCase):
    """
    Reafirma, endpoint por endpoint y en un solo lugar, el Permission
    EXACTO capturado por cada closure de require_permission(...) —
    esta es la comprobación que reemplaza al test descartado
    "no_es_intercambiable" (que usaba PROFESIONAL/pass-fail y no
    demostraba nada porque ADMIN y SUPERADMIN tienen ambos permisos, y
    PROFESIONAL no tiene ninguno de los dos).
    """

    def test_los_3_endpoints_de_solicitudes_horario_capturan_agenda_gestionar(self):
        for endpoint in (
            solicitudes_horario.get_solicitudes_admin,
            solicitudes_horario.aprobar_solicitud,
            solicitudes_horario.rechazar_solicitud,
        ):
            self.assertEqual(_permiso_de(endpoint), Permission.AGENDA_GESTIONAR)

    def test_get_correos_captura_reportes_ver_y_no_agenda_gestionar(self):
        permiso = _permiso_de(correos.get_correos)
        self.assertEqual(permiso, Permission.REPORTES_VER)
        self.assertNotEqual(permiso, Permission.AGENDA_GESTIONAR)

    def test_admin_no_recibe_agenda_ni_reportes_por_rol(self):
        from app.rbac.permissions import has_permission

        # SA-9: estas capacidades de ADMIN ya no nacen del rol.
        # Se resuelven mediante configuracion administrativa:
        # perfil + permiso persistido + alcance.
        self.assertFalse(
            has_permission(
                "admin",
                Permission.AGENDA_GESTIONAR,
            )
        )

        self.assertFalse(
            has_permission(
                "admin",
                Permission.REPORTES_VER,
            )
        )

    def test_superadmin_tiene_agenda_gestionar_y_reportes_ver_explicitos(self):
        from app.rbac.permissions import has_permission

        self.assertTrue(has_permission("superadmin", Permission.AGENDA_GESTIONAR))
        self.assertTrue(has_permission("superadmin", Permission.REPORTES_VER))


if __name__ == "__main__":
    unittest.main()
