import { describe, expect, it } from 'vitest';

import { evaluarPassword } from './password-validation';

describe('evaluarPassword', () => {
  it('acepta una contraseña que cumple toda la política SESAES', () => {
    expect(evaluarPassword('Nueva456!')).toEqual({
      minimo8: true,
      mayuscula: true,
      minuscula: true,
      numero: true,
      especial: true,
      sinEspacios: true,
      valida: true,
    });
  });

  it.each([
    'nueva456!',
    'NUEVA456!',
    'NuevaClave!',
    'Nueva456',
    'Nueva 456!',
    'Nu1!',
  ])('rechaza contraseña débil: %s', password => {
    expect(evaluarPassword(password).valida).toBe(false);
  });
});
