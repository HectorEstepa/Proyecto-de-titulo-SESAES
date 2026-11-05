"""
Helper central de auditoría (SA-2).

Reemplaza los 3 `registrar_auditoria` locales de admin.py, profesionales.py
y solicitudes_horario.py.

Contrato de seguridad (acordado, no renegociable en SA-2):
- El actor (usuario_id, actor_rol) se deriva EXCLUSIVAMENTE de
  `current_user`, nunca se acepta usuario_id/actor_id/actor_rol como
  parámetro externo del helper.
- current_user["id"] y current_user["rol"] son obligatorios: su ausencia
  falla cerrado (ValueError). Nunca se persiste un evento con actor
  desconocido de forma silenciosa.
- `resultado` solo puede ser "exito", "denegado" o "error"; cualquier
  otro valor lanza ValueError.
- Este helper SOLO hace `db.add(...)`. Nunca hace commit() ni
  rollback(): la transaccionalidad (commit único junto con la mutación
  de negocio, o rollback + commit best-effort del evento de error) es
  responsabilidad exclusiva del call-site.
- NUNCA pasar detalle=str(exc): una excepción puede contener información
  sensible. El call-site debe pasar solo mensajes/códigos de error
  seguros, definidos explícitamente.
"""

from typing import Any, Mapping, Optional

from app.models.auditoria import Auditoria

RESULTADOS_VALIDOS = {"exito", "denegado", "error"}


def registrar_evento_auditoria(
    db,
    current_user: Mapping[str, Any],
    accion: str,
    *,
    resultado: str = "exito",
    entidad: Optional[str] = None,
    entidad_id: Optional[int] = None,
    detalle: Optional[str] = None,
) -> Auditoria:
    """
    Construye un evento de Auditoria y lo agrega a la sesión (db.add).
    No hace commit ni rollback.

    Lanza ValueError si:
    - `resultado` no está en RESULTADOS_VALIDOS
    - current_user no trae "id"
    - current_user no trae "rol"
    """
    if resultado not in RESULTADOS_VALIDOS:
        raise ValueError(
            f"resultado inválido: {resultado!r}. "
            f"Debe ser uno de {sorted(RESULTADOS_VALIDOS)}."
        )

    usuario_id = current_user.get("id") if current_user else None
    actor_rol = current_user.get("rol") if current_user else None

    if usuario_id is None:
        raise ValueError(
            "No se puede registrar un evento de auditoría sin "
            "current_user['id']: el actor nunca se infiere ni se acepta "
            "como parámetro externo."
        )
    if not actor_rol:
        raise ValueError(
            "No se puede registrar un evento de auditoría sin "
            "current_user['rol']: el actor nunca se infiere ni se acepta "
            "como parámetro externo."
        )

    evento = Auditoria(
        usuario_id=usuario_id,
        actor_rol=actor_rol,
        accion=accion,
        resultado=resultado,
        entidad=entidad,
        entidad_id=entidad_id,
        detalle=detalle,
    )
    db.add(evento)
    return evento


def describir_cita(cita) -> str:
    """
    Identificación no sensible de una cita para el `detalle` de auditoría.

    Usa únicamente ids y fecha/hora (nunca nombre, RUT ni motivo de
    consulta): el detalle de auditoría no debe convertirse en una copia
    de datos clínicos ni personales. El nombre del paciente, si se
    necesita, se resuelve en la vista administrativa cruzando
    `usuario_id`/`entidad_id`, no se congela acá.
    """
    return (
        f"Estudiante id {cita.estudiante_id} — Profesional id "
        f"{cita.profesional_id} — {cita.fecha} {cita.hora}"
    )


def registrar_evento_cita(
    db,
    current_user: Mapping[str, Any],
    accion: str,
    *,
    cita,
    detalle: Optional[str] = None,
    resultado: str = "exito",
) -> Auditoria:
    """
    Variante especializada del helper central para la agenda médica.

    Fija SIEMPRE `entidad="cita"` y `entidad_id=cita.id`, de modo que el
    historial completo de una cita (creación, modificación, anulación)
    se reconstruye filtrando:

        Auditoria.entidad == "cita" AND Auditoria.entidad_id == <id>

    El actor y el timestamp exacto siguen saliendo de `current_user` y
    de `Auditoria.fecha` (DEFAULT now() del motor), respectivamente;
    esta función no acepta ni infiere ninguno de los dos. Mantiene el
    mismo contrato transaccional que registrar_evento_auditoria(): solo
    hace db.add(), el call-site controla commit/rollback.

    `cita` debe tener `id` (flush previo). Si no lo tiene, se falla
    cerrado con ValueError en vez de persistir un evento huérfano con
    entidad_id=NULL que no se podría asociar a ninguna cita.
    """
    if getattr(cita, "id", None) is None:
        raise ValueError(
            "No se puede auditar una cita sin id: haz flush() de la "
            "cita antes de registrar el evento."
        )

    return registrar_evento_auditoria(
        db,
        current_user,
        accion,
        resultado=resultado,
        entidad="cita",
        entidad_id=cita.id,
        detalle=detalle,
    )
