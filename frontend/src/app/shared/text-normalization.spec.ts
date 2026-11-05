import { describe, expect, it } from 'vitest';

import { coincideBusqueda, normalizarTexto } from './text-normalization';

describe('text-normalization', () => {
  it('normaliza tildes, mayúsculas y espacios repetidos', () => {
    expect(normalizarTexto('  José   PÉREZ  ')).toBe('jose perez');
  });

  it('busca sobre varios campos ya normalizados', () => {
    expect(coincideBusqueda('jose perez', 'José Pérez', 'Psicología')).toBe(true);
    expect(coincideBusqueda('psicologia', 'José Pérez', 'Psicología')).toBe(true);
    expect(coincideBusqueda('odontologia', 'José Pérez', 'Psicología')).toBe(false);
  });

  it('una consulta vacía no filtra', () => {
    expect(coincideBusqueda('   ', 'Cualquier valor')).toBe(true);
  });
});
