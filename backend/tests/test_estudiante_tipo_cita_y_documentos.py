# -*- coding: utf-8 -*-
"""
El estudiante reconoce sus citas de sobrecupo y urgentes, y el registro de atención
(PDF) coincide con los documentos que el profesional emitió.

- GET /citas/estudiante/{id} y GET /historial/estudiante/{id} exponen el tipo de cada cita.
- El tipo es una marca de la cita: no cambia cuando el profesional emite documentos ni
  cuando la cita se completa.
- El PDF de la atención lista los documentos emitidos (receta y justificativo van de la mano).
"""

from __future__ import annotations

import asyncio
import re
import zlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.init  # noqa: F401
import app.models.solicitud_horario  # noqa: F401

from app.database import Base
from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import citas as m
from app.schemas import JustificativoIn, MedicamentoRecetaIn, RecetaIn
from app.services.documento_clinico_service import anular_documento, emitir_documentos

EST = {"id": 99, "rol": "estudiante"}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    s.add(Usuario(id=10, correo="p@utem.cl", password="x", rol="profesional", activo=True, nombre="Dra. Ana Martínez"))
    s.add(Usuario(id=99, correo="e@utem.cl", password="x", rol="estudiante", activo=True, nombre="Valentina Rojas", rut="11.222.333-9", carrera="Informática"))
    s.add(Profesional(id=5, usuario_id=10, nombre="Dra. Ana Martínez", especialidad="Medicina General", iniciales="AM", rut="9.999.999-9"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _cita(db, estado="pendiente", fecha="2026-10-20", hora="10:30", **extra) -> Cita:
    c = Cita(estudiante_id=99, profesional_id=5, fecha=fecha, hora=hora, estado=estado, **extra)
    db.add(c)
    db.commit()
    return c


def _emitir(db, cita, receta=True, justificativo=True):
    prof = db.query(Profesional).get(5)
    est = db.query(Usuario).get(99)
    r = RecetaIn(medicamentos=[MedicamentoRecetaIn(medicamento="Paracetamol 500 mg", dosis="1 comprimido", frecuencia="cada 8 horas", periodo="3 días")]) if receta else None
    j = JustificativoIn() if justificativo else None
    docs = emitir_documentos(db, cita, prof, est, r, j)
    db.commit()
    return docs


def _citas(db):
    return {c["id"]: c for c in m.get_citas_estudiante(estudiante_id=99, db=db, current_user=EST)}


def _historial(db):
    return {h["id"]: h for h in m.get_historial(estudiante_id=99, db=db, current_user=EST)}


# ══════════════════════════════════════════════
# Próximas citas
# ══════════════════════════════════════════════
def test_cita_normal_se_informa_como_normal(db):
    c = _cita(db)
    r = _citas(db)[c.id]
    assert (r["tipo"], r["urgente"], r["sobrecupo"]) == ("normal", False, False)


def test_cita_de_sobrecupo_se_informa_como_sobrecupo(db):
    c = _cita(db, sobrecupo=True)
    r = _citas(db)[c.id]
    assert (r["tipo"], r["sobrecupo"], r["urgente"]) == ("sobrecupo", True, False)


def test_cita_urgente_se_informa_como_urgente_en_vez_de_quedar_fija_en_false(db):
    c = _cita(db, urgente=True)
    r = _citas(db)[c.id]
    assert (r["tipo"], r["urgente"]) == ("urgente", True)


def test_si_es_urgente_y_sobrecupo_prevalece_la_urgencia(db):
    c = _cita(db, urgente=True, sobrecupo=True)
    assert _citas(db)[c.id]["tipo"] == "urgente"


def test_solo_se_expone_lo_que_el_estudiante_necesita_del_sobrecupo(db):
    c = _cita(db, sobrecupo=True)
    assert set(_citas(db)[c.id]) == {"id", "iniciales", "especialidad", "profesional", "fecha", "hora",
                                      "urgente", "sobrecupo", "tipo", "aviso", "estado"}


# ══════════════════════════════════════════════
# Historial: el tipo se conserva al completar y al emitir documentos
# ══════════════════════════════════════════════
def test_sobrecupo_completado_con_receta_y_justificativo_sigue_marcado_como_sobrecupo(db):
    c = _cita(db, sobrecupo=True)
    c.estado = "completada"
    db.commit()
    _emitir(db, c)
    h = _historial(db)[c.id]
    assert h["tipo"] == "sobrecupo" and h["sobrecupo"] is True
    assert sorted(d["tipo"] for d in h["documentos"]) == ["justificativo", "receta"]


def test_emitir_documentos_no_modifica_las_marcas_de_la_cita(db):
    c = _cita(db, sobrecupo=True)
    c2 = _cita(db, hora="11:00", urgente=True)
    for cita in (c, c2):
        cita.estado = "completada"
        db.commit()
        _emitir(db, cita)
        db.refresh(cita)
    assert (c.sobrecupo, c.urgente) == (True, False)
    assert (c2.urgente, c2.sobrecupo) == (True, False)


def test_urgencia_completada_con_documentos_sigue_marcada_como_urgente(db):
    c = _cita(db, urgente=True)
    c.estado = "completada"
    db.commit()
    _emitir(db, c, receta=False)
    h = _historial(db)[c.id]
    assert h["tipo"] == "urgente"
    assert [d["tipo"] for d in h["documentos"]] == ["justificativo"]


def test_cancelada_o_inasistencia_conservan_su_tipo(db):
    a = _cita(db, estado="cancelada", sobrecupo=True)
    b = _cita(db, estado="inasistencia", hora="12:00", urgente=True)
    h = _historial(db)
    assert h[a.id]["tipo"] == "sobrecupo"
    assert h[b.id]["tipo"] == "urgente"


def test_cita_normal_completada_sigue_siendo_normal(db):
    c = _cita(db)
    c.estado = "completada"
    db.commit()
    assert _historial(db)[c.id]["tipo"] == "normal"


# ══════════════════════════════════════════════
# PDF: el registro de atención coincide con los documentos emitidos
# ══════════════════════════════════════════════
def _texto_pdf(resp) -> str:
    async def _leer():
        return b"".join([c async for c in resp.body_iterator])
    datos = asyncio.run(_leer())
    texto = []
    for flujo in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", datos, flags=re.S):
        try:
            contenido = zlib.decompress(flujo)
        except zlib.error:
            contenido = flujo
        for tj in re.findall(rb"\(((?:\\.|[^\\)])*)\)\s*Tj", contenido):
            texto.append(re.sub(rb"\\(.)", rb"\1", tj).decode("latin-1"))  # quita el escape de \( \) \\
    return " ".join(texto)


def _pdf(db, cita):
    return _texto_pdf(m.descargar_pdf_cita(cita_id=cita.id, db=db, current_user=EST))


def test_pdf_con_receta_y_justificativo_los_lista_y_no_dice_que_falta_la_receta(db):
    c = _cita(db)
    c.estado = "completada"
    db.commit()
    docs = _emitir(db, c)
    texto = _pdf(db, c)
    assert "Documentos emitidos en esta atencion" in texto.replace("ó", "o") or "Documentos emitidos en esta atenci" in texto
    for d in docs:
        assert d.folio in texto
    assert "Receta médica" in texto and "Justificativo médico" in texto
    assert "No se suministró medicamento" not in texto


def test_pdf_sin_documentos_dice_ninguno(db):
    c = _cita(db)
    c.estado = "completada"
    db.commit()
    assert "Ninguno." in _pdf(db, c)


def test_pdf_marca_como_anulado_un_documento_anulado(db):
    c = _cita(db)
    c.estado = "completada"
    db.commit()
    docs = _emitir(db, c, justificativo=False)
    anular_documento(docs[0], "Error de digitación")
    db.commit()
    assert f"{docs[0].folio} (anulado)" in _pdf(db, c)


def test_pdf_de_sobrecupo_o_urgencia_indica_el_tipo_de_atencion(db):
    a = _cita(db, sobrecupo=True)
    b = _cita(db, hora="12:00", urgente=True)
    n = _cita(db, hora="13:00")
    for cita in (a, b, n):
        cita.estado = "completada"
    db.commit()
    assert "Sobrecupo" in _pdf(db, a)
    assert "Urgente" in _pdf(db, b)
    assert "Tipo de atenci" not in _pdf(db, n)
