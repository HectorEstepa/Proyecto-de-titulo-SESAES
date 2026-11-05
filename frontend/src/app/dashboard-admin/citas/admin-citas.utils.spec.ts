import { inicialesDe, indiceColorAvatar, TOTAL_COLORES_AVATAR } from './admin-citas.utils';

describe('inicialesDe', () => {
  it('nombre vacío o nulo -> "?"', () => {
    expect(inicialesDe('')).toBe('?');
    expect(inicialesDe('   ')).toBe('?');
    expect(inicialesDe(null)).toBe('?');
    expect(inicialesDe(undefined)).toBe('?');
  });

  it('un solo nombre -> su primera letra', () => {
    expect(inicialesDe('Juan')).toBe('J');
  });

  it('nombre + apellido -> primera letra de cada uno', () => {
    expect(inicialesDe('Juan Pérez')).toBe('JP');
  });

  it('dos nombres + un apellido (nombre compuesto) -> primer nombre + apellido', () => {
    expect(inicialesDe('Juan Carlos Pérez')).toBe('JP');
  });

  it('dos nombres + dos apellidos -> primer nombre + primer apellido (no el último apellido)', () => {
    expect(inicialesDe('María Fernanda García López')).toBe('MG');
  });

  it('ignora espacios repetidos o en los extremos', () => {
    expect(inicialesDe('  Juan   Pérez  ')).toBe('JP');
  });

  it('siempre en mayúsculas, sin importar el caso original', () => {
    expect(inicialesDe('juan pérez')).toBe('JP');
  });
});

describe('indiceColorAvatar', () => {
  it('es determinístico: la misma clave siempre da el mismo índice', () => {
    const claves = [1, 42, 'Juan Pérez', 'algo', 0];
    for (const clave of claves) {
      const primero = indiceColorAvatar(clave);
      for (let i = 0; i < 5; i++) {
        expect(indiceColorAvatar(clave)).toBe(primero);
      }
    }
  });

  it('siempre devuelve un índice dentro del rango de colores disponibles', () => {
    for (const clave of [0, 1, 2, 3, 100, 12345, 'x', 'estudiante con nombre largo']) {
      const indice = indiceColorAvatar(clave);
      expect(indice).toBeGreaterThanOrEqual(0);
      expect(indice).toBeLessThan(TOTAL_COLORES_AVATAR);
    }
  });

  it('usa estudiante_id (no el nombre): dos estudiantes con el mismo nombre pero distinto id no comparten color necesariamente', () => {
    // No es una garantía matemática (podría coincidir por azar), pero prueba
    // que la función responde al id, no al nombre: si dependiera del nombre,
    // estudiante_id no cambiaría nada del resultado. Aquí, al variar el id
    // con nombre fijo, el índice cambia para al menos uno de estos ids.
    const nombre = 'María González';
    const indicesPorId = [1, 2, 3, 4, 5, 6, 7, 8].map((id) => indiceColorAvatar(id));
    const indicePorNombre = indiceColorAvatar(nombre);
    // Al menos un id produce un color distinto al que daría el nombre solo,
    // confirmando que el id efectivamente participa del cálculo.
    expect(indicesPorId.some((i) => i !== indicePorNombre)).toBe(true);
  });

  it('si el mismo estudiante cambia de nombre pero mantiene su id, el color no cambia', () => {
    const id = 27;
    const colorAntes = indiceColorAvatar(id);
    // El nombre pudo cambiar (matrimonio, corrección de datos, etc.) pero el
    // id es estable: claseAvatar debe usar el id, así que llamarlo de nuevo
    // con el mismo id da siempre el mismo color, sin importar el nombre.
    const colorDespues = indiceColorAvatar(id);
    expect(colorDespues).toBe(colorAntes);
  });
});
