import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { AdminAdministradoresComponent } from './admin-administradores';
import { AuthService } from '../../auth.service';
import { ToastService } from '../../shared/toast/toast.service';

const URL_LISTADO = '/usuarios/administradores';

type AdministradorFixture = {
  id: number;
  nombre: string | null;
  correo: string;
  telefono: string | null;
  foto_url: string | null;
  rol: 'admin' | 'superadmin';
  activo: boolean;
};

function admin(
  overrides: Partial<AdministradorFixture> = {}
): AdministradorFixture {
  return {
    id: 1,
    nombre: 'Admin Uno',
    correo: 'admin1@sesaes.cl',
    telefono: null,
    foto_url: null,
    rol: 'admin',
    activo: true,
    ...overrides
  };
}

function cargarContextoSuperadmin(
  httpMock: HttpTestingController
): void {
  const auth = TestBed.inject(AuthService);

  auth.cargarAccesoAdministrativo().subscribe();

  httpMock.expectOne(
    req =>
      req.url.includes(
        '/usuarios/me/acceso-administrativo'
      ) &&
      req.method === 'GET'
  ).flush({
    rol: 'superadmin',
    perfil: null,
    permisos: [
      'roles.gestionar'
    ],
    alcance: {
      tipo: 'institucional',
      especialidades: []
    }
  });
}


describe('AdminAdministradoresComponent (SA-4)', () => {
  let component: AdminAdministradoresComponent;
  let fixture: ComponentFixture<AdminAdministradoresComponent>;
  let httpMock: HttpTestingController;
  let toast: { success: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    sessionStorage.clear();
    localStorage.clear();

    // Este describe representa la pantalla Administradores ya autorizada.
    // La sesion activa debe tener roles.gestionar; usamos un id distinto
    // de los fixtures para que las mutaciones existentes sean sobre OTRA cuenta.
    sessionStorage.setItem('rol', 'superadmin');
    sessionStorage.setItem('usuario_id', '99');

    toast = { success: vi.fn(), error: vi.fn() };

    await TestBed.configureTestingModule({
      imports: [AdminAdministradoresComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ToastService, useValue: toast }
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminAdministradoresComponent);
    component = fixture.componentInstance;
    fixture.detectChanges(); // dispara ngOnInit -> cargarAdministradores()
    httpMock = TestBed.inject(HttpTestingController);

    // SA-10: este componente hijo solo se renderiza despu?s de que
    // el shell administrativo obtuvo el contexto efectivo.
    cargarContextoSuperadmin(httpMock);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
    localStorage.clear();
  });

  function flushListadoInicial(data: any[] = []): void {
    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush(data);
  }

  // ══════════════════════════════════════
  // LISTADO
  // ══════════════════════════════════════

  it('should create', () => {
    flushListadoInicial([]);
    expect(component).toBeTruthy();
  });

  it('carga y expone el listado de administradores', () => {
    flushListadoInicial([admin(), admin({ id: 2, correo: 'admin2@sesaes.cl' })]);
    expect(component.administradores.length).toBe(2);
    expect(component.cargando).toBe(false);
  });

  it('403 al listar -> mensaje de falta de permisos, sin lanzar excepción', () => {
    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET')
      .flush({ detail: 'Forbidden' }, { status: 403, statusText: 'Forbidden' });

    expect(component.errorListado).toBe('No tienes permisos para ver esta sección.');
    expect(component.cargando).toBe(false);
  });

  it('error genérico al listar -> mensaje genérico, no 403', () => {
    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });

    expect(component.errorListado).toBe('No se pudo cargar el listado de administradores.');
  });

  // ══════════════════════════════════════
  // FILTROS
  // ══════════════════════════════════════

  it('filtra por texto (correo)', () => {
    flushListadoInicial([admin({ id: 1, correo: 'ana@sesaes.cl' }), admin({ id: 2, correo: 'beto@sesaes.cl' })]);
    component.filtroTexto = 'ana';
    expect(component.administradoresFiltrados.length).toBe(1);
    expect(component.administradoresFiltrados[0].correo).toBe('ana@sesaes.cl');
  });

  it('filtra por texto (nombre)', () => {
    flushListadoInicial([admin({ id: 1, nombre: 'Ana Soto' }), admin({ id: 2, nombre: 'Beto Ríos' })]);
    component.filtroTexto = 'beto';
    expect(component.administradoresFiltrados.length).toBe(1);
    expect(component.administradoresFiltrados[0].nombre).toBe('Beto Ríos');
  });

  it('filtra por rol', () => {
    flushListadoInicial([admin({ id: 1, rol: 'admin' }), admin({ id: 2, rol: 'superadmin' })]);
    component.filtroRol = 'superadmin';
    expect(component.administradoresFiltrados.length).toBe(1);
    expect(component.administradoresFiltrados[0].rol).toBe('superadmin');
  });

  it('filtra por estado activo', () => {
    flushListadoInicial([admin({ id: 1, activo: true }), admin({ id: 2, activo: false })]);
    component.filtroEstado = 'activo';
    expect(component.administradoresFiltrados.length).toBe(1);
    expect(component.administradoresFiltrados[0].id).toBe(1);
  });

  it('filtra por estado inactivo', () => {
    flushListadoInicial([admin({ id: 1, activo: true }), admin({ id: 2, activo: false })]);
    component.filtroEstado = 'inactivo';
    expect(component.administradoresFiltrados.length).toBe(1);
    expect(component.administradoresFiltrados[0].id).toBe(2);
  });

  it('limpiarFiltros resetea los tres filtros sin disparar HTTP adicional', () => {
    flushListadoInicial([]);
    component.filtroTexto = 'x'; component.filtroRol = 'admin'; component.filtroEstado = 'activo';
    component.limpiarFiltros();
    expect(component.filtroTexto).toBe('');
    expect(component.filtroRol).toBe('');
    expect(component.filtroEstado).toBe('');
    httpMock.expectNone(req => req.url.includes(URL_LISTADO) && req.method === 'GET');
  });

  // ══════════════════════════════════════
  // RESUMEN
  // ══════════════════════════════════════

  it('calcula el resumen (total, activos, superadmins, inactivos) sobre el total real, no lo filtrado', () => {
    flushListadoInicial([
      admin({ id: 1, rol: 'admin', activo: true }),
      admin({ id: 2, rol: 'superadmin', activo: true }),
      admin({ id: 3, rol: 'admin', activo: false }),
    ]);
    component.filtroRol = 'superadmin'; // no debe afectar el resumen

    expect(component.totalAdministradores).toBe(3);
    expect(component.totalActivos).toBe(2);
    expect(component.totalSuperadmins).toBe(1);
    expect(component.totalInactivos).toBe(1);
  });

  // ══════════════════════════════════════
  // MODAL DE CREACIÓN
  // ══════════════════════════════════════

  it('abrirModalCrear resetea el formulario y abre el modal', () => {
    flushListadoInicial([]);
    component.nuevoAdmin.correo = 'sobrante@utem.cl';
    component.abrirModalCrear();
    expect(component.modalCrearAbierto).toBe(true);
    expect(component.nuevoAdmin.correo).toBe('');
    expect(component.nuevoAdmin.password).toBe('');
  });

  it('cerrarModalCrear limpia la contraseña aunque se haya escrito algo', () => {
    flushListadoInicial([]);
    component.abrirModalCrear();
    component.nuevoAdmin.password = 'algoSecreto123!';
    component.cerrarModalCrear();
    expect(component.modalCrearAbierto).toBe(false);
    expect(component.nuevoAdmin.password).toBe('');
  });

  it('creacionValida es false si falta correo, password o rol', () => {
    flushListadoInicial([]);
    component.nuevoAdmin = { correo: '', password: '', nombre: '', telefono: '', rol: 'admin' };
    expect(component.creacionValida).toBe(false);

    component.nuevoAdmin.correo = 'x@utem.cl';
    expect(component.creacionValida).toBe(false);

    component.nuevoAdmin.password = 'Abcdef1!';
    expect(component.creacionValida).toBe(true);
  });

  it('creacionValida acepta @utem.cl con mayusculas y espacios externos', () => {
    flushListadoInicial([]);

    component.nuevoAdmin = {
      correo: '  Persona@UTEM.CL  ',
      password: 'Abcdef1!',
      nombre: '',
      telefono: '',
      rol: 'admin'
    };

    expect(component.correoCreacionValido).toBe(true);
    expect(component.creacionValida).toBe(true);
  });

  it('creacionValida rechaza dominios no institucionales y dominios parecidos', () => {
    flushListadoInicial([]);

    component.nuevoAdmin.password = 'Abcdef1!';
    component.nuevoAdmin.rol = 'admin';

    for (const correo of [
      'persona@gmail.com',
      'persona@test.local',
      'persona@utem.cl.evil.com',
      'persona@sub.utem.cl',
      'persona@@utem.cl'
    ]) {
      component.nuevoAdmin.correo = correo;

      expect(component.correoCreacionValido).toBe(false);
      expect(component.creacionValida).toBe(false);
    }
  });

  it('crearAdministrador no dispara POST si el correo no es @utem.cl', () => {
    flushListadoInicial([]);

    component.nuevoAdmin = {
      correo: 'persona@gmail.com',
      password: 'Abcdef1!',
      nombre: '',
      telefono: '',
      rol: 'admin'
    };

    component.crearAdministrador();

    httpMock.expectNone(
      req => req.url.includes(URL_LISTADO) && req.method === 'POST'
    );
  });

  it('crearAdministrador normaliza correo institucional antes del POST', () => {
    flushListadoInicial([]);

    component.nuevoAdmin = {
      correo: '  Persona@UTEM.CL  ',
      password: 'Abcdef1!',
      nombre: '',
      telefono: '',
      rol: 'admin'
    };

    component.crearAdministrador();

    const reqPost = httpMock.expectOne(
      req => req.url.includes(URL_LISTADO) && req.method === 'POST'
    );

    expect(reqPost.request.body.correo).toBe('persona@utem.cl');

    reqPost.flush(admin({
      id: 99,
      correo: 'persona@utem.cl'
    }));

    const reqReload = httpMock.expectOne(
      req => req.url.includes(URL_LISTADO) && req.method === 'GET'
    );

    reqReload.flush([admin({
      id: 99,
      correo: 'persona@utem.cl'
    })]);

    expect(component.modalCrearAbierto).toBe(false);
  });

  it('crearAdministrador no dispara POST si el formulario es inválido', () => {
    flushListadoInicial([]);
    component.nuevoAdmin.correo = '';
    component.crearAdministrador();
    httpMock.expectNone(req => req.url.includes(URL_LISTADO) && req.method === 'POST');
  });

  it('crearAdministrador exitoso: recarga la lista, limpia password, cierra modal y muestra éxito', () => {
    flushListadoInicial([]);
    component.abrirModalCrear();
    component.nuevoAdmin = { correo: 'nuevo@utem.cl', password: 'Abcdef1!', nombre: 'Nuevo', telefono: '', rol: 'admin' };

    component.crearAdministrador();

    const reqPost = httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'POST');
    expect(reqPost.request.body).toEqual({ correo: 'nuevo@utem.cl', password: 'Abcdef1!', rol: 'admin', nombre: 'Nuevo' });
    reqPost.flush(admin({ id: 9, correo: 'nuevo@utem.cl' }));

    // Recarga completa tras éxito (no merge local optimista).
    const reqReload = httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET');
    reqReload.flush([admin({ id: 9, correo: 'nuevo@utem.cl' })]);

    expect(component.modalCrearAbierto).toBe(false);
    expect(component.nuevoAdmin.password).toBe('');
    expect(toast.success).toHaveBeenCalled();
    expect(component.administradores.length).toBe(1);
  });

  it('crearAdministrador 409 (correo duplicado): muestra el detail real del backend y no altera el listado', () => {
    flushListadoInicial([admin({ id: 1 })]);
    component.abrirModalCrear();
    component.nuevoAdmin = { correo: 'admin1@utem.cl', password: 'Abcdef1!', nombre: '', telefono: '', rol: 'admin' };

    component.crearAdministrador();

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'POST')
      .flush({ detail: 'Ya existe un usuario con ese correo.' }, { status: 409, statusText: 'Conflict' });

    expect(component.mensajeErrorModal).toBe('Ya existe un usuario con ese correo.');
    expect(component.modalCrearAbierto).toBe(true); // sigue abierto, no se asume éxito
    expect(component.nuevoAdmin.password).toBe(''); // password se limpia también ante error
    expect(component.administradores.length).toBe(1); // sin cambios locales
    httpMock.expectNone(req => req.url.includes(URL_LISTADO) && req.method === 'GET');
  });

  it('crearAdministrador 422 (política de password): usa el detail del backend', () => {
    flushListadoInicial([]);
    component.abrirModalCrear();
    component.nuevoAdmin = { correo: 'x@utem.cl', password: 'debil', nombre: '', telefono: '', rol: 'admin' };

    component.crearAdministrador();

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'POST')
      .flush({ detail: 'La contraseña no cumple la política de seguridad requerida (mínimo 8 caracteres...)' }, { status: 422, statusText: 'Unprocessable Entity' });

    expect(component.mensajeErrorModal).toContain('política de seguridad');
  });

  it('crearAdministrador 403: usa el fallback de permisos si el backend no trae detail', () => {
    flushListadoInicial([]);
    component.abrirModalCrear();
    component.nuevoAdmin = { correo: 'x@utem.cl', password: 'Abcdef1!', nombre: '', telefono: '', rol: 'admin' };

    component.crearAdministrador();

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'POST')
      .flush({}, { status: 403, statusText: 'Forbidden' });

    expect(component.mensajeErrorModal).toBe('No tienes permisos para crear cuentas administrativas.');
  });

  it('crearAdministrador con error sin detail y sin fallback conocido: mensaje genérico', () => {
    flushListadoInicial([]);
    component.abrirModalCrear();
    component.nuevoAdmin = { correo: 'x@utem.cl', password: 'Abcdef1!', nombre: '', telefono: '', rol: 'admin' };

    component.crearAdministrador();

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'POST')
      .flush({}, { status: 500, statusText: 'Server Error' });

    expect(component.mensajeErrorModal).toBe('Ocurrió un error inesperado.');
  });

  it('la contraseña nunca se escribe en localStorage ni sessionStorage durante la creación', () => {
    flushListadoInicial([]);
    const spyLocal = vi.spyOn(Storage.prototype, 'setItem');

    component.abrirModalCrear();
    component.nuevoAdmin = { correo: 'x@utem.cl', password: 'Abcdef1!', nombre: '', telefono: '', rol: 'admin' };
    component.crearAdministrador();

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'POST').flush(admin());
    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([]);

    const huboEscrituraConPassword = spyLocal.mock.calls.some(call => String(call[1]).includes('Abcdef1!'));
    expect(huboEscrituraConPassword).toBe(false);
    spyLocal.mockRestore();
  });

  // ══════════════════════════════════════
  // CAMBIAR ESTADO
  // ══════════════════════════════════════

  it('cambiarEstado exitoso: recarga la lista y muestra éxito', () => {
    flushListadoInicial([admin({ id: 1, activo: true })]);
    component.cambiarEstado(component.administradores[0], false);

    const reqPatch = httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/estado') && req.method === 'PATCH');
    expect(reqPatch.request.body).toEqual({ activo: false });
    reqPatch.flush(admin({ id: 1, activo: false }));

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([admin({ id: 1, activo: false })]);

    expect(toast.success).toHaveBeenCalled();
    expect(component.administradores[0].activo).toBe(false);
  });

  it('cambiarEstado 409 (último SUPERADMIN activo): muestra el detail real y NO altera el estado local', () => {
    flushListadoInicial([admin({ id: 1, rol: 'superadmin', activo: true })]);
    const original = component.administradores[0];

    component.cambiarEstado(original, false);

    httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/estado') && req.method === 'PATCH')
      .flush({ detail: 'No es posible desactivar al último SUPERADMIN activo.' }, { status: 409, statusText: 'Conflict' });

    expect(toast.error).toHaveBeenCalledWith('No es posible desactivar al último SUPERADMIN activo.');
    expect(component.administradores[0].activo).toBe(true); // sin cambio optimista
    httpMock.expectNone(req => req.url.includes(URL_LISTADO) && req.method === 'GET');
  });

  it('cambiarEstado 403: muestra mensaje de falta de permisos', () => {
    flushListadoInicial([admin({ id: 1 })]);
    component.cambiarEstado(component.administradores[0], false);

    httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/estado') && req.method === 'PATCH')
      .flush({}, { status: 403, statusText: 'Forbidden' });

    expect(toast.error).toHaveBeenCalledWith('No tienes permisos para cambiar el estado de esta cuenta.');
  });

  // ══════════════════════════════════════
  // CAMBIAR ROL
  // ══════════════════════════════════════

  it('cambiarRol exitoso: recarga la lista y muestra éxito', () => {
    flushListadoInicial([admin({ id: 1, rol: 'admin' })]);
    component.cambiarRol(component.administradores[0], 'superadmin');

    const reqPatch = httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/rol') && req.method === 'PATCH');
    expect(reqPatch.request.body).toEqual({ rol: 'superadmin' });
    reqPatch.flush(admin({ id: 1, rol: 'superadmin' }));

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([admin({ id: 1, rol: 'superadmin' })]);

    expect(toast.success).toHaveBeenCalled();
    expect(component.administradores[0].rol).toBe('superadmin');
  });

  it('cambiarRol 409 (degradar al último SUPERADMIN activo): muestra el detail real, sin cambio local', () => {
    flushListadoInicial([admin({ id: 1, rol: 'superadmin', activo: true })]);
    component.cambiarRol(component.administradores[0], 'admin');

    httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/rol') && req.method === 'PATCH')
      .flush({ detail: 'No es posible degradar al último SUPERADMIN activo.' }, { status: 409, statusText: 'Conflict' });

    expect(toast.error).toHaveBeenCalledWith('No es posible degradar al último SUPERADMIN activo.');
    expect(component.administradores[0].rol).toBe('superadmin');
  });

  it('cambiarRol no dispara PATCH si el rol destino es igual al actual', () => {
    flushListadoInicial([admin({ id: 1, rol: 'admin' })]);
    component.cambiarRol(component.administradores[0], 'admin');
    httpMock.expectNone(req => req.url.includes('/usuarios/administradores/1/rol'));
  });

  it('procesandoId evita una segunda mutación mientras la primera está en curso', () => {
    flushListadoInicial([admin({ id: 1, rol: 'admin' })]);
    component.cambiarRol(component.administradores[0], 'superadmin');
    // Segundo intento mientras el primero no ha respondido: no debe generar otra request.
    component.cambiarEstado(component.administradores[0], false);

    httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/rol') && req.method === 'PATCH').flush(admin({ id: 1, rol: 'superadmin' }));
    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([]);

    httpMock.expectNone(req => req.url.includes('/usuarios/administradores/1/estado'));
  });

  // ══════════════════════════════════════
  // CONFIRMACIÓN (desactivar / promover / degradar)
  // ══════════════════════════════════════

  it('desactivar requiere confirmación: pedirConfirmacionDesactivar abre el modal y NO dispara PATCH', () => {
    flushListadoInicial([admin({ id: 1, activo: true })]);
    component.pedirConfirmacionDesactivar(component.administradores[0]);

    expect(component.modalConfirmAbierto).toBe(true);
    expect(component.tipoConfirmacion).toBe('desactivar');
    expect(component.adminEnConfirmacion).toBe(component.administradores[0]);
    httpMock.expectNone(req => req.url.includes('/estado') && req.method === 'PATCH');
  });

  it('cancelar confirmación -> no PATCH y el modal se cierra', () => {
    flushListadoInicial([admin({ id: 1, activo: true })]);
    component.pedirConfirmacionDesactivar(component.administradores[0]);
    component.cancelarConfirmacion();

    expect(component.modalConfirmAbierto).toBe(false);
    expect(component.tipoConfirmacion).toBeNull();
    expect(component.adminEnConfirmacion).toBeNull();
    httpMock.expectNone(req => req.url.includes('/estado') && req.method === 'PATCH');
  });

  it('confirmar desactivación -> dispara el PATCH correcto y cierra el modal', () => {
    flushListadoInicial([admin({ id: 1, activo: true })]);
    component.pedirConfirmacionDesactivar(component.administradores[0]);
    component.confirmarAccionPendiente();

    expect(component.modalConfirmAbierto).toBe(false);
    const reqPatch = httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/estado') && req.method === 'PATCH');
    expect(reqPatch.request.body).toEqual({ activo: false });
    reqPatch.flush(admin({ id: 1, activo: false }));

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([admin({ id: 1, activo: false })]);
    expect(toast.success).toHaveBeenCalled();
  });

  it('promover ADMIN→SUPERADMIN requiere confirmación: no dispara PATCH hasta confirmar', () => {
    flushListadoInicial([admin({ id: 1, rol: 'admin' })]);
    component.pedirConfirmacionRol(component.administradores[0], 'superadmin');

    expect(component.modalConfirmAbierto).toBe(true);
    expect(component.tipoConfirmacion).toBe('promover');
    httpMock.expectNone(req => req.url.includes('/rol') && req.method === 'PATCH');

    component.confirmarAccionPendiente();
    const reqPatch = httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/rol') && req.method === 'PATCH');
    expect(reqPatch.request.body).toEqual({ rol: 'superadmin' });
    reqPatch.flush(admin({ id: 1, rol: 'superadmin' }));
    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([]);
  });

  it('degradar SUPERADMIN→ADMIN requiere confirmación: no dispara PATCH hasta confirmar', () => {
    flushListadoInicial([admin({ id: 1, rol: 'superadmin' })]);
    component.pedirConfirmacionRol(component.administradores[0], 'admin');

    expect(component.modalConfirmAbierto).toBe(true);
    expect(component.tipoConfirmacion).toBe('degradar');
    httpMock.expectNone(req => req.url.includes('/rol') && req.method === 'PATCH');
  });

  it('SUPERADMIN→ADMIN exitoso funciona tras confirmar', () => {
    flushListadoInicial([admin({ id: 1, rol: 'superadmin' })]);
    component.pedirConfirmacionRol(component.administradores[0], 'admin');
    component.confirmarAccionPendiente();

    const reqPatch = httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/rol') && req.method === 'PATCH');
    expect(reqPatch.request.body).toEqual({ rol: 'admin' });
    reqPatch.flush(admin({ id: 1, rol: 'admin' }));

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([admin({ id: 1, rol: 'admin' })]);
    expect(toast.success).toHaveBeenCalled();
    expect(component.administradores[0].rol).toBe('admin');
  });

  it('activar cuenta inactiva funciona de forma directa, sin pasar por el modal de confirmación', () => {
    flushListadoInicial([admin({ id: 1, activo: false })]);
    component.cambiarEstado(component.administradores[0], true);

    expect(component.modalConfirmAbierto).toBe(false);
    const reqPatch = httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/estado') && req.method === 'PATCH');
    expect(reqPatch.request.body).toEqual({ activo: true });
    reqPatch.flush(admin({ id: 1, activo: true }));

    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([admin({ id: 1, activo: true })]);
    expect(toast.success).toHaveBeenCalled();
  });

  it('409 después de confirmación conserva el valor anterior (estado)', () => {
    flushListadoInicial([admin({ id: 1, rol: 'superadmin', activo: true })]);
    const original = component.administradores[0];
    component.pedirConfirmacionDesactivar(original);
    component.confirmarAccionPendiente();

    httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/estado') && req.method === 'PATCH')
      .flush({ detail: 'No es posible desactivar al último SUPERADMIN activo.' }, { status: 409, statusText: 'Conflict' });

    expect(toast.error).toHaveBeenCalledWith('No es posible desactivar al último SUPERADMIN activo.');
    expect(component.administradores[0].activo).toBe(true);
    httpMock.expectNone(req => req.url.includes(URL_LISTADO) && req.method === 'GET');
  });

  it('409 después de confirmación conserva el valor anterior (rol)', () => {
    flushListadoInicial([admin({ id: 1, rol: 'superadmin', activo: true })]);
    component.pedirConfirmacionRol(component.administradores[0], 'admin');
    component.confirmarAccionPendiente();

    httpMock.expectOne(req => req.url.includes('/usuarios/administradores/1/rol') && req.method === 'PATCH')
      .flush({ detail: 'No es posible degradar al último SUPERADMIN activo.' }, { status: 409, statusText: 'Conflict' });

    expect(toast.error).toHaveBeenCalledWith('No es posible degradar al último SUPERADMIN activo.');
    expect(component.administradores[0].rol).toBe('superadmin');
  });

  it('no existe ninguna request DELETE en ningún flujo del componente', () => {
    flushListadoInicial([admin({ id: 1, activo: true, rol: 'admin' })]);
    component.pedirConfirmacionDesactivar(component.administradores[0]);
    component.confirmarAccionPendiente();
    httpMock.expectOne(req => req.url.includes('/estado') && req.method === 'PATCH').flush(admin({ id: 1, activo: false }));
    httpMock.expectOne(req => req.url.includes(URL_LISTADO) && req.method === 'GET').flush([]);

    httpMock.expectNone(req => req.method === 'DELETE');
    expect(typeof (component as any).eliminarAdministrador).toBe('undefined');
  });

  // ══════════════════════════════════════
  // TEMPLATE / ACCESIBILIDAD / RESPONSIVE
  // ══════════════════════════════════════

  it('estructura responsive presente: existe tabla desktop scopeada y lista mobile scopeada', () => {
    flushListadoInicial([admin({ id: 1 })]);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;

    expect(el.querySelector('.admins-desktop-table table.admin-tabla')).toBeTruthy();
    expect(el.querySelector('.admins-mobile-list')).toBeTruthy();
    expect(el.querySelectorAll('.admins-mobile-card').length).toBe(1);
  });

  it('los controles de acción tienen texto accesible (aria-label/title)', () => {
    flushListadoInicial([admin({ id: 1, activo: true, rol: 'admin' })]);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;

    const botonesAccion = Array.from(el.querySelectorAll('.admins-desktop-table .tabla-acciones .btn-tabla'));
    expect(botonesAccion.length).toBeGreaterThan(0);
    botonesAccion.forEach(boton => {
      const tieneAria = !!boton.getAttribute('aria-label')?.trim();
      const tieneTitle = !!boton.getAttribute('title')?.trim();
      expect(tieneAria || tieneTitle).toBe(true);
    });
  });

  // ══════════════════════════════════════
  // VISUALES
  // ══════════════════════════════════════

  it('rolVisual traduce el string técnico a una etiqueta legible', () => {
    flushListadoInicial([]);
    expect(component.rolVisual('superadmin')).toBe('Superadministrador');
    expect(component.rolVisual('admin')).toBe('Administrador');
  });

  it('iniciales cae al correo cuando no hay nombre', () => {
    flushListadoInicial([]);
    expect(component.iniciales(admin({ nombre: null, correo: 'zz@utem.cl' }))).toBe('ZZ');
  });
});
describe('AdminAdministradoresComponent - SA-6.2 refresco de sesion tras cambio de rol', () => {
  let component: AdminAdministradoresComponent;
  let fixture: ComponentFixture<AdminAdministradoresComponent>;
  let httpMock: HttpTestingController;
  let toast: { success: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    sessionStorage.clear();
    localStorage.clear();

    // Por defecto, la sesion de estas pruebas pertenece a otro SUPERADMIN.
    sessionStorage.setItem('rol', 'superadmin');
    sessionStorage.setItem('usuario_id', '99');

    toast = { success: vi.fn(), error: vi.fn() };

    await TestBed.configureTestingModule({
      imports: [AdminAdministradoresComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ToastService, useValue: toast }
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminAdministradoresComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    httpMock = TestBed.inject(HttpTestingController);

    // GET inicial disparado por ngOnInit.
    httpMock.expectOne(
      req => req.url.includes(URL_LISTADO) && req.method === 'GET'
    ).flush([]);

    // La sesi?n empieza como SUPERADMIN ya autorizada por el shell.
    cargarContextoSuperadmin(httpMock);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
    localStorage.clear();
  });

  it('cambiar rol de otra cuenta conserva la sesion y recarga el listado', () => {
    const emitSpy = vi.spyOn(component.sesionAdministrativaActualizada, 'emit');

    component.cambiarRol(
      admin({
        id: 1,
        rol: 'admin',
        correo: 'otra@utem.cl'
      }),
      'superadmin'
    );

    const reqPatch = httpMock.expectOne(
      req =>
        req.url.includes('/usuarios/administradores/1/rol') &&
        req.method === 'PATCH'
    );

    expect(reqPatch.request.body).toEqual({ rol: 'superadmin' });

    reqPatch.flush(
      admin({
        id: 1,
        rol: 'superadmin',
        correo: 'otra@utem.cl'
      })
    );

    // Como la sesion actual sigue siendo SUPERADMIN, conserva
    // roles.gestionar y debe recargar el listado.
    httpMock.expectOne(
      req => req.url.includes(URL_LISTADO) && req.method === 'GET'
    ).flush([]);

    expect(sessionStorage.getItem('rol')).toBe('superadmin');
    expect(sessionStorage.getItem('usuario_id')).toBe('99');
    expect(emitSpy).not.toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalled();
  });

  it('degradar la propia cuenta actualiza sesion, emite evento y evita GET sin permiso', () => {
    sessionStorage.setItem('rol', 'superadmin');
    sessionStorage.setItem('usuario_id', '15');

    const emitSpy = vi.spyOn(component.sesionAdministrativaActualizada, 'emit');

    component.cambiarRol(
      admin({
        id: 15,
        rol: 'superadmin',
        correo: 'superadmin@utem.cl'
      }),
      'admin'
    );

    const reqPatch = httpMock.expectOne(
      req =>
        req.url.includes('/usuarios/administradores/15/rol') &&
        req.method === 'PATCH'
    );

    expect(reqPatch.request.body).toEqual({ rol: 'admin' });

    reqPatch.flush(
      admin({
        id: 15,
        rol: 'admin',
        correo: 'superadmin@utem.cl'
      })
    );

    expect(sessionStorage.getItem('rol')).toBe('admin');
    expect(sessionStorage.getItem('usuario_id')).toBe('15');

    expect(emitSpy).toHaveBeenCalledTimes(1);

    // ADMIN ya no tiene roles.gestionar: no debemos lanzar el GET
    // que el backend rechazaria con 403.
    httpMock.expectNone(
      req => req.url.includes(URL_LISTADO) && req.method === 'GET'
    );

    expect(toast.success).toHaveBeenCalled();
  });
});

describe('AdminAdministradoresComponent - SA-12B apertura de acceso', () => {
  let component: AdminAdministradoresComponent;
  let fixture: ComponentFixture<AdminAdministradoresComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    sessionStorage.clear();
    localStorage.clear();
    sessionStorage.setItem('rol', 'superadmin');
    sessionStorage.setItem('usuario_id', '99');

    await TestBed.configureTestingModule({
      imports: [AdminAdministradoresComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ToastService,
          useValue: { success: vi.fn(), error: vi.fn() }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(AdminAdministradoresComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    httpMock = TestBed.inject(HttpTestingController);

    httpMock.expectOne(
      req => req.url.includes(URL_LISTADO) && req.method === 'GET'
    ).flush([]);
    cargarContextoSuperadmin(httpMock);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
    localStorage.clear();
  });

  it('abre configuración solo para una cuenta ADMIN', () => {
    const target = admin({ id: 7, rol: 'admin' });

    component.abrirAccesoAdministrativo(target);

    expect(component.adminAccesoSeleccionado?.id).toBe(7);
  });

  it('no abre configuración AccesoAdministrativo para SUPERADMIN', () => {
    component.abrirAccesoAdministrativo(
      admin({ id: 7, rol: 'superadmin' })
    );

    expect(component.adminAccesoSeleccionado).toBeNull();
  });

  it('cerrarAccesoAdministrativo limpia el target seleccionado', () => {
    component.abrirAccesoAdministrativo(admin({ id: 7, rol: 'admin' }));
    component.cerrarAccesoAdministrativo();

    expect(component.adminAccesoSeleccionado).toBeNull();
  });
});
