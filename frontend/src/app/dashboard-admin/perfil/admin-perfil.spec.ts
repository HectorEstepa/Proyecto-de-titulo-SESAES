import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';

import { AdminPerfilComponent } from './admin-perfil';

describe('AdminPerfilComponent (SA-1.2 — identidad real de Usuario)', () => {
  let component: AdminPerfilComponent;
  let fixture: ComponentFixture<AdminPerfilComponent>;
  let httpMock: HttpTestingController;

  const usuarioAdminMock = {
    id: 7, nombre: 'Admin SESAES', correo: 'admin@utem.cl',
    telefono: '+56911112222', foto_url: null, rol: 'admin', activo: true
  };

  const usuarioSuperadminMock = {
    id: 1, nombre: 'Super SESAES', correo: 'superadmin@utem.cl',
    telefono: null, foto_url: null, rol: 'superadmin', activo: true
  };

  beforeEach(async () => {
    // provideHttpClient/HttpTestingController se incluyen únicamente para
    // verificar que este componente NO dispara ningún HTTP propio: el
    // guardado real (PATCH /usuarios/me y cambiar-password) sigue siendo
    // responsabilidad del shell, este hijo solo emite la intención.
    await TestBed.configureTestingModule({
      imports: [AdminPerfilComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminPerfilComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  // ══════════════════════════════════════
  // SA-1.2 v2 — guard de carga: no editar/guardar sobre datos que
  // todavía no son la respuesta real de GET /usuarios/me.
  // ══════════════════════════════════════

  it('SA-1.2: mientras perfilCargado=false, no muestra el botón Editar ni permite habilitar edición', () => {
    fixture.componentRef.setInput('usuario', {});
    fixture.componentRef.setInput('perfilCargado', false);
    fixture.detectChanges();

    const botonEditar = fixture.nativeElement.querySelector('.btn-editar-perfil');
    expect(botonEditar).toBeFalsy();

    component.habilitarEdicionPerfilAdmin();
    expect(component.adminPerfilEnEdicion).toBe(false);
  });

  it('SA-1.2: mientras perfilCargado=false, guardarPerfilAdmin() no emite nada', () => {
    fixture.componentRef.setInput('usuario', {});
    fixture.componentRef.setInput('perfilCargado', false);
    fixture.detectChanges();

    let emitido = false;
    component.guardarPerfil.subscribe(() => emitido = true);

    // Aunque se manipule el estado interno directamente (bypass de la UI),
    // el guard de guardarPerfilAdmin() sigue bloqueando el guardado.
    component.configPerfil.nombre = 'Intento con perfil no cargado';
    component.guardarPerfilAdmin();

    expect(emitido).toBe(false);
  });

  // ══════════════════════════════════════
  // SA-1.2 v3 — estados de carga/error de "Mi Perfil", distintos entre
  // sí: cargando, error tras carga fallida, y formulario normal.
  // ══════════════════════════════════════

  it('SA-1.2 v3: cargandoPerfil=true -> muestra "Cargando tu perfil…"', () => {
    fixture.componentRef.setInput('usuario', {});
    fixture.componentRef.setInput('cargandoPerfil', true);
    fixture.componentRef.setInput('perfilCargado', false);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Cargando tu perfil…');
    expect(fixture.nativeElement.textContent).not.toContain('No se pudo cargar tu perfil.');
  });

  it('SA-1.2 v3: carga fallida (cargandoPerfil=false, perfilCargado=false) -> no muestra "Cargando…" indefinidamente, sino un estado de error', () => {
    fixture.componentRef.setInput('usuario', {});
    fixture.componentRef.setInput('cargandoPerfil', false);
    fixture.componentRef.setInput('perfilCargado', false);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('Cargando tu perfil…');
    expect(fixture.nativeElement.textContent).toContain('No se pudo cargar tu perfil.');
  });

  it('SA-1.2 v3: perfilCargado=false (con o sin carga en curso) -> el botón Editar no aparece', () => {
    fixture.componentRef.setInput('usuario', {});
    fixture.componentRef.setInput('cargandoPerfil', false);
    fixture.componentRef.setInput('perfilCargado', false);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.btn-editar-perfil')).toBeFalsy();
  });

  it('SA-1.2: al pasar perfilCargado=true, aparece el botón Editar y habilitar edición funciona', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    const botonEditar = fixture.nativeElement.querySelector('.btn-editar-perfil');
    expect(botonEditar).toBeTruthy();

    component.habilitarEdicionPerfilAdmin();
    expect(component.adminPerfilEnEdicion).toBe(true);
  });

  // ══════════════════════════════════════
  // Identidad real (Usuario, no ConfiguracionCentro)
  // ══════════════════════════════════════

  it('SA-1.2: renderiza la identidad real del Usuario (ADMIN) — nombre, correo y rol', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    expect(component.configPerfil.nombre).toBe('Admin SESAES');
    expect(component.rolVisual).toBe('Administrador');

    const inputsPerfil = fixture.nativeElement.querySelectorAll(
      '.campo-grupo input'
    ) as NodeListOf<HTMLInputElement>;

    const inputCorreo = Array.from(inputsPerfil).find(
      input => input.value === 'admin@utem.cl'
    );

    expect(inputCorreo).toBeTruthy();
    expect(inputCorreo?.value).toBe('admin@utem.cl');
  });

  it('SA-1.2: SUPERADMIN muestra rol "Superadministrador"', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioSuperadminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    expect(component.rolVisual).toBe('Superadministrador');
  });

  it('SA-1.2: el campo Correo es de solo lectura (disabled), nunca editable', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    const inputsPerfil = fixture.nativeElement.querySelectorAll(
      '.campo-grupo input'
    ) as NodeListOf<HTMLInputElement>;

    const inputCorreo = Array.from(inputsPerfil).find(
      input => input.value === 'admin@utem.cl'
    );

    expect(inputCorreo?.disabled).toBe(true);
  });

  it('SA-1.2: no existe ningún @Input `configCentro` — Mi Perfil no depende de ConfiguracionCentro', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock, foto_url: 'https://ejemplo.cl/foto.png' });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    expect((component as any).configCentro).toBeUndefined();
    expect(component.fotoActual).toBe('https://ejemplo.cl/foto.png');
  });

  // ══════════════════════════════════════
  // Edición / guardado (con perfilCargado=true)
  // ══════════════════════════════════════

  it('habilitar edición mantiene comportamiento: desbloquea campos y permite cancelar sin cambios', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    expect(component.adminPerfilEnEdicion).toBe(false);
    component.habilitarEdicionPerfilAdmin();
    expect(component.adminPerfilEnEdicion).toBe(true);
    expect(component.perfilAdminModificado).toBe(false);

    component.configPerfil.nombre = 'Otro nombre';
    expect(component.perfilAdminModificado).toBe(true);

    component.cancelarEdicionPerfilAdmin();
    expect(component.adminPerfilEnEdicion).toBe(false);
    expect(component.configPerfil.nombre).toBe('Admin SESAES');
    expect(component.configPerfil.contrasena_actual).toBe('');
  });

  it('SA-1.2: guardar emite nombre/telefono/foto contra Usuario (nunca contra ConfiguracionCentro)', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    component.habilitarEdicionPerfilAdmin();
    component.configPerfil.nombre = 'Nuevo Nombre Admin';
    component.configPerfil.telefono = '+56933334444';
    component.onFotoRecortada('data:image/png;base64,ABC');
    component.configPerfil.contrasena_actual = 'actual123';
    component.configPerfil.contrasena_nueva = 'nueva123';
    component.configPerfil.contrasena_conf = 'nueva123';

    let payload: any = null;
    component.guardarPerfil.subscribe((p: any) => payload = p);

    component.guardarPerfilAdmin();

    expect(payload).toEqual({
      nombre: 'Nuevo Nombre Admin',
      telefono: '+56933334444',
      foto_url: 'data:image/png;base64,ABC',
      contrasena_actual: 'actual123',
      contrasena_nueva: 'nueva123',
      contrasena_conf: 'nueva123'
    });
  });

  it('guardar no emite nada si no hay cambios (perfilAdminModificado en false)', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    let emitido = false;
    component.guardarPerfil.subscribe(() => emitido = true);

    component.guardarPerfilAdmin();

    expect(emitido).toBe(false);
  });

  it('finalizarEdicion(true) restablece edición, limpia contraseñas y descarta la foto en preview', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    component.habilitarEdicionPerfilAdmin();
    component.onFotoRecortada('data:image/png;base64,ABC');
    component.configPerfil.contrasena_actual = 'a';
    component.configPerfil.contrasena_nueva = 'b';
    component.configPerfil.contrasena_conf = 'b';

    component.finalizarEdicion(true);

    expect(component.adminPerfilEnEdicion).toBe(false);
    expect(component.fotoCambiada).toBe(false);
    expect(component.configPerfil.contrasena_actual).toBe('');
    expect(component.configPerfil.contrasena_nueva).toBe('');
    expect(component.configPerfil.contrasena_conf).toBe('');
  });

  it('finalizarEdicion(false) restablece edición pero NO toca los campos de contraseña', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    component.habilitarEdicionPerfilAdmin();
    component.configPerfil.contrasena_actual = 'sigue-aqui';

    component.finalizarEdicion(false);

    expect(component.adminPerfilEnEdicion).toBe(false);
    expect(component.configPerfil.contrasena_actual).toBe('sigue-aqui');
  });

  it('onFotoRecortada guarda la foto en preview local SIN mutar el @Input `usuario`', () => {
    const usuario = { ...usuarioAdminMock };
    fixture.componentRef.setInput('usuario', usuario);
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();

    component.onFotoRecortada('data:image/png;base64,ABC');

    expect(component.fotoActual).toBe('data:image/png;base64,ABC');
    expect(usuario.foto_url).toBeNull(); // el @Input original no se muta
    expect(component.fotoCambiada).toBe(true);
    expect(component.imagenParaRecortar).toBeNull();
  });

  it('ngOnChanges sincroniza el formulario cuando el shell reasigna `usuario`', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();
    expect(component.configPerfil.nombre).toBe('Admin SESAES');

    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock, nombre: 'Recargado' });
    fixture.detectChanges();
    expect(component.configPerfil.nombre).toBe('Recargado');
  });

  it('NO realiza ningún HTTP propio: el guardado se emite, no se ejecuta aquí', () => {
    fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
    fixture.componentRef.setInput('perfilCargado', true);
    fixture.detectChanges();
    // httpMock.verify() en afterEach comprueba que no quedó ninguna petición pendiente.
    expect(true).toBe(true);
  });
it('SA-1.2: SUPERADMIN sin foto usa iniciales reales "SS" y título dinámico', () => {
  fixture.componentRef.setInput('usuario', {
    ...usuarioSuperadminMock,
    nombre: 'Superadministrador SESAES',
    foto_url: null
  });
  fixture.componentRef.setInput('perfilCargado', true);
  fixture.detectChanges();

  expect(component.inicialesUsuario).toBe('SS');

  const placeholder = fixture.nativeElement.querySelector(
    '.perfil-foto-placeholder'
  ) as HTMLElement;

  expect(placeholder).toBeTruthy();
  expect(placeholder.textContent?.trim()).toBe('SS');
  expect(fixture.nativeElement.textContent).toContain(
    'Perfil del Superadministrador'
  );
});

it('SA-1.2: ADMIN sin foto usa iniciales reales "CP"', () => {
  fixture.componentRef.setInput('usuario', {
    ...usuarioAdminMock,
    nombre: 'Claudia Pérez',
    foto_url: null
  });
  fixture.componentRef.setInput('perfilCargado', true);
  fixture.detectChanges();

  expect(component.inicialesUsuario).toBe('CP');

  const placeholder = fixture.nativeElement.querySelector(
    '.perfil-foto-placeholder'
  ) as HTMLElement;

  expect(placeholder).toBeTruthy();
  expect(placeholder.textContent?.trim()).toBe('CP');
});

it('SA-1.2: solo contrasena_conf con contenido cuenta como perfil modificado', () => {
  fixture.componentRef.setInput('usuario', { ...usuarioAdminMock });
  fixture.componentRef.setInput('perfilCargado', true);
  fixture.detectChanges();

  expect(component.perfilAdminModificado).toBe(false);

  component.configPerfil.contrasena_conf = 'confirmacion123';

  expect(component.perfilAdminModificado).toBe(true);
});
});
