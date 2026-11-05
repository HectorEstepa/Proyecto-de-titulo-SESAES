import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { DashboardProfesionalComponent } from './dashboard-profesional';
import { AuthService } from '../auth.service';

/** Dashboard Profesional: modo claro/oscuro e iconos (la estructura no cambia). */
describe('DashboardProfesionalComponent — modo claro/oscuro e iconos', () => {
  let fixture: ComponentFixture<DashboardProfesionalComponent>;
  let c: DashboardProfesionalComponent;

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
  });

  it('modo claro: el contenedor no lleva la clase tema-oscuro', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.dashboard-prof').classList).not.toContain('tema-oscuro');
  });

  it('modo oscuro: el contenedor lleva la clase tema-oscuro', () => {
    c.temaOscuro = true;
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.dashboard-prof').classList).toContain('tema-oscuro');
  });

  it('alternar el tema cambia el estado y lo persiste', () => {
    c.toggleTema();
    expect(c.temaOscuro).toBe(true);
    expect(localStorage.getItem('prof_tema_oscuro')).toBe('true');
    c.toggleTema();
    expect(c.temaOscuro).toBe(false);
    expect(localStorage.getItem('prof_tema_oscuro')).toBe('false');
  });

  it('los iconos son Material Symbols Outlined (sin SVG inline)', () => {
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('svg').length).toBe(0);
    expect(el.querySelectorAll('.material-symbols-outlined').length).toBeGreaterThan(5);
  });

  it('la agenda reutiliza la grilla del administrador en modo consulta propia', () => {
    (c as any).profesionalId = 7;
    c.seccionActiva = 'horario';
    c.horarioTab = 'agenda';
    c.perfil = {
      ...c.perfil,
      nombre: 'Dra. Propia',
      especialidad: 'Nutrición',
      estado: 'activo'
    };
    c.semanaActual = [
      { nombre: 'Lun', num: 2, fecha: '2026-11-02', esHoy: false },
      { nombre: 'Mar', num: 3, fecha: '2026-11-03', esHoy: false },
      { nombre: 'Mié', num: 4, fecha: '2026-11-04', esHoy: true },
      { nombre: 'Jue', num: 5, fecha: '2026-11-05', esHoy: false },
      { nombre: 'Vie', num: 6, fecha: '2026-11-06', esHoy: false },
      { nombre: 'Sáb', num: 7, fecha: '2026-11-07', esHoy: false },
      { nombre: 'Dom', num: 8, fecha: '2026-11-08', esHoy: false }
    ];
    c.horasGrilla = ['09:00', '09:45'];
    fixture.detectChanges();

    const agenda = fixture.nativeElement.querySelector('app-admin-horario') as HTMLElement;
    expect(agenda).toBeTruthy();
    const texto = agenda.textContent ?? '';
    expect(texto).toContain('Dra. Propia');
    expect(texto).toContain('Solo consulta');
    expect(texto).not.toContain('Nueva cita');
    expect(texto).not.toContain('Solicitar sobrecupo');
    expect(texto).not.toContain('Solicitudes de horario pendientes');
  });
});
