import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';
import {
  normalizarRol,
  rutaDashboardPorRol
} from './shared/auth/role.model';
import { isPermission } from './shared/auth/permission.model';

/**
 * permissionGuard controla únicamente UX/navegación.
 *
 * El backend sigue siendo la autoridad real y vuelve a validar cada
 * permiso server-side mediante require_permission.
 *
 * Fail-closed:
 * - sesión inválida -> /login
 * - rol desconocido -> /login
 * - permission ausente o inválido -> false
 * - permission no concedido -> dashboard principal del rol
 *
 * ADMIN y SUPERADMIN comparten /dashboard/admin. Sus capacidades
 * internas son diferentes y se resuelven mediante RBAC.
 */
export const permissionGuard: CanActivateFn = (route) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isLoggedIn()) {
    router.navigate(['/login']);
    return false;
  }

  const rol = normalizarRol(auth.getRol());

  if (!rol) {
    router.navigate(['/login']);
    return false;
  }

  const permissionRequerido = route.data?.['permission'];

  if (!isPermission(permissionRequerido)) {
    return false;
  }

  if (auth.hasPermission(permissionRequerido)) {
    return true;
  }

  const destino = rutaDashboardPorRol(rol);

  router.navigate([destino ?? '/login']);
  return false;
};
