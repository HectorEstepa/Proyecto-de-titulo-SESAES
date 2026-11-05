import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { AdminAccesoAdministrativoComponent } from './admin-acceso-administrativo';
import { ToastService } from '../../../shared/toast/toast.service';

const URL_CATALOGO = '/usuarios/administradores/catalogo-acceso';
const URL_ACCESO = '/usuarios/administradores/7/acceso-administrativo';

const ADMIN = {
  id: 7,
  nombre: 'Secretaría Odontología',
  correo: 'secretaria@utem.cl',
  rol: 'admin' as const
};

const CATALOGO = {
  perfiles: [
    {
      perfil: 'administrador_general',
      tipo_alcance: 'institucional',
      permisos_permitidos: [
        'usuarios.ver',
        'usuarios.gestionar',
        'profesionales.ver',
        'profesionales.gestionar',
        'agenda.ver',
        'agenda.gestionar',
        'reportes.ver'
      ]
    },
    {
      perfil: 'secretaria_especialidad',
      tipo_alcance: 'especialidades',
      permisos_permitidos: [
        'usuarios.ver',
        'profesionales.ver',
        'agenda.ver',
        'agenda.gestionar'
      ]
    }
  ]
};

describe('AdminAccesoAdministrativoComponent (SA-12B)', () => {
  let component: AdminAccesoAdministrativoComponent;
  let fixture: ComponentFixture<AdminAccesoAdministrativoComponent>;
  let httpMock: HttpTestingController;
  let toast: { success: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    toast = { success: vi.fn(), error: vi.fn() };

    await TestBed.configureTestingModule({
      imports: [AdminAccesoAdministrativoComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ToastService, useValue: toast }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(AdminAccesoAdministrativoComponent);
    component = fixture.componentInstance;
    component.admin = ADMIN;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function iniciar(): void {
    fixture.detectChanges();
  }

  function flushCatalogo(): void {
    httpMock.expectOne(
      req => req.url.includes(URL_CATALOGO) && req.method === 'GET'
    ).flush(CATALOGO);
  }

  function flushAccesoSinConfigurar(): void {
    httpMock.expectOne(
      req => req.url.includes(URL_ACCESO) && req.method === 'GET'
    ).flush({
      usuario_id: 7,
      configurado: false,
      perfil: null,
      permisos: [],
      alcance: { tipo: null, especialidades: [] }
    });
  }

  it('carga catálogo y acceso actual al iniciar', () => {
    iniciar();
    flushCatalogo();
    flushAccesoSinConfigurar();

    expect(component.cargando).toBe(false);
    expect(component.configurado).toBe(false);
    expect(component.perfilesDisponibles.length).toBe(2);
    expect(component.form.perfil).toBe('');
  });

  it('hidrata una configuración persistida sin inventar defaults', () => {
    iniciar();
    flushCatalogo();

    httpMock.expectOne(
      req => req.url.includes(URL_ACCESO) && req.method === 'GET'
    ).flush({
      usuario_id: 7,
      configurado: true,
      perfil: 'secretaria_especialidad',
      permisos: ['agenda.ver', 'profesionales.ver'],
      alcance: {
        tipo: 'especialidades',
        especialidades: ['Odontología']
      }
    });

    expect(component.configurado).toBe(true);
    expect(component.form.perfil).toBe('secretaria_especialidad');
    expect(component.form.permisos).toEqual(['agenda.ver', 'profesionales.ver']);
    expect(component.form.especialidades).toEqual(['Odontología']);
    expect(component.formularioValido).toBe(true);
  });

  it('rechaza catálogo con permisos desconocidos y falla cerrado', () => {
    iniciar();

    httpMock.expectOne(
      req => req.url.includes(URL_CATALOGO) && req.method === 'GET'
    ).flush({
      perfiles: [{
        perfil: 'secretaria_especialidad',
        tipo_alcance: 'especialidades',
        permisos_permitidos: ['permiso.inventado']
      }]
    });

    expect(component.cargando).toBe(false);
    expect(component.errorCarga).toContain('catálogo');
    httpMock.expectNone(req => req.url.includes(URL_ACCESO));
  });

  it('un perfil de especialidad requiere al menos una especialidad', () => {
    iniciar();
    flushCatalogo();
    flushAccesoSinConfigurar();

    component.form.perfil = 'secretaria_especialidad';
    component.cambiarPerfil();
    expect(component.formularioValido).toBe(false);

    component.form.nuevaEspecialidad = '  Odontología  ';
    component.agregarEspecialidad();

    expect(component.form.especialidades).toEqual(['Odontología']);
    expect(component.formularioValido).toBe(true);
  });

  it('no agrega especialidades duplicadas ignorando mayúsculas', () => {
    iniciar();
    flushCatalogo();
    flushAccesoSinConfigurar();

    component.form.perfil = 'secretaria_especialidad';
    component.cambiarPerfil();

    component.form.nuevaEspecialidad = 'Odontología';
    component.agregarEspecialidad();
    component.form.nuevaEspecialidad = 'odontología';
    component.agregarEspecialidad();

    expect(component.form.especialidades).toEqual(['Odontología']);
  });

  it('al cambiar a perfil institucional limpia especialidades', () => {
    iniciar();
    flushCatalogo();
    flushAccesoSinConfigurar();

    component.form.perfil = 'secretaria_especialidad';
    component.cambiarPerfil();
    component.form.nuevaEspecialidad = 'Odontología';
    component.agregarEspecialidad();

    component.form.perfil = 'administrador_general';
    component.cambiarPerfil();

    expect(component.requiereEspecialidades).toBe(false);
    expect(component.form.especialidades).toEqual([]);
    expect(component.formularioValido).toBe(true);
  });

  it('solo permite seleccionar permisos presentes en el techo del perfil', () => {
    iniciar();
    flushCatalogo();
    flushAccesoSinConfigurar();

    component.form.perfil = 'secretaria_especialidad';
    component.cambiarPerfil();

    component.cambiarPermiso('agenda.ver', true);
    component.cambiarPermiso('reportes.ver', true);

    expect(component.form.permisos).toEqual(['agenda.ver']);
  });

  it('PUT guarda perfil, permisos y alcance como una unidad completa', () => {
    iniciar();
    flushCatalogo();
    flushAccesoSinConfigurar();

    component.form.perfil = 'secretaria_especialidad';
    component.cambiarPerfil();
    component.cambiarPermiso('agenda.ver', true);
    component.cambiarPermiso('agenda.gestionar', true);
    component.form.nuevaEspecialidad = 'Odontología';
    component.agregarEspecialidad();

    const cerrarSpy = vi.spyOn(component.cerrar, 'emit');
    component.guardar();

    const req = httpMock.expectOne(
      request => request.url.includes(URL_ACCESO) && request.method === 'PUT'
    );

    expect(req.request.body).toEqual({
      perfil: 'secretaria_especialidad',
      permisos: ['agenda.ver', 'agenda.gestionar'],
      alcance: {
        tipo: 'especialidades',
        especialidades: ['Odontología']
      }
    });

    req.flush({
      usuario_id: 7,
      configurado: true,
      perfil: 'secretaria_especialidad',
      permisos: ['agenda.ver', 'agenda.gestionar'],
      alcance: {
        tipo: 'especialidades',
        especialidades: ['Odontología']
      }
    });

    expect(toast.success).toHaveBeenCalledWith('Permisos y alcance actualizados correctamente.');
    expect(cerrarSpy).toHaveBeenCalledTimes(1);
  });

  it('422 conserva el formulario abierto y prioriza detail del backend', () => {
    iniciar();
    flushCatalogo();
    flushAccesoSinConfigurar();

    component.form.perfil = 'administrador_general';
    component.cambiarPerfil();
    component.guardar();

    httpMock.expectOne(
      request => request.url.includes(URL_ACCESO) && request.method === 'PUT'
    ).flush(
      { detail: 'Configuración administrativa inválida.' },
      { status: 422, statusText: 'Unprocessable Entity' }
    );

    expect(component.errorGuardado).toBe('Configuración administrativa inválida.');
    expect(component.guardando).toBe(false);
  });

  it('no permite cerrar mientras el PUT está en curso', () => {
    iniciar();
    flushCatalogo();
    flushAccesoSinConfigurar();

    component.form.perfil = 'administrador_general';
    component.cambiarPerfil();

    const cerrarSpy = vi.spyOn(component.cerrar, 'emit');
    component.guardar();
    component.solicitarCierre();

    expect(cerrarSpy).not.toHaveBeenCalled();

    httpMock.expectOne(
      request => request.url.includes(URL_ACCESO) && request.method === 'PUT'
    ).flush({
      usuario_id: 7,
      configurado: true,
      perfil: 'administrador_general',
      permisos: [],
      alcance: { tipo: 'institucional', especialidades: [] }
    });
  });
});
