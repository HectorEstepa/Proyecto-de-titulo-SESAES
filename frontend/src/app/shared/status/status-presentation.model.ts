/**
 * SESAES — Tipos de presentación para Badge / StatusBadge (Fase 2.1)
 *
 * Estos tipos describen ÚNICAMENTE cómo se muestra visualmente un estado
 * (texto, tono semántico, ícono), no el estado de negocio en sí.
 *
 * El backend y los dashboards siguen manejando los estados reales como
 * `string` (ej. `estado === 'pendiente'`); no existe hoy un enum/type
 * compartido entre frontend y backend para estos valores, y esta fase
 * no lo introduce. Cada mapper de dominio traduce el string real del
 * backend a un `StatusPresentation` (ver comentario de StatusPresentation
 * más abajo para la lista de mappers).
 */
import type { LucideIcon } from '@lucide/angular';

/** Tonos semánticos disponibles, definidos por los tokens de Fase 1 (--tone-*). */
export type BadgeTone =
  | 'success'
  | 'info'
  | 'warning'
  | 'danger'
  | 'lavender'
  | 'neutral';

/** Tamaños disponibles para Badge / StatusBadge. */
export type BadgeSize = 'sm' | 'md';

/**
 * Presentación visual de un estado de negocio: qué texto, tono e ícono
 * corresponden a un valor de estado concreto (ej. "pendiente" → Pendiente /
 * warning / Clock3). La construye cada mapper de dominio (los archivos
 * *-status.map.ts de este mismo directorio: cita-status.map.ts,
 * solicitud-horario-status.map.ts, disponibilidad-profesional-status.map.ts,
 * agenda-slot-status.map.ts, ficha-clinica-status.map.ts).
 */
export interface StatusPresentation {
  label: string;
  tone: BadgeTone;
  icon?: LucideIcon;
}
