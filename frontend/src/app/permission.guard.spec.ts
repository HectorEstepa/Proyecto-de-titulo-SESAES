import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, ActivatedRouteSnapshot, RouterStateSnapshot } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';

import { permissionGuard } from './permission.guard';
import { Permission } from './shared/auth/permission.model';

/**
 * permissionGuard es un Functional Guard (CanActivateFn), así que se
 * ejecuta dentro de un injection context real vía
 * TestBed.runInInjectionContext, tal como Angular lo invoca en
 * producción.
 */

/**
 * Construye un JWT sintético (header.payload.signature) SOLO para que
 * AuthService.tokenExpirado pueda leer 'exp' del payload. AuthService no
 * valida la firma (eso es responsabilidad exclusiva del backend), así
 * que la firma acá es un valor cualquiera sin criptografía real.
 */
function jwtSintetico(expSecondsFromNow: number | null): string {
  const header = { alg: 'none', typ: 'JWT' };
  const payload: Record<string, unknown> = {};
  if (expSecondsFromNow !== null) {
    payload['exp'] = Math.floor(Date.now() / 1000) + expSecondsFromNow;
  }
  const base64url = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${base64url(header)}.${base64url(payload)}.firma-no-verificada`;
}

/**
 * Monta el estado mínimo real que AuthService considera sesión válida,
 * usando las claves reales confirmadas en AuthService.guardarSesion:
 * 'access_token' y 'rol'.
 */
function montarSesion(rol: string | null, token: string | null): void {
  sessionStorage.clear();
  if (rol !== null) sessionStorage.setItem('rol', rol);
  if (token !== null) sessionStorage.setItem('access_token', token);
}

function rutaConPermission(permission: unknown): ActivatedRouteSnapshot {
  return { data: { permission } } as unknown as ActivatedRouteSnapshot;
}

const rutaVacia = {} as ActivatedRouteSnapshot;
const estadoDummy = {} as RouterStateSnapshot;

describe('permissionGuard', () => {
  let router: Router;
  let navigateSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient()],
    });

    router = TestBed.inject(Router);
    navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  function ejecutarGuard(route: ActivatedRouteSnapshot) {
    return TestBed.runInInjectionContext(() => permissionGuard(route, estadoDummy));
  }

  it('1. ADMIN sin contexto efectivo + agenda.gestionar -> false -> /dashboard/admin', () => {
    montarSesion(
      'admin',
      jwtSintetico(3600)
    );

    const resultado = ejecutarGuard(
      rutaConPermission(
        'agenda.gestionar' satisfies Permission
      )
    );

    expect(resultado).toBe(false);

    expect(
      navigateSpy
    ).toHaveBeenCalledWith([
      '/dashboard/admin'
    ]);
  });

  it('2. ADMIN + configuracion.gestionar -> false -> /dashboard/admin', () => {
    montarSesion('admin', jwtSintetico(3600));
    const resultado = ejecutarGuard(rutaConPermission('configuracion.gestionar' satisfies Permission));
    expect(resultado).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard/admin']);
  });

  it('3. SUPERADMIN sin contexto efectivo + configuracion.gestionar -> false -> /dashboard/admin', () => {
    montarSesion(
      'superadmin',
      jwtSintetico(3600)
    );

    const resultado = ejecutarGuard(
      rutaConPermission(
        'configuracion.gestionar' satisfies Permission
      )
    );

    expect(resultado).toBe(false);

    expect(
      navigateSpy
    ).toHaveBeenCalledWith([
      '/dashboard/admin'
    ]);
  });

  it('4. SUPERADMIN + ficha.ver_asignada -> false -> /dashboard/admin', () => {
    montarSesion('superadmin', jwtSintetico(3600));
    const resultado = ejecutarGuard(rutaConPermission('ficha.ver_asignada' satisfies Permission));
    expect(resultado).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard/admin']);
  });

  it('5. PROFESIONAL + agenda.gestionar -> false -> /dashboard/profesional', () => {
    montarSesion('profesional', jwtSintetico(3600));
    const resultado = ejecutarGuard(rutaConPermission('agenda.gestionar' satisfies Permission));
    expect(resultado).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard/profesional']);
  });

  it('6. ESTUDIANTE + reportes.ver -> false -> /dashboard/estudiante', () => {
    montarSesion('estudiante', jwtSintetico(3600));
    const resultado = ejecutarGuard(rutaConPermission('reportes.ver' satisfies Permission));
    expect(resultado).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard/estudiante']);
  });

  it('7. rol desconocido -> false -> /login', () => {
    montarSesion('gerente', jwtSintetico(3600));
    const resultado = ejecutarGuard(rutaConPermission('reportes.ver' satisfies Permission));
    expect(resultado).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('8. permission ausente -> false', () => {
    montarSesion('admin', jwtSintetico(3600));
    const resultado = ejecutarGuard(rutaVacia);
    expect(resultado).toBe(false);
  });

  it('9. permission vacío -> false', () => {
    montarSesion('admin', jwtSintetico(3600));
    const resultado = ejecutarGuard(rutaConPermission(''));
    expect(resultado).toBe(false);
  });

  it('10. permission inválido/manipulado -> false', () => {
    montarSesion('admin', jwtSintetico(3600));
    const resultado = ejecutarGuard(rutaConPermission('permiso.que.no.existe'));
    expect(resultado).toBe(false);
  });

  it('11. sin sesión/token -> false -> /login', () => {
    montarSesion(null, null);
    const resultado = ejecutarGuard(rutaConPermission('reportes.ver' satisfies Permission));
    expect(resultado).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('12. rol persistido pero token ausente -> false -> /login', () => {
    montarSesion('admin', null);
    const resultado = ejecutarGuard(rutaConPermission('reportes.ver' satisfies Permission));
    expect(resultado).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('13. token expirado -> false -> /login', () => {
    montarSesion('admin', jwtSintetico(-3600));
    const resultado = ejecutarGuard(rutaConPermission('reportes.ver' satisfies Permission));
    expect(resultado).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('14. PROFESIONAL + agenda.ver_profesional -> true', () => {
    montarSesion(
      'profesional',
      jwtSintetico(3600)
    );

    const resultado = ejecutarGuard(
      rutaConPermission(
        'agenda.ver_profesional' satisfies Permission
      )
    );

    expect(resultado).toBe(true);

    expect(
      navigateSpy
    ).not.toHaveBeenCalled();
  });

  it('15. ESTUDIANTE + perfil.ver_propio -> true', () => {
    montarSesion(
      'estudiante',
      jwtSintetico(3600)
    );

    const resultado = ejecutarGuard(
      rutaConPermission(
        'perfil.ver_propio' satisfies Permission
      )
    );

    expect(resultado).toBe(true);

    expect(
      navigateSpy
    ).not.toHaveBeenCalled();
  });

});
