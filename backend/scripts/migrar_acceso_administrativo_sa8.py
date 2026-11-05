"""
SESAES - Migracion puntual SA-8.

Crea las tablas:
- acceso_administrativo
- acceso_admin_especialidad

Caracteristicas:
- idempotente mediante Table.create(checkfirst=True);
- una sola transaccion;
- no borra ni modifica usuarios;
- no asigna perfiles automaticamente;
- no modifica ROLE_DEFAULT_PERMISSIONS;
- valida el esquema real antes de considerar exitosa la migracion.

Ejecucion manual, desde backend/:

    python -m scripts.migrar_acceso_administrativo_sa8
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.database import engine
from app.models.usuario import Usuario  # registra usuario para resolver FK
from app.models.acceso_administrativo import (
    AccesoAdministrativo,
    AccesoAdminEspecialidad,
)


class MigracionAccesoAdministrativoError(RuntimeError):
    pass


_TABLAS = {
    "acceso_administrativo",
    "acceso_admin_especialidad",
}

_CHECKS_ACCESO = {
    "ck_acceso_administrativo_perfil",
    "ck_acceso_administrativo_tipo_alcance",
    "ck_acceso_administrativo_perfil_alcance",
}

_CHECKS_ESPECIALIDAD = {
    "ck_acceso_admin_especialidad_nombre_no_vacio",
    "ck_acceso_admin_especialidad_normalizada_no_vacia",
}


def _columnas(inspector, tabla: str):
    return {
        columna["name"]: columna
        for columna in inspector.get_columns(tabla)
    }


def _validar_columnas_no_nulas(
    inspector,
    tabla: str,
    esperadas: set[str],
) -> list[str]:
    errores = []
    columnas = _columnas(inspector, tabla)

    faltantes = esperadas - columnas.keys()
    if faltantes:
        errores.append(
            f"{tabla}: faltan columnas {sorted(faltantes)}."
        )
        return errores

    for nombre in esperadas:
        if columnas[nombre].get("nullable", True):
            errores.append(
                f"{tabla}.{nombre} debe ser NOT NULL."
            )

    return errores


def _validar_esquema(conn) -> None:
    inspector = inspect(conn)
    errores: list[str] = []

    tablas = set(inspector.get_table_names())
    faltantes = _TABLAS - tablas

    if faltantes:
        raise MigracionAccesoAdministrativoError(
            "Faltan tablas SA-8: "
            + ", ".join(sorted(faltantes))
        )

    errores.extend(
        _validar_columnas_no_nulas(
            inspector,
            "acceso_administrativo",
            {
                "id",
                "usuario_id",
                "perfil",
                "tipo_alcance",
            },
        )
    )

    errores.extend(
        _validar_columnas_no_nulas(
            inspector,
            "acceso_admin_especialidad",
            {
                "id",
                "acceso_admin_id",
                "especialidad",
                "especialidad_normalizada",
            },
        )
    )

    # UNIQUE usuario_id: una configuracion por usuario.
    uniques_acceso = {
        tuple(u.get("column_names") or ())
        for u in inspector.get_unique_constraints(
            "acceso_administrativo"
        )
    }

    if ("usuario_id",) not in uniques_acceso:
        errores.append(
            "acceso_administrativo.usuario_id debe ser UNIQUE."
        )

    # UNIQUE alcance + especialidad normalizada.
    uniques_esp = {
        tuple(u.get("column_names") or ())
        for u in inspector.get_unique_constraints(
            "acceso_admin_especialidad"
        )
    }

    if (
        "acceso_admin_id",
        "especialidad_normalizada",
    ) not in uniques_esp:
        errores.append(
            "Falta UNIQUE(acceso_admin_id, "
            "especialidad_normalizada)."
        )

    # CHECK constraints.
    checks_acceso = {
        c.get("name")
        for c in inspector.get_check_constraints(
            "acceso_administrativo"
        )
    }

    faltantes_checks = _CHECKS_ACCESO - checks_acceso
    if faltantes_checks:
        errores.append(
            "acceso_administrativo: faltan CHECK constraints "
            f"{sorted(faltantes_checks)}."
        )

    checks_esp = {
        c.get("name")
        for c in inspector.get_check_constraints(
            "acceso_admin_especialidad"
        )
    }

    faltantes_checks_esp = _CHECKS_ESPECIALIDAD - checks_esp
    if faltantes_checks_esp:
        errores.append(
            "acceso_admin_especialidad: faltan CHECK constraints "
            f"{sorted(faltantes_checks_esp)}."
        )

    # Foreign keys.
    fks_acceso = inspector.get_foreign_keys(
        "acceso_administrativo"
    )

    fk_usuario = next(
        (
            fk for fk in fks_acceso
            if fk.get("constrained_columns") == ["usuario_id"]
            and fk.get("referred_table") == "usuario"
            and fk.get("referred_columns") == ["id"]
        ),
        None,
    )

    if fk_usuario is None:
        errores.append(
            "Falta FK acceso_administrativo.usuario_id "
            "-> usuario.id."
        )
    else:
        ondelete = (
            (fk_usuario.get("options") or {})
            .get("ondelete", "")
            .upper()
        )
        if ondelete != "RESTRICT":
            errores.append(
                "FK usuario_id debe usar ON DELETE RESTRICT."
            )

    fks_esp = inspector.get_foreign_keys(
        "acceso_admin_especialidad"
    )

    fk_acceso = next(
        (
            fk for fk in fks_esp
            if fk.get("constrained_columns")
            == ["acceso_admin_id"]
            and fk.get("referred_table")
            == "acceso_administrativo"
            and fk.get("referred_columns") == ["id"]
        ),
        None,
    )

    if fk_acceso is None:
        errores.append(
            "Falta FK acceso_admin_especialidad.acceso_admin_id "
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
        raise MigracionAccesoAdministrativoError(
            "Migracion SA-8 incompleta:\n- "
            + "\n- ".join(errores)
        )


def migrar_acceso_administrativo_sa8(
    bind: Engine = engine,
    *,
    emitir_mensaje: bool = True,
) -> None:
    with bind.begin() as conn:
        # Orden importante por las foreign keys.
        AccesoAdministrativo.__table__.create(
            bind=conn,
            checkfirst=True,
        )

        AccesoAdminEspecialidad.__table__.create(
            bind=conn,
            checkfirst=True,
        )

        _validar_esquema(conn)

    if emitir_mensaje:
        print(
            "Migracion SA-8 verificada: tablas de perfil y "
            "alcance administrativo creadas correctamente."
        )


if __name__ == "__main__":
    migrar_acceso_administrativo_sa8()
