export interface PasswordChecklist {
  minimo8: boolean;
  mayuscula: boolean;
  minuscula: boolean;
  numero: boolean;
  especial: boolean;
  sinEspacios: boolean;
  valida: boolean;
}

/**
 * Réplica de UX de la política de contraseñas SESAES.
 *
 * El backend sigue siendo la autoridad y vuelve a validar siempre antes de
 * persistir. Esta función solo permite feedback inmediato y evita duplicar
 * expresiones regulares entre dashboards.
 */
export function evaluarPassword(value: unknown): PasswordChecklist {
  const password = String(value ?? '');

  const minimo8 = Array.from(password).length >= 8;
  const mayuscula = /\p{Lu}/u.test(password);
  const minuscula = /\p{Ll}/u.test(password);
  const numero = /\p{N}/u.test(password);
  const especial = Array.from(password).some(
    char => !/[\p{L}\p{N}\s]/u.test(char)
  );
  const sinEspacios = !/\s/u.test(password);

  return {
    minimo8,
    mayuscula,
    minuscula,
    numero,
    especial,
    sinEspacios,
    valida: minimo8 && mayuscula && minuscula && numero && especial && sinEspacios,
  };
}
