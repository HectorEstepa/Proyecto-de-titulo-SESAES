import { describe, expect, it } from 'vitest';
import {
  PALETA_DONUT,
  construirDonut,
  construirGraficoLinea,
  etiquetaMesCorto,
  etiquetaMesLargo,
  etiquetaModulo,
  etiquetaRol,
  etiquetaTipoSolicitud,
  formatearFecha,
  formatearFechaCorta,
  formatearFechaDiaMesAnio,
  formatearFechaHora,
  inicial,
  nombreConTratamiento,
  pasoEje,
  tiempoRelativo,
  truncar
} from './superadmin-inicio.utils';

describe('Inicio SUPERADMIN — formato de fechas', () => {
  it('formatea fechas solo-día sin desfase de zona horaria', () => {
    expect(formatearFechaCorta('2026-06-22')).toBe('22 jun');
    expect(formatearFechaDiaMesAnio('2026-09-19')).toBe('19 sep 2026');
  });

  it('devuelve "—" ante null/undefined/ilegible: nunca inventa fechas', () => {
    for (const valor of [null, undefined, '', 'no-es-fecha']) {
      expect(formatearFecha(valor)).toBe('—');
      expect(formatearFechaHora(valor)).toBe('—');
      expect(formatearFechaCorta(valor)).toBe('—');
      expect(formatearFechaDiaMesAnio(valor)).toBe('—');
    }
  });

  it('formatea timestamps con fecha y hora', () => {
    expect(formatearFecha('2026-09-19T14:05:00')).toBe('19 sep 2026');
    expect(formatearFechaHora('2026-09-19T14:05:00')).toBe('19 sep 2026, 14:05');
    expect(formatearFechaHora('2026-01-02T03:04:00')).toBe('2 ene 2026, 03:04');
  });

  it('calcula el tiempo relativo como el Inicio de ADMIN', () => {
    const ahora = new Date('2026-09-19T12:00:00').getTime();
    expect(tiempoRelativo('2026-09-19T11:59:40', ahora)).toBe('Hace un momento');
    expect(tiempoRelativo('2026-09-19T11:30:00', ahora)).toBe('Hace 30 min');
    expect(tiempoRelativo('2026-09-19T09:00:00', ahora)).toBe('Hace 3 h');
    expect(tiempoRelativo('2026-09-16T12:00:00', ahora)).toBe('Hace 3 días');
    expect(tiempoRelativo(null, ahora)).toBe('');
  });

  it('etiqueta meses YYYY-MM', () => {
    expect(etiquetaMesCorto('2026-09')).toBe('sep');
    expect(etiquetaMesLargo('2026-09')).toBe('septiembre 2026');
    expect(etiquetaMesLargo('basura')).toBe('basura');
  });
});

describe('Inicio SUPERADMIN — etiquetas', () => {
  it('traduce el rol a un tipo legible', () => {
    expect(etiquetaRol('estudiante')).toBe('Estudiante');
    expect(etiquetaRol('profesional')).toBe('Profesional');
    expect(etiquetaRol('admin')).toBe('Administrador');
    expect(etiquetaRol('superadmin')).toBe('Superadmin');
    expect(etiquetaRol(null)).toBe('—');
  });

  it('mapea la entidad real de auditoría a un módulo', () => {
    expect(etiquetaModulo('cita')).toBe('Citas');
    expect(etiquetaModulo('profesional')).toBe('Profesionales');
    expect(etiquetaModulo('usuario')).toBe('Usuarios');
    expect(etiquetaModulo('solicitud_horario')).toBe('Horarios');
    expect(etiquetaModulo('dia_cerrado')).toBe('Agenda');
    expect(etiquetaModulo('otra_cosa_nueva')).toBe('Otra cosa nueva');
    expect(etiquetaModulo(null)).toBe('—');
  });

  it('etiqueta el tipo de solicitud', () => {
    expect(etiquetaTipoSolicitud('colacion')).toBe('Colación');
    expect(etiquetaTipoSolicitud('jornada')).toBe('Jornada');
    expect(etiquetaTipoSolicitud(null)).toBe('—');
  });

  it('antepone el tratamiento sin duplicarlo', () => {
    expect(nombreConTratamiento({ nombre: 'Ana Pérez', tratamiento: 'Dra.' })).toBe('Dra. Ana Pérez');
    expect(nombreConTratamiento({ nombre: 'Dra. Ana Pérez', tratamiento: 'Dra.' })).toBe('Dra. Ana Pérez');
    expect(nombreConTratamiento({ nombre: 'Ana Pérez', tratamiento: null })).toBe('Ana Pérez');
  });

  it('trunca texto largo y calcula iniciales', () => {
    expect(truncar('abcdefghij', 5)).toBe('abcd…');
    expect(truncar('corto', 10)).toBe('corto');
    expect(truncar(null, 10)).toBe('');
    expect(inicial('  sofía')).toBe('S');
    expect(inicial(null)).toBe('?');
  });
});

describe('Inicio SUPERADMIN — geometría del gráfico de línea', () => {
  const meses = (valores: number[]) =>
    valores.map((cantidad, i) => ({ mes: `2026-${String(i + 1).padStart(2, '0')}`, cantidad }));

  it('elige un paso de eje entero que cubre el máximo en 4 divisiones', () => {
    expect(pasoEje(1)).toBe(1);
    expect(pasoEje(3)).toBe(1);
    expect(pasoEje(4)).toBe(1);
    expect(pasoEje(5)).toBe(2);
    expect(pasoEje(12)).toBe(4);
    expect(pasoEje(37)).toBe(10);
    for (const max of [1, 7, 19, 64, 250, 999]) {
      expect(pasoEje(max) * 4).toBeGreaterThanOrEqual(max);
    }
  });

  it('genera un punto por mes, dentro del área útil, con ejes coherentes', () => {
    const g = construirGraficoLinea(meses([0, 2, 4, 8, 3, 0, 0, 1, 0, 0, 5, 12]));

    expect(g.puntos).toHaveLength(12);
    expect(g.total).toBe(35);
    expect(g.maximo).toBe(16);
    expect(g.ejeY.map(t => t.valor)).toEqual([0, 4, 8, 12, 16]);
    expect(g.ejeX.map(e => e.etiqueta).slice(0, 3)).toEqual(['ene', 'feb', 'mar']);

    for (const p of g.puntos) {
      expect(p.x).toBeGreaterThanOrEqual(34);
      expect(p.x).toBeLessThanOrEqual(g.ancho - 14);
      expect(p.y).toBeGreaterThanOrEqual(14);
      expect(p.y).toBeLessThanOrEqual(g.base);
    }
    // Un valor mayor queda más arriba (y menor) que uno menor.
    expect(g.puntos[11].y).toBeLessThan(g.puntos[1].y);
    // El cero descansa sobre la línea base.
    expect(g.puntos[0].y).toBe(g.base);
  });

  it('construye path y área cerrada', () => {
    const g = construirGraficoLinea(meses([1, 2, 3]));
    expect(g.path.startsWith('M')).toBe(true);
    expect(g.path.match(/L/g)).toHaveLength(2);
    expect(g.area.endsWith('Z')).toBe(true);
  });

  it('describe cada punto con singular/plural', () => {
    const g = construirGraficoLinea([
      { mes: '2026-08', cantidad: 1 },
      { mes: '2026-09', cantidad: 5 }
    ]);
    expect(g.puntos[0].titulo).toBe('agosto 2026: 1 cita');
    expect(g.puntos[1].titulo).toBe('septiembre 2026: 5 citas');
  });
});

describe('Inicio SUPERADMIN — geometría del donut', () => {
  it('reparte porcentajes desde las cantidades reales y ordena de mayor a menor', () => {
    const d = construirDonut([
      { especialidad: 'Nutrición', cantidad: 10 },
      { especialidad: 'Psicología', cantidad: 30 },
      { especialidad: 'Kinesiología', cantidad: 10 }
    ]);

    expect(d.total).toBe(50);
    expect(d.segmentos.map(s => s.etiqueta)).toEqual(['Psicología', 'Kinesiología', 'Nutrición']);
    expect(d.segmentos.map(s => s.porcentaje)).toEqual([60, 20, 20]);
    expect(d.segmentos[0].color).toBe(PALETA_DONUT[0]);
  });

  it('los segmentos suman la circunferencia y no se solapan', () => {
    const d = construirDonut([
      { especialidad: 'A', cantidad: 1 },
      { especialidad: 'B', cantidad: 2 },
      { especialidad: 'C', cantidad: 3 }
    ]);

    const largos = d.segmentos.map(s => Number(s.dash.split(' ')[0]));
    expect(largos.reduce((a, b) => a + b, 0)).toBeCloseTo(d.circunferencia, 0);
    expect(d.segmentos[0].offset).toBe(-0);
    expect(d.segmentos[1].offset).toBeCloseTo(-largos[0], 1);
    expect(d.segmentos[2].offset).toBeCloseTo(-(largos[0] + largos[1]), 1);
  });

  it('agrupa el excedente en "Otras" preservando el total', () => {
    const items = Array.from({ length: 9 }, (_, i) => ({
      especialidad: `Esp ${i}`,
      cantidad: 9 - i
    }));

    const d = construirDonut(items, 6);

    expect(d.segmentos).toHaveLength(6);
    expect(d.segmentos[5].etiqueta).toBe('Otras');
    expect(d.segmentos[5].cantidad).toBe(4 + 3 + 2 + 1); // los 4 menores
    expect(d.total).toBe(45);
    expect(d.segmentos.reduce((s, x) => s + x.cantidad, 0)).toBe(45);
  });

  it('ignora cantidades 0 y soporta un único segmento (100%)', () => {
    const unico = construirDonut([
      { especialidad: 'Psicología', cantidad: 7 },
      { especialidad: 'Nutrición', cantidad: 0 }
    ]);
    expect(unico.segmentos).toHaveLength(1);
    expect(unico.segmentos[0].porcentaje).toBe(100);

    const vacio = construirDonut([{ especialidad: 'X', cantidad: 0 }]);
    expect(vacio.total).toBe(0);
    expect(vacio.segmentos).toEqual([]);
  });

  it('rotula la especialidad vacía como "Sin especialidad"', () => {
    const d = construirDonut([{ especialidad: '', cantidad: 2 }]);
    expect(d.segmentos[0].etiqueta).toBe('Sin especialidad');
  });
});
