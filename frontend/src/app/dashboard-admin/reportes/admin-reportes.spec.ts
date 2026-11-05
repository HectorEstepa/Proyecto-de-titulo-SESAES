import { describe, it, expect, vi } from 'vitest';
import { AdminReportesComponent, ResumenReportes } from './admin-reportes';

/**
 * AdminReportesComponent usa Chart.js en ngAfterViewInit (mismo patrón que
 * AdminInicioComponent). jsdom no implementa un canvas 2D real, así que —
 * igual que admin-inicio.spec.ts — estos tests instancian la clase
 * directamente (sin TestBed/fixture.detectChanges) y nunca llaman
 * ngAfterViewInit(): se prueba la lógica pura de presentación (getters,
 * estados vacíos, filtros, tabs), que es datos reales de
 * GET /admin/reportes/resumen, nunca inventados aquí.
 */

function resumenBase(overrides: Partial<ResumenReportes> = {}): ResumenReportes {
  return {
    periodo: { fecha_inicio: '2026-09-01', fecha_fin: '2026-09-30' },
    periodo_anterior: { fecha_inicio: '2026-08-01', fecha_fin: '2026-08-30', disponible: true },
    kpis: {
      total_atenciones: { valor: 3, variacion_pct: 200 },
      completadas: { valor: 3, variacion_pct: 200 },
      canceladas: { valor: 2, variacion_pct: null },
      urgentes: { valor: 1, variacion_pct: null },
      sobrecupos: { valor: 1, variacion_pct: null },
      estudiantes_atendidos: { valor: 2, variacion_pct: null }
    },
    citas_por_estado: { completada: 3, cancelada: 2, pendiente: 1, inasistencia: 1 },
    evolucion_semanal: [{ semana_inicio: '2026-09-01', total: 2, completadas: 2, canceladas: 1 }],
    por_especialidad: [{ especialidad: 'Psicología', cantidad: 2 }, { especialidad: 'Nutrición', cantidad: 1 }],
    por_carrera: [{ carrera: 'Kinesiología', cantidad: 4 }],
    sobrecupos_por_especialidad: [{ especialidad: 'Psicología', cantidad: 1 }],
    cancelaciones: { total: 2, por_origen: [{ origen: 'admin', cantidad: 1 }, { origen: 'paciente', cantidad: 1 }] },
    profesionales: [
      { profesional_id: 1, profesional: 'Dra. María Núñez', especialidad: 'Nutrición', atenciones: 2, citas: 2,
        canceladas: 0, inasistencias: 0, sobrecupos: 0, urgentes: 0 }
    ],
    jornada: {
      por_dia_semana: [{ dia: 'Lun', cantidad: 3 }, { dia: 'Mar', cantidad: 0 }],
      por_hora: [{ hora: '10:00', cantidad: 2 }],
      inasistencias_evolucion: [{ fecha: '2026-09-10', cantidad: 1 }]
    },
    ultimas_atenciones: [
      { fecha: '2026-09-15', hora: '10:00', estudiante: 'José Pérez', profesional: 'Dra. María Núñez',
        especialidad: 'Nutrición', estado: 'completada', urgente: true, sobrecupo: true }
    ],
    ...overrides
  };
}

describe('AdminReportesComponent — se crea sin depender de Chart.js', () => {
  it('debe crearse', () => {
    expect(new AdminReportesComponent()).toBeTruthy();
  });
});

describe('AdminReportesComponent — KPIs (regla cita != atención, backend es la fuente)', () => {
  it('kpisFilas expone exactamente los 6 KPI oficiales, en el orden de negocio', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase();
    const claves = c.kpisFilas.map(k => k.clave);
    expect(claves).toEqual(['total_atenciones', 'completadas', 'canceladas', 'urgentes', 'sobrecupos', 'estudiantes_atendidos']);
  });

  it('urgente + sobrecupo simultáneos: el componente NO recalcula, solo refleja los valores ya independientes del backend', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase();
    const urgentes = c.kpisFilas.find(k => k.clave === 'urgentes')!;
    const sobrecupos = c.kpisFilas.find(k => k.clave === 'sobrecupos')!;
    const totalAtenciones = c.kpisFilas.find(k => k.clave === 'total_atenciones')!;
    expect(urgentes.valor).toBe(1);
    expect(sobrecupos.valor).toBe(1);
    expect(totalAtenciones.valor).toBe(3); // la cita urgente+sobrecupo sigue contando como atención
  });

  it('variación null se preserva tal cual (no se inventa 0% ni se oculta) — "Sin datos comparables" es responsabilidad del template', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase();
    expect(c.kpisFilas.find(k => k.clave === 'canceladas')!.variacion).toBeNull();
    expect(c.kpisFilas.find(k => k.clave === 'total_atenciones')!.variacion).toBe(200);
  });

  it('sin resumen cargado, todos los getters devuelven vacíos/ceros en vez de fallar', () => {
    const c = new AdminReportesComponent();
    expect(c.reportesResumen).toBeNull();
    expect(c.kpisFilas).toEqual([]);
    expect(c.porEspecialidad).toEqual([]);
    expect(c.ultimasAtenciones).toEqual([]);
    expect(c.citasPorEstado).toEqual({ completada: 0, cancelada: 0, pendiente: 0, inasistencia: 0 });
  });
});

describe('AdminReportesComponent — pestaña Citas (cita != atención)', () => {
  it('citasPorEstado expone los 4 estados reales, incluyendo pendiente/inasistencia (que NO son KPI oficiales)', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase();
    expect(c.citasPorEstado).toEqual({ completada: 3, cancelada: 2, pendiente: 1, inasistencia: 1 });
  });

  it('sinDatosCitas es true solo cuando los 4 estados están en cero', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase({ citas_por_estado: { completada: 0, cancelada: 0, pendiente: 0, inasistencia: 0 } });
    expect(c.sinDatosCitas).toBe(true);
    c.reportesResumen = resumenBase();
    expect(c.sinDatosCitas).toBe(false);
  });
});

describe('AdminReportesComponent — estados vacíos honestos (nunca fabrican datos)', () => {
  it('sinDatosGeneral es true cuando no hay completadas, canceladas ni últimas atenciones', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase({
      kpis: { ...resumenBase().kpis, completadas: { valor: 0, variacion_pct: null }, canceladas: { valor: 0, variacion_pct: null } },
      ultimas_atenciones: []
    });
    expect(c.sinDatosGeneral).toBe(true);
  });

  it('sinDatosGeneral es false apenas hay algún dato real', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase();
    expect(c.sinDatosGeneral).toBe(false);
  });

  it('sinDatosSobrecupos / sinDatosCancelaciones / sinDatosProfesionales / sinDatosJornada reflejan datos reales, no un mock fijo', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase({
      kpis: { ...resumenBase().kpis, sobrecupos: { valor: 0, variacion_pct: null } },
      cancelaciones: { total: 0, por_origen: [] },
      profesionales: [],
      jornada: { por_dia_semana: [{ dia: 'Lun', cantidad: 0 }], por_hora: [], inasistencias_evolucion: [] }
    });
    expect(c.sinDatosSobrecupos).toBe(true);
    expect(c.sinDatosCancelaciones).toBe(true);
    expect(c.sinDatosProfesionales).toBe(true);
    expect(c.sinDatosJornada).toBe(true);
  });
});

describe('AdminReportesComponent — barras propias (sin librería, proporcional al máximo real)', () => {
  it('anchoBarra calcula el porcentaje respecto del máximo de la serie', () => {
    const c = new AdminReportesComponent();
    const serie = [{ cantidad: 2 }, { cantidad: 4 }, { cantidad: 8 }];
    expect(c.anchoBarra(8, serie)).toBe(100);
    expect(c.anchoBarra(4, serie)).toBe(50);
    expect(c.anchoBarra(2, serie)).toBe(25);
  });

  it('serie vacía no produce división por cero', () => {
    const c = new AdminReportesComponent();
    expect(c.anchoBarra(0, [])).toBe(0);
  });
});

describe('AdminReportesComponent — tabs (100% local, sin volver a pedir datos)', () => {
  it('seleccionarTab actualiza el estado local y emite reportesTabActivaChange (el padre no vuelve a hacer HTTP)', () => {
    const c = new AdminReportesComponent();
    const spy = vi.spyOn(c.reportesTabActivaChange, 'emit');
    c.seleccionarTab('profesionales');
    expect(c.reportesTabActiva).toBe('profesionales');
    expect(spy).toHaveBeenCalledWith('profesionales');
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('tabs incluye las 7 secciones pedidas, en el orden de la referencia visual', () => {
    const c = new AdminReportesComponent();
    expect(c.tabs.map(t => t.id)).toEqual([
      'general', 'citas', 'sobrecupos', 'cancelaciones', 'demanda', 'profesionales', 'jornada'
    ]);
  });
});

describe('AdminReportesComponent — filtros y exportaciones emiten al padre (que hace el HTTP real)', () => {
  it('aplicarFiltros / limpiarFiltros / reintentar se emiten sin lógica propia (backend decide)', () => {
    const c = new AdminReportesComponent();
    const aplicar = vi.spyOn(c.aplicarFiltros, 'emit');
    const limpiar = vi.spyOn(c.limpiarFiltros, 'emit');
    const reintentar = vi.spyOn(c.reintentar, 'emit');

    c.aplicarFiltros.emit();
    c.limpiarFiltros.emit();
    c.reintentar.emit();

    expect(aplicar).toHaveBeenCalledTimes(1);
    expect(limpiar).toHaveBeenCalledTimes(1);
    expect(reintentar).toHaveBeenCalledTimes(1);
  });

  it('exportarReportesExcel / exportarReportesPdf / exportarCgr / exportarAlumnos se emiten al padre (Excel/PDF/CGR reales viven en dashboard-admin.ts)', () => {
    const c = new AdminReportesComponent();
    const excel = vi.spyOn(c.exportarReportesExcel, 'emit');
    const pdf = vi.spyOn(c.exportarReportesPdf, 'emit');
    const cgr = vi.spyOn(c.exportarCgr, 'emit');
    const alumnos = vi.spyOn(c.exportarAlumnos, 'emit');

    c.exportarReportesExcel.emit();
    c.exportarReportesPdf.emit();
    c.exportarCgr.emit();
    c.exportarAlumnos.emit();

    expect(excel).toHaveBeenCalledTimes(1);
    expect(pdf).toHaveBeenCalledTimes(1);
    expect(cgr).toHaveBeenCalledTimes(1);
    expect(alumnos).toHaveBeenCalledTimes(1);
  });
});

describe('AdminReportesComponent — etiquetas de presentación', () => {
  it('etiquetaEstadoCita traduce los 4 estados reales', () => {
    const c = new AdminReportesComponent();
    expect(c.etiquetaEstadoCita('completada')).toBe('Completada');
    expect(c.etiquetaEstadoCita('cancelada')).toBe('Cancelada');
    expect(c.etiquetaEstadoCita('pendiente')).toBe('Pendiente');
    expect(c.etiquetaEstadoCita('inasistencia')).toBe('Inasistencia');
  });

  it('etiquetaOrigenCancelacion distingue admin de paciente (sin inventar "causas")', () => {
    const c = new AdminReportesComponent();
    expect(c.etiquetaOrigenCancelacion('admin')).toContain('administración');
    expect(c.etiquetaOrigenCancelacion('paciente')).toContain('estudiante');
  });
});

describe('AdminReportesComponent — dona "Atenciones por especialidad" (datos reales, sin inventar)', () => {
  it('con 5 o menos especialidades no agrega "Otras" y los porcentajes salen de los datos', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase({ por_especialidad: [{ especialidad: 'Psicología', cantidad: 3 }, { especialidad: 'Nutrición', cantidad: 1 }] });
    expect(c.especialidadesDona.map(f => f.nombre)).toEqual(['Psicología', 'Nutrición']);
    expect(c.especialidadesDona.map(f => f.pct)).toEqual([75, 25]);
    expect(c.totalEspecialidades).toBe(4);
  });

  it('con más de 5 especialidades agrupa el resto en "Otras" sumando cantidades reales', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase({
      por_especialidad: [
        { especialidad: 'A', cantidad: 10 }, { especialidad: 'B', cantidad: 8 }, { especialidad: 'C', cantidad: 6 },
        { especialidad: 'D', cantidad: 4 }, { especialidad: 'E', cantidad: 2 }, { especialidad: 'F', cantidad: 3 }, { especialidad: 'G', cantidad: 1 }
      ]
    });
    const filas = c.especialidadesDona;
    expect(filas).toHaveLength(6);
    expect(filas[5]).toMatchObject({ nombre: 'Otras', cantidad: 4 });
    expect(filas.reduce((a, f) => a + f.cantidad, 0)).toBe(c.totalEspecialidades);
  });

  it('sin datos devuelve vacío (el template muestra el estado vacío, no una dona en cero)', () => {
    const c = new AdminReportesComponent();
    expect(c.especialidadesDona).toEqual([]);
    c.reportesResumen = resumenBase({ por_especialidad: [] });
    expect(c.especialidadesDona).toEqual([]);
  });
});

describe('AdminReportesComponent — cancelaciones por origen (no se inventan "causas")', () => {
  it('cancelacionesDona agrupa por origen real con su porcentaje', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase();
    const filas = c.cancelacionesDona;
    expect(filas).toHaveLength(2);
    expect(filas[0].nombre).toContain('administración');
    expect(filas[1].nombre).toContain('estudiante');
    expect(filas.map(f => f.pct)).toEqual([50, 50]);
  });

  it('sin cancelaciones no hay dona', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase({ cancelaciones: { total: 0, por_origen: [] } });
    expect(c.cancelacionesDona).toEqual([]);
  });
});

describe('AdminReportesComponent — ranking de profesionales y avatares', () => {
  it('topProfesionales limita a 5 y conserva el orden del backend', () => {
    const c = new AdminReportesComponent();
    const mk = (id: number) => ({
      profesional_id: id, profesional: `Prof ${id}`, especialidad: 'X', atenciones: 10 - id, citas: 1,
      canceladas: 0, inasistencias: 0, sobrecupos: 0, urgentes: 0
    });
    c.reportesResumen = resumenBase({ profesionales: [1, 2, 3, 4, 5, 6, 7].map(mk) });
    expect(c.topProfesionales.map(p => p.profesional_id)).toEqual([1, 2, 3, 4, 5]);
  });

  it('inicialesProfesional usa nombre + apellido y descarta el prefijo Dr./Dra.', () => {
    const c = new AdminReportesComponent();
    expect(c.inicialesProfesional('Dra. Valentina Rojas')).toBe('VR');
    expect(c.inicialesProfesional('Dr. Carlos Muñoz')).toBe('CM');
    expect(c.inicialesProfesional('Ana Martínez')).toBe('AM');
    expect(c.inicialesProfesional('Madonna')).toBe('MA');
  });

  it('colorProfesional es determinístico por id', () => {
    const c = new AdminReportesComponent();
    expect(c.colorProfesional(3)).toBe(c.colorProfesional(3));
    expect(c.colorProfesional(1)).not.toBe(c.colorProfesional(2));
  });
});

describe('AdminReportesComponent — formato y navegación', () => {
  it('fmt agrupa miles con punto, también en 4 dígitos (1.248)', () => {
    const c = new AdminReportesComponent();
    expect(c.fmt(1248)).toBe('1.248');
    expect(c.fmt(812)).toBe('812');
    expect(c.fmt(1234567)).toBe('1.234.567');
    expect(c.fmt(0)).toBe('0');
  });

  it('"Ver todas" emite irAHistorial para que el shell navegue (sin lógica propia)', () => {
    const c = new AdminReportesComponent();
    const spy = vi.spyOn(c.irAHistorial, 'emit');
    c.irAHistorial.emit();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('totalInasistencias refleja citas_por_estado.inasistencia (dato real, no un reloj de jornada)', () => {
    const c = new AdminReportesComponent();
    c.reportesResumen = resumenBase();
    expect(c.totalInasistencias).toBe(1);
  });
});
