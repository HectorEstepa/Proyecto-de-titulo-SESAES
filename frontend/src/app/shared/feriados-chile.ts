/**
 * Feriados oficiales de Chile.
 * Fuente: calendario oficial 2026 (verificado en fuentes gubernamentales/turísticas).
 * 'nacional' = feriado en todo el país. 'regional' = solo aplica a comunas/regiones
 * específicas (se muestra igual como referencia, pero no implica cierre del centro).
 */
export interface FeriadoChile {
  fecha: string;   // YYYY-MM-DD
  nombre: string;
  tipo: 'nacional' | 'regional';
}

export const FERIADOS_CHILE: FeriadoChile[] = [
  // ── 2026 ──
  { fecha: '2026-01-01', nombre: 'Año Nuevo',                                  tipo: 'nacional' },
  { fecha: '2026-04-03', nombre: 'Viernes Santo',                              tipo: 'nacional' },
  { fecha: '2026-04-04', nombre: 'Sábado Santo',                               tipo: 'nacional' },
  { fecha: '2026-04-05', nombre: 'Domingo de Resurrección',                    tipo: 'nacional' },
  { fecha: '2026-05-01', nombre: 'Día del Trabajo',                            tipo: 'nacional' },
  { fecha: '2026-05-21', nombre: 'Día de las Glorias Navales',                 tipo: 'nacional' },
  { fecha: '2026-06-07', nombre: 'Día de la Batalla de Arica',                 tipo: 'regional' },
  { fecha: '2026-06-20', nombre: 'Día Nacional de los Pueblos Indígenas',      tipo: 'nacional' },
  { fecha: '2026-06-29', nombre: 'San Pedro y San Pablo',                      tipo: 'nacional' },
  { fecha: '2026-07-16', nombre: 'Virgen del Carmen, Reina y Patrona de Chile',tipo: 'nacional' },
  { fecha: '2026-08-15', nombre: 'Asunción de la Virgen',                      tipo: 'nacional' },
  { fecha: '2026-08-20', nombre: 'Natalicio de Bernardo O’Higgins',            tipo: 'regional' },
  { fecha: '2026-09-18', nombre: 'Fiestas Patrias',                            tipo: 'nacional' },
  { fecha: '2026-09-19', nombre: 'Día de las Glorias del Ejército',            tipo: 'nacional' },
  { fecha: '2026-10-12', nombre: 'Día del Descubrimiento de Dos Mundos',       tipo: 'nacional' },
  { fecha: '2026-10-31', nombre: 'Día de las Iglesias Evangélicas y Protestantes', tipo: 'nacional' },
  { fecha: '2026-11-01', nombre: 'Día de Todos los Santos',                    tipo: 'nacional' },
  { fecha: '2026-12-08', nombre: 'Inmaculada Concepción',                      tipo: 'nacional' },
  { fecha: '2026-12-25', nombre: 'Navidad',                                    tipo: 'nacional' },
];

const FERIADOS_MAP: Map<string, FeriadoChile> = new Map(FERIADOS_CHILE.map(f => [f.fecha, f]));

/** Devuelve el feriado en esa fecha (YYYY-MM-DD), o undefined si no es feriado. */
export function obtenerFeriado(fecha: string): FeriadoChile | undefined {
  return FERIADOS_MAP.get(fecha);
}

export function esFeriado(fecha: string): boolean {
  return FERIADOS_MAP.has(fecha);
}
