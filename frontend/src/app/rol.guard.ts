import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';
import {
  normalizarRol,
  Role,
  rutaDashboardPorRol
} from './shared/auth/role.model';

/**
 * Protege dashboards según el rol de la sesión.
 *
 * Se usa junto a authGuard. La ruta puede declarar:
 *
 *   data: { roles: ['admin', 'superadmin'] }
 *
 * También conserva compatibilidad con el antiguo:
 *
 *   data: { rol: 'admin' }
 *
 * La autorización sensible sigue perteneciendo al backend.
 */
function obtenerRolesPermitidos(route: any): Role[] | null {
  const raw = route.data?.['roles'] ?? route.data?.['rol'];

  if (raw === undefined || raw === null) return null;

  const candidatos = Array.isArray(raw) ? raw : [raw];

  if (candidatos.length === 0) return null;

  const resultado: Role[] = [];

  for (const candidato of candidatos) {
    if (typeof candidato !== 'string') return null;

    const rol = normalizarRol(candidato);
    if (!rol) return null;

    resultado.push(rol);
  }

  return resultado;
}

export const rolGuard: CanActivateFn = (route) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const rolActual = normalizarRol(auth.getRol());

  if (!rolActual) {
    router.navigate(['/login']);
    return false;
  }

  const rolesPermitidos = obtenerRolesPermitidos(route);

  // Metadata ausente o inválida: fail-closed.
  if (!rolesPermitidos) {
    return false;
  }

  if (rolesPermitidos.includes(rolActual)) {
    return true;
  }

  const destino = rutaDashboardPorRol(rolActual);

  router.navigate([destino ?? '/login']);
  return false;
};
