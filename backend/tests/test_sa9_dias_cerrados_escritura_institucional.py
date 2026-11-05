import inspect

import pytest
from fastapi import HTTPException

from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class EmptyQuery:
    def __init__(self):
        self.filter_calls = 0

    def filter(self, *args):
        self.filter_calls += 1
        return self

    def first(self):
        return None


class FakeDB:
    def __init__(self):
        self.query_calls = []
        self.add_calls = []
        self.delete_calls = []
        self.commit_calls = 0

    def query(self, model):
        self.query_calls.append(model)
        return EmptyQuery()

    def add(self, obj):
        self.add_calls.append(obj)

    def delete(self, obj):
        self.delete_calls.append(obj)

    def commit(self):
        self.commit_calls += 1


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


def test_post_dia_cerrado_usa_agenda_gestionar_efectivo():
    source = inspect.getsource(
        admin.crear_dia_cerrado
    )

    assert (
        "require_effective_permission(Permission.AGENDA_GESTIONAR)"
        in source
    )

    assert (
        "require_permission(Permission.AGENDA_GESTIONAR)"
        not in source
    )


def test_delete_dia_cerrado_usa_agenda_gestionar_efectivo():
    source = inspect.getsource(
        admin.eliminar_dia_cerrado
    )

    assert (
        "require_effective_permission(Permission.AGENDA_GESTIONAR)"
        in source
    )

    assert (
        "require_permission(Permission.AGENDA_GESTIONAR)"
        not in source
    )


@pytest.mark.parametrize(
    "endpoint,args",
    [
        (
            admin.crear_dia_cerrado,
            {
                "body": {
                    "fecha": "2026-09-18",
                    "motivo": "Prueba",
                },
            },
        ),
        (
            admin.eliminar_dia_cerrado,
            {
                "dia_id": 1,
            },
        ),
    ],
)
def test_escrituras_dias_cerrados_rechazan_scope_limitado_antes_de_bd(
    monkeypatch,
    endpoint,
    args,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    with pytest.raises(HTTPException) as exc:
        endpoint(
            **args,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403

    # No debe consultar ni mutar recursos institucionales.
    assert db.query_calls == []
    assert db.add_calls == []
    assert db.delete_calls == []
    assert db.commit_calls == 0


@pytest.mark.parametrize(
    "endpoint,args",
    [
        (
            admin.crear_dia_cerrado,
            {
                "body": {
                    "fecha": "2026-09-18",
                },
            },
        ),
        (
            admin.eliminar_dia_cerrado,
            {
                "dia_id": 1,
            },
        ),
    ],
)
def test_escrituras_dias_cerrados_sin_alcance_fallan_cerrado(
    monkeypatch,
    endpoint,
    args,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        endpoint(
            **args,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []
    assert db.commit_calls == 0


def test_post_institucional_supera_guard_y_conserva_validacion_fecha(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    with pytest.raises(HTTPException) as exc:
        admin.crear_dia_cerrado(
            body={},
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    # Lleg? a la validaci?n propia del endpoint.
    assert exc.value.status_code == 400
    assert "fecha" in exc.value.detail.lower()

    # La validaci?n de fecha ocurre antes de consultar BD.
    assert db.query_calls == []


def test_delete_institucional_supera_guard_y_conserva_404(
    monkeypatch,
):
    db = FakeDB()

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    with pytest.raises(HTTPException) as exc:
        admin.eliminar_dia_cerrado(
            dia_id=999,
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    # Si supera el guard institucional, consulta el recurso.
    assert exc.value.status_code == 404
    assert len(db.query_calls) == 1
    assert db.commit_calls == 0


def test_guard_institucional_aparece_antes_de_mutaciones():
    for endpoint in (
        admin.crear_dia_cerrado,
        admin.eliminar_dia_cerrado,
    ):
        source = inspect.getsource(endpoint)

        pos_scope = source.find(
            "obtener_alcance_administrativo_efectivo"
        )

        pos_institucional = source.find(
            "not alcance.institucional"
        )

        assert pos_scope != -1
        assert pos_institucional != -1

        mutation_positions = [
            pos
            for token in (
                "db.add(",
                "db.delete(",
                "db.commit(",
            )
            if (pos := source.find(token)) != -1
        ]

        assert mutation_positions

        assert pos_scope < min(mutation_positions)
        assert pos_institucional < min(mutation_positions)
