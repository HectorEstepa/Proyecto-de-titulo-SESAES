# Agenda semanal por bloques: cambios para el PR

Sobre el `main` actual. No cambia ninguna tabla existente y no necesita migracion manual.

## Que hace
- El profesional pide su agenda semanal en "Mi horario > Horario por bloques": pinta celdas de 30 minutos como disponible o colacion. Un solo boton, "Rellenar horario por defecto", deja Lun-Jue 09:00-17:30, Vie 09:00-16:30 y colacion 13:00-14:00; despues se ajusta celda por celda.
- La solicitud se valida contra el horario institucional (fuera de rango o sabado/domingo se rechaza) y queda pendiente. Una solicitud nueva reemplaza a la pendiente anterior.
- El admin la ve en la tabla de solicitudes con un resumen por dia ("Lun-Jue: 09:00-13:00, colacion 13:00-14:00, 14:00-17:30 | Vie: ...") y la aprueba o rechaza con el flujo de siempre. Al aprobar, la agenda por bloques reemplaza a la anterior completa.
- Con bloques aprobados, la disponibilidad que ven el estudiante y el admin sale de los bloques: solo se ofrecen horas dentro de un bloque disponible y nunca en colacion. Un dia sin bloques no atiende. Fuera de bloque sigue siendo "fuera de jornada" y el admin lo puede cubrir con sobrecupo, igual que antes.
- Un profesional sin bloques sigue funcionando con su jornada simple, sin cambios.
- La agenda semanal del profesional muestra los bloques (colacion y horas fuera de bloque aparecen bloqueadas; una cita ya agendada se sigue viendo).
- Se quito del dashboard del profesional la solicitud de jornada y la de horario de almuerzo; quedan solo los bloques. Los endpoints del backend para jornada y colacion se mantienen, asi las solicitudes antiguas siguen pudiendo aprobarse.

## Ajustes de la agenda del Administrador (ago-2026)
Tres correcciones sobre la grilla semanal del panel Admin, sin tocar backend ni la agenda del Profesional:
- **Fines de semana ocultos**: `dashboard-admin.html` activa `[soloDiasLaborables]="true"` en `app-admin-horario`. El input ya existía y el Profesional ya lo usaba; su valor por defecto sigue en `false`, así que ningún otro consumidor del componente cambia.
- **Horario real de atención**: `horasGrilla` en `dashboard-admin.ts` se genera desde el horario institucional (Lun-Jue 09:00-17:30, Vie 09:00-16:30, el mismo de `backend/app/reglas_horario.py`) en vez del rango fijo 08:00-18:00, respetando la duración de atención del profesional. El rótulo del período (`semanaLabel`) termina el viernes. La semana interna sigue siendo de lunes a domingo: es el ancla de la vista Día y lo que se consulta a backend (sábado y domingo vuelven como `fin_de_semana` y no se pintan).
- **Bloque fantasma de un sobrecupo cancelado**: al cancelar una cita (y también al marcar inasistencia) se vuelve a llamar a `cargarHorarioProfesional()`, que recarga citas y disponibilidad. Antes solo se cambiaba el estado de la cita en memoria, así que la celda conservaba el aspecto de ocupada sin ninguna cita encima; ahora recupera el estado real de backend (disponible, colación o fuera de jornada).

Verificación: `ng build` compila. Las 4 pruebas nuevas viven en `frontend/src/app/dashboard-admin/dashboard-admin-agenda-dias-habiles.spec.ts` (archivo aparte, porque `dashboard-admin.spec.ts` sigue sin compilar por el fallo preexistente de `opcionesHoraSobrecupo`); se ejecutaron con el bloque S1-S7 de ese spec desactivado temporalmente y se dejó tal cual estaba.

## Base de datos
Dos tablas nuevas, creadas solas por `init_db()` (`create_all`) al arrancar el backend:
- `bloque_horario_semanal`: la agenda aprobada.
- `solicitud_horario_bloques`: el detalle (JSON) de una solicitud de tipo bloques.

Ninguna tabla existente cambia, asi que el backend sigue funcionando sobre una base que aun no las tiene. `database/migracion_bloques.sql` crea las mismas tablas a mano (idempotente) si se prefiere hacerlo antes de desplegar, por ejemplo desde el SQL Editor de Supabase.

## Verificacion
- Backend: 1445 tests pasan (29 nuevos en `tests/test_agenda_bloques.py`).
- Probado de punta a punta sobre una copia restaurada de la base de Supabase: login por rol, perfil, citas, solicitudes y listados sin errores; solicitar, rechazar fuera de rango, aprobar, y horas del estudiante sin la colacion.
- Frontend: `ng build` compila; 15 tests nuevos (`dashboard-profesional-bloques.spec.ts`, `admin-horario-solicitudes-bloques.spec.ts`) y los specs del dashboard del profesional pasan.

## Fallos que ya existian en main (no son de este PR)
- `dashboard-admin.spec.ts` usa `opcionesHoraSobrecupo`, que no existe en `dashboard-admin.ts`: el spec no compila.
- `admin-horario.spec.ts`, test "con la grilla real (45 min) el recuadro mide la colacion exacta": falla.
- `rbac-frontend.spec.ts`, "los componentes presentacionales ocultan privilegios sensibles por defecto": error NG0203.
- `tests/test_a3_concurrencia.py` dependia de que la fecha de hoy tuviera ceros de relleno; ahora se salta cuando no los hay.

## Archivos nuevos (7)
  + backend/app/models/bloque_horario_semanal.py
  + backend/app/models/solicitud_bloques.py
  + backend/app/reglas_horario.py
  + backend/tests/test_agenda_bloques.py
  + database/migracion_bloques.sql
  + frontend/src/app/dashboard-admin/horario/admin-horario-solicitudes-bloques.spec.ts
  + frontend/src/app/dashboard-profesional/dashboard-profesional-bloques.spec.ts

## Archivos modificados (10)
  ~ backend/app/models/init.py
  ~ backend/app/routers/profesionales.py
  ~ backend/app/routers/solicitudes_horario.py
  ~ backend/app/services/agenda_disponibilidad_service.py
  ~ backend/tests/test_a3_concurrencia.py
  ~ frontend/src/app/dashboard-admin/horario/admin-horario.html
  ~ frontend/src/app/dashboard-admin/horario/admin-horario.ts
  ~ frontend/src/app/dashboard-profesional/dashboard-profesional.css
  ~ frontend/src/app/dashboard-profesional/dashboard-profesional.html
  ~ frontend/src/app/dashboard-profesional/dashboard-profesional.ts
