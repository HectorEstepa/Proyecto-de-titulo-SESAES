"""
SESAES - Migracion puntual SA-9.2.

Crea la tabla acceso_admin_permiso para persistir permisos
administrativos explicitamente asignados.

Caracteristicas:
- requiere que SA-8 ya exista;
- idempotente mediante Table.create(checkfirst=True);
- una sola transaccion;
- no asigna ningun permiso automaticamente;
- no modifica usuarios ni perfiles;
- valida el esquema real antes de considerar exitosa la migracion.

Ejecucion manual desde backend/:

    python -m scripts.migrar_permisos_admin_sa9
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.database import engine
from app.models.usuario import Usuario  # noqa: F401
from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminPermiso,
)


class MigracionPermisosAdminError(RuntimeError):
    pass


_TABLA = "acceso_admin_permiso"
_CHECK = "ck_acceso_admin_permiso_valido"


def _validar_prerrequisitos(conn) -> None:
    inspector = inspect(conn)
    tablas = set(inspector.get_table_names())

    if "acceso_administrativo" not in tablas:
        raise MigracionPermisosAdminError(
            "SA-9.2 requiere la tabla acceso_administrativo de SA-8."
        )


def _validar_esquema(conn) -> None:
    inspector = inspect(conn)
    errores: list[str] = []

    tablas = set(inspector.get_table_names())

    if _TABLA not in tablas:
        raise MigracionPermisosAdminError(
            "Falta la tabla acceso_admin_permiso."
        )

    columnas = {
        c["name"]: c
        for c in inspector.get_columns(_TABLA)
    }

    esperadas = {
        "id",
        "acceso_admin_id",
        "permiso",
    }

    faltantes = esperadas - columnas.keys()

    if faltantes:
        errores.append(
            f"Faltan columnas {sorted(faltantes)}."
        )
    else:
        for nombre in esperadas:
            if columnas[nombre].get("nullable", True):
                errores.append(
                    f"{_TABLA}.{nombre} debe ser NOT NULL."
                )

    uniques = {
        tuple(u.get("column_names") or ())
        for u in inspector.get_unique_constraints(_TABLA)
    }

    if ("acceso_admin_id", "permiso") not in uniques:
        errores.append(
            "Falta UNIQUE(acceso_admin_id, permiso)."
        )

    checks = {
        c.get("name")
        for c in inspector.get_check_constraints(_TABLA)
    }

    if _CHECK not in checks:
        errores.append(
            f"Falta CHECK constraint {_CHECK}."
        )

    fks = inspector.get_foreign_keys(_TABLA)

    fk_acceso = next(
        (
            fk
            for fk in fks
            if fk.get("constrained_columns") == ["acceso_admin_id"]
            and fk.get("referred_table") == "acceso_administrativo"
            and fk.get("referred_columns") == ["id"]
        ),
        None,
    )

    if fk_acceso is None:
        errores.append(
            "Falta FK acceso_admin_permiso.acceso_admin_id "
            "-> acceso_administrativo.id."
        )
    else:
        ondelete = (
            (fk_acceso.get("options") or {})
            .get("ondelete", "")
            .upper()
        )

        if ondelete != "CASCADE":
            errores.append(
                "FK acceso_admin_id debe usar ON DELETE CASCADE."
            )

    if errores:
        raise MigracionPermisosAdminError(
            "Migracion SA-9.2 incompleta:\n- "
            + "\n- ".join(errores)
        )


def migrar_permisos_admin_sa9(
    bind: Engine = engine,
    *,
    emitir_mensaje: bool = True,
) -> None:
    with bind.begin() as conn:
        _validar_prerrequisitos(conn)

        AccesoAdminPermiso.__table__.create(
            bind=conn,
            checkfirst=True,
        )

        _validar_esquema(conn)

    if emitir_mensaje:
        print(
            "Migracion SA-9.2 verificada: persistencia de "
            "permisos ADMIN creada correctamente."
        )


if __name__ == "__main__":
    migrar_permisos_admin_sa9()
