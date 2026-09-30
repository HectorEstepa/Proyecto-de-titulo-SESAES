import * as XLSX from 'xlsx';

/**
 * Construcción de las exportaciones Excel de Reportes/Historial.
 *
 * Funciones PURAS (sin DOM ni descargas) para poder verificar exactamente
 * qué se exporta. Reglas de formato:
 *
 *  · Un dato por columna y un registro por fila: nunca se concatenan
 *    campos distintos en una misma celda.
 *  · Encabezados fijos y en el mismo orden siempre (constantes COLUMNAS_*).
 *  · Fecha (DD/MM/AAAA) y Hora (HH:MM) en columnas separadas.
 *  · Los estados salen legibles ("Completada"), no como código interno.
 *  · Los textos se exportan TAL CUAL vienen del origen (tildes, ñ,
 *    mayúsculas/minúsculas). Ninguna normalización de búsqueda toca los
 *    valores exportados.
 *  · El archivo es un .xlsx real (UTF-8 nativo), no texto tabulado.
 *
 * Nota: el origen guarda el nombre del estudiante/profesional en UN solo
 * campo ("nombre completo"). No se parte en Nombre/Apellido porque no hay
 * forma fiable de hacerlo (apellidos compuestos, nombres compuestos) y
 * sería inventar datos.
 */

export const ETIQUETAS_ESTADO_CITA: Readonly<Record<string, string>> = {
  pendiente: 'Pendiente',
  completada: 'Completada',
  cancelada: 'Cancelada',
  inasistencia: 'Inasistencia'
};

/** Estado legible. Un estado desconocido se conserva tal cual (no se oculta). */
export function etiquetaEstadoCita(estado: unknown): string {
  const original = String(estado ?? '').trim();
  if (!original) return '';
  return ETIQUETAS_ESTADO_CITA[original.toLowerCase()] ?? original;
}

/** 'YYYY-MM-DD' → 'DD/MM/YYYY'. Si no es ISO se conserva el valor original. */
export function formatearFechaExcel(fecha: unknown): string {
  const original = String(fecha ?? '').trim();
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(original);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : original;
}

const texto = (valor: unknown): string => (valor === null || valor === undefined ? '' : String(valor));

// ── Historial de citas ─────────────────────────────────────────
export const COLUMNAS_HISTORIAL = [
  'Estudiante', 'RUT', 'Carrera', 'Especialidad', 'Profesional', 'Fecha', 'Hora', 'Estado'
] as const;

export type FilaHistorialExcel = Record<(typeof COLUMNAS_HISTORIAL)[number], string>;

/**
 * Una fila por cita, en el mismo orden en que se recibe. Recibe la lista
 * YA filtrada (la que muestra Historial tras "Aplicar filtros"): esta
 * función no filtra ni consulta nada, por lo que el Excel contiene
 * exactamente el resultado filtrado.
 */
export function filasHistorialExcel(historial: readonly any[]): FilaHistorialExcel[] {
  return historial.map(h => ({
    Estudiante: texto(h.estudiante),
    RUT: texto(h.rut),
    Carrera: texto(h.carrera),
    Especialidad: texto(h.especialidad),
    Profesional: texto(h.profesional),
    Fecha: formatearFechaExcel(h.fecha),
    Hora: texto(h.hora),
    Estado: etiquetaEstadoCita(h.estado)
  }));
}

// ── Citas por especialidad ─────────────────────────────────────
export const COLUMNAS_ESPECIALIDAD = ['Especialidad', 'Cantidad', 'Porcentaje'] as const;

/** Mismas columnas y valores que la exportación original (compatibilidad). */
export function filasEspecialidadExcel(
  items: readonly { especialidad: string; cantidad: number; porcentaje: number }[]
): Record<(typeof COLUMNAS_ESPECIALIDAD)[number], string | number>[] {
  return items.map(d => ({
    Especialidad: d.especialidad,
    Cantidad: d.cantidad,
    Porcentaje: d.porcentaje + '%'
  }));
}

// ── Libro ──────────────────────────────────────────────────────
/** Libro de una hoja: encabezados = claves de la primera fila, en orden. */
export function construirLibroXlsx(datos: readonly object[], nombreHoja: string): XLSX.WorkBook {
  const hoja = XLSX.utils.json_to_sheet(datos as object[]);
  const libro = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(libro, hoja, nombreHoja);
  return libro;
}

// ── Exportaciones CGR (atenciones y listado de alumnos) ────────────
/**
 * Contrato de las exportaciones CGR. Las REGLAS (qué filas, exclusiones,
 * orden y valores vacíos) las aplica el backend en /admin/exportar/cgr/datos
 * y /admin/exportar/alumnos/datos; aquí solo se le da forma de hoja Excel.
 * Los encabezados y su orden son los que ya definía el endpoint.
 */
export const COLUMNAS_CGR_ATENCIONES = [
  'Nombre Completo', 'RUT', 'Tipo de Atención', 'Fecha', 'Hora',
  'Medicamento Suministrado', 'Profesional que Atendió'
] as const;

export const COLUMNAS_CGR_ALUMNOS = ['Nombre Completo', 'RUT', 'Carrera', 'Correo'] as const;

export const NOMBRE_HOJA_CGR_ATENCIONES = 'Atenciones';
export const NOMBRE_HOJA_CGR_ALUMNOS = 'Alumnos';

/** Valor ausente: el backend ya lo entrega como "—"; se respeta la misma semántica. */
export const SIN_DATO = '—';

/** Respuesta de los endpoints de datos: /exportar/cgr/datos y /exportar/alumnos/datos. */
export interface TablaCgr {
  columnas: string[];
  filas: (string | null)[][];
  total?: number;
}

/** El backend respondió con columnas distintas a las del contrato. */
export class FormatoCgrInesperadoError extends Error {
  constructor(esperadas: readonly string[], recibidas: readonly string[]) {
    super(
      `Columnas inesperadas en la exportación CGR. Esperadas: [${esperadas.join(', ')}]; ` +
      `recibidas: [${recibidas.join(', ')}].`
    );
    this.name = 'FormatoCgrInesperadoError';
  }
}

function validarTabla(tabla: TablaCgr, esperadas: readonly string[]): void {
  const recibidas = Array.isArray(tabla?.columnas) ? tabla.columnas : [];
  const igual = recibidas.length === esperadas.length && esperadas.every((c, i) => c === recibidas[i]);
  if (!igual) throw new FormatoCgrInesperadoError(esperadas, recibidas);
  if (!Array.isArray(tabla.filas) || tabla.filas.some(f => !Array.isArray(f) || f.length !== esperadas.length)) {
    throw new FormatoCgrInesperadoError(esperadas, ['filas con formato distinto al de las columnas']);
  }
}

const valorCgr = (v: unknown): string => (v === null || v === undefined || v === '' ? SIN_DATO : String(v));

/**
 * Filas de "Atenciones": un valor de texto por celda, en el orden del contrato.
 * Fecha → DD/MM/AAAA y Hora → HH:MM, en columnas separadas (como texto, igual
 * que el resto de los reportes). Todo lo demás (tildes, ñ, mayúsculas, "No
 * aplica", "—") se conserva tal cual lo entrega el backend.
 */
export function filasCgrAtencionesExcel(tabla: TablaCgr): string[][] {
  validarTabla(tabla, COLUMNAS_CGR_ATENCIONES);
  const iFecha = COLUMNAS_CGR_ATENCIONES.indexOf('Fecha');
  return tabla.filas.map(fila =>
    fila.map((valor, i) => (i === iFecha ? formatearFechaExcel(valor) || SIN_DATO : valorCgr(valor)))
  );
}

/** Filas de "Alumnos": valores tal cual, en el orden del contrato. */
export function filasCgrAlumnosExcel(tabla: TablaCgr): string[][] {
  validarTabla(tabla, COLUMNAS_CGR_ALUMNOS);
  return tabla.filas.map(fila => fila.map(valorCgr));
}

const ANCHO_MINIMO = 10;
const ANCHO_MAXIMO = 60;

/**
 * Libro de una hoja a partir de encabezados + filas. La fila de encabezados
 * existe SIEMPRE (también con cero registros), tiene autofiltro y cada columna
 * un ancho razonable según su contenido.
 */
export function construirLibroTabla(
  columnas: readonly string[],
  filas: readonly (readonly string[])[],
  nombreHoja: string
): XLSX.WorkBook {
  const hoja = XLSX.utils.aoa_to_sheet([[...columnas], ...filas.map(f => [...f])]);

  hoja['!cols'] = columnas.map((encabezado, c) => {
    const mayor = filas.reduce((max, fila) => Math.max(max, String(fila[c] ?? '').length), encabezado.length);
    return { wch: Math.min(Math.max(mayor + 2, ANCHO_MINIMO), ANCHO_MAXIMO) };
  });

  hoja['!autofilter'] = {
    ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: filas.length, c: columnas.length - 1 } })
  };

  const libro = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(libro, hoja, nombreHoja);
  return libro;
}

export function libroCgrAtenciones(tabla: TablaCgr): XLSX.WorkBook {
  return construirLibroTabla(COLUMNAS_CGR_ATENCIONES, filasCgrAtencionesExcel(tabla), NOMBRE_HOJA_CGR_ATENCIONES);
}

export function libroCgrAlumnos(tabla: TablaCgr): XLSX.WorkBook {
  return construirLibroTabla(COLUMNAS_CGR_ALUMNOS, filasCgrAlumnosExcel(tabla), NOMBRE_HOJA_CGR_ALUMNOS);
}

export const MIME_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/** Serializa el libro a un .xlsx real (contenedor ZIP/OOXML) listo para guardar. */
export function libroAXlsxBlob(libro: XLSX.WorkBook): Blob {
  const bytes = XLSX.write(libro, { type: 'array', bookType: 'xlsx' }) as ArrayBuffer;
  return new Blob([bytes], { type: MIME_XLSX });
}
