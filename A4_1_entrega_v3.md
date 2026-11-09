# A.4.1 v3 FINAL — hardening mínimo de esquema sobre `a4_1_trazabilidad_v2.patch`

**Base obligatoria verificada:** `edc67bc` ✅ (patch generado y re-verificado desde un checkout limpio de ese commit).

`a4_1_trazabilidad_v3.patch` es **acumulativo contra `edc67bc`** (incluye v1 + v2 + estas correcciones). v2 quedó aprobada funcionalmente; v3 solo corrige los cinco puntos de hardening pedidos. No commit, no push, no merge, no A.4.2.

## 1. `CitaSobrecupo.fecha_creacion` ahora `NOT NULL`

```python
fecha_creacion = Column(DateTime, server_default=func.now(), nullable=False)
```

`Cita.fecha_creacion` **no se tocó** — sigue `nullable=True` porque sí existen citas históricas anteriores a A.4.1 con fecha real desconocida. `CitaSobrecupo` es una tabla completamente nueva: no existe, ni puede existir, ningún `CitaSobrecupo` anterior a esta migración, así que no hay ningún caso histórico que compatibilizar — `NOT NULL` es correcto ahí. Documentado explícitamente en el docstring del campo, contrastando ambos casos.

## 2. Validación de invariantes NOT NULL en la migración

`_validar_esquema()` en `migrar_a4_1_trazabilidad.py` ahora, además de FKs/CASCADE/UNIQUE/índices (v2), confirma:

- `cita_sobrecupo.cita_id` → `NOT NULL`.
- `cita_sobrecupo.fecha_creacion` → `NOT NULL`, y sigue verificando su `DEFAULT now()`.
- `cita_sobrecupo.motivo` / `cita_sobrecupo.estado_revision` → **no** se validan como NOT NULL (deliberado — compatibilidad temporal con frontend y preparación para aprobación futura, respectivamente).
- `cita_sobrecupo_conflicto.cita_sobrecupo_id` → `NOT NULL`.
- `cita_sobrecupo_conflicto.codigo` → `NOT NULL`.

Ningún campo de `Cita` se tocó en esta validación — siguen siendo nullable por compatibilidad histórica real, como pide explícitamente el punto 2 del ticket.

## 3. Migración — sin ampliar alcance

No se agregó ninguna columna, tabla, índice ni FK nueva más allá de lo ya presente en v2. Solo se volvió más estricta la *verificación* de lo que ya existía (una columna que antes era `nullable=True` a nivel de modelo/migración ahora es `nullable=False`, y la validación lo confirma).

## 4. Referencias de fases futuras alineadas

Se reemplazaron las menciones a números de subfase que ya no coinciden con el roadmap definitivo:

- `app/models/cita_sobrecupo.py`: "A.4.3" (aprobación) y "A.4.4"/"A.4.5" (lista de conflictos) → reemplazados por frases sin número ("fase futura de aprobación/rechazo del profesional", "fase futura de análisis estructurado de conflictos", "las fases futuras de análisis de conflictos / unificación con urgencias"), siguiendo la opción preferida por el ticket ("escribir 'fase futura de aprobación/conflictos' cuando el número específico no sea necesario").
- Las referencias a **"A.4.7" (frontend)** en `citas.py` y `schemas.py` se dejaron **sin cambio**: en el roadmap definitivo del ticket, A.4.7 sigue siendo la fase de frontend, así que ya estaban alineadas.
- Ningún comportamiento cambió por este punto — solo texto de comentarios/docstrings.

Nota aparte (fuera del patch, informativa): el reporte de diagnóstico A.4 entregado al inicio de esta serie (`A4_diagnostico.md`) también usa la numeración antigua de subfases (A.4.2 notificación, A.4.3 aprobación, A.4.4 lista de conflictos, A.4.5 permisos/urgencias, A.4.6 frontend) en su sección de subfases propuestas. Ese documento no forma parte del patch de código y no se editó acá, pero queda señalado por transparencia: si se retoma como referencia, su numeración de subfases quedó desactualizada frente al roadmap definitivo de este ticket.

## 5. Tests — números reales

Se agregaron dos tests nuevos en `test_a4_1_trazabilidad.py`:

- `test_invariantes_not_null_de_esquema_a41`: confirma `Cita.fecha_creacion`/`creado_por_*` con `nullable is True`, y `CitaSobrecupo.cita_id`/`fecha_creacion` + `CitaSobrecupoConflicto.cita_sobrecupo_id`/`codigo` con `nullable is False` (contra `Base.metadata`, sin tocar una BD real — es un chequeo de definición de esquema).
- `test_cita_sobrecupo_fecha_creacion_la_genera_el_server_default`: crea un sobrecupo real vía `crear_cita()` y confirma que `CitaSobrecupo.fecha_creacion` queda poblada por el `server_default` sin que nadie la fije manualmente.

```
tests/test_a4_1_trazabilidad.py      20 passed   (18 de v2 + 2 nuevos de invariantes NOT NULL)
tests/ -k "a2 or a3"                190 passed, 2 skipped (postgres)
tests/ (suite completa)             995 passed, 3 skipped, 0 failed
git diff --check                    sin salida (sin errores de espacio en blanco)
```

Re-verificado desde un **checkout limpio de `edc67bc`** con `a4_1_trazabilidad_v3.patch` aplicado (`git apply` + suite completa): mismo resultado, `995 passed, 3 skipped`.

`test_a4_1_migracion_postgres.py` sigue sin poder ejecutarse contra PostgreSQL real en este entorno (sin servidor disponible) — se salta explícitamente vía `TEST_POSTGRES_URL` no definida, igual que en v1/v2. La nueva validación de invariantes NOT NULL (`cita_sobrecupo.cita_id`/`fecha_creacion`, `cita_sobrecupo_conflicto.cita_sobrecupo_id`/`codigo`) quedó implementada en `_validar_esquema()` pero, por la misma limitación, no ejercitada contra Postgres real en esta sesión.

## 6. Entrega

- `a4_1_trazabilidad_v3.patch` — acumulativo contra `edc67bc`, verificado con `git apply --check` y con una corrida completa de la suite desde un checkout limpio.
- `A4_1_entrega_v3.md` — este documento.

No se hizo commit, push ni merge. No se inició A.4.2.
