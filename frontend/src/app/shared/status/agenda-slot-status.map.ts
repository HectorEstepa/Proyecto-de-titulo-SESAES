/**
 * SESAES — Presentación de estados de bloque de Agenda (Fase 2.1)
 *
 * Valores reales verificados en
 * frontend/src/app/dashboard-admin/dashboard-admin.ts → getBloqueEstado():
 * 'bloqueado' | 'cerrado-centro' | 'urgente' | 'sobrecupo' | 'ocupado' |
 * 'colacion' | 'fuera-horario' | 'disponible'.
 *
 * Esta fase cubre únicamente el subconjunto especificado
 * (disponible, bloqueado, colacion, fuera-horario, cerrado-centro).
 * Los estados de ocupación real de un bloque con cita (urgente, sobrecupo,
 * ocupado) no se incluyen aquí: dependen de datos de Cita y se resolverán
 * junto con la migración visual de la grilla de agenda en una fase
 * posterior, no en el StatusBadge genérico.
 *
 * "bloqueado": verificado en profesionalActualBloqueado (dashboard-admin.ts) —
 * representa indisponibilidad ADMINISTRATIVA cuando el profesional no está
 * `activo` (licencia/inasistencia), no un estado crítico. Se mantiene
 * tone = warning, no danger.
 */
import {
  LucideCircleCheck,
  LucideLock,
  LucideUtensils,
  LucideMoon,
  LucideDoorClosed,
} from '@lucide/angular';
import type { StatusPresentation } from './status-presentation.model';

export type AgendaSlotEstado =
  | 'disponible'
  | 'bloqueado'
  | 'colacion'
  | 'fuera-horario'
  | 'cerrado-centro';

export const AGENDA_SLOT_STATUS_MAP: Record<AgendaSlotEstado, StatusPresentation> = {
  disponible: { label: 'Disponible', tone: 'success', icon: LucideCircleCheck },
  bloqueado: { label: 'Bloqueado', tone: 'warning', icon: LucideLock },
  colacion: { label: 'Colación', tone: 'lavender', icon: LucideUtensils },
  'fuera-horario': { label: 'Fuera de horario', tone: 'neutral', icon: LucideMoon },
  'cerrado-centro': { label: 'Centro cerrado', tone: 'neutral', icon: LucideDoorClosed },
};

export function agendaSlotStatusPresentation(estado: string): StatusPresentation {
  return AGENDA_SLOT_STATUS_MAP[estado as AgendaSlotEstado] ?? { label: estado, tone: 'neutral' };
}
