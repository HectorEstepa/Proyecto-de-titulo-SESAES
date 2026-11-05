from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.routers import estudiante as m
from app.routers import profesionales as p
from app.security import password_cumple_politica


class FakeQuery:
    def __init__(self, results):
        self._results = list(results)

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._results[0] if self._results else None


class FakeDB:
    def __init__(self, usuarios):
        self.usuarios = list(usuarios)
        self.commit_called = False

    def query(self, model):
        assert model is Usuario
        return FakeQuery(self.usuarios)

    def commit(self):
        self.commit_called = True


def estudiante():
    return SimpleNamespace(
        id=99,
        rol="estudiante",
        password="hash-vieja",
        debe_cambiar_password=False,
        correo="estudiante@utem.cl",
        nombre="Estudiante Prueba",
    )


def datos(actual="Actual123!", nueva="Nueva456!"):
    return m.CambiarPasswordIn(
        contrasena_actual=actual,
        contrasena_nueva=nueva,
    )


def test_cambiar_password_dueno_verifica_actual_y_hashea_nueva(monkeypatch):
    usuario = estudiante()
    db = FakeDB([usuario])
    monkeypatch.setattr(
        m,
        "verify_password",
        lambda plain, stored: plain == "Actual123!",
    )
    monkeypatch.setattr(m, "hash_password", lambda plain: f"hash::{plain}")

    correo_enviado = {}
    def fake_correo(**kwargs):
        correo_enviado.update(kwargs)

    monkeypatch.setattr(m, "simular_envio_correo", fake_correo)

    resultado = m.cambiar_password_estudiante(
        estudiante_id=99,
        datos=datos(),
        db=db,
        current_user={"id": 99, "rol": "estudiante"},
    )

    assert resultado["message"]
    assert usuario.password == "hash::Nueva456!"
    assert usuario.debe_cambiar_password is False
    assert correo_enviado["destinatario"] == "estudiante@utem.cl"
    assert correo_enviado["tipo"] == "seguridad"
    assert "password" not in correo_enviado["cuerpo"].lower()
    assert "contraseña" in correo_enviado["cuerpo"].lower()
    assert db.commit_called


def test_cambiar_password_rechaza_password_actual_incorrecta(monkeypatch):
    db = FakeDB([estudiante()])
    monkeypatch.setattr(m, "verify_password", lambda plain, stored: False)

    with pytest.raises(HTTPException) as exc:
        m.cambiar_password_estudiante(
            estudiante_id=99,
            datos=datos(actual="incorrecta"),
            db=db,
            current_user={"id": 99, "rol": "estudiante"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called


def test_cambiar_password_rechaza_nueva_muy_corta():
    db = FakeDB([estudiante()])

    with pytest.raises(HTTPException) as exc:
        m.cambiar_password_estudiante(
            estudiante_id=99,
            datos=datos(nueva="12345"),
            db=db,
            current_user={"id": 99, "rol": "estudiante"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called


def test_cambiar_password_rechaza_reutilizar_password_actual(monkeypatch):
    db = FakeDB([estudiante()])
    monkeypatch.setattr(
        m,
        "verify_password",
        lambda plain, stored: plain == "Actual123!",
    )

    with pytest.raises(HTTPException) as exc:
        m.cambiar_password_estudiante(
            estudiante_id=99,
            datos=datos(nueva="Actual123!"),
            db=db,
            current_user={"id": 99, "rol": "estudiante"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called



@pytest.mark.parametrize(
    "password_debil",
    [
        "nueva456!",
        "NUEVA456!",
        "NuevaClave!",
        "Nueva456",
        "Nueva 456!",
        "Nu1!",
    ],
)
def test_cambiar_password_rechaza_password_que_no_cumple_politica(password_debil):
    db = FakeDB([estudiante()])

    with pytest.raises(HTTPException) as exc:
        m.cambiar_password_estudiante(
            estudiante_id=99,
            datos=datos(nueva=password_debil),
            db=db,
            current_user={"id": 99, "rol": "estudiante"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called

def test_cambiar_password_otro_estudiante_da_403():
    db = FakeDB([estudiante()])

    with pytest.raises(HTTPException) as exc:
        m.cambiar_password_estudiante(
            estudiante_id=99,
            datos=datos(),
            db=db,
            current_user={"id": 100, "rol": "estudiante"},
        )

    assert exc.value.status_code == 403
    assert not db.commit_called


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_cambiar_password_admin_superadmin_da_403(rol):
    db = FakeDB([estudiante()])

    with pytest.raises(HTTPException) as exc:
        m.cambiar_password_estudiante(
            estudiante_id=99,
            datos=datos(),
            db=db,
            current_user={"id": 99, "rol": rol},
        )

    assert exc.value.status_code == 403
    assert not db.commit_called


def test_primer_acceso_no_se_reutiliza_despues_de_resuelto():
    usuario = estudiante()
    usuario.debe_cambiar_password = False
    db = FakeDB([usuario])

    with pytest.raises(HTTPException) as exc:
        m.resolver_primer_acceso(
            estudiante_id=99,
            datos=m.PrimerAccesoIn(nueva_password="nueva123"),
            db=db,
            current_user={"id": 99, "rol": "estudiante"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called

def test_politica_password_compartida_acepta_password_fuerte():
    assert password_cumple_politica("Nueva456!") is True


@pytest.mark.parametrize(
    "password_debil",
    [
        "nueva456!",
        "NUEVA456!",
        "NuevaClave!",
        "Nueva456",
        "Nueva 456!",
        "Nu1!",
        "",
        None,
    ],
)
def test_politica_password_compartida_rechaza_password_debil(password_debil):
    assert password_cumple_politica(password_debil) is False


def test_primer_acceso_si_cambia_password_exige_politica_fuerte():
    usuario = estudiante()
    usuario.debe_cambiar_password = True
    db = FakeDB([usuario])

    with pytest.raises(HTTPException) as exc:
        m.resolver_primer_acceso(
            estudiante_id=99,
            datos=m.PrimerAccesoIn(nueva_password="nueva123"),
            db=db,
            current_user={"id": 99, "rol": "estudiante"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called


class FakeDBProfesional:
    def __init__(self, profesional, usuario):
        self.profesional = profesional
        self.usuario = usuario
        self.commit_called = False

    def query(self, model):
        if model is Profesional:
            return FakeQuery([self.profesional])
        if model is Usuario:
            return FakeQuery([self.usuario])
        raise AssertionError(f"Modelo inesperado: {model}")

    def commit(self):
        self.commit_called = True


def profesional_y_usuario():
    usuario = SimpleNamespace(
        id=77,
        rol="profesional",
        password="hash-vieja",
        debe_cambiar_password=True,
    )
    profesional = SimpleNamespace(
        id=12,
        usuario_id=77,
    )
    return profesional, usuario


def datos_prof(actual="Actual123!", nueva="Nueva456!"):
    return p.CambiarPasswordProfesionalIn(
        contrasena_actual=actual,
        contrasena_nueva=nueva,
    )


def test_profesional_cambiar_password_aplica_misma_politica(monkeypatch):
    profesional, usuario = profesional_y_usuario()
    db = FakeDBProfesional(profesional, usuario)

    monkeypatch.setattr(
        p,
        "verificar_acceso_profesional",
        lambda current_user, prof_id, db: None,
    )
    monkeypatch.setattr(
        p,
        "verify_password",
        lambda plain, stored: plain == "Actual123!",
    )
    monkeypatch.setattr(p, "hash_password", lambda plain: f"hash::{plain}")

    resultado = p.cambiar_password(
        prof_id=12,
        body=datos_prof(),
        db=db,
        current_user={"id": 77, "rol": "profesional"},
    )

    assert resultado["message"]
    assert usuario.password == "hash::Nueva456!"
    assert usuario.debe_cambiar_password is False
    assert db.commit_called


@pytest.mark.parametrize(
    "password_debil",
    [
        "nueva456!",
        "NUEVA456!",
        "NuevaClave!",
        "Nueva456",
        "Nueva 456!",
        "Nu1!",
    ],
)
def test_profesional_rechaza_password_que_no_cumple_politica(
    monkeypatch,
    password_debil,
):
    profesional, usuario = profesional_y_usuario()
    db = FakeDBProfesional(profesional, usuario)

    monkeypatch.setattr(
        p,
        "verificar_acceso_profesional",
        lambda current_user, prof_id, db: None,
    )

    with pytest.raises(HTTPException) as exc:
        p.cambiar_password(
            prof_id=12,
            body=datos_prof(nueva=password_debil),
            db=db,
            current_user={"id": 77, "rol": "profesional"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called


def test_profesional_rechaza_password_actual_incorrecta(monkeypatch):
    profesional, usuario = profesional_y_usuario()
    db = FakeDBProfesional(profesional, usuario)

    monkeypatch.setattr(
        p,
        "verificar_acceso_profesional",
        lambda current_user, prof_id, db: None,
    )
    monkeypatch.setattr(p, "verify_password", lambda plain, stored: False)

    with pytest.raises(HTTPException) as exc:
        p.cambiar_password(
            prof_id=12,
            body=datos_prof(actual="incorrecta"),
            db=db,
            current_user={"id": 77, "rol": "profesional"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called


def test_profesional_rechaza_reutilizar_password_actual(monkeypatch):
    profesional, usuario = profesional_y_usuario()
    db = FakeDBProfesional(profesional, usuario)

    monkeypatch.setattr(
        p,
        "verificar_acceso_profesional",
        lambda current_user, prof_id, db: None,
    )
    monkeypatch.setattr(
        p,
        "verify_password",
        lambda plain, stored: plain == "Actual123!",
    )

    with pytest.raises(HTTPException) as exc:
        p.cambiar_password(
            prof_id=12,
            body=datos_prof(nueva="Actual123!"),
            db=db,
            current_user={"id": 77, "rol": "profesional"},
        )

    assert exc.value.status_code == 400
    assert not db.commit_called
