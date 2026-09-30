import { ChangeDetectorRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from '../auth.service';
import { ToastService } from '../shared/toast/toast.service';
import { DashboardAdminComponent } from './dashboard-admin';

/**
 * Cableado de las exportaciones Excel del shell con el módulo puro
 * reportes-excel.ts. El contenido del archivo se prueba en
 * reportes/reportes-excel.spec.ts; aquí se comprueba QUÉ recibe cada
 * exportación desde el shell.
 */

function crearShell() {
  const http = { get: vi.fn(), post: vi.fn() } as unknown as HttpClient;
  const auth = {
    getNombre: vi.fn(() => 'Sofía'),
    getFotoUrl: vi.fn(() => null),
    getRol: vi.fn(() => 'superadmin'),
    hasPermission: vi.fn(() => true),
    getUsuarioId: vi.fn(() => null)
  } as unknown as AuthService;

  const shell = new DashboardAdminComponent(
    {} as Router,
    http,
    {} as ChangeDetectorRef,
    { success: vi.fn(), error: vi.fn() } as unknown as ToastService,
    auth
  );
  const exportarComoXlsx = vi.fn();
  (shell as any).exportarComoXlsx = exportarComoXlsx;
  return { shell, http, exportarComoXlsx };
}

const CITAS_FILTRADAS = [
  {
    id: 7, estudiante: 'José Pérez García', rut: '12.345.678-9', carrera: 'Kinesiología',
    especialidad: 'Nutrición y Dietética', profesional: 'Dra. María Núñez',
    fecha: '2026-09-15', hora: '10:00', estado: 'completada'
  },
  {
    id: 8, estudiante: 'Ñandú Soto', rut: '18.000.000-0', carrera: 'Derecho',
    especialidad: 'Nutrición y Dietética', profesional: 'Dra. María Núñez',
    fecha: '2026-09-16', hora: '11:00', estado: 'completada'
  }
];

describe('Shell — exportarHistorialExcel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('exporta exactamente el resultado filtrado que muestra Historial, como .xlsx', () => {
    const { shell, exportarComoXlsx } = crearShell();
    shell.historialAdmin = CITAS_FILTRADAS;

    shell.exportarHistorialExcel();

    expect(exportarComoXlsx).toHaveBeenCalledTimes(1);
    const [filas, nombreArchivo, nombreHoja] = exportarComoXlsx.mock.calls[0];
    expect(nombreArchivo).toBe('historial_citas');
    expect(nombreHoja).toBe('Historial de citas');
    expect(filas).toHaveLength(2);
    expect(filas.map((f: any) => f.Estudiante)).toEqual(['José Pérez García', 'Ñandú Soto']);
  });

  it('cada dato va en su columna: fecha y hora separadas, estado legible, sin códigos ni mezclas', () => {
    const { shell, exportarComoXlsx } = crearShell();
    shell.historialAdmin = CITAS_FILTRADAS;

    shell.exportarHistorialExcel();

    const primera = exportarComoXlsx.mock.calls[0][0][0];
    expect(primera).toEqual({
      Estudiante: 'José Pérez García',
      RUT: '12.345.678-9',
      Carrera: 'Kinesiología',
      Especialidad: 'Nutrición y Dietética',
      Profesional: 'Dra. María Núñez',
      Fecha: '15/09/2026',
      Hora: '10:00',
      Estado: 'Completada'
    });
  });

  it('usa los datos ya cargados: no vuelve a consultar ni "sale" del filtro aplicado', () => {
    const { shell, http } = crearShell();
    shell.historialAdmin = CITAS_FILTRADAS;
    // Filtros escritos pero NO aplicados: no deben influir en el archivo.
    shell.histFiltroEstado = 'cancelada';
    shell.histFiltroEspecialidad = 'Psicología';

    shell.exportarHistorialExcel();

    expect((http.get as any)).not.toHaveBeenCalled();
    const exportar = (shell as any).exportarComoXlsx;
    expect(exportar.mock.calls[0][0]).toHaveLength(2);
  });

  it('un cambio de filtros aplicado (nueva lista) cambia exactamente el contenido exportado', () => {
    const { shell, exportarComoXlsx } = crearShell();

    shell.historialAdmin = CITAS_FILTRADAS;
    shell.exportarHistorialExcel();

    shell.historialAdmin = [CITAS_FILTRADAS[1]];
    shell.exportarHistorialExcel();

    expect(exportarComoXlsx.mock.calls[0][0]).toHaveLength(2);
    expect(exportarComoXlsx.mock.calls[1][0].map((f: any) => f.Estudiante)).toEqual(['Ñandú Soto']);
  });

  it('con el resultado vacío delega en exportarComoXlsx (que avisa "No hay datos") sin inventar filas', () => {
    const { shell, exportarComoXlsx } = crearShell();
    shell.historialAdmin = [];

    shell.exportarHistorialExcel();

    expect(exportarComoXlsx).toHaveBeenCalledWith([], 'historial_citas', 'Historial de citas');
  });
});

describe('Shell — exportarEspecialidadExcel', () => {
  it('conserva las columnas originales (compatibilidad) con tildes intactas', () => {
    const { shell, exportarComoXlsx } = crearShell();
    shell.graficoEspecialidad = [
      { especialidad: 'Nutrición y Dietética', cantidad: 30, porcentaje: 60 },
      { especialidad: 'Psicología', cantidad: 20, porcentaje: 40 }
    ];

    shell.exportarEspecialidadExcel();

    expect(exportarComoXlsx).toHaveBeenCalledWith(
      [
        { Especialidad: 'Nutrición y Dietética', Cantidad: 30, Porcentaje: '60%' },
        { Especialidad: 'Psicología', Cantidad: 20, Porcentaje: '40%' }
      ],
      'citas_por_especialidad',
      'Citas por especialidad'
    );
  });
});
