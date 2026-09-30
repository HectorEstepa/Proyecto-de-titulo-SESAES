/**
 * Utilidades para guardar archivos descargados de la API con AUTENTICACIÓN.
 *
 * `window.open(url)` NO puede enviar la cabecera `Authorization: Bearer`, y
 * el backend responde 401 sin ella. Las descargas protegidas deben pedirse
 * con HttpClient (así pasan por auth.interceptor, que adjunta el Bearer y
 * maneja el 401 cerrando sesión) y guardarse desde un Blob.
 */

/**
 * Nombres base que ya definía el backend en /admin/exportar/* (texto
 * tabulado .xls); el .xlsx conserva el nombre y solo cambia la extensión.
 */
export function nombreArchivoCgr(anio: number | string, fechaFin?: string | null): string {
  return `cgr_atenciones_${anio}${fechaFin ? `_hasta_${fechaFin}` : ''}.xlsx`;
}

export const NOMBRE_ARCHIVO_ALUMNOS = 'listado_alumnos.xlsx';

/** Mensaje para el usuario según el estado HTTP (el 401 lo maneja el interceptor). */
export function mensajeErrorDescarga(status: number): string {
  if (status === 403) return 'No tienes permisos para descargar este archivo.';
  if (status === 0) return 'No se pudo conectar con el servidor. Revisa tu conexión.';
  return 'No se pudo descargar el archivo. Intenta nuevamente.';
}

/** Guarda un Blob como archivo descargado (sin abrir ninguna URL). */
export function guardarBlob(blob: Blob, nombreArchivo: string): void {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = nombreArchivo;
  enlace.rel = 'noopener';
  enlace.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
