/**
 * SESAES — Presentación de estados de disponibilidad del Profesional (Fase 2.1)
 *
 * Valores reales verificados en backend/app/models/profesional.py
 * (`estado = Column(String, default="activo")`) y en su uso en
 * frontend/src/app/dashboard-admin/dashboard-admin.ts.
 *
 * Nota de auditoría: dashboard-admin.ts:1000 también filtra por un valor
 * adicional `'enfermo'` (`['enfermo','inasistencia','licencia'].includes(p.estado)`)
 * que no estaba en el vocabulario especificado para esta fase. Se deja
 * fuera de este mapper — cae en el fallback `neutral` de
 * `disponibilidadProfesionalStatusPresentation` — y se documenta aquí para
 * que se resuelva explícitamente en una fase posterior.
 */
import {
  LucideCircleCheck,
  LucideCalendarOff,
  LucideUserX,
} from '@lucide/angular';
import type { StatusPresentation } from './status-presentation.model';

export type DisponibilidadProfesionalEstado = 'activo' | 'licencia' | 'inasistencia';

export const DISPONIBILIDAD_PROFESIONAL_STATUS_MAP: Record<DisponibilidadProfesionalEstado, StatusPresentation> = {
  activo: { label: 'Activo', tone: 'success', icon: LucideCircleCheck },
  licencia: { label: 'En licencia', tone: 'warning', icon: LucideCalendarOff },
  inasistencia: { label: 'Inasistencia', tone: 'danger', icon: LucideUserX },
};

export function disponibilidadProfesionalStatusPresentation(estado: string): StatusPresentation {
  return DISPONIBILIDAD_PROFESIONAL_STATUS_MAP[estado as DisponibilidadProfesionalEstado]
    ?? { label: estado, tone: 'neutral' };
}
