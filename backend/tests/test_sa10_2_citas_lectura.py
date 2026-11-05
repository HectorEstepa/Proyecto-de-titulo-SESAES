from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Registrar modelos/relaciones antes de create_all.
import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
)
from app.rbac.permissions import Permission
from app.routers import admin
from app.routers import agenda


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
    )

    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _dependencia_de(endpoint):
    parametro = inspect.signature(
        endpoint
    ).parameters["current_user"]

    return parametro.default.dependency


def _permiso_de(endpoint):
    dependencia = _dependencia_de(
        endpoint
    )

    closure = inspect.getclosurevars(
        dependencia
    )

    return closure.nonlocals.get(
        "permission"
    )


def _usuario(
    db,
    *,
    correo,
    nombre,
    rut,
):
    usuario = Usuario(
        correo=correo,
        password="hash-sa10-2",
        rol="estudiante",
        nombre=nombre,
        rut=rut,
        activo=True,
    )

    db.add(usuario)
    db.flush()

    return usuario


def _profesional(
    db,
    *,
    nombre,
    especialidad,
    iniciales,
):
    profesional = Profesional(
        nombre=nombre,
        especialidad=especialidad,
        iniciales=iniciales,
        estado="activo",
    )

    db.add(profesional)
    db.flush()

    return profesional


def _cita(
    db,
    *,
    estudiante_id,
    profesional_id,
    fecha,
    hora,
    estado="pendiente",
    urgente=False,
    sobrecupo=False,
):
    cita = Cita(
        estudiante_id=estudiante_id,
        profesional_id=profesional_id,
        fecha=fecha,
        hora=hora,
        estado=estado,
        urgente=urgente,
        sobrecupo=sobrecupo,
        medicamento="SECRETO",
        observaciones="NO EXPONER",
        observaciones_atencion="CLINICO",
    )

    db.add(cita)
    db.flush()

    return cita


def _alcance_institucional():
    return AlcanceAdministrativoEfectivo(
        institucional=True,
        especialidades_normalizadas=frozenset(),
    )


def _alcance_nutricion():
    return AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset({
            "nutricion",
        }),
    )


def test_listar_profesionales_agenda_exige_exactamente_agenda_ver():
    assert (
        _permiso_de(
            agenda.listar_profesionales_agenda
        )
        is Permission.AGENDA_VER
    )


def test_listar_profesionales_agenda_devuelve_campos_minimos_y_scope(
    db_session,
    monkeypatch,
):
    nutricion = _profesional(
        db_session,
        nombre="Nutricionista Agenda",
        especialidad="Nutricion",
        iniciales="NA",
    )
    nutricion.tratamiento = "Nut."
    nutricion.duracion_min = 45
    nutricion.color_identificador = "#123456"

    _profesional(
        db_session,
        nombre="Odontologo Fuera Scope",
        especialidad="Odontologia",
        iniciales="OD",
    )
    db_session.commit()

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_nutricion()
        ),
    )

    resultado = agenda.listar_profesionales_agenda(
        db=db_session,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert len(resultado) == 1
    assert resultado[0]["id"] == nutricion.id
    assert set(resultado[0]) == {
        "id",
        "nombre",
        "tratamiento",
        "especialidad",
        "iniciales",
        "duracion_min",
        "estado",
        "color_identificador",
    }
    assert "correo" not in resultado[0]
    assert "rut" not in resultado[0]
    assert "usuario_id" not in resultado[0]


def test_listar_citas_admin_exige_exactamente_agenda_ver():
    assert (
        _permiso_de(
            agenda.listar_citas_admin
        )
        is Permission.AGENDA_VER
    )


def test_listar_citas_admin_no_exige_reportes_ver(
    monkeypatch,
):
    dependencia = _dependencia_de(
        agenda.listar_citas_admin
    )

    permisos_consultados = []

    def resolver(
        db,
        current_user,
        permission,
    ):
        permisos_consultados.append(
            permission
        )

        return (
            permission
            is Permission.AGENDA_VER
        )

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        resolver,
    )

    current_user = {
        "id": 50,
        "rol": "admin",
    }

    resultado = dependencia(
        current_user=current_user,
        db=object(),
    )

    assert resultado == current_user

    assert permisos_consultados == [
        Permission.AGENDA_VER,
    ]

    assert (
        Permission.REPORTES_VER
        not in permisos_consultados
    )


def test_sin_agenda_ver_dependencia_responde_403(
    monkeypatch,
):
    dependencia = _dependencia_de(
        agenda.listar_citas_admin
    )

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        lambda db, current_user, permission: False,
    )

    with pytest.raises(
        HTTPException
    ) as exc:
        dependencia(
            current_user={
                "id": 50,
                "rol": "admin",
            },
            db=object(),
        )

    assert exc.value.status_code == 403


def test_historial_sigue_exigiendo_reportes_ver():
    assert (
        _permiso_de(
            admin.get_historial_admin
        )
        is Permission.REPORTES_VER
    )


def test_listado_institucional_devuelve_solo_campos_operacionales(
    db_session,
    monkeypatch,
):
    estudiante = _usuario(
        db_session,
        correo="ana-sa10-2@utem.cl",
        nombre="Ana Perez",
        rut="11.111.111-1",
    )

    profesional = _profesional(
        db_session,
        nombre="Profesional Nutricion",
        especialidad="Nutricion",
        iniciales="PN",
    )

    _cita(
        db_session,
        estudiante_id=estudiante.id,
        profesional_id=profesional.id,
        fecha="2026-09-10",
        hora="10:00",
        urgente=True,
        sobrecupo=True,
    )

    db_session.commit()

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = agenda.listar_citas_admin(
        db=db_session,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 1

    fila = resultado[0]

    assert set(fila) == {
        "id",
        "estudiante",
        "estudiante_id",
        "rut",
        "estudiante_foto_url",
        "iniciales",
        "especialidad",
        "profesional",
        "profesional_id",
        "profesional_foto_url",
        "fecha",
        "hora",
        "estado",
        "urgente",
        "sobrecupo",
    }

    assert fila["estudiante"] == "Ana Perez"
    assert fila["especialidad"] == "Nutricion"
    assert fila["profesional"] == "Profesional Nutricion"
    assert fila["urgente"] is True
    assert fila["sobrecupo"] is True

    for campo in {
        "medicamento",
        "observaciones",
        "observaciones_atencion",
        "anamnesis",
        "diagnostico",
        "ficha",
        "cuestionario",
    }:
        assert campo not in fila


def test_listado_incluye_foto_de_perfil_via_relacion_existente_sin_query_extra(
    db_session,
    monkeypatch,
):
    """
    estudiante_foto_url debe salir del MISMO objeto Usuario que ya se
    consulta para nombre/rut (no agrega ninguna consulta nueva por
    estudiante): si el estudiante tiene foto_url, se expone tal cual; si
    no, sale None y el frontend cae de vuelta a las iniciales.
    """
    con_foto = _usuario(
        db_session,
        correo="con-foto-sa10-2@utem.cl",
        nombre="Bruno Rios",
        rut="22.222.222-2",
    )
    con_foto.foto_url = "https://cdn.sesaes.cl/perfiles/bruno.jpg"

    sin_foto = _usuario(
        db_session,
        correo="sin-foto-sa10-2@utem.cl",
        nombre="Carla Diaz",
        rut="33.333.333-3",
    )

    profesional = _profesional(
        db_session,
        nombre="Profesional Kinesiologia",
        especialidad="Kinesiologia",
        iniciales="PK",
    )

    _cita(
        db_session,
        estudiante_id=con_foto.id,
        profesional_id=profesional.id,
        fecha="2026-09-11",
        hora="09:00",
    )
    _cita(
        db_session,
        estudiante_id=sin_foto.id,
        profesional_id=profesional.id,
        fecha="2026-09-11",
        hora="10:00",
    )

    db_session.commit()

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = agenda.listar_citas_admin(
        db=db_session,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert len(resultado) == 2

    por_estudiante = {fila["estudiante"]: fila for fila in resultado}
    assert por_estudiante["Bruno Rios"]["estudiante_foto_url"] == "https://cdn.sesaes.cl/perfiles/bruno.jpg"
    assert por_estudiante["Carla Diaz"]["estudiante_foto_url"] is None



def test_alcance_especialidad_sin_profesionales_devuelve_vacio(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_nutricion()
        ),
    )

    resultado = agenda.listar_citas_admin(
        db=db_session,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == []

def test_alcance_especialidad_no_filtra_citas_ajenas(
    db_session,
    monkeypatch,
):
    estudiante_1 = _usuario(
        db_session,
        correo="nutri-sa10-2@utem.cl",
        nombre="Estudiante Nutri",
        rut="22.222.222-2",
    )

    estudiante_2 = _usuario(
        db_session,
        correo="odonto-sa10-2@utem.cl",
        nombre="Estudiante Odonto",
        rut="33.333.333-3",
    )

    nutricion = _profesional(
        db_session,
        nombre="Nutricionista",
        especialidad="Nutricion",
        iniciales="NU",
    )

    odontologia = _profesional(
        db_session,
        nombre="Odontologo",
        especialidad="Odontologia",
        iniciales="OD",
    )

    _cita(
        db_session,
        estudiante_id=estudiante_1.id,
        profesional_id=nutricion.id,
        fecha="2026-09-11",
        hora="09:00",
    )

    _cita(
        db_session,
        estudiante_id=estudiante_2.id,
        profesional_id=odontologia.id,
        fecha="2026-09-11",
        hora="10:00",
    )

    db_session.commit()

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_nutricion()
        ),
    )

    resultado = agenda.listar_citas_admin(
        db=db_session,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert len(resultado) == 1

    assert (
        resultado[0]["profesional_id"]
        == nutricion.id
    )

    assert (
        resultado[0]["especialidad"]
        == "Nutricion"
    )


def test_filtros_operacionales_reducen_resultado(
    db_session,
    monkeypatch,
):
    ana = _usuario(
        db_session,
        correo="ana-filtro-sa10-2@utem.cl",
        nombre="Ana Perez",
        rut="44.444.444-4",
    )

    pedro = _usuario(
        db_session,
        correo="pedro-filtro-sa10-2@utem.cl",
        nombre="Pedro Soto",
        rut="55.555.555-5",
    )

    profesional = _profesional(
        db_session,
        nombre="Profesional General",
        especialidad="Medicina General",
        iniciales="MG",
    )

    cita_objetivo = _cita(
        db_session,
        estudiante_id=ana.id,
        profesional_id=profesional.id,
        fecha="2026-09-12",
        hora="11:00",
        estado="pendiente",
    )

    _cita(
        db_session,
        estudiante_id=pedro.id,
        profesional_id=profesional.id,
        fecha="2026-09-20",
        hora="12:00",
        estado="completada",
    )

    db_session.commit()

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    resultado = agenda.listar_citas_admin(
        estudiante="Ana",
        fecha_inicio="2026-09-12",
        fecha_fin="2026-09-12",
        estado="pendiente",
        db=db_session,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert [
        fila["id"]
        for fila in resultado
    ] == [
        cita_objetivo.id,
    ]


def test_sa10_2d_matriz_backend_lecturas_y_mutaciones_exigen_permisos_exactos():
    lecturas_agenda = [
        agenda.listar_profesionales_agenda,
        agenda.listar_citas_admin,
        agenda.get_citas_profesional_admin,
        admin.get_resumen_dia,
        admin.get_proximas_citas,
        admin.listar_dias_cerrados,
        admin.citas_canceladas_por_dia_cerrado,
    ]

    for endpoint in lecturas_agenda:
        assert _permiso_de(endpoint) is Permission.AGENDA_VER

    mutaciones_agenda = [
        admin.crear_cita_urgente,
        admin.cancelar_cita_admin,
        admin.cambiar_prioridad_cita,
        admin.crear_dia_cerrado,
        admin.eliminar_dia_cerrado,
    ]

    for endpoint in mutaciones_agenda:
        assert _permiso_de(endpoint) is Permission.AGENDA_GESTIONAR

    lecturas_profesionales = [
        admin.get_profesionales_admin,
        admin.get_historial_estados,
    ]

    for endpoint in lecturas_profesionales:
        assert _permiso_de(endpoint) is Permission.PROFESIONALES_VER

    mutaciones_profesionales = [
        admin.crear_profesional,
        admin.actualizar_profesional,
        admin.eliminar_profesional,
        admin.cambiar_estado_profesional,
    ]

    for endpoint in mutaciones_profesionales:
        assert _permiso_de(endpoint) is Permission.PROFESIONALES_GESTIONAR

    lecturas_estudiantes = [
        admin.buscar_estudiantes,
        admin.listar_estudiantes,
        admin.perfil_estudiante_admin,
    ]

    for endpoint in lecturas_estudiantes:
        assert _permiso_de(endpoint) is Permission.USUARIOS_VER


def test_sa10_2d_agenda_ver_no_autoriza_dependencia_de_mutacion(
    monkeypatch,
):
    dependencia = _dependencia_de(
        admin.cancelar_cita_admin
    )

    permisos_consultados = []

    def resolver(
        db,
        current_user,
        permission,
    ):
        permisos_consultados.append(permission)
        return permission is Permission.AGENDA_VER

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        resolver,
    )

    with pytest.raises(HTTPException) as exc:
        dependencia(
            current_user={
                "id": 50,
                "rol": "admin",
            },
            db=object(),
        )

    assert exc.value.status_code == 403
    assert permisos_consultados == [
        Permission.AGENDA_GESTIONAR,
    ]


def test_sa10_2d_profesionales_ver_no_autoriza_dependencia_de_mutacion(
    monkeypatch,
):
    dependencia = _dependencia_de(
        admin.actualizar_profesional
    )

    permisos_consultados = []

    def resolver(
        db,
        current_user,
        permission,
    ):
        permisos_consultados.append(permission)
        return permission is Permission.PROFESIONALES_VER

    monkeypatch.setattr(
        "app.rbac.dependencies.tiene_permiso_efectivo",
        resolver,
    )

    with pytest.raises(HTTPException) as exc:
        dependencia(
            current_user={
                "id": 50,
                "rol": "admin",
            },
            db=object(),
        )

    assert exc.value.status_code == 403
    assert permisos_consultados == [
        Permission.PROFESIONALES_GESTIONAR,
    ]


def test_sa10_2d_agenda_profesional_respeta_scope_y_no_expone_campos_clinicos(
    db_session,
    monkeypatch,
):
    estudiante = _usuario(
        db_session,
        correo="scope-prof-sa10-2d@utem.cl",
        nombre="Estudiante Scope",
        rut="66.666.666-6",
    )

    nutricion = _profesional(
        db_session,
        nombre="Nutricionista Scope",
        especialidad="Nutricion",
        iniciales="NS",
    )

    odontologia = _profesional(
        db_session,
        nombre="Odontologo Fuera Scope",
        especialidad="Odontologia",
        iniciales="OF",
    )

    _cita(
        db_session,
        estudiante_id=estudiante.id,
        profesional_id=nutricion.id,
        fecha="2026-09-21",
        hora="09:00",
        urgente=True,
        sobrecupo=True,
    )

    db_session.commit()

    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_nutricion(),
    )

    resultado = agenda.get_citas_profesional_admin(
        nutricion.id,
        db=db_session,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert len(resultado) == 1
    assert set(resultado[0]) == {
        "id",
        "estudiante",
        "estudiante_id",
        "especialidad",
        "fecha",
        "hora",
        "estado",
        "urgente",
        "sobrecupo",
    }

    for campo in {
        "medicamento",
        "observaciones",
        "observaciones_atencion",
        "anamnesis",
        "diagnostico",
        "ficha",
        "cuestionario",
    }:
        assert campo not in resultado[0]

    with pytest.raises(HTTPException) as exc:
        agenda.get_citas_profesional_admin(
            odontologia.id,
            db=db_session,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403


def test_sa10_2d_endpoints_agenda_fallan_cerrado_sin_scope(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        agenda,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    current_user = {
        "id": 50,
        "rol": "admin",
    }

    with pytest.raises(HTTPException) as exc_profesionales:
        agenda.listar_profesionales_agenda(
            db=db_session,
            current_user=current_user,
        )

    assert exc_profesionales.value.status_code == 403

    with pytest.raises(HTTPException) as exc_citas:
        agenda.listar_citas_admin(
            db=db_session,
            current_user=current_user,
        )

    assert exc_citas.value.status_code == 403
