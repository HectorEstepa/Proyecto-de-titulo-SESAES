/**
 * Helpers puros de la sección "Gestión de Citas" (Admin / SUPERADMIN).
 *
 * Viven fuera del componente para poder probarse sin TestBed y para que la
 * lógica de fechas quede en un solo lugar. No dependen de Angular ni de HTTP.
 */

// ─────────────────────────────────────────────────────────────
// Rangos de fechas
// ─────────────────────────────────────────────────────────────

export type RangoCitas = 'ultimos30' | 'mes' | 'hoy' | 'semana' | 'todas';

export const RANGO_POR_DEFECTO: RangoCitas = 'ultimos30';

export const OPCIONES_RANGO: ReadonlyArray<{ valor: RangoCitas; etiqueta: string }> = [
  { valor: 'ultimos30', etiqueta: 'Últimos 30 días' },
  { valor: 'mes', etiqueta: 'Este mes' },
  { valor: 'hoy', etiqueta: 'Hoy' },
  { valor: 'semana', etiqueta: 'Próximos 7 días' },
  { valor: 'todas', etiqueta: 'Todas las fechas' },
];

export interface VentanaFechas {
  /** YYYY-MM-DD, inclusive. */
  inicio: string;
  /** YYYY-MM-DD, inclusive. */
  fin: string;
}

export interface VentanasRango {
  /** Período que el usuario está viendo. `null` = sin límite de fechas. */
  actual: VentanaFechas | null;
  /** Período inmediatamente anterior, de igual duración, para comparar. */
  previa: VentanaFechas | null;
  /** Texto de comparación para las tarjetas (p. ej. "vs. mes anterior"). */
  comparacion: string;
}

/**
 * Fecha local en formato YYYY-MM-DD.
 *
 * No usa toISOString(): esa función convierte a UTC y, en Chile durante la
 * tarde-noche, devolvería el día siguiente.
 */
export function fechaISOLocal(fecha: Date): string {
  const anio = fecha.getFullYear();
  const mes = String(fecha.getMonth() + 1).padStart(2, '0');
  const dia = String(fecha.getDate()).padStart(2, '0');
  return `${anio}-${mes}-${dia}`;
}

function desplazar(fecha: Date, dias: number): Date {
  return new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate() + dias);
}

/**
 * Calcula el período visible y el período previo equivalente.
 * El previo siempre termina el día anterior al inicio del actual, así ambos
 * pueden pedirse al backend en una sola consulta contigua.
 */
export function ventanasRango(rango: RangoCitas, hoy: Date = new Date()): VentanasRango {
  const base = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());

  switch (rango) {
    case 'hoy': {
      const ayer = desplazar(base, -1);
      return {
        actual: { inicio: fechaISOLocal(base), fin: fechaISOLocal(base) },
        previa: { inicio: fechaISOLocal(ayer), fin: fechaISOLocal(ayer) },
        comparacion: 'vs. ayer',
      };
    }
    case 'semana':
      return {
        actual: { inicio: fechaISOLocal(base), fin: fechaISOLocal(desplazar(base, 6)) },
        previa: {
          inicio: fechaISOLocal(desplazar(base, -7)),
          fin: fechaISOLocal(desplazar(base, -1)),
        },
        comparacion: 'vs. 7 días anteriores',
      };
    case 'mes': {
      const primero = new Date(base.getFullYear(), base.getMonth(), 1);
      const ultimo = new Date(base.getFullYear(), base.getMonth() + 1, 0);
      const primeroPrevio = new Date(base.getFullYear(), base.getMonth() - 1, 1);
      const ultimoPrevio = new Date(base.getFullYear(), base.getMonth(), 0);
      return {
        actual: { inicio: fechaISOLocal(primero), fin: fechaISOLocal(ultimo) },
        previa: { inicio: fechaISOLocal(primeroPrevio), fin: fechaISOLocal(ultimoPrevio) },
        comparacion: 'vs. mes anterior',
      };
    }
    case 'todas':
      return { actual: null, previa: null, comparacion: '' };
    case 'ultimos30':
    default:
      return {
        actual: { inicio: fechaISOLocal(desplazar(base, -29)), fin: fechaISOLocal(base) },
        previa: {
          inicio: fechaISOLocal(desplazar(base, -59)),
          fin: fechaISOLocal(desplazar(base, -30)),
        },
        comparacion: 'vs. 30 días anteriores',
      };
  }
}

export function fechaEnVentana(fecha: string, ventana: VentanaFechas): boolean {
  return fecha >= ventana.inicio && fecha <= ventana.fin;
}

// ─────────────────────────────────────────────────────────────
// Presentación
// ─────────────────────────────────────────────────────────────

/**
 * Iniciales del estudiante (primer nombre + último apellido).
 *
 * El backend devuelve `iniciales` del PROFESIONAL en /agenda/citas, por eso
 * el avatar del estudiante se calcula aquí a partir de su nombre.
 */
/**
 * Iniciales del estudiante: primera letra del primer nombre + primera letra
 * del primer apellido.
 *
 * Convención chilena: [nombre(s)...] [apellido paterno] [apellido materno].
 * Se asume que la mitad inicial de las palabras son nombres y la mitad
 * final son apellidos (si el total es impar, el nombre se queda con la
 * palabra extra, que es el caso más común de un segundo nombre). Así:
 *   "Juan"                          -> J
 *   "Juan Pérez"                    -> JP
 *   "Juan Carlos Pérez"             -> JP  (Juan Carlos = nombre compuesto)
 *   "María Fernanda García López"   -> MG  (primer nombre + primer apellido)
 */
export function inicialesDe(nombre: string | null | undefined): string {
  const partes = String(nombre ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (partes.length === 0) return '?';
  if (partes.length === 1) return partes[0].charAt(0).toUpperCase();

  const mitad = Math.ceil(partes.length / 2);
  return (partes[0].charAt(0) + partes[mitad].charAt(0)).toUpperCase();
}

export const TOTAL_COLORES_AVATAR = 6;

/** Índice estable (0..5) para colorear el avatar según nombre o id. */
export function indiceColorAvatar(clave: string | number | null | undefined): number {
  const texto = String(clave ?? '');
  let suma = 0;
  for (let i = 0; i < texto.length; i++) suma += texto.charCodeAt(i);
  return suma % TOTAL_COLORES_AVATAR;
}

/**
 * Variación porcentual entera entre dos períodos.
 * Devuelve `null` cuando no existe base de comparación (previo = 0 y actual > 0),
 * para no mostrar porcentajes infinitos ni inventados.
 */
export function variacionPorcentual(actual: number, previo: number): number | null {
  if (previo === 0) return actual === 0 ? 0 : null;
  return Math.round(((actual - previo) / previo) * 100);
}

// ─────────────────────────────────────────────────────────────
// Paginación
// ─────────────────────────────────────────────────────────────

export interface ItemPagina {
  num: number;
  elipsis: boolean;
}

/** Ventana de páginas: 1 … 4 5 6 … 20. Con 7 páginas o menos muestra todas. */
export function paginasVisibles(actual: number, total: number): ItemPagina[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => ({ num: i + 1, elipsis: false }));
  }

  const conservar = new Set<number>([1, total]);
  const desde = Math.max(2, Math.min(actual - 1, total - 4));
  const hasta = Math.min(total - 1, Math.max(actual + 1, 5));
  for (let p = desde; p <= hasta; p++) conservar.add(p);

  const ordenadas = [...conservar].sort((a, b) => a - b);
  const items: ItemPagina[] = [];
  let anterior = 0;

  for (const p of ordenadas) {
    if (anterior && p - anterior === 2) items.push({ num: anterior + 1, elipsis: false });
    else if (anterior && p - anterior > 2) items.push({ num: -p, elipsis: true });
    items.push({ num: p, elipsis: false });
    anterior = p;
  }

  return items;
}
