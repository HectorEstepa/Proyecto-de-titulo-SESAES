/**
 * SESAES — RBAC frontend: roles.
 *
 * Los STRING VALUES coinciden EXACTAMENTE con backend/app/rbac/roles.py.
 * El frontend usa estos valores únicamente para UX/navegación.
 * La autorización real permanece en el backend.
 */

export type Role = 'superadmin' | 'admin' | 'profesional' | 'estudiante';

export const ROLES: readonly Role[] = [
  'superadmin',
  'admin',
  'profesional',
  'estudiante',
] as const;

/**
 * Normaliza un valor de rol crudo a un Role válido.
 * Fail-closed: null, vacío o desconocido -> null.
 */
export function normalizarRol(
  value: string | null | undefined
): Role | null {
  if (!value) return null;

  const normalizado = value.trim().toLowerCase();

  return (ROLES as readonly string[]).includes(normalizado)
    ? (normalizado as Role)
    : null;
}

/**
 * Ruta principal correspondiente a cada rol.
 *
 * ADMIN y SUPERADMIN comparten deliberadamente el mismo shell
 * administrativo. Sus diferencias de acceso se resuelven mediante
 * permisos RBAC, no mediante dashboards duplicados.
 */
export function rutaDashboardPorRol(
  value: string | null | undefined
): string | null {
  const rol = normalizarRol(value);
  if (!rol) return null;

  switch (rol) {
    case 'admin':
    case 'superadmin':
      return '/dashboard/admin';

    case 'profesional':
      return '/dashboard/profesional';

    case 'estudiante':
      return '/dashboard/estudiante';
  }
}
