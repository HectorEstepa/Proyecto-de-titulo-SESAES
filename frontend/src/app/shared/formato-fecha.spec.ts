import { fechaCorta, fechaLarga } from './formato-fecha';

describe('formato-fecha', () => {
  it('fechaCorta abrevia el mes en español', () => {
    expect(fechaCorta('2026-07-20')).toBe('20 jul 2026');
    expect(fechaCorta('2026-01-05')).toBe('5 ene 2026');
    expect(fechaCorta('2026-09-30')).toBe('30 sep 2026');
  });

  it('fechaLarga incluye el día de la semana con mayúscula inicial', () => {
    expect(fechaLarga('2026-07-20')).toBe('Lunes, 20 de julio de 2026');
    expect(fechaLarga('2026-10-18')).toBe('Domingo, 18 de octubre de 2026');
  });

  it('no desfasa el día por zona horaria', () => {
    expect(fechaCorta('2026-03-01')).toBe('1 mar 2026');
    expect(fechaLarga('2026-12-31')).toBe('Jueves, 31 de diciembre de 2026');
  });

  it('un texto que no es una fecha ISO se devuelve tal cual', () => {
    expect(fechaCorta('21/09/2026')).toBe('21/09/2026');
    expect(fechaLarga('')).toBe('');
    expect(fechaCorta(null)).toBe('');
    expect(fechaCorta(undefined)).toBe('');
    expect(fechaCorta('2026-13-40')).toBe('2026-13-40');
  });
});
