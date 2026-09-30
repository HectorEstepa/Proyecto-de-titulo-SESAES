# -*- coding: utf-8 -*-
"""
Tests — Inicio institucional de SUPERADMIN (app/routers/admin_inicio.py)
y ajuste aditivo de GET /admin/auditoria (limit + actor_nombre).

Mismo patrón que el resto de la suite: SQLite en memoria creada desde el
Base real y endpoints llamados como funciones Python, pasando `db` y
`current_user` como lo haría FastAPI tras resolver las dependencias. Las
métricas se ejercitan con fecha/hora inyectadas para que las ventanas
(12 meses / 90 días / 30 días) sean deterministas.
"""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401 — registra todos los modelos
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminPermiso,
)
from app.models.auditoria import Auditoria
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.solicitud_horario import SolicitudHorario
from app.models.usuario import Usuario
from app.rbac.admin_access import PERMISOS_RESERVADOS_SUPERADMIN
from app.rbac.admin_authorization import AlcanceAdministrativoEfectivo
from app.rbac.permissions import Permission
from app.routers import admin, admin_inicio
from app.routers.admin_inicio import (
    PERMISOS_GESTION,
    PERMISOS_RESUMEN,
    construir_gestion,
    construir_resumen,
    get_gestion_inicio,
    get_resumen_inicio,
    requerir_permisos_institucionales,
)

HOY = date(2026, 9, 19)
AHORA = datetime(2026, 9, 19, 12, 0, 0)


# ══════════════════════════════════════
# Fixtures / helpers
# ══════════════════════════════════════

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@contextmanager
def contar_sentencias(session):
    sentencias: list[str] = []

    def _antes(conn, cursor, statement, params, context, executemany):
        sentencias.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", _antes)
    try:
        yield sentencias
    finally:
        event.remove(engine, "before_cursor_execute", _antes)


_contador = {"n": 0}


def _usuario(db, rol="estudiante", *, nombre=None, activo=True):
    _contador["n"] += 1
    u = Usuario(
        correo=f"u{_contador['n']}@sesaes.cl",
        password="hash",
        rol=rol,
        nombre=nombre or f"Usuario {_contador['n']}",
        activo=activo,
    )
    db.add(u)
    db.flush()
    return u


def _prof(db, nombre, especialidad="Psicología", estado="activo"):
    p = Profesional(
        nombre=nombre,
        especialidad=especialidad,
        iniciales=nombre[:2].upper(),
        estado=estado,
    )
    db.add(p)
    db.flush()
    return p


def _cita(db, estudiante, profesional, fecha, estado="pendiente"):
    c = Cita(
        estudiante_id=estudiante.id,
        profesional_id=profesional.id,
        fecha=fecha,
        hora="10:00",
        estado=estado,
    )
    db.add(c)
    db.flush()
    return c


def _solicitud(db, profesional, fecha_solicitud, estado="pendiente"):
    s = SolicitudHorario(
        profesional_id=profesional.id,
        tipo="colacion",
        hora_inicio="13:00",
        hora_fin="14:00",
        estado=estado,
        fecha_solicitud=fecha_solicitud,
    )
    db.add(s)
    db.flush()
    return s


def _auditoria(db, usuario, resultado, fecha, accion="Acción de prueba"):
    a = Auditoria(
        usuario_id=usuario.id,
        actor_rol=usuario.rol,
        accion=accion,
        resultado=resultado,
        detalle="detalle",
        entidad="cita",
        entidad_id=1,
        fecha=fecha,
    )
    db.add(a)
    db.flush()
    return a


def _cu(usuario):
    return {"id": usuario.id, "rol": usuario.rol, "correo": usuario.correo}


def _admin_operativo(db):
    """ADMIN institucional con TODOS los permisos operativos delegables."""
    u = _usuario(db, "admin")
    acceso = AccesoAdministrativo(
        usuario_id=u.id,
        perfil="administrador_general",
        tipo_alcance="institucional",
    )
    db.add(acceso)
    db.flush()
    for permiso in (
        "usuarios.ver",
        "usuarios.gestionar",
        "profesionales.ver",
        "profesionales.gestionar",
        "agenda.ver",
        "agenda.gestionar",
        "reportes.ver",
    ):
        db.add(AccesoAdminPermiso(acceso_admin_id=acceso.id, permiso=permiso))
    db.flush()
    return u


def _dependencia_de(endpoint):
    return inspect.signature(endpoint).parameters["current_user"].default.dependency


# ══════════════════════════════════════
# RBAC — acceso fail-closed, sin permiso nuevo
# ══════════════════════════════════════

def test_no_se_agrega_permiso_nuevo_al_catalogo():
    # El Inicio se apoya solo en permisos ya existentes.
    assert len(list(Permission)) == 21
    for permiso in PERMISOS_RESUMEN + PERMISOS_GESTION:
        assert isinstance(permiso, Permission)


def test_roles_gestionar_es_reservado_de_superadmin():
    # Es la pieza que impide que un ADMIN llegue a estos endpoints.
    assert Permission.ROLES_GESTIONAR in PERMISOS_RESERVADOS_SUPERADMIN
    assert Permission.ROLES_GESTIONAR in PERMISOS_RESUMEN
    assert Permission.ROLES_GESTIONAR in PERMISOS_GESTION


def test_endpoints_estan_conectados_a_su_combinacion_de_permisos():
    for endpoint, esperado in (
        (get_resumen_inicio, PERMISOS_RESUMEN),
        (get_gestion_inicio, PERMISOS_GESTION),
    ):
        dependencia = _dependencia_de(endpoint)
        cierre = inspect.getclosurevars(dependencia).nonlocals
        assert tuple(cierre["permisos"]) == tuple(esperado)


@pytest.mark.parametrize("permisos", [PERMISOS_RESUMEN, PERMISOS_GESTION])
def test_superadmin_activo_pasa(db, permisos):
    sa = _usuario(db, "superadmin")
    dep = requerir_permisos_institucionales(*permisos)
    assert dep(current_user=_cu(sa), db=db) == _cu(sa)


@pytest.mark.parametrize("permisos", [PERMISOS_RESUMEN, PERMISOS_GESTION])
def test_admin_con_todos_los_permisos_operativos_recibe_403(db, permisos):
    admin_u = _admin_operativo(db)
    dep = requerir_permisos_institucionales(*permisos)
    with pytest.raises(HTTPException) as exc:
        dep(current_user=_cu(admin_u), db=db)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["profesional", "estudiante"])
@pytest.mark.parametrize("permisos", [PERMISOS_RESUMEN, PERMISOS_GESTION])
def test_otros_roles_reciben_403(db, rol, permisos):
    u = _usuario(db, rol)
    dep = requerir_permisos_institucionales(*permisos)
    with pytest.raises(HTTPException) as exc:
        dep(current_user=_cu(u), db=db)
    assert exc.value.status_code == 403


def test_admin_sin_configuracion_administrativa_recibe_403(db):
    u = _usuario(db, "admin")
    dep = requerir_permisos_institucionales(*PERMISOS_RESUMEN)
    with pytest.raises(HTTPException) as exc:
        dep(current_user=_cu(u), db=db)
    assert exc.value.status_code == 403


def test_superadmin_desactivado_recibe_403(db):
    sa = _usuario(db, "superadmin", activo=False)
    dep = requerir_permisos_institucionales(*PERMISOS_RESUMEN)
    with pytest.raises(HTTPException) as exc:
        dep(current_user=_cu(sa), db=db)
    assert exc.value.status_code == 403


def test_usuario_inexistente_o_rol_invalido_falla_cerrado(db):
    dep = requerir_permisos_institucionales(*PERMISOS_RESUMEN)
    for cu in (
        {"id": 9999, "rol": "superadmin"},
        {"id": None, "rol": "superadmin"},
        {},
    ):
        with pytest.raises(HTTPException) as exc:
            dep(current_user=cu, db=db)
        assert exc.value.status_code == 403


@pytest.mark.parametrize("alcance", [
    None,
    AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset({"psicología"}),
    ),
])
def test_alcance_no_institucional_falla_cerrado(db, monkeypatch, alcance):
    sa = _usuario(db, "superadmin")
    monkeypatch.setattr(
        admin_inicio,
        "obtener_alcance_administrativo_efectivo",
        lambda *_a, **_k: alcance,
    )
    dep = requerir_permisos_institucionales(*PERMISOS_RESUMEN)
    with pytest.raises(HTTPException) as exc:
        dep(current_user=_cu(sa), db=db)
    assert exc.value.status_code == 403


# ══════════════════════════════════════
# Resumen — KPIs
# ══════════════════════════════════════

def test_resumen_sin_datos_devuelve_ceros_y_serie_completa(db):
    r = construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=True)

    assert r["kpis"] == {
        "estudiantes_registrados": 0,
        "profesionales_activos": 0,
        "citas_mes": 0,
        "especialidades": 0,
        "solicitudes_pendientes": 0,
        "incidencias": {"total": 0, "dias": 30},
    }
    assert len(r["citas_por_mes"]["meses"]) == 12
    assert all(m["cantidad"] == 0 for m in r["citas_por_mes"]["meses"])
    assert r["profesionales_mas_solicitados"]["items"] == []


def test_kpis_cuentan_datos_reales(db):
    e1 = _usuario(db, "estudiante")
    _usuario(db, "estudiante")
    _usuario(db, "profesional")
    _usuario(db, "superadmin")

    p_activo = _prof(db, "Ana", "Psicología")
    _prof(db, "Beto", "Nutrición", estado="licencia")
    _prof(db, "Caro", "Kinesiología", estado="inasistencia")

    _solicitud(db, p_activo, AHORA, "pendiente")
    _solicitud(db, p_activo, AHORA, "aprobado")
    _solicitud(db, p_activo, AHORA, "rechazado")

    _cita(db, e1, p_activo, "2026-09-10", "pendiente")
    _cita(db, e1, p_activo, "2026-09-11", "completada")
    _cita(db, e1, p_activo, "2026-09-12", "cancelada")
    _cita(db, e1, p_activo, "2026-09-13", "inasistencia")
    _cita(db, e1, p_activo, "2026-08-31", "completada")  # otro mes

    k = construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=True)["kpis"]

    assert k["estudiantes_registrados"] == 2
    assert k["profesionales_activos"] == 1
    assert k["solicitudes_pendientes"] == 1
    assert k["citas_mes"] == 2
    assert k["especialidades"] == 3


def test_especialidades_se_deduplican_normalizadas_y_omiten_vacias(db):
    _prof(db, "A", "Psicología")
    _prof(db, "B", "  psicología ")
    _prof(db, "C", "PSICOLOGÍA")
    _prof(db, "D", "Nutrición")
    _prof(db, "E", "")
    _prof(db, "F", None)

    k = construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=False)["kpis"]
    assert k["especialidades"] == 2


# ══════════════════════════════════════
# Resumen — incidencias (auditoría denegado/error, 30 días)
# ══════════════════════════════════════

def test_incidencias_cuentan_denegado_y_error_dentro_de_30_dias(db):
    u = _usuario(db, "superadmin")
    _auditoria(db, u, "denegado", AHORA - timedelta(days=1))
    _auditoria(db, u, "error", AHORA - timedelta(days=29))
    _auditoria(db, u, "exito", AHORA - timedelta(days=1))          # no cuenta
    _auditoria(db, u, "denegado", AHORA - timedelta(days=31))      # fuera de ventana
    _auditoria(db, u, "error", AHORA - timedelta(days=400))        # fuera de ventana

    k = construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=True)["kpis"]
    assert k["incidencias"] == {"total": 2, "dias": 30}


def test_incidencias_es_null_si_no_se_autoriza_auditoria(db):
    u = _usuario(db, "superadmin")
    _auditoria(db, u, "error", AHORA)

    k = construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=False)["kpis"]
    assert k["incidencias"] is None


def test_endpoint_resumen_incluye_incidencias_para_superadmin(db):
    sa = _usuario(db, "superadmin")
    _auditoria(db, sa, "denegado", datetime.now())

    r = get_resumen_inicio(db=db, current_user=_cu(sa))

    assert r["kpis"]["incidencias"]["total"] == 1


# ══════════════════════════════════════
# Resumen — citas por mes (12 meses)
# ══════════════════════════════════════

def test_citas_por_mes_ventana_de_12_meses_con_bordes(db):
    e = _usuario(db)
    p = _prof(db, "Ana")

    _cita(db, e, p, "2025-09-30")                 # anterior a la ventana
    _cita(db, e, p, "2025-10-01")                 # primer día incluido
    _cita(db, e, p, "2025-10-31", "completada")
    _cita(db, e, p, "2026-09-01")
    _cita(db, e, p, "2026-09-30", "completada")
    _cita(db, e, p, "2026-09-15", "cancelada")    # no cuenta
    _cita(db, e, p, "2026-10-01")                 # posterior a la ventana

    serie = construir_resumen(
        db, hoy=HOY, ahora=AHORA, incluir_incidencias=False
    )["citas_por_mes"]

    assert serie["desde"] == "2025-10"
    assert serie["hasta"] == "2026-09"
    assert [m["mes"] for m in serie["meses"]][:2] == ["2025-10", "2025-11"]
    assert len(serie["meses"]) == 12

    por_mes = {m["mes"]: m["cantidad"] for m in serie["meses"]}
    assert por_mes["2025-10"] == 2
    assert por_mes["2025-11"] == 0   # mes sin citas viene con 0
    assert por_mes["2026-09"] == 2
    assert sum(por_mes.values()) == 4
    assert "2025-09" not in por_mes and "2026-10" not in por_mes


def test_citas_por_mes_cruza_cambio_de_anio(db):
    r = construir_resumen(
        db, hoy=date(2026, 2, 10), ahora=AHORA, incluir_incidencias=False
    )["citas_por_mes"]

    assert r["desde"] == "2025-03"
    assert r["hasta"] == "2026-02"
    assert [m["mes"] for m in r["meses"]][9:] == ["2025-12", "2026-01", "2026-02"]


def test_citas_mes_coincide_con_el_ultimo_mes_de_la_serie(db):
    e = _usuario(db)
    p = _prof(db, "Ana")
    for dia in ("2026-09-01", "2026-09-19", "2026-09-28"):
        _cita(db, e, p, dia)

    r = construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=False)

    assert r["kpis"]["citas_mes"] == 3
    assert r["citas_por_mes"]["meses"][-1] == {"mes": "2026-09", "cantidad": 3}


# ══════════════════════════════════════
# Resumen — profesionales más solicitados (top 5, 90 días)
# ══════════════════════════════════════

def test_top_profesionales_ventana_de_90_dias_e_indica_periodo(db):
    e = _usuario(db)
    p = _prof(db, "Ana")

    desde = HOY - timedelta(days=89)
    _cita(db, e, p, desde.isoformat())                              # incluida
    _cita(db, e, p, (desde - timedelta(days=1)).isoformat())        # 90 días atrás: fuera
    _cita(db, e, p, HOY.isoformat())                                # hoy: incluida
    _cita(db, e, p, (HOY + timedelta(days=1)).isoformat())          # futura: fuera
    _cita(db, e, p, HOY.isoformat(), "cancelada")                   # no cuenta

    top = construir_resumen(
        db, hoy=HOY, ahora=AHORA, incluir_incidencias=False
    )["profesionales_mas_solicitados"]

    assert top["dias"] == 90
    assert top["desde"] == desde.isoformat()
    assert top["hasta"] == HOY.isoformat()
    assert [i["cantidad"] for i in top["items"]] == [2]


def test_top_profesionales_orden_desempate_y_limite_de_5(db):
    e = _usuario(db)
    cantidades = {"Ana": 3, "Beto": 3, "Caro": 2, "Dani": 2, "Eli": 1, "Fran": 1}
    for nombre, n in cantidades.items():
        p = _prof(db, nombre, "Psicología")
        for i in range(n):
            _cita(db, e, p, (HOY - timedelta(days=i)).isoformat(),
                  "completada" if i % 2 else "pendiente")

    items = construir_resumen(
        db, hoy=HOY, ahora=AHORA, incluir_incidencias=False
    )["profesionales_mas_solicitados"]["items"]

    assert [i["nombre"] for i in items] == ["Ana", "Beto", "Caro", "Dani", "Eli"]
    assert [i["cantidad"] for i in items] == [3, 3, 2, 2, 1]
    assert set(items[0]) == {
        "profesional_id", "nombre", "tratamiento", "especialidad", "cantidad"
    }


# ══════════════════════════════════════
# Gestión — últimos usuarios y solicitudes pendientes
# ══════════════════════════════════════

def test_gestion_vacia(db):
    g = construir_gestion(db)
    assert g["ultimos_usuarios"] == []
    assert g["solicitudes_pendientes"] == {"total": 0, "items": []}


def test_ultimos_usuarios_orden_limite_y_sin_datos_sensibles(db):
    for i in range(7):
        _usuario(db, "estudiante", nombre=f"Est {i}")

    g = construir_gestion(db)

    nombres = [u["nombre"] for u in g["ultimos_usuarios"]]
    assert nombres == ["Est 6", "Est 5", "Est 4", "Est 3", "Est 2"]
    for u in g["ultimos_usuarios"]:
        # Minimización: nada de correo, RUT ni contraseña.
        assert set(u) == {"id", "nombre", "rol", "fecha_creacion"}


def test_fecha_creacion_null_para_historicos_y_real_para_nuevos(db):
    historico = _usuario(db, "estudiante", nombre="Histórico")
    nuevo = _usuario(db, "estudiante", nombre="Nuevo")
    db.flush()
    db.execute(
        Usuario.__table__.update()
        .where(Usuario.id == historico.id)
        .values(fecha_creacion=None)
    )
    db.commit()

    por_nombre = {
        u["nombre"]: u["fecha_creacion"]
        for u in construir_gestion(db)["ultimos_usuarios"]
    }

    assert por_nombre["Histórico"] is None       # la UI mostrará "—"
    assert por_nombre["Nuevo"] is not None       # server_default real
    assert nuevo.id > historico.id


def test_solicitudes_pendientes_total_items_y_orden(db):
    p1 = _prof(db, "Ana", "Psicología")
    p2 = _prof(db, "Beto", "Nutrición")
    for i in range(6):
        _solicitud(db, p1 if i % 2 else p2, AHORA - timedelta(hours=i))
    _solicitud(db, p1, AHORA, "aprobado")
    _solicitud(db, p1, AHORA, "rechazado")

    s = construir_gestion(db)["solicitudes_pendientes"]

    assert s["total"] == 6
    assert len(s["items"]) == 5
    fechas = [i["fecha_solicitud"] for i in s["items"]]
    assert fechas == sorted(fechas, reverse=True)
    assert all(i["estado"] == "pendiente" for i in s["items"])
    assert {"profesional_nombre", "especialidad", "tipo", "hora_inicio",
            "hora_fin", "fecha_solicitud"} <= set(s["items"][0])
    assert s["items"][0]["profesional_nombre"] == "Beto"


def test_endpoint_gestion_para_superadmin(db):
    sa = _usuario(db, "superadmin")
    _prof(db, "Ana")

    g = get_gestion_inicio(db=db, current_user=_cu(sa))

    assert [u["rol"] for u in g["ultimos_usuarios"]] == ["superadmin"]


# ══════════════════════════════════════
# Performance — sin N+1
# ══════════════════════════════════════

def _poblar(db, n):
    e = _usuario(db)
    for i in range(n):
        p = _prof(db, f"Prof {i}", f"Esp {i}")
        _cita(db, e, p, HOY.isoformat())
        _solicitud(db, p, AHORA - timedelta(minutes=i))
        _usuario(db)


def test_resumen_usa_cantidad_constante_de_consultas(db):
    _poblar(db, 2)
    with contar_sentencias(db) as pocas:
        construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=True)

    _poblar(db, 30)
    with contar_sentencias(db) as muchas:
        construir_resumen(db, hoy=HOY, ahora=AHORA, incluir_incidencias=True)

    assert len(pocas) == len(muchas)
    assert len(muchas) <= 4  # kpis + especialidades + serie mensual + top


def test_gestion_usa_cantidad_constante_de_consultas(db):
    _poblar(db, 2)
    with contar_sentencias(db) as pocas:
        construir_gestion(db)

    _poblar(db, 30)
    with contar_sentencias(db) as muchas:
        construir_gestion(db)

    assert len(pocas) == len(muchas)
    assert len(muchas) <= 3  # usuarios + total pendientes + pendientes (JOIN)


# ══════════════════════════════════════
# /admin/auditoria — limit + actor_nombre (cambio aditivo)
# ══════════════════════════════════════

def _get_auditoria(db, **kwargs):
    kwargs.setdefault("fecha_inicio", None)
    kwargs.setdefault("fecha_fin", None)
    kwargs.setdefault("limit", 200)
    return admin.get_auditoria(db=db, current_user={"id": 1, "rol": "superadmin"}, **kwargs)


def test_auditoria_incluye_actor_nombre_y_conserva_campos_previos(db):
    u = _usuario(db, "superadmin", nombre="Sofía Súper")
    _auditoria(db, u, "exito", AHORA, accion="Cerró el centro")

    (fila,) = _get_auditoria(db)

    assert fila["actor_nombre"] == "Sofía Súper"
    assert {"id", "usuario_id", "actor_rol", "accion", "resultado",
            "detalle", "entidad", "entidad_id", "fecha"} <= set(fila)


def test_auditoria_actor_nombre_null_si_usuario_sin_nombre_o_ausente(db):
    sin_nombre = Usuario(correo="sn@sesaes.cl", password="x", rol="admin", nombre=None)
    db.add(sin_nombre)
    db.flush()
    _auditoria(db, sin_nombre, "exito", AHORA)
    db.add(Auditoria(usuario_id=None, actor_rol="admin", accion="Huérfano",
                     resultado="exito", fecha=AHORA - timedelta(days=1)))
    db.flush()

    filas = _get_auditoria(db)

    assert [f["actor_nombre"] for f in filas] == [None, None]


def test_auditoria_limit_ordena_desc_y_respeta_tope(db):
    u = _usuario(db, "superadmin")
    for i in range(5):
        _auditoria(db, u, "exito", AHORA - timedelta(hours=i), accion=f"A{i}")

    assert [f["accion"] for f in _get_auditoria(db, limit=2)] == ["A0", "A1"]
    assert len(_get_auditoria(db)) == 5
    assert len(_get_auditoria(db, limit=9999)) == 5   # tope 200, no error
    assert len(_get_auditoria(db, limit=0)) == 1      # mínimo 1
    assert len(_get_auditoria(db, limit=-7)) == 1


def test_auditoria_sigue_exigiendo_auditoria_ver():
    dependencia = _dependencia_de(admin.get_auditoria)
    permiso = inspect.getclosurevars(dependencia).nonlocals["permission"]
    assert permiso == Permission.AUDITORIA_VER
