import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { DashboardProfesionalComponent } from './dashboard-profesional';
import { AuthService } from '../auth.service';
import { environment } from '../config';

const API = environment.apiUrl;

/** Inicio del profesional y flujo "Iniciar atención" → historial del paciente → "Registrar atención". */
describe('DashboardProfesionalComponent — Inicio y flujo de atención', () => {
  let fixture: ComponentFixture<DashboardProfesionalComponent>;
  let c: DashboardProfesionalComponent;
  let el: HTMLElement;
  let http: HttpTestingController;

  const hoy = new Date().toISOString().slice(0, 10);
  const cita = (id: number, hora: string, estado: string, extra: any = {}) =>
    ({ id, hora, estado, fecha: hoy, estudiante: `Estudiante ${id}`, estudiante_id: 100 + id, carrera: 'Kinesiología', observaciones: 'Control', urgente: false, ...extra });

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
    http = TestBed.inject(HttpTestingController);
    (c as any).profesionalId = 5;   // es privado: se fija directamente para estas pruebas
    c.seccionActiva = 'inicio';
    c.perfil = { ...c.perfil, nombre: 'Carlos Muñoz', estado: 'activo' };
    c.documentosHoy = { total: 3, recetas: 2, justificativos: 1 };
    c.citasHoy = [cita(2, '11:30', 'pendiente'), cita(1, '08:30', 'completada'), cita(3, '10:00', 'pendiente', { urgente: true }), cita(4, '09:00', 'cancelada')];
    c.citasSinCerrar = [];
    c.pacientesHistorial = [];
  });

  describe('Inicio', () => {
    it('saluda por el nombre, sin saludo según la hora del día', () => {
      fixture.detectChanges();
      const titulo = el.querySelector('.inicio-cab-titulo-prof')?.textContent?.trim();
      expect(titulo).toBe('¡Hola, Carlos Muñoz!');
      expect(el.textContent).not.toMatch(/Buenos días|Buenas tardes|Buenas noches/);
    });

    it('muestra el avance del día sin contar las canceladas', () => {
      fixture.detectChanges();
      expect(c.atencionesHoyTotal).toBe(3);
      expect(c.atencionesHoyRealizadas).toBe(1);
      expect(c.avanceHoyPct).toBe(33);
      expect(el.querySelector('.inicio-kpi-num-prof')?.textContent?.replace(/\s+/g, ' ').trim()).toBe('1 / 3');
      expect(el.textContent).toContain('1 de 3 atenciones realizadas');
    });

    it('la próxima cita y los documentos del día salen de datos reales', () => {
      fixture.detectChanges();
      const nums = Array.from(el.querySelectorAll('.inicio-kpi-num-prof')).map(n => n.textContent?.replace(/\s+/g, ' ').trim());
      expect(nums[1]).toBe('10:00');   // la primera pendiente por hora
      expect(nums[2]).toBe('3');
      expect(c.proximaAtencionPendiente?.id).toBe(3);
    });

    it('la agenda marca Completada, En espera y Programada, e inicia solo la que toca', () => {
      fixture.detectChanges();
      expect(c.agendaHoyCitas.map(x => x.hora)).toEqual(['08:30', '09:00', '10:00', '11:30']);
      expect(c.etiquetaEstadoAgenda(c.citasHoy[1])).toBe('Completada');
      expect(c.etiquetaEstadoAgenda(c.citasHoy[2])).toBe('En espera');
      expect(c.etiquetaEstadoAgenda(c.citasHoy[0])).toBe('Programada');
      expect(c.etiquetaEstadoAgenda(c.citasHoy[3])).toBe('Cancelada');
      expect(el.querySelectorAll('.inicio-btn-iniciar-prof')).toHaveLength(1);
      expect(el.querySelector('.inicio-btn-iniciar-prof')?.textContent).toContain('Iniciar atención');
    });

    it('sin nada pendiente, la acción rápida "Iniciar atención" queda desactivada', () => {
      c.citasHoy = [cita(1, '08:30', 'completada')];
      fixture.detectChanges();
      expect(c.proximaAtencionPendiente).toBeNull();
      expect((el.querySelector('.inicio-accion-principal-prof') as HTMLButtonElement).disabled).toBe(true);
    });

    it('el recordatorio se puede cerrar y no vuelve a aparecer', () => {
      fixture.detectChanges();
      expect(el.querySelector('.inicio-recuerda-prof')).not.toBeNull();
      (el.querySelector('.inicio-recuerda-cerrar-prof') as HTMLButtonElement).click();
      fixture.detectChanges();
      expect(el.querySelector('.inicio-recuerda-prof')).toBeNull();
      expect(localStorage.getItem('prof_recuerda_cerrado')).toBe('1');
    });

    it('"Pendientes por revisar" reúne citas sin cerrar, fichas incompletas y solicitudes', () => {
      c.citasSinCerrar = [cita(9, '09:00', 'pendiente', { fecha: '2020-01-01' })];
      c.pacientesHistorial = [{ estudiante_id: 1, nombre: 'Diego Soto', carrera: 'Ing. Civil', tiene_ficha: false, dias_desde_ultima_visita: 0 }];
      const titulos = c.pendientesPorRevisar.map(p => p.titulo);
      expect(titulos).toContain('Cita sin cerrar');
      expect(titulos).toContain('Ficha clínica incompleta');
      c.pacientesHistorial = [];
      c.citasSinCerrar = [];
      expect(c.pendientesPorRevisar).toEqual([]);
      fixture.detectChanges();
      expect(el.textContent).toContain('Todo al día');
    });

    it('carga los documentos emitidos hoy desde el backend', () => {
      c.cargarDocumentosHoy();
      http.expectOne(`${API}/documentos/profesional/5/hoy`).flush({ fecha: hoy, total: 4, recetas: 3, justificativos: 1 });
      expect(c.documentosHoy.total).toBe(4);
    });

    it('no repite el bloque de notificaciones', () => {
      fixture.detectChanges();
      expect(el.querySelector('.inicio-grid-prof')?.textContent).not.toContain('Notificaciones');
    });
  });

  describe('Flujo de atención', () => {
    const ficha = (extra: any = {}) => ({ existe: true, preguntas: [], respuestas: {}, citas: [], total_atenciones: 0, ...extra });

    it('"Iniciar atención" abre el historial del paciente con el contexto de la cita', () => {
      const c1 = cita(3, '10:00', 'pendiente');
      c.iniciarAtencion(c1);
      expect(c.seccionActiva).toBe('historial-clinico');
      expect(c.pacienteSeleccionado.estudiante_id).toBe(103);
      http.match(r => r.url.endsWith('/pacientes')).forEach(r => r.flush([]));
      http.expectOne(`${API}/historial-clinico/5/103`).flush(ficha({ citas: [{ ...c1 }] }));
      fixture.detectChanges();
      expect(c.citaContextoAtencion?.id).toBe(3);
      expect(el.querySelector('.atencion-banner-prof')?.textContent).toContain('Atención de hoy · 10:00');
      expect(el.querySelector('.atencion-banner-prof')?.textContent).toContain('Motivo: Control');
    });

    it('"Registrar atención" usa la cita con la que se inició, aunque haya otra pendiente antes', () => {
      const antigua = cita(8, '09:00', 'pendiente', { fecha: '2020-01-01' });
      const actual = cita(3, '10:00', 'pendiente');
      c.iniciarAtencion(actual);
      http.match(r => r.url.endsWith('/pacientes')).forEach(r => r.flush([]));
      http.expectOne(`${API}/historial-clinico/5/103`).flush(ficha({ citas: [antigua, actual] }));
      expect(c.fichaCitaPendienteActual?.id).toBe(3);
    });

    it('si no hay cita pendiente, el botón queda desactivado y explica por qué', () => {
      c.pacienteSeleccionado = { estudiante_id: 1, nombre: 'Ana' };
      c.fichaCitas = [];
      expect(c.puedeRegistrarAtencion).toBe(false);
      expect(c.motivoSinAtencion).toContain('No hay una cita pendiente');
      c.fichaCitas = [cita(1, '10:00', 'pendiente')];
      expect(c.puedeRegistrarAtencion).toBe(true);
      expect(c.motivoSinAtencion).toBe('');
    });

    it('el menú lateral "Historial clínico" cierra la ficha y vuelve al buscador', () => {
      c.seccionActiva = 'historial-clinico';
      c.pacienteSeleccionado = { estudiante_id: 1, nombre: 'Ana' };
      c.navegarA('historial-clinico');
      http.match(r => r.url.endsWith('/pacientes')).forEach(r => r.flush([]));
      expect(c.pacienteSeleccionado).toBeNull();
      expect(c.citaEnAtencion).toBeNull();
    });

    it('"Volver a pacientes" pide confirmación solo si hay antecedentes sin guardar', () => {
      const confirmar = vi.spyOn(window, 'confirm');
      c.pacienteSeleccionado = { estudiante_id: 1, nombre: 'Ana' };
      c.fichaEnEdicion = true;
      c.fichaRespuestas = {};
      c.fichaRespuestasInicial = JSON.stringify({});
      c.volverAPacientes();                                   // sin cambios: sale sin preguntar
      expect(confirmar).not.toHaveBeenCalled();
      expect(c.pacienteSeleccionado).toBeNull();

      c.pacienteSeleccionado = { estudiante_id: 1, nombre: 'Ana' };
      c.fichaEnEdicion = true;
      c.fichaRespuestas = { a: 'nuevo' };
      confirmar.mockReturnValue(false);
      c.volverAPacientes();                                   // con cambios y "cancelar": se queda
      expect(c.pacienteSeleccionado).not.toBeNull();
      confirmar.mockReturnValue(true);
      c.volverAPacientes();                                   // con cambios y "aceptar": sale
      expect(c.pacienteSeleccionado).toBeNull();
    });

    it('en la ficha, "Ver ficha" pasa a ser "Antecedentes" con su estado, y existe "Volver a pacientes"', () => {
      c.seccionActiva = 'historial-clinico';
      c.pacienteSeleccionado = { estudiante_id: 1, nombre: 'Ana' };
      c.fichaExiste = false;
      c.fichaCitas = [];
      fixture.detectChanges();
      const texto = el.textContent ?? '';
      expect(texto).toContain('Volver a pacientes');
      expect(texto).toContain('Antecedentes');
      expect(texto).toContain('Sin responder');
      expect(texto).not.toContain('Ver ficha');
    });

    it('en la lista de pacientes el botón se llama "Abrir historial"', () => {
      c.seccionActiva = 'historial-clinico';
      c.pacienteSeleccionado = null;
      c.pacientesHistorial = [{ estudiante_id: 1, nombre: 'Ana', carrera: 'X', rut: '1-9', tiene_ficha: true, total_atenciones: 1, dias_desde_ultima_visita: 0 }];
      fixture.detectChanges();
      expect(el.textContent).toContain('Abrir historial');
    });
  });
});
