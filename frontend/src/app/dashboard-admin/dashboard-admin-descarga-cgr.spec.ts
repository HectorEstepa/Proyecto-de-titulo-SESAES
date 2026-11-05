import { ChangeDetectorRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router, provideRouter } from '@angular/router';
import * as XLSX from 'xlsx';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { authInterceptor } from '../auth.interceptor';
import { AuthService } from '../auth.service';
import { environment } from '../config';
import { ToastService } from '../shared/toast/toast.service';
import { DashboardAdminComponent } from './dashboard-admin';
import { COLUMNAS_CGR_ALUMNOS, COLUMNAS_CGR_ATENCIONES, MIME_XLSX } from './reportes/reportes-excel';

/**
 * Exportaciones CGR (B2): el backend entrega los DATOS en JSON, el .xlsx se
 * arma en el frontend con reportes-excel y se guarda desde un Blob. La
 * petición va autenticada con el interceptor REAL (sin Bearer el backend
 * respondería 401) y nunca se usa window.open.
 */

const API = environment.apiUrl;
const URL_ATENCIONES = `${API}/admin/exportar/cgr/datos`;
const URL_ALUMNOS = `${API}/admin/exportar/alumnos/datos`;

const ATENCIONES = {
  columnas: [...COLUMNAS_CGR_ATENCIONES],
  filas: [
    ['José Pérez García', '12.345.678-9', 'Nutrición y Dietética', '2026-09-15', '10:00', 'No aplica', 'Dra. María Núñez'],
    ['ÁLVARO NÚÑEZ', '9.876.543-2', 'Psicología', '2026-09-16', '08:30', 'Paracetamol', 'Dr. Andrés de la Fuente']
  ],
  total: 2
};

const ALUMNOS = {
  columnas: [...COLUMNAS_CGR_ALUMNOS],
  filas: [['ÁLVARO NÚÑEZ', '9.876.543-2', 'Diseño', 'a@utem.cl'], ['—', '—', '—', 's@utem.cl']],
  total: 2
};

async function leerBlob(blob: Blob) {
  const bytes = await new Promise<ArrayBuffer>((ok, error) => {
    const lector = new FileReader();
    lector.onload = () => ok(lector.result as ArrayBuffer);
    lector.onerror = () => error(lector.error);
    lector.readAsArrayBuffer(blob);
  });
  const libro = XLSX.read(bytes, { type: 'array' });
  return {
    bytes: new Uint8Array(bytes),
    hojas: libro.SheetNames,
    matriz: XLSX.utils.sheet_to_json<unknown[]>(libro.Sheets[libro.SheetNames[0]], { header: 1, raw: true }) as unknown[][]
  };
}

describe('Shell — exportaciones CGR (datos JSON + .xlsx en frontend)', () => {
  let http: HttpTestingController;
  let router: Router;
  let toast: { success: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn> };
  let descargas: { nombre: string }[];
  let createObjectURL: ReturnType<typeof vi.fn>;

  function crearShell(puedeExportarCgr = true) {
    const authStub = {
      getNombre: vi.fn(() => 'Sofía'),
      getFotoUrl: vi.fn(() => null),
      getRol: vi.fn(() => 'superadmin'),
      hasPermission: vi.fn((p: string) => (p === 'reportes.cgr.exportar' ? puedeExportarCgr : true)),
      getUsuarioId: vi.fn(() => null)
    } as unknown as AuthService;

    return new DashboardAdminComponent(
      router,
      TestBed.inject(HttpClient),
      { detectChanges: vi.fn(), markForCheck: vi.fn() } as unknown as ChangeDetectorRef,
      toast as unknown as ToastService,
      authStub
    );
  }

  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem('access_token', 'TOKEN-REAL-123');
    sessionStorage.setItem('rol', 'superadmin');

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([])
      ]
    });
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    toast = { success: vi.fn(), error: vi.fn() };

    createObjectURL = vi.fn(() => 'blob:mock');
    (URL as any).createObjectURL = createObjectURL;
    (URL as any).revokeObjectURL = vi.fn();
    descargas = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      descargas.push({ nombre: this.download });
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  const archivoGuardado = (): Blob => createObjectURL.mock.calls[0][0] as Blob;

  // ── Petición ─────────────────────────────────────────────────
  it('pide los datos con el Bearer real, el año y respuesta JSON (no abre ninguna URL)', () => {
    const abrir = vi.spyOn(window, 'open');
    const shell = crearShell();
    shell.cgrAnio = 2026;
    shell.cgrFechaFin = '';

    shell.exportarCGR();

    const req = http.expectOne(r => r.url === URL_ATENCIONES);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer TOKEN-REAL-123');
    expect(req.request.responseType).toBe('json');
    expect(req.request.params.get('anio')).toBe('2026');
    expect(req.request.params.has('fecha_fin')).toBe(false);
    expect(abrir).not.toHaveBeenCalled();
    req.flush(ATENCIONES);
  });

  it('respeta fecha_fin y nombra el archivo .xlsx según los filtros', () => {
    const shell = crearShell();
    shell.cgrAnio = 2026;
    shell.cgrFechaFin = '2026-05-31';

    shell.exportarCGR();

    const req = http.expectOne(r => r.url === URL_ATENCIONES);
    expect(req.request.params.get('anio')).toBe('2026');
    expect(req.request.params.get('fecha_fin')).toBe('2026-05-31');
    req.flush(ATENCIONES);

    expect(descargas).toEqual([{ nombre: 'cgr_atenciones_2026_hasta_2026-05-31.xlsx' }]);
  });

  it('respeta el año elegido y usa el nombre base con solo la extensión cambiada', () => {
    const shell = crearShell();
    shell.cgrAnio = 2025;

    shell.exportarCGR();

    const req = http.expectOne(r => r.url === URL_ATENCIONES);
    expect(req.request.params.get('anio')).toBe('2025');
    req.flush(ATENCIONES);
    expect(descargas[0].nombre).toBe('cgr_atenciones_2025.xlsx');
  });

  // ── Archivo generado ─────────────────────────────────────────
  it('genera un .xlsx real con hoja "Atenciones", encabezados y una fila por atención', async () => {
    const shell = crearShell();
    shell.exportarCGR();
    http.expectOne(r => r.url === URL_ATENCIONES).flush(ATENCIONES);

    const blob = archivoGuardado();
    expect(blob.type).toBe(MIME_XLSX);
    const { bytes, hojas, matriz } = await leerBlob(blob);

    expect([bytes[0], bytes[1]]).toEqual([0x50, 0x4b]);
    expect(hojas).toEqual(['Atenciones']);
    expect(matriz[0]).toEqual([...COLUMNAS_CGR_ATENCIONES]);
    expect(matriz).toHaveLength(3);
    expect(matriz[1]).toEqual([
      'José Pérez García', '12.345.678-9', 'Nutrición y Dietética',
      '15/09/2026', '10:00', 'No aplica', 'Dra. María Núñez'
    ]);
    expect(matriz[2][0]).toBe('ÁLVARO NÚÑEZ');            // Unicode y capitalización originales
    expect(matriz[2][3]).toBe('16/09/2026');
    expect(matriz[2][4]).toBe('08:30');                    // fecha y hora en columnas separadas
  });

  it('el listado de alumnos también va autenticado y produce un .xlsx con hoja "Alumnos"', async () => {
    const abrir = vi.spyOn(window, 'open');
    const shell = crearShell();

    shell.exportarListadoAlumnos();

    const req = http.expectOne(r => r.url === URL_ALUMNOS);
    expect(req.request.headers.get('Authorization')).toBe('Bearer TOKEN-REAL-123');
    expect(req.request.responseType).toBe('json');
    expect(req.request.params.keys()).toEqual([]);
    req.flush(ALUMNOS);

    expect(descargas).toEqual([{ nombre: 'listado_alumnos.xlsx' }]);
    const { hojas, matriz } = await leerBlob(archivoGuardado());
    expect(hojas).toEqual(['Alumnos']);
    expect(matriz[0]).toEqual([...COLUMNAS_CGR_ALUMNOS]);
    expect(matriz.slice(1)).toEqual(ALUMNOS.filas);
    expect(abrir).not.toHaveBeenCalled();
  });

  it('sin registros igual se entrega el archivo con sus encabezados', async () => {
    const shell = crearShell();
    shell.exportarCGR();
    http.expectOne(r => r.url === URL_ATENCIONES).flush({ columnas: [...COLUMNAS_CGR_ATENCIONES], filas: [], total: 0 });

    const { matriz } = await leerBlob(archivoGuardado());
    expect(matriz).toEqual([[...COLUMNAS_CGR_ATENCIONES]]);
  });

  it('los métodos heredados de años fijos usan el mismo flujo autenticado', () => {
    const shell = crearShell();
    const abrir = vi.spyOn(window, 'open');

    shell.exportarCGR2025();
    const r25 = http.expectOne(r => r.url === URL_ATENCIONES);
    expect(r25.request.params.get('anio')).toBe('2025');
    expect(r25.request.headers.get('Authorization')).toBe('Bearer TOKEN-REAL-123');
    r25.flush(ATENCIONES);

    shell.exportarCGR2026();
    const r26 = http.expectOne(r => r.url === URL_ATENCIONES);
    expect(r26.request.params.get('anio')).toBe('2026');
    expect(r26.request.params.get('fecha_fin')).toBe('2026-05-31');
    r26.flush(ATENCIONES);

    expect(abrir).not.toHaveBeenCalled();
    expect(descargas.map(d => d.nombre)).toEqual([
      'cgr_atenciones_2025.xlsx',
      'cgr_atenciones_2026_hasta_2026-05-31.xlsx'
    ]);
  });

  // ── Contrato ─────────────────────────────────────────────────
  it('si el backend responde con columnas distintas NO se genera el archivo y se avisa', () => {
    const shell = crearShell();
    shell.exportarCGR();

    http.expectOne(r => r.url === URL_ATENCIONES)
      .flush({ columnas: ['RUT', 'Nombre Completo'], filas: [['1-9', 'Ana']], total: 1 });

    expect(descargas).toEqual([]);
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('formato inesperado'));
  });

  // ── Errores ──────────────────────────────────────────────────
  it('401: el interceptor cierra la sesión y redirige al login; no hay archivo ni aviso duplicado', () => {
    const shell = crearShell();
    shell.exportarCGR();

    http.expectOne(r => r.url === URL_ATENCIONES)
      .flush({ detail: 'No autenticado' }, { status: 401, statusText: 'Unauthorized' });

    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
    expect(descargas).toEqual([]);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('401 en el listado de alumnos recibe el mismo tratamiento', () => {
    const shell = crearShell();
    shell.exportarListadoAlumnos();

    http.expectOne(r => r.url === URL_ALUMNOS)
      .flush({ detail: 'No autenticado' }, { status: 401, statusText: 'Unauthorized' });

    expect(router.navigate).toHaveBeenCalledWith(['/login']);
    expect(descargas).toEqual([]);
  });

  it('403: avisa que no tiene permisos, no descarga y no cierra la sesión', () => {
    const shell = crearShell();
    shell.exportarCGR();

    http.expectOne(r => r.url === URL_ATENCIONES)
      .flush({ detail: 'Forbidden' }, { status: 403, statusText: 'Forbidden' });

    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('permisos'));
    expect(descargas).toEqual([]);
    expect(router.navigate).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('access_token')).toBe('TOKEN-REAL-123');
  });

  it('500 y error de red: aviso visible y sin archivo', () => {
    const shell = crearShell();

    shell.exportarCGR();
    http.expectOne(r => r.url === URL_ATENCIONES).flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    expect(toast.error).toHaveBeenLastCalledWith(expect.stringContaining('No se pudo descargar'));

    shell.exportarListadoAlumnos();
    http.expectOne(r => r.url === URL_ALUMNOS).error(new ProgressEvent('error'));
    expect(toast.error).toHaveBeenLastCalledWith(expect.stringContaining('conectar'));

    expect(descargas).toEqual([]);
  });

  // ── Permisos ─────────────────────────────────────────────────
  it('sin permiso reportes.cgr.exportar no se hace ninguna petición ni se genera archivo', () => {
    const shell = crearShell(false);

    shell.exportarCGR();
    shell.exportarCGR2025();
    shell.exportarCGR2026();
    shell.exportarListadoAlumnos();

    http.expectNone(r => r.url.includes('/admin/exportar/'));
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(descargas).toEqual([]);
  });

  it('ya no se usa el texto tabulado (.xls) desde el frontend', () => {
    const shell = crearShell();
    shell.exportarCGR();
    shell.exportarListadoAlumnos();

    http.expectNone(r => r.url === `${API}/admin/exportar/cgr`);
    http.expectNone(r => r.url === `${API}/admin/exportar/alumnos`);
    http.expectOne(r => r.url === URL_ATENCIONES).flush(ATENCIONES);
    http.expectOne(r => r.url === URL_ALUMNOS).flush(ALUMNOS);
  });
});
