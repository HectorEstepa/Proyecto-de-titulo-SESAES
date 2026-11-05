/**
 * SESAES — Presentación de estados de Cita (Fase 2.1)
 *
 * Valores reales verificados en backend/app/models/cita.py
 * (`estado = Column(String, default="pendiente")`) y en su uso en
 * frontend/src/app/dashboard-.../*.ts (`cita.estado === '...'`).
 */
import {
  LucideClock3,
  LucideCircleCheck,
  LucideCircleX,
  LucideUserX,
} from '@lucide/angular';
import type { StatusPresentation } from './status-presentation.model';

export type CitaEstado = 'pendiente' | 'completada' | 'cancelada' | 'inasistencia';

export const CITA_STATUS_MAP: Record<CitaEstado, StatusPresentation> = {
  pendiente: { label: 'Pendiente', tone: 'warning', icon: LucideClock3 },
  completada: { label: 'Completada', tone: 'success', icon: LucideCircleCheck },
  cancelada: { label: 'Cancelada', tone: 'danger', icon: LucideCircleX },
  inasistencia: { label: 'Inasistencia', tone: 'danger', icon: LucideUserX },
};

export function citaStatusPresentation(estado: string): StatusPresentation {
  return CITA_STATUS_MAP[estado as CitaEstado] ?? { label: estado, tone: 'neutral' };
}
