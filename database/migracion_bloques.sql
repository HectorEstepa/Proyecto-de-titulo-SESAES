-- Agenda semanal por bloques: tablas nuevas.
--
-- NO hace falta correr este archivo si se levanta el backend: al arrancar,
-- `init_db()` hace `Base.metadata.create_all()` y crea estas dos tablas solas.
-- Sirve para crearlas a mano (por ejemplo desde el SQL Editor de Supabase) si
-- se prefiere hacerlo antes de desplegar. Es idempotente y no modifica ninguna
-- tabla existente.

CREATE TABLE IF NOT EXISTS bloque_horario_semanal (
    id             SERIAL PRIMARY KEY,
    profesional_id INTEGER NOT NULL REFERENCES profesional(id),
    dia_semana     INTEGER NOT NULL,            -- 0=Lunes ... 4=Viernes
    hora_inicio    VARCHAR NOT NULL,            -- 'HH:MM'
    hora_fin       VARCHAR NOT NULL,            -- 'HH:MM'
    tipo           VARCHAR NOT NULL DEFAULT 'disponible'   -- 'disponible' | 'colacion'
);
CREATE INDEX IF NOT EXISTS ix_bloque_horario_semanal_id
    ON bloque_horario_semanal (id);
CREATE INDEX IF NOT EXISTS ix_bloque_horario_semanal_profesional_id
    ON bloque_horario_semanal (profesional_id);

CREATE TABLE IF NOT EXISTS solicitud_horario_bloques (
    solicitud_id INTEGER PRIMARY KEY REFERENCES solicitud_horario(id) ON DELETE CASCADE,
    bloques_json TEXT NOT NULL
);
