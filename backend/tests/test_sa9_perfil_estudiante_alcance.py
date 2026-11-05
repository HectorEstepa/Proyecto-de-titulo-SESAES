from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.cita import Cita
from app.models.profesional import Profesional
from app.models.usuario import Usuario
from app.rbac.admin_authorization import (
    AlcanceAdministrativoEfectivo,
    normalizar_especialidad,
)
from app.routers import admin


class RecordingQuery:
    def __init__(
        self,
        *,
        rows=None,
        scalar_value=0,
    ):
        self.rows = list(rows or [])
        self.scalar_value = scalar_value
        self.events = []
        self.filter_calls = []

    def filter(self, *conditions):
        self.events.append("filter")
        self.filter_calls.append(conditions)
        return self

    def order_by(self, *args, **kwargs):
        self.events.append("order_by")
        return self

    def limit(self, value):
        self.events.append(("limit", value))
        return self

    def all(self):
        self.events.append("all")
        return list(self.rows)

    def first(self):
        self.events.append("first")
        return self.rows[0] if self.rows else None

    def scalar(self):
        self.events.append("scalar")
        return self.scalar_value


class FakeDB:
    def __init__(
        self,
        *,
        estudiante=None,
        citas=None,
        profesionales=None,
        scalar_values=None,
    ):
        self.estudiante = estudiante
        self.citas = list(citas or [])
        self.profesionales = list(
            profesionales or []
        )
        self.scalar_values = list(
            scalar_values or []
        )

        self.usuario_queries = []
        self.cita_queries = []
        self.profesional_queries = []
        self.scalar_queries = []
        self.query_calls = []

    def query(self, *entities):
        self.query_calls.append(entities)

        if len(entities) == 1 and entities[0] is Usuario:
            query = RecordingQuery(
                rows=(
                    [self.estudiante]
                    if self.estudiante is not None
                    else []
                )
            )
            self.usuario_queries.append(query)
            return query

        if len(entities) == 1 and entities[0] is Cita:
            query = RecordingQuery(
                rows=self.citas
            )
            self.cita_queries.append(query)
            return query

        if len(entities) == 1 and entities[0] is Profesional:
            query = RecordingQuery(
                rows=self.profesionales
            )
            self.profesional_queries.append(query)
            return query

        value = (
            self.scalar_values.pop(0)
            if self.scalar_values
            else 0
        )

        query = RecordingQuery(
            scalar_value=value
        )
        self.scalar_queries.append(query)

        return query


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


def _filtros_scope(query):
    encontrados = []

    for call in query.filter_calls:
        for condition in call:
            left = getattr(
                condition,
                "left",
                None,
            )

            if getattr(
                left,
                "name",
                None,
            ) != "profesional_id":
                continue

            right = getattr(
                condition,
                "right",
                None,
            )

            value = getattr(
                right,
                "value",
                None,
            )

            if isinstance(
                value,
                (list, tuple, set),
            ):
                encontrados.append(
                    list(value)
                )

    return encontrados


def _estudiante():
    return SimpleNamespace(
        id=20,
        nombre="Ana",
        rut="11.111.111-1",
        carrera="Gastronom?a",
        correo="ana@ejemplo.cl",
    )


def _cita():
    return SimpleNamespace(
        id=100,
        estudiante_id=20,
        profesional_id=10,
        fecha="2026-09-01",
        hora="09:00",
        estado="completada",
    )


def _profesional():
    return SimpleNamespace(
        id=10,
        nombre="Nutricionista Uno",
        especialidad="Nutrici?n",
    )


def test_perfil_limitado_scopea_citas_y_metricas(
    monkeypatch,
):
    db = FakeDB(
        estudiante=_estudiante(),
        citas=[_cita()],
        profesionales=[_profesional()],
        scalar_values=[
            3,
            2,
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    monkeypatch.setattr(
        admin,
        "_ids_profesionales_en_alcance",
        lambda db, alcance: [10, 11],
    )

    resultado = admin.perfil_estudiante_admin(
        estudiante_id=20,
        db=db,
        current_user={
            "id": 50,
            "rol": "admin",
        },
    )

    assert resultado == {
        "id": 20,
        "nombre": "Ana",
        "rut": "11.111.111-1",
        "carrera": "Gastronom?a",
        "correo": "ana@ejemplo.cl",
        "citas_totales": 3,
        "citas_atendidas": 2,
        "ultimas_atenciones": [
            {
                "id": 100,
                "fecha": "2026-09-01",
                "hora": "09:00",
                "estado": "completada",
                "especialidad": "Nutrici?n",
                "profesional": "Nutricionista Uno",
            }
        ],
    }

    assert len(db.scalar_queries) == 2
    assert len(db.cita_queries) == 1

    for query in db.scalar_queries:
        assert _filtros_scope(query) == [
            [10, 11],
        ]

    assert _filtros_scope(
        db.cita_queries[0]
    ) == [
        [10, 11],
    ]


def test_perfil_limitado_fuera_de_scope_da_404(
    monkeypatch,
):
    db = FakeDB(
        estudiante=_estudiante(),
        scalar_values=[0],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    monkeypatch.setattr(
        admin,
        "_ids_profesionales_en_alcance",
        lambda db, alcance: [10],
    )

    with pytest.raises(HTTPException) as exc:
        admin.perfil_estudiante_admin(
            estudiante_id=20,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404

    # No debe consultar ni devolver atenciones fuera del scope.
    assert db.cita_queries == []
    assert db.profesional_queries == []


def test_perfil_limitado_sin_profesionales_da_404_sin_buscar_estudiante(
    monkeypatch,
):
    db = FakeDB(
        estudiante=_estudiante(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_limitado(
            "Nutrici?n"
        ),
    )

    monkeypatch.setattr(
        admin,
        "_ids_profesionales_en_alcance",
        lambda db, alcance: [],
    )

    with pytest.raises(HTTPException) as exc:
        admin.perfil_estudiante_admin(
            estudiante_id=20,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 404
    assert db.query_calls == []


def test_perfil_institucional_conserva_acceso_global(
    monkeypatch,
):
    db = FakeDB(
        estudiante=_estudiante(),
        citas=[_cita()],
        profesionales=[_profesional()],
        scalar_values=[
            5,
            4,
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.perfil_estudiante_admin(
        estudiante_id=20,
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado["citas_totales"] == 5
    assert resultado["citas_atendidas"] == 4
    assert len(resultado["ultimas_atenciones"]) == 1

    for query in db.scalar_queries:
        assert _filtros_scope(query) == []

    assert _filtros_scope(
        db.cita_queries[0]
    ) == []


def test_perfil_institucional_sin_citas_sigue_visible(
    monkeypatch,
):
    db = FakeDB(
        estudiante=_estudiante(),
        citas=[],
        scalar_values=[
            0,
            0,
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.perfil_estudiante_admin(
        estudiante_id=20,
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    assert resultado["id"] == 20
    assert resultado["citas_totales"] == 0
    assert resultado["citas_atendidas"] == 0
    assert resultado["ultimas_atenciones"] == []


def test_perfil_sin_alcance_da_403(
    monkeypatch,
):
    db = FakeDB(
        estudiante=_estudiante(),
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: None,
    )

    with pytest.raises(HTTPException) as exc:
        admin.perfil_estudiante_admin(
            estudiante_id=20,
            db=db,
            current_user={
                "id": 50,
                "rol": "admin",
            },
        )

    assert exc.value.status_code == 403
    assert db.query_calls == []


def test_perfil_inexistente_conserva_404(
    monkeypatch,
):
    db = FakeDB(
        estudiante=None,
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    with pytest.raises(HTTPException) as exc:
        admin.perfil_estudiante_admin(
            estudiante_id=999,
            db=db,
            current_user={
                "id": 1,
                "rol": "superadmin",
            },
        )

    assert exc.value.status_code == 404


def test_perfil_no_expone_campos_clinicos(
    monkeypatch,
):
    cita = _cita()

    # Aunque el objeto tenga campos cl?nicos, no deben salir.
    cita.medicamento = "NO DEBE SALIR"
    cita.observaciones_atencion = "NO DEBE SALIR"

    db = FakeDB(
        estudiante=_estudiante(),
        citas=[cita],
        profesionales=[_profesional()],
        scalar_values=[
            1,
            1,
        ],
    )

    monkeypatch.setattr(
        admin,
        "obtener_alcance_administrativo_efectivo",
        lambda db, current_user: _alcance_institucional(),
    )

    resultado = admin.perfil_estudiante_admin(
        estudiante_id=20,
        db=db,
        current_user={
            "id": 1,
            "rol": "superadmin",
        },
    )

    atencion = resultado["ultimas_atenciones"][0]

    assert "medicamento" not in atencion
    assert "observaciones_atencion" not in atencion
