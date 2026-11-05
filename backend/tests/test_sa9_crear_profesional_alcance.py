import inspect

import pytest
from fastapi import HTTPException

from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin
from app.schemas import ProfesionalCreate


class NoMutationDB:
    def __init__(self):
        self.query_calls = []
        self.add_calls = []
        self.flush_calls = 0
        self.commit_calls = 0
        self.refresh_calls = []

    def query(self, model):
        self.query_calls.append(model)
        raise AssertionError(
            "No deb?a consultar la BD."
        )

    def add(self, obj):
        self.add_calls.append(obj)

    def flush(self):
        self.flush_calls += 1

    def commit(self):
        self.commit_calls += 1

    def refresh(self, obj):
        self.refresh_calls.append(obj)


def _alcance_limitado(*especialidades):
    return AlcanceAdministrativoEfectivo(
        institucional=False,
        especialidades_normalizadas=frozenset(
            normalizar_especialidad(e).normalizada
            for e in especialidades
        ),
    )


def _alcance_institucional():
    return AlcanceAdministrativoEfectivo(
        institucional=True,
        especialidades_normalizadas=frozenset(),
    )


def _datos(
    *,
    especialidad="Nutrici?n",
    rut=None,
    color_identificador=None,
):
    return ProfesionalCreate(
        nombre="Profesional Nuevo",
        especialidad=especialidad,
        correo="nuevo@utem.cl",
        rut=rut,
        color_identificador=color_identificador,
    )


def _assert_sin_mutaciones(db):
    assert db.query_calls == []
    assert db.add_calls == []
    assert db.flush_calls == 0
    assert db.commit_calls == 0
    assert db.refresh_calls == []


def test_crear_profesional_usa_gestionar_efectivo():
    source = inspect.getsource(
        admin.crear_profesional
    )

    assert (
        "require_effective_permission"
        in source
    )

    assert (
        "Permission.PROFESIONALES_GESTIONAR"
        in source
    )

    assert (
        "require_permission(Permission.PROFESIONALES_GESTIONAR)"
        not in source
    )


def test_crear_profesional_sin_alcance_falla_antes_de_validar_o_mutar(
    monkeypatch,
):
    db = NoMutationDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    monkeypatch.setattr(
        admin,
        "validar_rut",
        lambda value: (_ for _ in ()).throw(
            AssertionError(
                "No deb?a validar RUT sin alcance."
            )
        ),
    )

    monkeypatch.setattr(
        admin,
        "color_identificador_es_valido",
        lambda value: (_ for _ in ()).throw(
            AssertionError(
                "No deb?a validar color sin alcance."
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_profesional(
            datos=_datos(),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    _assert_sin_mutaciones(db)


def test_crear_profesional_fuera_de_scope_da_403_antes_de_validaciones(
    monkeypatch,
):
    db = NoMutationDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    monkeypatch.setattr(
        admin,
        "validar_rut",
        lambda value: (_ for _ in ()).throw(
            AssertionError(
                "No deb?a validar RUT fuera de scope."
            )
        ),
    )

    monkeypatch.setattr(
        admin,
        "color_identificador_es_valido",
        lambda value: (_ for _ in ()).throw(
            AssertionError(
                "No deb?a validar color fuera de scope."
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_profesional(
            datos=_datos(
                especialidad="Odontolog?a"
            ),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403

    assert "especialidad" in exc.value.detail.lower()

    _assert_sin_mutaciones(db)


def test_crear_profesional_scope_normaliza_especialidad(
    monkeypatch,
):
    db = NoMutationDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "  Nutrici?n  "
        ),
    )

    # Si el scope acepta la variante normalizada, debe llegar
    # a la validaci?n de RUT existente.
    monkeypatch.setattr(
        admin,
        "validar_rut",
        lambda value: False,
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_profesional(
            datos=_datos(
                especialidad="NUTRICI?N",
                rut="rut-invalido",
            ),
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 400
    assert "RUT" in exc.value.detail

    _assert_sin_mutaciones(db)


def test_crear_profesional_institucional_supera_guard_de_scope(
    monkeypatch,
):
    db = NoMutationDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: (
            _alcance_institucional()
        ),
    )

    monkeypatch.setattr(
        admin,
        "validar_rut",
        lambda value: False,
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_profesional(
            datos=_datos(
                especialidad="Especialidad Hist?rica",
                rut="rut-invalido",
            ),
            db=db,
            current_user={
                "id": -1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 400
    assert "RUT" in exc.value.detail

    _assert_sin_mutaciones(db)


def test_scope_se_comprueba_antes_de_validaciones_y_flush():
    source = inspect.getsource(
        admin.crear_profesional
    )

    pos_resolver = source.find(
        "obtener_alcance_administrativo_efectivo"
    )

    pos_scope = source.find(
        "especialidad_permitida_por_alcance"
    )

    pos_rut = source.find(
        "validar_rut"
    )

    pos_color = source.find(
        "color_identificador_es_valido"
    )

    pos_usuario = source.find(
        "nuevo_usuario = Usuario("
    )

    pos_flush = source.find(
        "db.flush()"
    )

    pos_commit = source.find(
        "db.commit()"
    )

    assert (
        -1
        < pos_resolver
        < pos_scope
        < pos_rut
        < pos_usuario
        < pos_flush
        < pos_commit
    )

    assert pos_scope < pos_color
