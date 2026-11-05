/**
 * SESAES — Presentación de estados de Ficha Clínica / filtro de historial (Fase 2.1)
 *
 * Estos valores no son un campo `estado` persistido en
 * backend/app/models/historial_paciente.py (que solo tiene
 * `completado_por` y `revisado_por_profesional: boolean`). Son un
 * vocabulario de PRESENTACIÓN derivado en el frontend:
 * frontend/src/app/dashboard-profesional/dashboard-profesional.ts
 * (`filtroEstadoHistorial: '' | 'completa' | 'sin_completar' | 'por_revisar'`),
 * calculado a partir de los booleanos `tiene_ficha` y `pendiente_revision`
 * que expone backend/app/routers/historial_clinico.py.
 */
import {
  LucideCircleCheck,
  LucideFileClock,
  LucideFileSearch,
} from '@lucide/angular';
import type { StatusPresentation } from './status-presentation.model';

export type FichaClinicaEstado = 'completa' | 'sin_completar' | 'por_revisar';

export const FICHA_CLINICA_STATUS_MAP: Record<FichaClinicaEstado, StatusPresentation> = {
  completa: { label: 'Completa', tone: 'success', icon: LucideCircleCheck },
  sin_completar: { label: 'Sin completar', tone: 'warning', icon: LucideFileClock },
  por_revisar: { label: 'Por revisar', tone: 'info', icon: LucideFileSearch },
};

export function fichaClinicaStatusPresentation(estado: string): StatusPresentation {
  return FICHA_CLINICA_STATUS_MAP[estado as FichaClinicaEstado] ?? { label: estado, tone: 'neutral' };
}
