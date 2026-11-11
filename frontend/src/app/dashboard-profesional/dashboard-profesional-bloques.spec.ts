import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { DashboardProfesionalComponent } from './dashboard-profesional';
import { AuthService } from '../auth.service';

/** Dashboard Profesional: solicitud de horario por bloques y su efecto en la agenda. */
describe('DashboardProfesionalComponent: agenda semanal por bloques', () => {
  let fixture: ComponentFixture<DashboardProfesionalComponent>;
  let c: DashboardProfesionalComponent;
  let http: HttpTestingController;

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
    http = TestBed.inject(HttpTestingController);
    (c as any).profesionalId = 7;
  });

  it('las celdas de cada dia respetan el horario institucional', () => {
    expect(c.slotsDelDia(0)[0]).toBe('09:00');
    expect(c.slotsDelDia(0).at(-1)).toBe('17:00');   // la ultima celda de 30 min termina 17:30
    expect(c.slotsDelDia(4).at(-1)).toBe('16:00');   // el viernes termina 16:30
  });

  it('rellenar horario por defecto: Lun-Jue 09:00-17:30, Vie 09:00-16:30 y colacion 12:00-13:00', () => {
    c.aplicarHorarioPorDefecto();
    for (const dia of [0, 1, 2, 3]) {
      expect(c.estadoCelda(dia, '09:00')).toBe('disponible');
      expect(c.estadoCelda(dia, '17:00')).toBe('disponible');
      expect(c.estadoCelda(dia, '17:30')).toBeNull();
      expect(c.estadoCelda(dia, '12:00')).toBe('colacion');
      expect(c.estadoCelda(dia, '12:30')).toBe('colacion');
      expect(c.estadoCelda(dia, '13:00')).toBe('disponible');
    }
    expect(c.estadoCelda(4, '16:00')).toBe('disponible');
    expect(c.estadoCelda(4, '16:30')).toBeNull();
    expect(c.estadoCelda(4, '12:00')).toBe('colacion');
  });

  it('el pincel pinta y despinta una celda', () => {
    c.bloquesModoPincel = 'colacion';
    c.clickCeldaBloque(1, '13:00');
    expect(c.estadoCelda(1, '13:00')).toBe('colacion');
    c.clickCeldaBloque(1, '13:00');
    expect(c.estadoCelda(1, '13:00')).toBeNull();
  });

  it('con una solicitud pendiente la grilla no se puede editar', () => {
    c.solicitudesHorario = [{ tipo: 'bloques', estado: 'pendiente' }];
    c.clickCeldaBloque(0, '09:00');
    c.aplicarHorarioPorDefecto();
    expect(c.bloquesSeleccionVacia).toBe(true);
  });

  it('al enviar fusiona las celdas contiguas en bloques', () => {
    c.aplicarHorarioPorDefecto();
    c.enviarSolicitudBloques();
    const req = http.expectOne(r => r.url.endsWith('/profesional/7/solicitar-bloques-horario'));
    expect(req.request.method).toBe('POST');
    const bloques = req.request.body.bloques;
    expect(bloques.filter((b: any) => b.dia_semana === 0)).toEqual([
      { dia_semana: 0, hora_inicio: '09:00', hora_fin: '12:00', tipo: 'disponible' },
      { dia_semana: 0, hora_inicio: '12:00', hora_fin: '13:00', tipo: 'colacion' },
      { dia_semana: 0, hora_inicio: '13:00', hora_fin: '17:30', tipo: 'disponible' },
    ]);
    expect(bloques.filter((b: any) => b.dia_semana === 4).at(-1))
      .toEqual({ dia_semana: 4, hora_inicio: '13:00', hora_fin: '16:30', tipo: 'disponible' });
    expect(bloques.length).toBe(15);
    req.flush({ message: 'ok' });
    http.expectOne(r => r.url.endsWith('/profesional/7/solicitudes-horario')).flush([]);
    expect(c.enviandoBloques).toBe(false);
  });

  it('no envia nada si no hay ningun bloque disponible', () => {
    c.bloquesModoPincel = 'colacion';
    c.clickCeldaBloque(0, '13:00');
    c.enviarSolicitudBloques();
    http.expectNone(r => r.url.endsWith('/solicitar-bloques-horario'));
  });

  it('la grilla se precarga con los bloques ya aprobados', () => {
    c.precargarBloquesAprobados([
      { dia_semana: 2, hora_inicio: '09:00', hora_fin: '12:00', tipo: 'disponible' },
      { dia_semana: 2, hora_inicio: '12:00', hora_fin: '13:00', tipo: 'colacion' },
    ]);
    expect(c.estadoCelda(2, '11:30')).toBe('disponible');
    expect(c.estadoCelda(2, '12:00')).toBe('colacion');
    expect(c.estadoCelda(2, '13:00')).toBeNull();
  });

  describe('horario predeterminado y días de atención', () => {
    const LUNES = '2026-11-02';
    const VIERNES = '2026-11-06';
    const SABADO = '2026-11-07';
    const DOMINGO = '2026-11-08';

    it('sin bloques ni jornada aprobada usa Lun-Jue 09:00-17:30 y Vie 09:00-16:30', () => {
      c.perfil.bloques_semanales = [];
      c.perfil.duracion_min = 30;
      c.generarHorasGrilla();

      expect(c.horasGrilla[0]).toBe('09:00');
      expect(c.horasGrilla.at(-1)).toBe('17:00'); // la última celda termina 17:30
      expect(c.agendaBloqueEstadoFn(LUNES, '08:30')).toBe('fuera-horario');
      expect(c.agendaBloqueEstadoFn(LUNES, '09:00')).toBe('disponible');
      expect(c.agendaBloqueEstadoFn(LUNES, '17:00')).toBe('disponible');
      expect(c.agendaBloqueEstadoFn(VIERNES, '16:00')).toBe('disponible');
      expect(c.agendaBloqueEstadoFn(VIERNES, '16:30')).toBe('fuera-horario');
    });

    it('un registro antiguo con horario 08:00 no muestra la fila de las 08:00', () => {
      c.perfil.bloques_semanales = [];
      c.perfil.duracion_min = 30;
      c.perfil.horario_inicio = '08:00';
      c.perfil.horario_fin = '17:30';
      c.generarHorasGrilla();

      expect(c.horasGrilla[0]).toBe('09:00');
      expect(c.horasGrilla).not.toContain('08:00');
      expect(c.agendaBloqueEstadoFn(LUNES, '08:00')).toBe('fuera-horario');
    });

    it('sábado y domingo nunca se marcan como disponibles', () => {
      c.perfil.bloques_semanales = [];
      expect(c.agendaBloqueEstadoFn(SABADO, '09:00')).toBe('cerrado-centro');
      expect(c.agendaBloqueEstadoFn(DOMINGO, '10:00')).toBe('cerrado-centro');
      expect(c.getBloqueEstado(SABADO, '09:00')).toBe('cerrado-centro');
      expect(c.getBloqueEstado(DOMINGO, '10:00')).toBe('cerrado-centro');
    });

    it('el período visible termina el viernes, no el domingo', () => {
      c.semanaActual = [
        { nombre: 'Lun', num: 2, fecha: LUNES, esHoy: false },
        { nombre: 'Mar', num: 3, fecha: '2026-11-03', esHoy: false },
        { nombre: 'Mié', num: 4, fecha: '2026-11-04', esHoy: true },
        { nombre: 'Jue', num: 5, fecha: '2026-11-05', esHoy: false },
        { nombre: 'Vie', num: 6, fecha: VIERNES, esHoy: false },
        { nombre: 'Sáb', num: 7, fecha: SABADO, esHoy: false },
        { nombre: 'Dom', num: 8, fecha: DOMINGO, esHoy: false },
      ];
      expect(c.agendaPeriodoLabel).toBe('2 – 6 de noviembre 2026');
    });

    it('distingue horario predeterminado de horario personalizado aprobado', () => {
      c.solicitudesHorario = [];
      c.perfil.bloques_semanales = [];
      expect(c.horarioVigenteEtiqueta).toBe('Horario predeterminado');

      c.perfil.bloques_semanales = [
        { dia_semana: 0, hora_inicio: '09:00', hora_fin: '13:00', tipo: 'disponible' },
      ];
      expect(c.horarioVigenteEtiqueta).toBe('Horario personalizado aprobado');

      c.solicitudesHorario = [{ tipo: 'bloques', estado: 'pendiente' }];
      expect(c.horarioVigenteEtiqueta).toBe('Cambio de horario pendiente');
    });
  });

  describe('efecto en la agenda del profesional', () => {
    const LUNES = '2026-10-19';
    const MARTES = '2026-10-20';

    it('con bloques, fuera de ellos y en colacion la celda queda bloqueada', () => {
      c.perfil.bloques_semanales = [
        { dia_semana: 0, hora_inicio: '09:00', hora_fin: '13:00', tipo: 'disponible' },
        { dia_semana: 0, hora_inicio: '13:00', hora_fin: '14:00', tipo: 'colacion' },
        { dia_semana: 0, hora_inicio: '14:00', hora_fin: '17:30', tipo: 'disponible' },
      ];
      expect(c.getBloqueEstado(LUNES, '10:00')).toBe('libre');
      expect(c.getBloqueEstado(LUNES, '13:00')).toBe('bloqueado');
      expect(c.getBloqueInfo(LUNES, '13:00')).toBe('Colación');
      expect(c.getBloqueEstado(MARTES, '10:00')).toBe('bloqueado');   // martes sin bloques
    });

    it('una cita ya agendada se sigue viendo aunque quede fuera de los bloques', () => {
      c.perfil.bloques_semanales = [{ dia_semana: 0, hora_inicio: '09:00', hora_fin: '10:00', tipo: 'disponible' }];
      c.citasSemana = [{ fecha: LUNES, hora: '15:00', estudiante: 'Ana' }];
      expect(c.getBloqueEstado(LUNES, '15:00')).toBe('ocupado');
    });

    it('sin bloques se mantiene la jornada simple de siempre', () => {
      c.perfil.bloques_semanales = [];
      c.perfil.hora_almuerzo_inicio = '13:00';
      c.perfil.hora_almuerzo_fin = '14:00';
      expect(c.getBloqueEstado(LUNES, '10:00')).toBe('libre');
      expect(c.getBloqueEstado(LUNES, '13:00')).toBe('bloqueado');
    });

    it('la grilla de horas cubre del primer al ultimo bloque disponible', () => {
      c.perfil.duracion_min = 60;
      c.perfil.bloques_semanales = [
        { dia_semana: 0, hora_inicio: '10:00', hora_fin: '12:00', tipo: 'disponible' },
        { dia_semana: 3, hora_inicio: '14:00', hora_fin: '16:00', tipo: 'disponible' },
      ];
      c.generarHorasGrilla();
      expect(c.horasGrilla[0]).toBe('10:00');
      expect(c.horasGrilla.at(-1)).toBe('15:00');
    });
  });

  describe('agenda compartida: horario aprobado como bloqueo estricto', () => {
    const LUNES = '2026-10-19';   // lunes

    beforeEach(() => {
      c.perfil.bloques_semanales = [
        { dia_semana: 0, hora_inicio: '09:00', hora_fin: '13:00', tipo: 'disponible' },
        { dia_semana: 0, hora_inicio: '13:00', hora_fin: '14:00', tipo: 'colacion' },
        { dia_semana: 0, hora_inicio: '14:00', hora_fin: '17:30', tipo: 'disponible' },
      ];
    });

    it('usa estados de bloqueo estricto, no los de la jornada simple', () => {
      expect(c.agendaBloqueEstadoFn(LUNES, '10:00')).toBe('disponible');
      expect(c.agendaBloqueEstadoFn(LUNES, '13:00')).toBe('colacion-aprobada');
      // Fuera de los bloques: no cae en el 'fuera-horario' de la jornada
      // simple, que sí admite sobrecupo del administrador.
      expect(c.agendaBloqueEstadoFn(LUNES, '08:00')).toBe('bloqueado-horario');
      expect(c.agendaBloqueEstadoFn(LUNES, '15:00')).toBe('disponible');
    });

    it('el fin de semana y los días cerrados siguen siendo del centro', () => {
      expect(c.agendaBloqueEstadoFn('2026-10-24', '10:00')).toBe('cerrado-centro');
      c.diasCerrados = [{ fecha: LUNES, motivo: 'Feriado' }];
      expect(c.agendaBloqueEstadoFn(LUNES, '10:00')).toBe('cerrado-centro');
    });
  });
});
