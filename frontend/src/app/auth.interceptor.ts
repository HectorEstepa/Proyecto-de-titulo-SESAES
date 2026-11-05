import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { environment } from './config';
import { AuthService } from './auth.service';

/**
 * Interceptor global:
 *  1. Adjunta 'Authorization: Bearer <token>' a toda petición dirigida
 *     a nuestra propia API (nunca a dominios externos).
 *  2. Si el backend responde 401 (token vencido/inválido), limpia la
 *     sesión y redirige al login en vez de dejar que cada componente
 *     tenga que manejarlo por su cuenta.
 *
 * Sin este interceptor, ningún endpoint protegido con JWT en el backend
 * funcionaría desde el frontend — es el complemento obligatorio de los
 * cambios de auth_dependencies.py.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const esNuestraApi = req.url.startsWith(environment.apiUrl);
  const token = auth.getToken();

  const peticion = (esNuestraApi && token)
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(peticion).pipe(
    catchError((error: HttpErrorResponse) => {
      // No cerramos sesión si el 401 vino del propio /login (contraseña
      // incorrecta, por ejemplo) — ahí no hay sesión que limpiar todavía.
      const esLogin = req.url.includes('/login');
      if (error.status === 401 && esNuestraApi && !esLogin) {
        auth.logout();
        router.navigate(['/login']);
      }
      return throwError(() => error);
    })
  );
};
