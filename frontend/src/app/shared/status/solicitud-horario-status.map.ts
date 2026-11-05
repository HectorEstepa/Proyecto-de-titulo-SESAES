/**
 * SESAES — Presentación de estados de SolicitudHorario (Fase 2.1)
 *
 * Valores reales verificados en backend/app/models/solicitud_horario.py
 * (`estado = Column(String, default="pendiente")  # "pendiente" | "aprobado" | "rechazado"`).
 */
import {
  LucideClock3,
  LucideCircleCheck,
  LucideCircleX,
} from '@lucide/angular';
import type { StatusPresentation } from './status-presentation.model';

export type SolicitudHorarioEstado = 'pendiente' | 'aprobado' | 'rechazado';

export const SOLICITUD_HORARIO_STATUS_MAP: Record<SolicitudHorarioEstado, StatusPresentation> = {
  pendiente: { label: 'Pendiente', tone: 'warning', icon: LucideClock3 },
  aprobado: { label: 'Aprobada', tone: 'success', icon: LucideCircleCheck },
  rechazado: { label: 'Rechazada', tone: 'danger', icon: LucideCircleX },
};

export function solicitudHorarioStatusPresentation(estado: string): StatusPresentation {
  return SOLICITUD_HORARIO_STATUS_MAP[estado as SolicitudHorarioEstado] ?? { label: estado, tone: 'neutral' };
}
