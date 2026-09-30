import { ChangeDetectorRef } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { By } from '@angular/platform-browser';
import { Router, provideRouter } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from '../auth.service';
import { Permission } from '../shared/auth/permission.model';
import { ToastService } from '../shared/toast/toast.service';
import { DashboardAdminComponent } from './dashboard-admin';
import { AdminInicioComponent } from './inicio/admin-inicio';
import { SuperadminInicioComponent } from './superadmin-inicio/superadmin-inicio';

/**
 * Selector del Inicio en el shell (ADMIN vs SUPERADMIN).
 *
 * Reglas que este spec demuestra:
 *  1. ADMIN sigue montando el Inicio ADMIN existente (AdminInicioComponent).
 *  2. SUPERADMIN monta el nuevo Inicio institucional.
 *  3. Mientras el contexto administrativo se carga no se monta ninguno.
 *  4. Resuelto el contexto, la selección es determinista: depende solo de
 *     los permisos efectivos (roles.gestionar + auditoria.ver), nunca del
 *     rol declarado ni del orden/temporización de los ciclos de render.
 *
 * No toca el spec existente del shell.
 */

const PERMISOS_SUPERADMIN = [
  'roles.gestionar', 'auditoria.ver', 'reportes.ver', 'usuarios.ver', 'agenda.gestionar'
];
/** Permisos efectivos de un SUPERADMIN (incluye agenda.ver para abrir Horario). */
const PERMISOS_SUPERADMIN_COMPLETOS = [...PERMISOS_SUPERADMIN, 'agenda.ver'];
const PERMISOS_ADMIN = ['reportes.ver', 'usuarios.ver', 'agenda.ver', 'agenda.gestionar'];

// ══════════════════════════════════════════════════════════════════
// A. Unidad — el selector es una función pura (mismo mock que el resto
//    de la suite del shell: auth plano, componente construido directo).
// ══════════════════════════════════════════════════════════════════
function crearShell(
  permisos: Permission[],
  opciones: { cargando?: boolean; rol?: string; seccion?: string } = {}
) {
  const auth = {
    getNombre: vi.fn(() => 'Sofía'),
    getFotoUrl: vi.fn(() => null),
    getRol: vi.fn(() => opciones.rol ?? 'superadmin'),
    hasPermission: vi.fn((p: Permission) => permisos.includes(p)),
    getUsuarioId: vi.fn(() => null)
  } as unknown as AuthService;

  const shell = new DashboardAdminComponent(
    {} as Router,
    {} as HttpClient,
    {} as ChangeDetectorRef,
    { success: vi.fn(), error: vi.fn() } as unknown as ToastService,
    auth
  );
  shell.contextoAdministrativoCargando = opciones.cargando ?? false;
  shell.seccionActiva = (opciones.seccion ?? 'inicio') as any;
  return shell;
}

describe('Shell — vistaInicio (selector puro)', () => {
  it('arranca en "pendiente": el contexto todavía no se ha cargado', () => {
    // Estado inicial real del shell, sin tocar ninguna bandera.
    const auth = { hasPermission: vi.fn(() => false), getRol: vi.fn(() => null) } as unknown as AuthService;
    const shell = new DashboardAdminComponent(
      {} as Router, {} as HttpClient, {} as ChangeDetectorRef, {} as ToastService, auth
    );
    expect(shell.contextoAdministrativoCargando).toBe(true);
    expect(shell.vistaInicio).toBe('pendiente');
  });

  it('mientras carga es "pendiente" aunque haya permisos residuales', () => {
    const shell = crearShell(['roles.gestionar', 'auditoria.ver'], { cargando: true });
    expect(shell.vistaInicio).toBe('pendiente');
    expect(crearShell(PERMISOS_ADMIN as Permission[], { cargando: true }).vistaInicio).toBe('pendiente');
  });

  it('resuelto + roles.gestionar Y auditoria.ver → "institucional"', () => {
    expect(crearShell(['roles.gestionar', 'auditoria.ver']).vistaInicio).toBe('institucional');
  });

  it('resuelto sin esa combinación → "operativa" (ADMIN)', () => {
    expect(crearShell(PERMISOS_ADMIN as Permission[]).vistaInicio).toBe('operativa');
    expect(crearShell(['roles.gestionar']).vistaInicio).toBe('operativa');
    expect(crearShell(['auditoria.ver']).vistaInicio).toBe('operativa');
    expect(crearShell([]).vistaInicio).toBe('operativa');
  });

  it('decide solo por permisos efectivos, no por el rol declarado', () => {
    // Rol "superadmin" sin permisos reservados → NO institucional.
    expect(crearShell([], { rol: 'superadmin' }).vistaInicio).toBe('operativa');
    // Rol "admin" con la combinación → sigue la regla de permisos, no el rol.
    expect(crearShell(['roles.gestionar', 'auditoria.ver'], { rol: 'admin' }).vistaInicio).toBe('institucional');
  });

  it('es determinista: lecturas repetidas y en cualquier sección devuelven lo mismo', () => {
    const shell = crearShell(['roles.gestionar', 'auditoria.ver']);
    const lecturas = Array.from({ length: 50 }, () => shell.vistaInicio);
    expect(new Set(lecturas)).toEqual(new Set(['institucional']));

    shell.seccionActiva = 'horario' as any;
    expect(shell.vistaInicio).toBe('institucional');
  });
});

// ══════════════════════════════════════════════════════════════════
// B. Render real — qué componente queda montado.
//    Se monta el AdminInicioComponent REAL (se comprueba por identidad de
//    clase). Solo se reemplaza su plantilla interna: Chart.js necesita un
//    <canvas> que jsdom no implementa y ese detalle no es lo que se prueba.
// ══════════════════════════════════════════════════════════════════
describe('Shell — Inicio montado según el contexto efectivo', () => {
  let fixture: ComponentFixture<DashboardAdminComponent>;
  let http: HttpTestingController;

  async function montar(rol: 'admin' | 'superadmin') {
    sessionStorage.clear();
    localStorage.clear();
    sessionStorage.setItem('rol', rol);
    sessionStorage.setItem('usuario_id', '99');
    sessionStorage.setItem('nombre', 'Sofía Vera');

    await TestBed.configureTestingModule({
      imports: [DashboardAdminComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])]
    })
      .overrideComponent(AdminInicioComponent, {
        set: { template: '<div data-testid="admin-inicio-real"></div>', templateUrl: undefined, styleUrl: undefined } as any
      })
      .compileComponents();

    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(DashboardAdminComponent);
    fixture.detectChanges(); // ngOnInit → pide el contexto efectivo
  }

  function responderContexto(permisos: string[], rol: 'admin' | 'superadmin') {
    http.expectOne(r => r.url.includes('/usuarios/me/acceso-administrativo')).flush({
      rol,
      perfil: rol === 'admin' ? 'administrador_general' : null,
      permisos,
      alcance: { tipo: 'institucional', especialidades: [] }
    });
    fixture.detectChanges();
  }

  /**
   * El shell usa la detección de cambios por defecto de Angular 22 (OnPush) y
   * por eso llama a `cdr.detectChanges()` tras cada cambio de estado. Los
   * tests hacen lo mismo cuando cambian estado de forma programática.
   */
  function refrescar() {
    fixture.debugElement.injector.get(ChangeDetectorRef).detectChanges();
  }

  const montados = () => ({
    admin: fixture.debugElement.query(By.directive(AdminInicioComponent)),
    superadmin: fixture.debugElement.query(By.directive(SuperadminInicioComponent))
  });

  /** 'ninguno' | 'admin' | 'superadmin' (falla si hubiese ambos a la vez). */
  function vistaMontada(): 'ninguno' | 'admin' | 'superadmin' {
    const { admin, superadmin } = montados();
    expect(!!admin && !!superadmin, 'nunca deben coexistir ambos Inicios').toBe(false);
    return admin ? 'admin' : superadmin ? 'superadmin' : 'ninguno';
  }

  afterEach(() => {
    fixture?.destroy();
    TestBed.resetTestingModule();
    sessionStorage.clear();
    localStorage.clear();
  });

  // ── 1. ADMIN ────────────────────────────────────────────────────
  it('1) ADMIN sigue montando el Inicio ADMIN existente (AdminInicioComponent real)', async () => {
    await montar('admin');
    responderContexto(PERMISOS_ADMIN, 'admin');

    const { admin, superadmin } = montados();
    expect(admin).toBeTruthy();
    expect(admin.componentInstance).toBeInstanceOf(AdminInicioComponent);
    expect(superadmin).toBeNull();

    // Saludo y subtítulo del Inicio ADMIN, sin cambios.
    const titulo = fixture.nativeElement.querySelector('.topbar-title')?.textContent ?? '';
    expect(titulo).toContain('Hola, Sofía Vera 👋');
    expect(titulo).not.toContain('👑');
    expect(fixture.nativeElement.querySelector('.topbar-sub')?.textContent)
      .toContain('Gestiona profesionales, horarios y reservas de bienestar estudiantil.');
  });

  it('1) ADMIN conserva el enlace de datos del shell hacia su Inicio (inputs sin cambios)', async () => {
    await montar('admin');
    responderContexto(PERMISOS_ADMIN, 'admin');

    const inicio = montados().admin.componentInstance as AdminInicioComponent;
    const shell = fixture.componentInstance;

    expect(inicio.puedeVerAgenda).toBe(true);
    expect(inicio.puedeGestionarAgenda).toBe(true);
    expect(inicio.estadisticas).toBe(shell.estadisticas);
    expect(inicio.resumenDia).toBe(shell.resumenDia);
    expect(inicio.proximasCitas).toBe(shell.proximasCitas);
  });

  it('1) ADMIN no dispara ninguna petición del Inicio institucional', async () => {
    await montar('admin');
    responderContexto(PERMISOS_ADMIN, 'admin');

    for (const ruta of ['/admin/inicio/resumen', '/admin/inicio/gestion', '/usuarios/administradores']) {
      http.expectNone(r => r.url.includes(ruta));
    }
  });

  // ── 2. SUPERADMIN ───────────────────────────────────────────────
  it('2) SUPERADMIN monta el nuevo Inicio institucional y NO el de ADMIN', async () => {
    await montar('superadmin');
    responderContexto(PERMISOS_SUPERADMIN, 'superadmin');

    const { admin, superadmin } = montados();
    expect(superadmin).toBeTruthy();
    expect(superadmin.componentInstance).toBeInstanceOf(SuperadminInicioComponent);
    expect(admin).toBeNull();

    const titulo = fixture.nativeElement.querySelector('.topbar-title')?.textContent ?? '';
    expect(titulo).toContain('Hola, Sofía Vera 👑');
    expect(fixture.nativeElement.querySelector('.topbar-sub')?.textContent)
      .toContain('Resumen general del sistema');
  });

  it('2) SUPERADMIN: el Inicio institucional solo se monta en la sección "inicio"', async () => {
    await montar('superadmin');
    responderContexto(PERMISOS_SUPERADMIN, 'superadmin');
    expect(vistaMontada()).toBe('superadmin');

    fixture.componentInstance.seccionActiva = 'horario' as any;
    refrescar();
    expect(vistaMontada()).toBe('ninguno');

    fixture.componentInstance.seccionActiva = 'inicio' as any;
    refrescar();
    expect(vistaMontada()).toBe('superadmin');
  });

  it('2) el sidebar no cambia: conserva su navegación para SUPERADMIN', async () => {
    await montar('superadmin');
    responderContexto(PERMISOS_SUPERADMIN, 'superadmin');

    const nav = Array.from(fixture.nativeElement.querySelectorAll('.sidebar .nav-item') as NodeListOf<HTMLElement>)
      .map(b => (b.textContent ?? '').replace(/\s+/g, ' ').trim());
    expect(nav[0]).toContain('Inicio');
    expect(nav.some(t => t.includes('Administradores'))).toBe(true);
  });

  // ── 3. Durante la carga ─────────────────────────────────────────
  it.each(['admin', 'superadmin'] as const)(
    '3) durante la carga del contexto NO se monta ningún Inicio (%s)',
    async rol => {
      await montar(rol);

      // Contexto pedido pero sin resolver.
      http.expectOne(r => r.url.includes('/usuarios/me/acceso-administrativo'));
      fixture.detectChanges();

      expect(fixture.componentInstance.vistaInicio).toBe('pendiente');
      expect(vistaMontada()).toBe('ninguno');

      // Y por tanto tampoco se emite ninguna petición de datos de un Inicio.
      for (const ruta of ['/admin/inicio/', '/usuarios/administradores', '/admin/auditoria', '/admin/estadisticas']) {
        http.expectNone(r => r.url.includes(ruta));
      }
    }
  );

  it('3) tampoco en una recarga posterior del contexto: se desmonta y no queda nada visible', async () => {
    await montar('superadmin');
    responderContexto(PERMISOS_SUPERADMIN, 'superadmin');
    expect(vistaMontada()).toBe('superadmin');

    // Mismo disparador real que usa la sección Administradores.
    fixture.componentInstance.onSesionAdministrativaActualizada();
    refrescar();
    expect(vistaMontada()).toBe('ninguno'); // sin datos privilegiados a la vista

    responderContexto(PERMISOS_SUPERADMIN, 'superadmin');
    expect(vistaMontada()).toBe('superadmin');
  });

  // ── 4. Selección determinista una vez cargado el contexto ───────
  it.each([
    { rol: 'admin', permisos: PERMISOS_ADMIN, esperada: 'admin' },
    { rol: 'superadmin', permisos: PERMISOS_SUPERADMIN, esperada: 'superadmin' }
  ] as const)(
    '4) resuelto el contexto la vista es siempre la misma y no parpadea ($rol)',
    async ({ rol, permisos, esperada }) => {
      await montar(rol);

      const secuencia: string[] = [vistaMontada()];
      responderContexto([...permisos], rol);
      secuencia.push(vistaMontada());

      const instancia = (montados()[esperada]).componentInstance;
      for (let i = 0; i < 10; i++) {
        refrescar();
        secuencia.push(vistaMontada());
      }

      // Una única transición: ninguno → vista correcta. Sin pasar por la otra.
      expect(secuencia[0]).toBe('ninguno');
      expect(new Set(secuencia.slice(1))).toEqual(new Set([esperada]));
      // Y sin desmontar/remontar en cada ciclo: es la misma instancia.
      expect(montados()[esperada].componentInstance).toBe(instancia);
    }
  );

  it('4) el mismo contexto produce la misma vista en montajes independientes', async () => {
    const resultados: string[] = [];
    for (let i = 0; i < 3; i++) {
      await montar('superadmin');
      responderContexto(PERMISOS_SUPERADMIN, 'superadmin');
      resultados.push(vistaMontada());
      fixture.destroy();
      TestBed.resetTestingModule();
    }
    expect(resultados).toEqual(['superadmin', 'superadmin', 'superadmin']);
  });

  it('4) si el contexto falla, jamás se monta el institucional (fail-closed) y queda el Inicio ADMIN de siempre', async () => {
    await montar('superadmin');
    http.expectOne(r => r.url.includes('/usuarios/me/acceso-administrativo'))
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(fixture.componentInstance.vistaInicio).toBe('operativa');
    expect(vistaMontada()).toBe('admin');
    expect(montados().superadmin).toBeNull();
  });

  it('4) rol "superadmin" sin permisos reservados en el contexto: no obtiene el institucional', async () => {
    await montar('superadmin');
    responderContexto(['reportes.ver'], 'superadmin');

    expect(vistaMontada()).toBe('admin');
  });

  it('4) al re-resolver con otros permisos la vista cambia solo por los permisos efectivos', async () => {
    await montar('superadmin');
    responderContexto(PERMISOS_SUPERADMIN, 'superadmin');
    expect(vistaMontada()).toBe('superadmin');

    // Se revalida el acceso y ahora el backend entrega un perfil ADMIN.
    fixture.componentInstance.onSesionAdministrativaActualizada();
    refrescar();
    expect(vistaMontada()).toBe('ninguno');

    responderContexto(PERMISOS_ADMIN, 'admin');
    expect(vistaMontada()).toBe('admin');
  });

  // ── Acciones de navegación desde el Inicio institucional ────────
  const accion = (clave: string) =>
    fixture.nativeElement.querySelector(`app-superadmin-inicio [data-accion="${clave}"]`) as HTMLButtonElement | null;

  it.each([
    ['citasMes', 'historial'],
    ['especialidad', 'reportes'],
    ['solicitudes', 'horario'],
    ['administradores', 'administradores']
  ])('acción "%s" → abre la sección real "%s" (igual que el sidebar)', async (clave, seccion) => {
    await montar('superadmin');
    responderContexto(PERMISOS_SUPERADMIN_COMPLETOS, 'superadmin');
    expect(fixture.componentInstance.seccionActiva).toBe('inicio');

    accion(clave)!.click();
    refrescar();

    expect(fixture.componentInstance.seccionActiva).toBe(seccion);
    // El Inicio se desmonta al cambiar de sección; nada del Inicio ADMIN aparece.
    expect(vistaMontada()).toBe('ninguno');
  });

  it.each(['auditoria', 'actividad'])(
    'acción "%s" → abre Configuración en la pestaña Seguridad (donde vive la auditoría)',
    async clave => {
      await montar('superadmin');
      responderContexto(PERMISOS_SUPERADMIN_COMPLETOS, 'superadmin');

      accion(clave)!.click();
      refrescar();

      expect(fixture.componentInstance.seccionActiva).toBe('configuracion');
      expect(fixture.componentInstance.configTabActiva).toBe('seguridad');
    }
  );

  it('sin permiso para un destino, su acción no se muestra (fail-closed)', async () => {
    await montar('superadmin');
    // Conserva los permisos institucionales pero sin reportes.ver ni agenda.ver.
    responderContexto(['roles.gestionar', 'auditoria.ver'], 'superadmin');

    expect(vistaMontada()).toBe('superadmin');
    expect(accion('citasMes')).toBeNull();      // historial: reportes.ver
    expect(accion('especialidad')).toBeNull();  // reportes:  reportes.ver
    expect(accion('solicitudes')).toBeNull();   // horario:   agenda.ver
    expect(accion('administradores')).not.toBeNull();
    expect(accion('auditoria')).not.toBeNull();
  });

  it('el manejador rechaza un destino no permitido: avisa y no cambia de sección', async () => {
    await montar('superadmin');
    responderContexto(['roles.gestionar', 'auditoria.ver'], 'superadmin');
    const toast = vi.spyOn(TestBed.inject(ToastService), 'error');

    fixture.componentInstance.onNavegarDesdeInicioInstitucional('reportes');

    expect(toast).toHaveBeenCalledWith('No tienes permisos para acceder a esta sección.');
    expect(fixture.componentInstance.seccionActiva).toBe('inicio');
  });

  it('ADMIN: su Inicio no recibe acciones nuevas y no se le monta el institucional', async () => {
    await montar('admin');
    responderContexto(PERMISOS_ADMIN, 'admin');

    expect(vistaMontada()).toBe('admin');
    expect(fixture.nativeElement.querySelector('[data-accion]')).toBeNull();
  });
});
