/**
 * SESAES — Icon map (Fase 1)
 *
 * Mapa de CONCEPTOS VISUALES ESTABLES → icono de @lucide/angular.
 * Estos son conceptos de navegación/acción que no cambian entre
 * dashboards ni dependen del estado de un registro de negocio
 * (cita, solicitud, disponibilidad, etc.).
 *
 * NO agregar aquí íconos para estados de negocio (pendiente,
 * completada, cancelada, aprobado, rechazado, activo, licencia,
 * disponible, bloqueado, colacion, etc.) — ese mapeo
 * (estado real → label → icono → tono) se define en Fase 2
 * junto con el componente StatusBadge, porque cada dominio
 * (Cita, SolicitudHorario, disponibilidad de agenda, ficha
 * clínica) tiene su propio vocabulario de estados y no deben
 * mezclarse en un único enum global.
 */
import {
  LucideHouse,
  LucideCalendarDays,
  LucideSearch,
  LucideBell,
  LucideCircleUserRound,
  LucideSettings,
  LucideEye,
  LucidePencil,
  LucideSave,
  LucideDownload,
  LucideHistory,
  LucideUsers,
  LucideGraduationCap,
  LucideStethoscope,
  LucidePill,
  type LucideIcon,
} from '@lucide/angular';

/**
 * Claves de conceptos visuales estables usadas en los 3 dashboards.
 * Se mantienen en español porque así se usan en el resto del código
 * (labels de navegación, textos de la UI).
 */
export const ICON_MAP = {
  inicio: LucideHouse,
  agenda: LucideCalendarDays,
  buscar: LucideSearch,
  notificaciones: LucideBell,
  perfil: LucideCircleUserRound,
  configuracion: LucideSettings,
  ver: LucideEye,
  editar: LucidePencil,
  guardar: LucideSave,
  descargar: LucideDownload,
  historial: LucideHistory,
  pacientes: LucideUsers,
  estudiantes: LucideGraduationCap,
  profesionales: LucideStethoscope,
  medicamento: LucidePill,
} as const satisfies Record<string, LucideIcon>;

export type IconMapKey = keyof typeof ICON_MAP;
