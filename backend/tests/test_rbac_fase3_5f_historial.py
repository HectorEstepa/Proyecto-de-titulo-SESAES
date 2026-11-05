# -*- coding: utf-8 -*-
"""
SESAES — Fase 3.5F, Prioridad 1: tests dirigidos para el bloque clínico de
app/routers/historial_clinico.py.

Regla central verificada en este archivo:

    PERMISSION + OWNERSHIP PROFESIONAL + RELACIÓN CLÍNICA CONCRETA = ACCESO

CITA != ATENCIÓN: solo estado == "completada" cuenta como atención
realizada para efectos de métricas (total_atenciones, última_visita,
días_desde_ultima_visita).

Deliberadamente NO se usa un FakeDB/FakeQuery que ignore los filtros (como
el de test_rbac_fase3_5f_profesionales.py): la relación clínica depende de
distinguir profesional_id, estudiante_id Y estado al mismo tiempo, así que
una cita cancelada de OTRO profesional/estudiante no puede colarse como si
fuera una cita pendiente propia. Para eso se usa una base SQLite real en
memoria con los modelos reales del proyecto — los filtros de SQLAlchemy se
ejecutan de verdad, no se simulan.

No toca profesionales.py, estudiante.py, solicitudes_horario.py, frontend,
ni agenda.py (fuera de alcance de este checkpoint).
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.init  # noqa: F401 — registra todas las relaciones SQLAlchemy
import app.models.solicitud_horario  # noqa: F401 — referenciado por Profesional pero ausente de models/init.py
from app.database import Base
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.models.historial_paciente import HistorialPaciente
from app.rbac.permissions import Permission
from app.routers import historial_clinico as m


# ══════════════════════════════════════════════════════════════════
# DB real en memoria (SQLite) — filtros de verdad, no simulados.
# ══════════════════════════════════════════════════════════════════
@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_prof_y_usuarios(db, prof_id=5, usuario_prof_id=10, estudiante_id=99):
    db.add(Usuario(id=usuario_prof_id, correo="prof@utem.cl", password="x", rol="profesional", nombre="Dra. Owner"))
    db.add(Usuario(id=estudiante_id, correo="ana@utem.cl", password="x", rol="estudiante", nombre="Ana", rut="1-9"))
    db.add(Profesional(id=prof_id, usuario_id=usuario_prof_id, nombre="Dra. Owner", especialidad="Medicina", estado="activo"))
    db.commit()


def _cita(db, profesional_id=5, estudiante_id=99, estado="pendiente", fecha="2024-01-01", hora="09:00"):
    c = Cita(profesional_id=profesional_id, estudiante_id=estudiante_id, estado=estado, fecha=fecha, hora=hora)
    db.add(c)
    db.commit()
    return c


def _ficha(db, profesional_id=5, estudiante_id=99, respuestas=None):
    f = HistorialPaciente(profesional_id=profesional_id, estudiante_id=estudiante_id, respuestas=respuestas or {})
    db.add(f)
    db.commit()
    return f


PROF_USER = {"id": 10, "rol": "profesional"}
OTRO_PROF_USER = {"id": 999, "rol": "profesional"}


# ══════════════════════════════════════════════════════════════════
# A. _tiene_relacion_clinica
# ══════════════════════════════════════════════════════════════════
def test_relacion_via_historial_paciente_autoriza(db):
    _seed_prof_y_usuarios(db)
    _ficha(db)
    assert m._tiene_relacion_clinica(5, 99, db) is True


def test_relacion_via_cita_pendiente_autoriza(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="pendiente")
    assert m._tiene_relacion_clinica(5, 99, db) is True


def test_relacion_via_cita_completada_autoriza(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada")
    assert m._tiene_relacion_clinica(5, 99, db) is True


def test_relacion_cancelada_sin_historial_no_autoriza(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="cancelada")
    assert m._tiene_relacion_clinica(5, 99, db) is False


def test_relacion_inasistencia_sin_historial_no_autoriza(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="inasistencia")
    assert m._tiene_relacion_clinica(5, 99, db) is False


def test_sin_ninguna_relacion_no_autoriza(db):
    _seed_prof_y_usuarios(db)
    assert m._tiene_relacion_clinica(5, 99, db) is False


def test_relacion_no_se_contagia_de_otro_estudiante(db):
    """Una cita pendiente con OTRO estudiante no autoriza el par consultado."""
    _seed_prof_y_usuarios(db)
    _cita(db, estudiante_id=100, estado="pendiente")
    assert m._tiene_relacion_clinica(5, 99, db) is False


def test_relacion_no_se_contagia_de_otro_profesional(db):
    """Una cita pendiente del estudiante con OTRO profesional no autoriza a este."""
    db.add(Usuario(id=10, correo="p1@utem.cl", password="x", rol="profesional", nombre="P1"))
    db.add(Usuario(id=11, correo="p2@utem.cl", password="x", rol="profesional", nombre="P2"))
    db.add(Usuario(id=99, correo="ana@utem.cl", password="x", rol="estudiante", nombre="Ana"))
    db.add(Profesional(id=5, usuario_id=10, nombre="P1", especialidad="Medicina", estado="activo"))
    db.add(Profesional(id=6, usuario_id=11, nombre="P2", especialidad="Medicina", estado="activo"))
    db.commit()
    _cita(db, profesional_id=6, estudiante_id=99, estado="pendiente")
    assert m._tiene_relacion_clinica(5, 99, db) is False


# ══════════════════════════════════════════════════════════════════
# B/C/F. _exigir_acceso_clinico — PERMISSION + OWNERSHIP + RELACIÓN
# ══════════════════════════════════════════════════════════════════
def test_exigir_acceso_clinico_profesional_ajeno_403(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="pendiente")
    with pytest.raises(HTTPException) as exc:
        m._exigir_acceso_clinico(OTRO_PROF_USER, 5, 99, db, Permission.FICHA_VER_ASIGNADA)
    assert exc.value.status_code == 403


def test_exigir_acceso_clinico_sin_relacion_403(db):
    _seed_prof_y_usuarios(db)
    with pytest.raises(HTTPException) as exc:
        m._exigir_acceso_clinico(PROF_USER, 5, 99, db, Permission.FICHA_VER_ASIGNADA)
    assert exc.value.status_code == 403


def test_exigir_acceso_clinico_dueno_con_relacion_pasa(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada")
    m._exigir_acceso_clinico(PROF_USER, 5, 99, db, Permission.FICHA_VER_ASIGNADA)  # no debe lanzar


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_exigir_acceso_clinico_admin_y_superadmin_sin_bypass(db, rol):
    """ADMIN/SUPERADMIN no tienen FICHA_VER_ASIGNADA por defecto => 403, con o sin relación."""
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada")
    with pytest.raises(HTTPException) as exc:
        m._exigir_acceso_clinico({"id": 10, "rol": rol}, 5, 99, db, Permission.FICHA_VER_ASIGNADA)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_get_ficha_endpoint_admin_superadmin_403(db, rol):
    """SA-6.3: un rol administrativo no puede leer una ficha clinica."""
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada")

    with pytest.raises(HTTPException) as exc:
        m.obtener_historial(
            profesional_id=5,
            estudiante_id=99,
            db=db,
            current_user={"id": 10, "rol": rol},
        )

    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_put_ficha_endpoint_admin_superadmin_403(db, rol):
    """SA-6.3: un rol administrativo no puede modificar una ficha clinica."""
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada")

    with pytest.raises(HTTPException) as exc:
        m.guardar_historial(
            profesional_id=5,
            estudiante_id=99,
            datos=m.HistorialGuardarIn(respuestas={"1": "dato-clinico"}),
            db=db,
            current_user={"id": 10, "rol": rol},
        )

    assert exc.value.status_code == 403

    historial = db.query(HistorialPaciente).filter(
        HistorialPaciente.profesional_id == 5,
        HistorialPaciente.estudiante_id == 99,
    ).first()

    assert historial is None


def test_get_ficha_exige_ficha_ver_asignada():
    source = inspect.getsource(m.obtener_historial)
    assert "Permission.FICHA_VER_ASIGNADA" in source


def test_put_ficha_exige_ficha_editar_asignada():
    source = inspect.getsource(m.guardar_historial)
    assert "Permission.FICHA_EDITAR_ASIGNADA" in source


def test_get_ficha_endpoint_sin_relacion_403(db):
    _seed_prof_y_usuarios(db)
    with pytest.raises(HTTPException) as exc:
        m.obtener_historial(profesional_id=5, estudiante_id=99, db=db, current_user=PROF_USER)
    assert exc.value.status_code == 403


def test_get_ficha_endpoint_con_cita_pendiente_permite(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="pendiente")
    resultado = m.obtener_historial(profesional_id=5, estudiante_id=99, db=db, current_user=PROF_USER)
    assert resultado["estudiante_nombre"] == "Ana"


def test_put_ficha_endpoint_sin_relacion_403(db):
    _seed_prof_y_usuarios(db)
    with pytest.raises(HTTPException) as exc:
        m.guardar_historial(
            profesional_id=5, estudiante_id=99,
            datos=m.HistorialGuardarIn(respuestas={"1": "ok"}),
            db=db, current_user=PROF_USER,
        )
    assert exc.value.status_code == 403


def test_put_ficha_endpoint_con_cita_completada_permite(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada")
    m.guardar_historial(
        profesional_id=5, estudiante_id=99,
        datos=m.HistorialGuardarIn(respuestas={"1": "ok"}),
        db=db, current_user=PROF_USER,
    )
    historial = db.query(HistorialPaciente).filter(
        HistorialPaciente.profesional_id == 5, HistorialPaciente.estudiante_id == 99
    ).first()
    assert historial is not None
    assert historial.respuestas == {"1": "ok"}


# ══════════════════════════════════════════════════════════════════
# D. cuestionario-estudiante GET/POST — solo pendiente/completada
# ══════════════════════════════════════════════════════════════════
ESTUDIANTE_USER = {"id": 99, "rol": "estudiante"}


def _solicitar_cuestionario(db, profesional_id=5, estudiante_id=99):
    """El cuestionario previo es opcional: el profesional debe haberlo pedido."""
    from app.models.cuestionario_solicitud import CuestionarioEnvio
    db.add(CuestionarioEnvio(profesional_id=profesional_id, estudiante_id=estudiante_id, solicitado=True))
    db.commit()


@pytest.mark.parametrize("estado", ["pendiente", "completada"])
def test_cuestionario_get_permitido_con_cita_valida(db, estado):
    _seed_prof_y_usuarios(db)
    _cita(db, estado=estado)
    _solicitar_cuestionario(db)
    resultado = m.obtener_cuestionario_para_estudiante(profesional_id=5, db=db, current_user=ESTUDIANTE_USER)
    assert resultado["profesional_nombre"] == "Dra. Owner"


@pytest.mark.parametrize("estado", ["cancelada", "inasistencia"])
def test_cuestionario_get_bloqueado_con_cita_invalida(db, estado):
    _seed_prof_y_usuarios(db)
    _cita(db, estado=estado)
    with pytest.raises(HTTPException) as exc:
        m.obtener_cuestionario_para_estudiante(profesional_id=5, db=db, current_user=ESTUDIANTE_USER)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("estado", ["pendiente", "completada"])
def test_cuestionario_post_permitido_con_cita_valida(db, estado):
    _seed_prof_y_usuarios(db)
    _cita(db, estado=estado)
    _solicitar_cuestionario(db)
    resultado = m.responder_cuestionario_estudiante(
        profesional_id=5, datos=m.RespuestasEstudianteIn(respuestas={"1": "no"}),
        db=db, current_user=ESTUDIANTE_USER,
    )
    assert resultado["message"].startswith("Cuestionario enviado")


@pytest.mark.parametrize("estado", ["cancelada", "inasistencia"])
def test_cuestionario_post_bloqueado_con_cita_invalida(db, estado):
    _seed_prof_y_usuarios(db)
    _cita(db, estado=estado)
    with pytest.raises(HTTPException) as exc:
        m.responder_cuestionario_estudiante(
            profesional_id=5, datos=m.RespuestasEstudianteIn(respuestas={"1": "no"}),
            db=db, current_user=ESTUDIANTE_USER,
        )
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# E/F. Métricas: SOLO citas completadas cuentan como atención.
# ══════════════════════════════════════════════════════════════════
def test_obtener_historial_metricas_solo_cuentan_completadas(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada", fecha="2024-01-10")
    _cita(db, estado="pendiente", fecha="2024-06-01")   # más reciente, pero NO cuenta
    resultado = m.obtener_historial(profesional_id=5, estudiante_id=99, db=db, current_user=PROF_USER)
    assert resultado["total_atenciones"] == 1
    assert resultado["ultima_visita"] == "2024-01-10"


def test_obtener_historial_pendiente_mas_reciente_no_reemplaza_ultima_visita(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada", fecha="2024-01-10")
    _cita(db, estado="pendiente", fecha="2024-12-31")
    resultado = m.obtener_historial(profesional_id=5, estudiante_id=99, db=db, current_user=PROF_USER)
    assert resultado["ultima_visita"] == "2024-01-10"


def test_obtener_historial_cancelada_e_inasistencia_mas_recientes_no_reemplazan_ultima_visita(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada", fecha="2024-01-10")
    _cita(db, estado="cancelada", fecha="2024-11-01")
    _cita(db, estado="inasistencia", fecha="2024-12-01")
    resultado = m.obtener_historial(profesional_id=5, estudiante_id=99, db=db, current_user=PROF_USER)
    assert resultado["ultima_visita"] == "2024-01-10"
    assert resultado["total_atenciones"] == 1


def test_obtener_historial_dias_desde_ultima_visita_usa_ultima_completada(db):
    from datetime import date, timedelta
    _seed_prof_y_usuarios(db)
    hace_5_dias = (date.today() - timedelta(days=5)).isoformat()
    hoy = date.today().isoformat()
    _cita(db, estado="completada", fecha=hace_5_dias)
    _cita(db, estado="pendiente", fecha=hoy)
    resultado = m.obtener_historial(profesional_id=5, estudiante_id=99, db=db, current_user=PROF_USER)
    assert resultado["dias_desde_ultima_visita"] == 5


def test_listar_pacientes_atendidos_metricas_solo_cuentan_completadas(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada", fecha="2024-01-10")
    _cita(db, estado="cancelada", fecha="2024-12-01")
    resultado = m.listar_pacientes_atendidos(profesional_id=5, anio=None, busqueda=None, carrera=None, db=db, current_user=PROF_USER)
    assert len(resultado) == 1
    assert resultado[0]["total_atenciones"] == 1
    assert resultado[0]["ultima_visita"] == "2024-01-10"


def test_listar_pacientes_atendidos_incluye_paciente_solo_con_cita_pendiente(db):
    """Sección E: puede incluir paciente con cita pendiente para preparación clínica."""
    _seed_prof_y_usuarios(db)
    _cita(db, estado="pendiente", fecha="2024-06-01")
    resultado = m.listar_pacientes_atendidos(profesional_id=5, anio=None, busqueda=None, carrera=None, db=db, current_user=PROF_USER)
    assert len(resultado) == 1
    assert resultado[0]["total_atenciones"] == 0
    assert resultado[0]["ultima_visita"] is None


def test_obtener_historial_completada_con_fecha_invalida_suma_atencion_pero_no_ultima_visita(db):
    """
    Una cita completada con fecha inválida/legacy sigue siendo una
    atención real (total_atenciones aumenta), pero esa fecha no puede
    usarse para ultima_visita/dias_desde_ultima_visita.
    """
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada", fecha="2024-01-10")
    _cita(db, estado="completada", fecha="fecha-legacy-invalida")
    resultado = m.obtener_historial(profesional_id=5, estudiante_id=99, db=db, current_user=PROF_USER)
    assert resultado["total_atenciones"] == 2
    assert resultado["ultima_visita"] == "2024-01-10"


def test_listar_pacientes_completada_con_fecha_invalida_suma_atencion_pero_no_ultima_visita(db):
    _seed_prof_y_usuarios(db)
    _cita(db, estado="completada", fecha="2024-01-10")
    _cita(db, estado="completada", fecha="fecha-legacy-invalida")
    resultado = m.listar_pacientes_atendidos(profesional_id=5, anio=None, busqueda=None, carrera=None, db=db, current_user=PROF_USER)
    assert len(resultado) == 1
    assert resultado[0]["total_atenciones"] == 2
    assert resultado[0]["ultima_visita"] == "2024-01-10"


def test_listar_pacientes_atendidos_exige_ficha_ver_asignada():
    source = inspect.getsource(m.listar_pacientes_atendidos)
    assert "Permission.FICHA_VER_ASIGNADA" in source


def test_listar_pacientes_atendidos_rechaza_profesional_ajeno(db):
    _seed_prof_y_usuarios(db)
    with pytest.raises(HTTPException) as exc:
        m.listar_pacientes_atendidos(profesional_id=5, anio=None, busqueda=None, carrera=None, db=db, current_user=OTRO_PROF_USER)
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# H. GET /cuestionarios-pendientes/{estudiante_id} (corrección final
# Fase 3.5F): recurso propio del estudiante dentro del dominio clínico
# — mismo criterio de ownership estricto que estudiante.py.
# roles_permitidos ya NO incluye "admin".
# ══════════════════════════════════════════════════════════════════
def test_cuestionarios_pendientes_ya_no_incluye_admin_en_roles_permitidos():
    source = inspect.getsource(m.cuestionarios_pendientes)
    assert '["estudiante", "admin"]' not in source
    assert '["estudiante"]' in source


def test_cuestionarios_pendientes_estudiante_dueno_permitido(db):
    """1. estudiante dueño -> permitido (no lanza, devuelve lista)."""
    _seed_prof_y_usuarios(db)
    resultado = m.cuestionarios_pendientes(estudiante_id=99, db=db, current_user={"id": 99, "rol": "estudiante"})
    assert isinstance(resultado, list)


def test_cuestionarios_pendientes_estudiante_otro_id_da_403(db):
    """2. estudiante con otro estudiante_id -> 403."""
    _seed_prof_y_usuarios(db)
    with pytest.raises(HTTPException) as exc:
        m.cuestionarios_pendientes(estudiante_id=99, db=db, current_user={"id": 100, "rol": "estudiante"})
    assert exc.value.status_code == 403


def test_cuestionarios_pendientes_admin_da_403(db):
    """3. ADMIN -> 403."""
    _seed_prof_y_usuarios(db)
    with pytest.raises(HTTPException) as exc:
        m.cuestionarios_pendientes(estudiante_id=99, db=db, current_user={"id": 1, "rol": "admin"})
    assert exc.value.status_code == 403


def test_cuestionarios_pendientes_superadmin_da_403(db):
    """4. SUPERADMIN -> 403."""
    _seed_prof_y_usuarios(db)
    with pytest.raises(HTTPException) as exc:
        m.cuestionarios_pendientes(estudiante_id=99, db=db, current_user={"id": 1, "rol": "superadmin"})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_cuestionarios_pendientes_admin_superadmin_con_id_coincidente_da_403(db, rol):
    """5. ADMIN/SUPERADMIN con id numéricamente coincidente -> 403 (rechazo por rol, no solo por ownership)."""
    _seed_prof_y_usuarios(db)
    with pytest.raises(HTTPException) as exc:
        m.cuestionarios_pendientes(estudiante_id=99, db=db, current_user={"id": 99, "rol": rol})
    assert exc.value.status_code == 403
