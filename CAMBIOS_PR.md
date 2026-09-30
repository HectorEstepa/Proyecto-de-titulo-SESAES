# Cambios para el PR — Agenda por bloques, rango institucional, aceptar/rechazar cita

Generado automáticamente a partir del merge de 3 vías contra main.

```
ARCHIVOS NUEVOS (4):
  + backend/app/models/ausencia_profesional.py
  + backend/app/models/bloque_horario_semanal.py
  + backend/app/reglas_horario.py
  + backend/scripts/migrar_agenda_bloques.py

ARCHIVOS MODIFICADOS - código (19):
  ~ backend/app/models/cita.py
  ~ backend/app/models/init.py
  ~ backend/app/models/profesional.py
  ~ backend/app/models/solicitud_horario.py
  ~ backend/app/routers/admin.py
  ~ backend/app/routers/citas.py
  ~ backend/app/routers/profesionales.py
  ~ backend/app/routers/solicitudes_horario.py
  ~ backend/app/services/agenda_disponibilidad_service.py
  ~ frontend/src/app/dashboard-admin/dashboard-admin.ts
  ~ frontend/src/app/dashboard-admin/horario/admin-horario.css
  ~ frontend/src/app/dashboard-admin/horario/admin-horario.html
  ~ frontend/src/app/dashboard-admin/horario/admin-horario.ts
  ~ frontend/src/app/dashboard-estudiante/dashboard-estudiante.css
  ~ frontend/src/app/dashboard-estudiante/dashboard-estudiante.html
  ~ frontend/src/app/dashboard-estudiante/dashboard-estudiante.ts
  ~ frontend/src/app/dashboard-profesional/dashboard-profesional.css
  ~ frontend/src/app/dashboard-profesional/dashboard-profesional.html
  ~ frontend/src/app/dashboard-profesional/dashboard-profesional.ts

ARCHIVOS MODIFICADOS - tests (9):
  ~ backend/tests/test_a2_disponibilidad_real.py
  ~ backend/tests/test_a2b_disponibilidad_rango.py
  ~ backend/tests/test_a2c_disponibilidad_duracion_completa.py
  ~ backend/tests/test_a3_concurrencia.py
  ~ backend/tests/test_a4_1_trazabilidad.py
  ~ backend/tests/test_a4_2_conflictos.py
  ~ backend/tests/test_a4_3_politica_sobrecupo.py
  ~ backend/tests/test_a4_4_sobrecupo_slot_ocupado.py
  ~ backend/tests/test_sa9_estado_profesional_alcance.py
```
