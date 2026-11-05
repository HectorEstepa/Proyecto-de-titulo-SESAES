import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';

/**
 * Protege las rutas de dashboard: si no hay sesión activa (o se navegó
 * "hacia adelante" después de haber cerrado sesión), redirige al login
 * en vez de mostrar el contenido protegido.
 */
export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isLoggedIn()) {
    return true;
  }

  router.navigate(['/login']);
  return false;
};
