import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { DashboardProfesionalComponent } from './dashboard-profesional';
import { AuthService } from '../auth.service';

/** Ajustes del Inicio tras la primera revisión con capturas. */
describe('DashboardProfesionalComponent — ajustes del Inicio', () => {
  let fixture: ComponentFixture<DashboardProfesionalComponent>;
  let c: DashboardProfesionalComponent;
  let el: HTMLElement;
  const hoy = new Date().toISOString().slice(0, 10);

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [DashboardProfesionalComponent],
      providers: [
        provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
        { provide: AuthService, useValue: { getRol: () => 'profesional', getUsuarioId: () => 7, logout: vi.fn() } }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(DashboardProfesionalComponent);
    c = fixture.componentInstance;
    el = fixture.nativeElement as HTMLElement;
    (c as any).profesionalId = 5;
    c.perfil = { ...c.perfil, nombre: 'Dra. Ana Martínez', estado: 'activo' };
    c.documentosHoy = { total: 0, recetas: 0, justificativos: 0 };
    c.citasSinCerrar = [];
    c.pacientesHistorial = [];
  });

  it('la barra superior no muestra "Bienvenido/a" en el Inicio', () => {
    c.seccionActiva = 'inicio';
    fixture.detectChanges();
    expect((el.querySelector('.topbar-title') as HTMLElement).style.visibility).toBe('hidden');
    expect(el.textContent).not.toContain('Bienvenido');
  });

  it('las otras secciones conservan el título en la barra superior', () => {
    c.seccionActiva = 'solicitudes';
    fixture.detectChanges();
    const titulo = el.querySelector('.topbar-title') as HTMLElement;
    expect(titulo.style.visibility).toBe('visible');
    expect(titulo.textContent).toContain('Solicitudes');
  });

  it('una cita sin motivo informado dice "Motivo no informado" y no repite el tipo de atención', () => {
    c.seccionActiva = 'inicio';
    c.citasHoy = [{ id: 1, hora: '08:00', estado: 'pendiente', fecha: hoy, estudiante: 'Valentina Rojas', estudiante_id: 11, carrera: 'Contador Auditor', observaciones: '', urgente: false }];
    fixture.detectChanges();
    const motivo = el.querySelector('.inicio-agenda-motivo-prof') as HTMLElement;
    expect(motivo.querySelector('strong')?.textContent).toBe('Motivo no informado');
    expect(motivo.querySelector('span')?.textContent?.trim()).toBe(c.tipoAtencionGlobal(c.citasHoy[0]));
  });
});
