import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  Router,
  RouterStateSnapshot,
  provideRouter
} from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

import { rolGuard } from './rol.guard';
import { routes } from './app.routes';

const estadoDummy = {} as RouterStateSnapshot;

function rutaConRoles(roles: unknown): ActivatedRouteSnapshot {
  return {
    data: { roles }
  } as unknown as ActivatedRouteSnapshot;
}

function rutaConRolLegacy(rol: unknown): ActivatedRouteSnapshot {
  return {
    data: { rol }
  } as unknown as ActivatedRouteSnapshot;
}

describe('rolGuard', () => {
  let router: Router;
  let navigateSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient()]
    });

    router = TestBed.inject(Router);
    navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  function sesion(rol: string | null): void {
    sessionStorage.clear();
    if (rol !== null) {
      sessionStorage.setItem('rol', rol);
    }
  }

  function ejecutar(route: ActivatedRouteSnapshot) {
    return TestBed.runInInjectionContext(
      () => rolGuard(route, estadoDummy)
    );
  }

  it('ADMIN puede entrar al dashboard administrativo', () => {
    sesion('admin');

    expect(ejecutar(rutaConRoles(['admin', 'superadmin']))).toBe(true);
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('SUPERADMIN puede entrar al mismo dashboard administrativo', () => {
    sesion('superadmin');

    expect(ejecutar(rutaConRoles(['admin', 'superadmin']))).toBe(true);
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('PROFESIONAL no entra al dashboard admin y vuelve al suyo', () => {
    sesion('profesional');

    expect(ejecutar(rutaConRoles(['admin', 'superadmin']))).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard/profesional']);
  });

  it('ESTUDIANTE no entra al dashboard admin y vuelve al suyo', () => {
    sesion('estudiante');

    expect(ejecutar(rutaConRoles(['admin', 'superadmin']))).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard/estudiante']);
  });

  it('SUPERADMIN rechazado en otra ruta vuelve a /dashboard/admin', () => {
    sesion('superadmin');

    expect(ejecutar(rutaConRoles(['estudiante']))).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard/admin']);
  });

  it('sin rol de sesión -> false y /login', () => {
    sesion(null);

    expect(ejecutar(rutaConRoles(['admin']))).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('rol desconocido -> false y /login', () => {
    sesion('gerente');

    expect(ejecutar(rutaConRoles(['admin']))).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('metadata de roles ausente o inválida falla cerrado', () => {
    sesion('admin');

    const ruta = { data: {} } as unknown as ActivatedRouteSnapshot;

    expect(ejecutar(ruta)).toBe(false);
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('mantiene compatibilidad con data.rol legado', () => {
    sesion('profesional');

    expect(ejecutar(rutaConRolLegacy('profesional'))).toBe(true);
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('la ruta productiva admin declara ADMIN + SUPERADMIN y no duplica dashboard', () => {
    const admin = routes.find(r => r.path === 'dashboard/admin');

    expect(admin?.data?.['roles']).toEqual(['admin', 'superadmin']);
    expect(routes.some(r => r.path === 'dashboard/superadmin')).toBe(false);
  });
});
