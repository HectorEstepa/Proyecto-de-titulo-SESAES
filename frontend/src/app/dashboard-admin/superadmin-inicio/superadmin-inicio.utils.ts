/**
 * Utilidades puras del Inicio de SUPERADMIN (formato, etiquetas y
 * geometría de gráficos). Sin Angular ni HTTP: se prueban aisladas.
 */
import { CitasMesPunto, EspecialidadCitas } from './superadmin-inicio.models';

const MESES_CORTOS = [
  'ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic'
];

const MESES_LARGOS = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
];

const dos = (n: number): string => String(n).padStart(2, '0');

/** 'YYYY-MM-DD' (solo fecha) → '22 jun'. Parseo manual: sin desfase de zona. */
export function formatearFechaCorta(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  if (!m) return '—';
  return `${Number(m[3])} ${MESES_CORTOS[Number(m[2]) - 1]}`;
}

/** 'YYYY-MM-DD' → '22 jun 2026'. */
export function formatearFechaDiaMesAnio(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  if (!m) return '—';
  return `${Number(m[3])} ${MESES_CORTOS[Number(m[2]) - 1]} ${m[1]}`;
}

function aFecha(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Timestamp del backend → '19 sep 2026'. Null/ilegible → '—' (nunca inventa). */
export function formatearFecha(iso: string | null | undefined): string {
  const d = aFecha(iso);
  if (!d) return '—';
  return `${d.getDate()} ${MESES_CORTOS[d.getMonth()]} ${d.getFullYear()}`;
}

/** Timestamp del backend → '19 sep 2026, 14:05'. */
export function formatearFechaHora(iso: string | null | undefined): string {
  const d = aFecha(iso);
  if (!d) return '—';
  return `${formatearFecha(iso)}, ${dos(d.getHours())}:${dos(d.getMinutes())}`;
}

/** Mismo criterio que el resumen de actividad del Inicio de ADMIN. */
export function tiempoRelativo(iso: string | null | undefined, ahora = Date.now()): string {
  const d = aFecha(iso);
  if (!d) return '';
  const min = Math.floor((ahora - d.getTime()) / 60000);
  if (min < 1) return 'Hace un momento';
  if (min < 60) return `Hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `Hace ${h} h`;
  return `Hace ${Math.floor(h / 24)} días`;
}

/** 'YYYY-MM' → 'sep'. */
export function etiquetaMesCorto(mes: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(mes);
  return m ? MESES_CORTOS[Number(m[2]) - 1] : mes;
}

/** 'YYYY-MM' → 'septiembre 2026'. */
export function etiquetaMesLargo(mes: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(mes);
  return m ? `${MESES_LARGOS[Number(m[2]) - 1]} ${m[1]}` : mes;
}

export function etiquetaRol(rol: string | null | undefined): string {
  switch ((rol ?? '').toLowerCase()) {
    case 'estudiante': return 'Estudiante';
    case 'profesional': return 'Profesional';
    case 'admin': return 'Administrador';
    case 'superadmin': return 'Superadmin';
    default: return rol ? rol : '—';
  }
}

/** Módulo mostrado para un evento, a partir de la `entidad` real de auditoría. */
export function etiquetaModulo(entidad: string | null | undefined): string {
  switch (entidad) {
    case 'cita': return 'Citas';
    case 'profesional': return 'Profesionales';
    case 'usuario': return 'Usuarios';
    case 'solicitud_horario': return 'Horarios';
    case 'dia_cerrado': return 'Agenda';
    case null:
    case undefined:
    case '': return '—';
    default: {
      const legible = entidad.replace(/_/g, ' ');
      return legible.charAt(0).toUpperCase() + legible.slice(1);
    }
  }
}

export function etiquetaTipoSolicitud(tipo: string | null | undefined): string {
  switch ((tipo ?? '').toLowerCase()) {
    case 'colacion': return 'Colación';
    case 'jornada': return 'Jornada';
    default: return tipo ? tipo : '—';
  }
}

/** Antepone el tratamiento salvo que el nombre ya lo traiga (dato histórico). */
export function nombreConTratamiento(
  p: { nombre: string | null; tratamiento?: string | null }
): string {
  const nombre = (p.nombre ?? '').trim();
  const tratamiento = (p.tratamiento ?? '').trim();
  if (!tratamiento) return nombre;
  return nombre.toLowerCase().startsWith(tratamiento.toLowerCase())
    ? nombre
    : `${tratamiento} ${nombre}`.trim();
}

export function truncar(texto: string | null | undefined, max: number): string {
  const t = (texto ?? '').trim();
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
}

export function inicial(nombre: string | null | undefined, respaldo = '?'): string {
  const t = (nombre ?? '').trim();
  return t ? t.charAt(0).toUpperCase() : respaldo;
}

// ───────────────────────────── Gráficos ─────────────────────────────

/** Paso "redondo" tal que 4 divisiones cubren el máximo (ticks enteros). */
export function pasoEje(maximo: number): number {
  const base = [1, 2, 4, 5, 10];
  let escala = 1;
  for (;;) {
    for (const b of base) {
      const paso = b * escala;
      if (paso * 4 >= maximo) return paso;
    }
    escala *= 10;
  }
}

export interface PuntoLinea {
  x: number;
  y: number;
  mes: string;
  valor: number;
  titulo: string;
}

export interface GraficoLinea {
  ancho: number;
  alto: number;
  base: number;
  puntos: PuntoLinea[];
  path: string;
  area: string;
  ejeY: { y: number; valor: number }[];
  ejeX: { x: number; etiqueta: string }[];
  maximo: number;
  total: number;
}

export function construirGraficoLinea(
  meses: CitasMesPunto[],
  ancho = 560,
  alto = 220
): GraficoLinea {
  const izq = 34, der = 14, arriba = 14, abajo = 26;
  const anchoUtil = ancho - izq - der;
  const altoUtil = alto - arriba - abajo;
  const base = arriba + altoUtil;

  const mayor = Math.max(1, ...meses.map(m => m.cantidad));
  const paso = pasoEje(mayor);
  const maximo = paso * 4;

  const n = meses.length;
  const puntos: PuntoLinea[] = meses.map((m, i) => ({
    x: n > 1 ? izq + (i * anchoUtil) / (n - 1) : izq + anchoUtil / 2,
    y: base - (m.cantidad / maximo) * altoUtil,
    mes: m.mes,
    valor: m.cantidad,
    titulo: `${etiquetaMesLargo(m.mes)}: ${m.cantidad} ${m.cantidad === 1 ? 'cita' : 'citas'}`
  }));

  const r = (v: number) => Math.round(v * 10) / 10;
  const path = puntos.map((p, i) => `${i === 0 ? 'M' : 'L'}${r(p.x)},${r(p.y)}`).join(' ');
  const area = puntos.length
    ? `${path} L${r(puntos[puntos.length - 1].x)},${r(base)} L${r(puntos[0].x)},${r(base)} Z`
    : '';

  return {
    ancho,
    alto,
    base,
    puntos,
    path,
    area,
    ejeY: [0, 1, 2, 3, 4].map(k => ({
      valor: k * paso,
      y: base - (k * paso / maximo) * altoUtil
    })),
    ejeX: puntos.map(p => ({ x: p.x, etiqueta: etiquetaMesCorto(p.mes) })),
    maximo,
    total: meses.reduce((s, m) => s + m.cantidad, 0)
  };
}

export const PALETA_DONUT = [
  '#0d9488', '#4f8ef7', '#e99a24', '#8b65cf', '#d95757', '#94a3b8'
];

export interface SegmentoDonut {
  etiqueta: string;
  cantidad: number;
  porcentaje: number;
  color: string;
  /** Valor para stroke-dasharray. */
  dash: string;
  /** Valor para stroke-dashoffset. */
  offset: number;
}

export interface GraficoDonut {
  total: number;
  radio: number;
  circunferencia: number;
  segmentos: SegmentoDonut[];
}

/**
 * Agrupa en "Otras" lo que exceda `maxSegmentos` y calcula la geometría.
 * Los porcentajes se derivan de las cantidades reales (no del redondeo
 * por fila que entrega el backend).
 */
export function construirDonut(
  items: Pick<EspecialidadCitas, 'especialidad' | 'cantidad'>[],
  maxSegmentos = 6,
  radio = 70
): GraficoDonut {
  const validos = items
    .filter(i => i.cantidad > 0)
    .sort((a, b) => b.cantidad - a.cantidad || a.especialidad.localeCompare(b.especialidad));

  let filas = validos.map(i => ({ etiqueta: i.especialidad || 'Sin especialidad', cantidad: i.cantidad }));

  if (filas.length > maxSegmentos) {
    const visibles = filas.slice(0, maxSegmentos - 1);
    const otras = filas.slice(maxSegmentos - 1).reduce((s, f) => s + f.cantidad, 0);
    filas = [...visibles, { etiqueta: 'Otras', cantidad: otras }];
  }

  const total = filas.reduce((s, f) => s + f.cantidad, 0);
  const circunferencia = 2 * Math.PI * radio;

  let acumulado = 0;
  const segmentos = filas.map((f, i) => {
    const largo = total ? (f.cantidad / total) * circunferencia : 0;
    const segmento: SegmentoDonut = {
      etiqueta: f.etiqueta,
      cantidad: f.cantidad,
      porcentaje: total ? Math.round((f.cantidad / total) * 100) : 0,
      color: PALETA_DONUT[i % PALETA_DONUT.length],
      dash: `${largo.toFixed(2)} ${(circunferencia - largo).toFixed(2)}`,
      offset: -acumulado
    };
    acumulado += largo;
    return segmento;
  });

  return { total, radio, circunferencia, segmentos };
}
