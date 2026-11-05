# -*- coding: utf-8 -*-
"""
Documentos clínicos (receta y justificativo): emisión al completar la
atención, capacidades por especialidad, folio/huella, anulación, PDF con QR
y validación pública con límite de uso.

DB real en SQLite en memoria (mismo patrón que test_sa11_3b).
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.cita import Cita
from app.models.documento_clinico import DocumentoClinico
from app.models.especialidad_capability import EspecialidadCapability
from app.models.notificacion import Notificacion
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rate_limiter import limiter
from app.rbac.clinical_capabilities import ClinicalCapability, normalizar_especialidad
from app.routers import documentos_clinicos as docs_router
from app.routers import profesionales as prof_router
from app.schemas import CompletarCitaBody, JustificativoIn, RecetaIn
from app.services import documento_clinico_service as svc

PROF_ID, USUARIO_PROF_ID, EST_ID, CITA_ID = 5, 10, 99, 7
PROF_USER = {"id": USUARIO_PROF_ID, "rol": "profesional"}
EST_USER = {"id": EST_ID, "rol": "estudiante"}
OTRO_EST_USER = {"id": 123, "rol": "estudiante"}

RECETA = {"medicamentos": [{"medicamento": "Amoxicilina 500 mg cápsula", "dosis": "1 cápsula",
                            "frecuencia": "Cada 8 horas", "periodo": "7 días",
                            "indicacion": "Tomar con alimentos"}]}
JUSTIFICATIVO = {"reposo": True, "reposo_desde": "2020-01-01", "reposo_hasta": "2020-01-03",
                 "restricciones": "Sin educación física", "observaciones": "Control en 3 días"}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _setup(db, capacidades=("emitir_receta", "emitir_justificativo"), especialidad="Enfermería"):
    db.add(Usuario(id=USUARIO_PROF_ID, correo="p@utem.cl", password="x", rol="profesional", activo=True, nombre="Ana"))
    db.add(Usuario(id=EST_ID, correo="e@utem.cl", password="x", rol="estudiante", activo=True,
                   nombre="Valentina Torres Silva", rut="19.876.543-2", carrera="Estudiante"))
    db.add(Usuario(id=123, correo="o@utem.cl", password="x", rol="estudiante", activo=True, nombre="Otro"))
    db.add(Profesional(id=PROF_ID, usuario_id=USUARIO_PROF_ID, nombre="Ana Pérez", tratamiento="Dra.",
                       especialidad=especialidad, iniciales="AP", rut="12.345.678-5"))
    db.add(Cita(id=CITA_ID, profesional_id=PROF_ID, estudiante_id=EST_ID, estado="pendiente",
                fecha="2020-01-01", hora="09:00"))
    for c in capacidades:
        db.add(EspecialidadCapability(especialidad_normalizada=normalizar_especialidad(especialidad),
                                      capability=c, activo=True))
    db.commit()


def _completar(db, **kw):
    return prof_router.completar_cita(
        prof_id=PROF_ID, cita_id=CITA_ID, body=CompletarCitaBody(**kw), db=db, current_user=PROF_USER)


# ───────────────────────── emisión ─────────────────────────
def test_completar_con_receta_y_justificativo_emite_ambos(db):
    _setup(db)
    r = _completar(db, receta=RECETA, justificativo=JUSTIFICATIVO)

    assert {d["tipo"] for d in r["documentos"]} == {"receta", "justificativo"}
    docs = db.query(DocumentoClinico).all()
    assert len(docs) == 2
    for d in docs:
        assert re.fullmatch(r"SES-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", d.folio)
        assert d.estado == "vigente" and svc.huella_es_valida(d)
        assert d.contenido["profesional"]["nombre"] == "Dra. Ana Pérez"
    assert db.query(Cita).get(CITA_ID).estado == "completada"


def test_el_justificativo_nunca_incluye_diagnostico(db):
    _setup(db)
    _completar(db, justificativo=JUSTIFICATIVO)
    doc = db.query(DocumentoClinico).one()
    assert "diagnostico" not in str(doc.contenido).lower()
    assert doc.contenido["reposo"]["dias"] == 3


def test_sin_documentos_la_respuesta_es_la_de_siempre(db):
    _setup(db)
    assert _completar(db) == {"message": "Cita marcada como completada"}
    assert db.query(DocumentoClinico).count() == 0
    assert db.query(Notificacion).count() == 0


def test_emitir_notifica_al_estudiante_sin_contenido_clinico(db):
    _setup(db)
    _completar(db, receta=RECETA)
    n = db.query(Notificacion).one()
    assert n.usuario_id == EST_ID
    assert "Amoxicilina" not in n.mensaje and "historial" in n.mensaje


def test_sin_capacidad_403_y_no_se_muta_nada(db):
    _setup(db, capacidades=("emitir_justificativo",))          # puede justificativo, NO receta
    with pytest.raises(HTTPException) as exc:
        _completar(db, receta=RECETA, justificativo=JUSTIFICATIVO)
    assert exc.value.status_code == 403
    db.expire_all()
    assert db.query(Cita).get(CITA_ID).estado == "pendiente"   # la cita no se completó
    assert db.query(DocumentoClinico).count() == 0             # y tampoco salió el justificativo


def test_segunda_receta_vigente_en_la_misma_atencion_409(db):
    _setup(db)
    _completar(db, receta=RECETA)
    with pytest.raises(HTTPException) as exc:
        _completar(db, receta=RECETA)
    assert exc.value.status_code == 409
    assert db.query(DocumentoClinico).count() == 1


def test_validaciones_de_esquema():
    with pytest.raises(Exception):
        RecetaIn(medicamentos=[])
    with pytest.raises(Exception):
        JustificativoIn(reposo=True)                                     # falta desde/hasta
    with pytest.raises(Exception):
        JustificativoIn(reposo=True, reposo_desde="2020-01-05", reposo_hasta="2020-01-01")
    assert JustificativoIn(reposo=False, reposo_desde="2020-01-05").reposo_desde is None


# ───────────────────────── consulta / PDF / anulación ─────────────────────────
def test_acceso_a_documentos_solo_estudiante_dueno_o_profesional(db):
    _setup(db)
    _completar(db, receta=RECETA)
    doc = db.query(DocumentoClinico).one()

    assert len(docs_router.listar_documentos_de_cita(CITA_ID, db=db, current_user=EST_USER)) == 1
    assert len(docs_router.listar_documentos_de_cita(CITA_ID, db=db, current_user=PROF_USER)) == 1
    for intruso in (OTRO_EST_USER, {"id": 1, "rol": "admin"}):
        with pytest.raises(HTTPException) as exc:
            docs_router.descargar_documento_pdf(doc.id, db=db, current_user=intruso)
        assert exc.value.status_code == 403


@pytest.mark.parametrize("payload,kw", [(RECETA, "receta"), (JUSTIFICATIVO, "justificativo")])
def test_pdf_se_genera_con_qr(db, payload, kw):
    _setup(db)
    _completar(db, **{kw: payload})
    doc = db.query(DocumentoClinico).one()
    resp = docs_router.descargar_documento_pdf(doc.id, db=db, current_user=EST_USER)
    assert resp.media_type == "application/pdf"
    assert resp.body.startswith(b"%PDF") and len(resp.body) > 3000
    assert doc.folio in resp.headers["content-disposition"]


def test_anular_solo_el_profesional_emisor_y_el_pdf_queda_marcado(db):
    _setup(db)
    _completar(db, receta=RECETA)
    doc = db.query(DocumentoClinico).one()

    with pytest.raises(HTTPException) as exc:
        docs_router.anular_documento(doc.id, docs_router.AnularIn(motivo="error de dosis"), db=db, current_user=EST_USER)
    assert exc.value.status_code == 403

    docs_router.anular_documento(doc.id, docs_router.AnularIn(motivo="error de dosis"), db=db, current_user=PROF_USER)
    db.refresh(doc)
    assert doc.estado == "anulado" and doc.motivo_anulacion == "error de dosis"
    assert docs_router.descargar_documento_pdf(doc.id, db=db, current_user=EST_USER).body.startswith(b"%PDF")

    with pytest.raises(HTTPException) as exc:
        docs_router.anular_documento(doc.id, docs_router.AnularIn(motivo="otra vez"), db=db, current_user=PROF_USER)
    assert exc.value.status_code == 409


def test_tras_anular_se_puede_emitir_una_nueva(db):
    _setup(db)
    _completar(db, receta=RECETA)
    doc = db.query(DocumentoClinico).one()
    docs_router.anular_documento(doc.id, docs_router.AnularIn(motivo="error de dosis"), db=db, current_user=PROF_USER)
    _completar(db, receta=RECETA)
    assert db.query(DocumentoClinico).filter_by(estado="vigente").count() == 1


# ───────────────────────── validación pública ─────────────────────────
def test_validacion_vigente_enmascara_al_estudiante_y_no_expone_contenido_clinico(db):
    _setup(db)
    _completar(db, receta=RECETA)
    doc = db.query(DocumentoClinico).one()

    r = svc.validar_publicamente(db, doc.folio)
    assert r["valido"] is True and r["estado"] == "vigente"
    assert r["estudiante"] == "Valentina T. S."
    assert r["tipo"] == "Receta médica" and r["emitido_por"] == "Dra. Ana Pérez"
    assert "Amoxicilina" not in str(r) and "19.876.543-2" not in str(r)


def test_validacion_acepta_codigo_sin_guiones_y_en_minusculas(db):
    _setup(db)
    _completar(db, receta=RECETA)
    doc = db.query(DocumentoClinico).one()
    assert svc.validar_publicamente(db, doc.folio.replace("-", "").lower())["valido"] is True


def test_validacion_detecta_documento_modificado(db):
    _setup(db)
    _completar(db, receta=RECETA)
    doc = db.query(DocumentoClinico).one()
    adulterado = dict(doc.contenido)
    adulterado["medicamentos"] = [{**adulterado["medicamentos"][0], "dosis": "10 cápsulas"}]
    doc.contenido = adulterado
    db.commit()
    assert svc.validar_publicamente(db, doc.folio) == {"valido": False, "estado": "modificado"}


def test_validacion_anulado_y_no_encontrado(db):
    _setup(db)
    _completar(db, receta=RECETA)
    doc = db.query(DocumentoClinico).one()
    docs_router.anular_documento(doc.id, docs_router.AnularIn(motivo="error de dosis"), db=db, current_user=PROF_USER)
    r = svc.validar_publicamente(db, doc.folio)
    assert r["valido"] is False and r["estado"] == "anulado"
    assert svc.validar_publicamente(db, "SES-AAAA-BBBB-CCCC") == {"valido": False, "estado": "no_encontrado"}


def test_endpoint_publico_sin_sesion_y_con_limite_de_uso(db):
    """La ruta pública no pide sesión y frena el barrido de códigos (20/min)."""
    _setup(db)
    _completar(db, receta=RECETA)
    folio = db.query(DocumentoClinico).one().folio

    app = FastAPI()
    app.state.limiter = limiter
    limiter.reset()

    def pedido():
        return Request({"type": "http", "method": "GET", "path": "/documentos/validar/x", "headers": [],
                        "query_string": b"", "client": ("203.0.113.9", 5000), "server": ("test", 80),
                        "scheme": "http", "app": app})

    # Sin current_user ni token: la función no los recibe.
    ok = docs_router.validar_documento(request=pedido(), codigo=folio, db=db)
    assert ok["valido"] is True

    with pytest.raises(RateLimitExceeded):
        for _ in range(25):
            docs_router.validar_documento(request=pedido(), codigo="SES-AAAA-BBBB-CCCC", db=db)
    limiter.reset()


def test_enmascarar_nombre():
    assert svc.enmascarar_nombre("Valentina Torres Silva") == "Valentina T. S."
    assert svc.enmascarar_nombre("Ana") == "Ana"
    assert svc.enmascarar_nombre(None) == "—"


# ───────────────────── capacidades de fábrica por especialidad ─────────────────────
def test_un_medico_emite_receta_y_justificativo_sin_ninguna_autorizacion(db):
    _setup(db, capacidades=(), especialidad="Medicina General")      # ninguna regla en base de datos
    r = _completar(db, receta=RECETA, justificativo=JUSTIFICATIVO)
    assert {d["tipo"] for d in r["documentos"]} == {"receta", "justificativo"}


def test_un_psicologo_certifica_pero_no_receta(db):
    _setup(db, capacidades=(), especialidad="Psicología")
    with pytest.raises(HTTPException) as exc:
        _completar(db, receta=RECETA)
    assert exc.value.status_code == 403
    _completar(db, justificativo=JUSTIFICATIVO)
    assert db.query(DocumentoClinico).one().tipo == "justificativo"


def test_enfermeria_no_trae_nada_de_fabrica_y_requiere_autorizacion_adicional(db):
    _setup(db, capacidades=(), especialidad="Enfermería")
    with pytest.raises(HTTPException) as exc:
        _completar(db, receta=RECETA)
    assert exc.value.status_code == 403


# ───────────────────── indicador del Inicio: documentos emitidos hoy ─────────────────────
def test_documentos_emitidos_hoy_cuenta_solo_los_vigentes_del_dia_del_profesional(db):
    _setup(db)
    _completar(db, receta=RECETA, justificativo=JUSTIFICATIVO)
    r = docs_router.resumen_documentos_hoy(PROF_ID, db=db, current_user=PROF_USER)
    assert (r["total"], r["recetas"], r["justificativos"]) == (2, 1, 1)

    receta = db.query(DocumentoClinico).filter_by(tipo="receta").one()
    docs_router.anular_documento(receta.id, docs_router.AnularIn(motivo="error de dosis"), db=db, current_user=PROF_USER)
    r = docs_router.resumen_documentos_hoy(PROF_ID, db=db, current_user=PROF_USER)
    assert (r["total"], r["recetas"], r["justificativos"]) == (1, 0, 1)      # lo anulado no cuenta


def test_documentos_de_ayer_no_cuentan_como_de_hoy(db):
    from datetime import datetime, timedelta, timezone
    _setup(db)
    _completar(db, receta=RECETA)
    manana = datetime.now(timezone.utc) + timedelta(days=1, hours=1)
    assert svc.contar_documentos_del_dia(db, PROF_ID, ahora=manana)["total"] == 0


def test_solo_el_propio_profesional_ve_su_resumen_de_hoy(db):
    _setup(db)
    for intruso in (EST_USER, OTRO_EST_USER):
        with pytest.raises(HTTPException) as exc:
            docs_router.resumen_documentos_hoy(PROF_ID, db=db, current_user=intruso)
        assert exc.value.status_code == 403
