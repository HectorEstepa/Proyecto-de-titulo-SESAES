import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  NOMBRE_ARCHIVO_ALUMNOS,
  guardarBlob,
  mensajeErrorDescarga,
  nombreArchivoCgr
} from './descarga-archivo';

describe('descarga-archivo — nombres', () => {
  it('conserva los nombres base del backend y cambia solo la extensión a .xlsx', () => {
    expect(nombreArchivoCgr(2026)).toBe('cgr_atenciones_2026.xlsx');
    expect(nombreArchivoCgr('2026', '')).toBe('cgr_atenciones_2026.xlsx');
    expect(nombreArchivoCgr(2026, null)).toBe('cgr_atenciones_2026.xlsx');
    expect(nombreArchivoCgr(2026, '2026-05-31')).toBe('cgr_atenciones_2026_hasta_2026-05-31.xlsx');
    expect(NOMBRE_ARCHIVO_ALUMNOS).toBe('listado_alumnos.xlsx');
  });
});

describe('descarga-archivo — mensajes de error', () => {
  it('distingue permisos, red y error genérico', () => {
    expect(mensajeErrorDescarga(403)).toContain('permisos');
    expect(mensajeErrorDescarga(0)).toContain('conectar');
    expect(mensajeErrorDescarga(500)).toContain('No se pudo descargar');
    expect(mensajeErrorDescarga(404)).toContain('No se pudo descargar');
  });
});

describe('descarga-archivo — guardarBlob', () => {
  afterEach(() => vi.restoreAllMocks());

  it('guarda el blob con el nombre indicado sin abrir ninguna URL ni ventana', () => {
    const createObjectURL = vi.fn(() => 'blob:mock');
    const revokeObjectURL = vi.fn();
    (URL as any).createObjectURL = createObjectURL;
    (URL as any).revokeObjectURL = revokeObjectURL;

    let descargado = '';
    let href = '';
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      descargado = this.download;
      href = this.href;
    });
    const abrir = vi.spyOn(window, 'open');
    vi.useFakeTimers();

    const blob = new Blob(['a\tb\n'], { type: 'text/tab-separated-values' });
    guardarBlob(blob, 'archivo.xls');

    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(descargado).toBe('archivo.xls');
    expect(href).toBe('blob:mock');
    expect(abrir).not.toHaveBeenCalled();

    vi.advanceTimersByTime(60000);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock');
    vi.useRealTimers();
  });
});
