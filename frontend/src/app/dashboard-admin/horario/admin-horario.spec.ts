import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AdminHorarioComponent } from './admin-horario';

describe('AdminHorarioComponent', () => {
  let component: AdminHorarioComponent;
  let fixture: ComponentFixture<AdminHorarioComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminHorarioComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(AdminHorarioComponent);
    component = fixture.componentInstance;

    fixture.componentRef.setInput(
      'formatearFechaFn',
      (fecha: string) => `FORMATO:${fecha}`
    );
    fixture.componentRef.setInput(
      'bloqueEstadoFn',
      () => 'disponible'
    );
    fixture.componentRef.setInput(
      'bloqueInfoFn',
      () => ''
    );
    fixture.componentRef.setInput(
      'esFeriadoFn',
      () => false
    );
    fixture.componentRef.setInput(
      'nombreFeriadoFn',
      () => ''
    );
  });

  it('debe crearse', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('debe mostrar y emitir acciones sobre solicitudes pendientes', () => {
    const aprobarSpy = vi.spyOn(component.aprobarSolicitud, 'emit');
    const rechazarSpy = vi.spyOn(component.rechazarSolicitud, 'emit');

    const solicitud = {
      id: 1,
      profesional_nombre: 'Profesional SESAES',
      especialidad: 'Medicina',
      tipo: 'jornada',
      hora_inicio: '08:00',
      hora_fin: '17:00',
      fecha_solicitud: '2026-08-31T09:00:00'
    };

    fixture.componentRef.setInput('puedeGestionarAgenda', true);
    fixture.componentRef.setInput('solicitudesHorarioAdmin', [solicitud]);
    fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
    );

    botones.find(b => b.textContent?.includes('Aprobar'))!.click();
    botones.find(b => b.textContent?.includes('Rechazar'))!.click();

    expect(aprobarSpy).toHaveBeenCalledWith(solicitud);
    expect(rechazarSpy).toHaveBeenCalledWith(solicitud);
  });

  it('debe emitir los cambios de filtros', () => {
    const especialidadSpy = vi.spyOn(
      component.filtroEspecialidadChange,
      'emit'
    );
    const profesionalSpy = vi.spyOn(
      component.filtroProfesionalIdChange,
      'emit'
    );

    component.filtroEspecialidadChange.emit('Medicina');
    component.filtroProfesionalIdChange.emit('10');

    expect(especialidadSpy).toHaveBeenCalledWith('Medicina');
    expect(profesionalSpy).toHaveBeenCalledWith('10');
  });

  it('debe mostrar el aviso cuando el profesional está bloqueado', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('profesionalActualBloqueado', true);
    fixture.componentRef.setInput('profesionalActual', {
      nombre: 'Profesional Bloqueado',
      estado: 'licencia'
    });

    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Profesional Bloqueado');
    expect(texto).toContain('licencia');
  });

  it('debe renderizar la semana y emitir un clic de bloque', () => {
    const bloqueSpy = vi.spyOn(component.bloqueClick, 'emit');

    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('semanaActual', [
      {
        nombre: 'Lun',
        num: 31,
        fecha: '2026-08-31',
        esHoy: true
      }
    ]);
    fixture.componentRef.setInput('semanaLabel', 'Agosto 2026');
    fixture.componentRef.setInput('horasGrilla', ['08:00']);

    fixture.detectChanges();

    const bloque = fixture.nativeElement.querySelector(
      '.bloque-celda'
    ) as HTMLDivElement;

    expect(bloque).toBeTruthy();
    bloque.click();

    expect(bloqueSpy).toHaveBeenCalledWith({
      fecha: '2026-08-31',
      hora: '08:00'
    });
  });

  it('debe emitir navegación semanal y Hoy', () => {
    const anteriorSpy = vi.spyOn(component.anterior, 'emit');
    const siguienteSpy = vi.spyOn(component.siguiente, 'emit');
    const hoySpy = vi.spyOn(component.hoy, 'emit');

    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
    );

    botones.find(b => b.getAttribute('aria-label') === 'Semana anterior')!.click();
    botones.find(b => b.getAttribute('aria-label') === 'Semana siguiente')!.click();
    botones.find(b => b.textContent?.trim() === 'Hoy')!.click();

    expect(anteriorSpy).toHaveBeenCalledTimes(1);
    expect(siguienteSpy).toHaveBeenCalledTimes(1);
    expect(hoySpy).toHaveBeenCalledTimes(1);
  });

  it('debe emitir Nueva Cita e Imprimir Agenda', () => {
    const nuevaSpy = vi.spyOn(component.abrirNuevaCita, 'emit');
    const imprimirSpy = vi.spyOn(component.imprimir, 'emit');

    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('profesionalActualBloqueado', false);
    fixture.componentRef.setInput('puedeGestionarAgenda', true);
    fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
    );

    botones.find(b => b.textContent?.includes('Nueva cita'))!.click();
    botones.find(b => b.textContent?.includes('Imprimir'))!.click();

    expect(nuevaSpy).toHaveBeenCalledTimes(1);
    expect(imprimirSpy).toHaveBeenCalledTimes(1);
  });

  it('debe mostrar las citas del día y emitir cancelación', () => {
    const cancelarSpy = vi.spyOn(component.cancelarCita, 'emit');

    const cita = {
      id: 20,
      estudiante: 'Ana Pérez',
      especialidad: 'Psicología',
      hora: '10:00',
      estado: 'pendiente',
      urgente: false
    };

    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('diaSeleccionado', '2026-08-31');
    fixture.componentRef.setInput('citasDiaSeleccionado', [cita]);
    fixture.componentRef.setInput('puedeGestionarAgenda', true);

    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Ana Pérez');

    const cancelar = fixture.nativeElement.querySelector(
      '.detalle-acciones button'
    ) as HTMLButtonElement;

    cancelar.click();

    expect(cancelarSpy).toHaveBeenCalledWith(cita);
  });

  it('debe emitir cierre del detalle del día', () => {
    const diaSpy = vi.spyOn(component.diaSeleccionadoChange, 'emit');

    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('diaSeleccionado', '2026-08-31');
    fixture.componentRef.setInput('citasDiaSeleccionado', []);

    fixture.detectChanges();

    const cerrar = fixture.nativeElement.querySelector(
      '.detalle-cerrar'
    ) as HTMLButtonElement;

    expect(cerrar).toBeTruthy();
    cerrar.click();

    expect(diaSpy).toHaveBeenCalledWith(null);
  });

  it('read-only oculta solicitudes, Nueva Cita y cancelación', () => {
    const solicitud = {
      id: 30,
      profesional_nombre: 'Profesional Read Only',
      especialidad: 'Medicina',
      tipo: 'jornada',
      hora_inicio: '08:00',
      hora_fin: '17:00',
      fecha_solicitud: '2026-09-07T09:00:00'
    };
    const cita = {
      id: 31,
      estudiante: 'Estudiante Read Only',
      especialidad: 'Medicina',
      hora: '11:00',
      estado: 'pendiente',
      urgente: false
    };

    fixture.componentRef.setInput('puedeGestionarAgenda', false);
    fixture.componentRef.setInput('solicitudesHorarioAdmin', [solicitud]);
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('diaSeleccionado', '2026-09-07');
    fixture.componentRef.setInput('citasDiaSeleccionado', [cita]);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).not.toContain('Aprobar');
    expect(texto).not.toContain('Rechazar');
    expect(texto).not.toContain('Nueva Cita');
    expect(fixture.nativeElement.querySelector('.detalle-acciones')).toBeNull();
  });

  // Test original AGENDA-A. Se conserva su cobertura vigente (orden de las
  // tres pestañas, Semana habilitada y activa). La única parte que dejó de
  // corresponder es que Día y Mes estuvieran deshabilitados: esa afirmación
  // se retiró porque Día y Mes se habilitan en esta iteración, y queda
  // cubierta con lo contrario en el test siguiente.
  it('AGENDA-A mantiene Semana como vista inicial activa y habilitada (antes: "única vista habilitada"; Día y Mes ya no están deshabilitados)', () => {
    fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('.agenda-view-switch button') as NodeListOf<HTMLButtonElement>
    );

    expect(botones.map(b => b.textContent?.trim())).toEqual(['Día', 'Semana', 'Mes']);
    expect(botones[1].disabled).toBe(false);
    expect(botones[1].classList.contains('active')).toBe(true);
  });

  it('AGENDA-B habilita Día, Semana y Mes, con Semana como vista inicial', () => {
    expect(component.vista).toBe('semana');
    fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('.agenda-view-switch button') as NodeListOf<HTMLButtonElement>
    );

    expect(botones[0].disabled).toBe(false); // Día
    expect(botones[1].disabled).toBe(false); // Semana
    expect(botones[2].disabled).toBe(false); // Mes
    expect(botones.map(b => b.classList.contains('active'))).toEqual([false, true, false]);
    expect(botones.map(b => b.getAttribute('aria-selected'))).toEqual(['false', 'true', 'false']);
  });

  it('emite vistaChange al elegir otra vista y no re-emite la vista ya activa', () => {
    const vistaSpy = vi.spyOn(component.vistaChange, 'emit');
    fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('.agenda-view-switch button') as NodeListOf<HTMLButtonElement>
    );

    botones[1].click(); // Semana: ya activa
    expect(vistaSpy).not.toHaveBeenCalled();

    botones[0].click();
    botones[2].click();
    expect(vistaSpy.mock.calls.map(c => c[0])).toEqual(['dia', 'mes']);
  });

  it('el botón Imprimir queda deshabilitado mientras no haya un profesional seleccionado', () => {
    const imprimirSpy = vi.spyOn(component.imprimir, 'emit');
    fixture.detectChanges();

    const boton = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
    ).find(b => b.textContent?.includes('Imprimir'))!;

    expect(boton.disabled).toBe(true);
    boton.click();
    expect(imprimirSpy).not.toHaveBeenCalled();
  });

  describe('vista Día', () => {
    const dia = { nombre: 'Jue', num: 17, fecha: '2026-09-17', esHoy: false };

    beforeEach(() => {
      fixture.componentRef.setInput('filtroProfesionalId', '10');
      fixture.componentRef.setInput('vista', 'dia');
      fixture.componentRef.setInput('diaActual', dia);
      fixture.componentRef.setInput('periodoLabel', 'Jueves 17 de Septiembre 2026');
      fixture.componentRef.setInput('horasGrilla', ['08:00', '09:00']);
      // La semana sigue informada por el padre, pero la vista Día no debe usarla.
      fixture.componentRef.setInput('semanaActual', [
        { nombre: 'Lun', num: 14, fecha: '2026-09-14', esHoy: false },
        dia
      ]);
    });

    it('renderiza una sola columna con las horas de la grilla y no la semana completa', () => {
      fixture.detectChanges();

      const columnas = fixture.nativeElement.querySelectorAll('.dia-col');
      expect(columnas.length).toBe(1);
      expect(fixture.nativeElement.querySelectorAll('.bloque-celda').length).toBe(2);
      expect(fixture.nativeElement.querySelector('.agenda-week-grid')
        .classList.contains('agenda-day-grid')).toBe(true);
      expect(fixture.nativeElement.querySelector('.agenda-month')).toBeNull();
    });

    it('muestra el período informado, el título de vista y la navegación por día', () => {
      fixture.detectChanges();
      const texto = fixture.nativeElement.textContent as string;

      expect(texto).toContain('Jueves 17 de Septiembre 2026');
      expect(texto).toContain('Vista diaria');
      expect(texto).toContain('Día visible');
      expect(fixture.nativeElement.querySelector('[aria-label="Día anterior"]')).toBeTruthy();
      expect(fixture.nativeElement.querySelector('[aria-label="Día siguiente"]')).toBeTruthy();
      expect(fixture.nativeElement.querySelector('[aria-label="Semana anterior"]')).toBeNull();
    });

    it('emite el clic de un bloque con la fecha del día visible', () => {
      const bloqueSpy = vi.spyOn(component.bloqueClick, 'emit');
      fixture.detectChanges();

      (fixture.nativeElement.querySelectorAll('.bloque-celda')[1] as HTMLElement).click();

      expect(bloqueSpy).toHaveBeenCalledWith({ fecha: '2026-09-17', hora: '09:00' });
    });

    it('los indicadores cuentan solo las citas del día visible', () => {
      fixture.componentRef.setInput('citasHorario', [
        { id: 1, fecha: '2026-09-17', hora: '08:00', estado: 'pendiente', estudiante: 'Ana' },
        { id: 2, fecha: '2026-09-17', hora: '09:00', estado: 'completada', estudiante: 'Luis', urgente: true },
        { id: 3, fecha: '2026-09-17', hora: '09:00', estado: 'cancelada', estudiante: 'Eva' },
        { id: 4, fecha: '2026-09-14', hora: '08:00', estado: 'pendiente', estudiante: 'Otro día' }
      ]);
      fixture.detectChanges();

      expect(component.citasProgramadasSemana).toBe(2);
      expect(component.atencionesRealizadasSemana).toBe(1);
      expect(component.urgenciasSemana).toBe(1);
    });

    it('multicita: dos o más citas en el mismo horario aparecen TODAS en la misma celda del día', () => {
      fixture.componentRef.setInput('bloqueEstadoFn', (_f: string, h: string) => h === '08:00' ? 'sobrecupo' : 'disponible');
      fixture.componentRef.setInput('bloqueCitasFn', (_f: string, h: string) => h === '08:00'
        ? [
            { id: 1, estudiante: 'Diego Soto', sobrecupo: false, urgente: false },
            { id: 2, estudiante: 'Carlos Muñoz', sobrecupo: true, urgente: false },
            { id: 3, estudiante: 'Elena Paz', sobrecupo: true, urgente: false }
          ]
        : []);
      fixture.detectChanges();

      const celda = fixture.nativeElement.querySelectorAll('.bloque-celda')[0] as HTMLElement;
      expect(celda.classList.contains('multi-cita')).toBe(true);
      expect(celda.classList.contains('sobrecupo-bloque')).toBe(true);
      const lineas = Array.from(celda.querySelectorAll('.bloque-info')).map(e => e.textContent?.trim());
      expect(lineas).toHaveLength(3);
      expect(celda.textContent).toContain('Diego Soto');
      expect(celda.textContent).toContain('Carlos Muñoz');
      expect(celda.textContent).toContain('Elena Paz');
      expect(fixture.nativeElement.querySelectorAll('.bloque-celda')[1].classList.contains('multi-cita')).toBe(false);
    });

    it('urgencias y sobrecupos conservan su estado visual en la vista Día', () => {
      fixture.componentRef.setInput('bloqueEstadoFn', (_f: string, h: string) => h === '08:00' ? 'urgente' : 'sobrecupo');
      fixture.componentRef.setInput('bloqueCitasFn', (_f: string, h: string) => h === '08:00'
        ? [{ id: 1, estudiante: 'Ana', urgente: true }]
        : [{ id: 2, estudiante: 'Luis', sobrecupo: true }]);
      fixture.detectChanges();

      const [urgente, sobrecupo] = Array.from(fixture.nativeElement.querySelectorAll('.bloque-celda')) as HTMLElement[];
      expect(urgente.classList.contains('urgente-bloque')).toBe(true);
      expect(urgente.querySelector('.bloque-info-urgente')).toBeTruthy();
      expect(sobrecupo.classList.contains('sobrecupo-bloque')).toBe(true);
      expect(sobrecupo.querySelector('.bloque-info-sobrecupo')).toBeTruthy();
    });

    it('si el endpoint no informó el día muestra "Sin datos" y las celdas quedan neutras, nunca disponibles', () => {
      fixture.componentRef.setInput('bloqueEstadoFn', () => 'sin-datos');
      fixture.componentRef.setInput('diaResumenFn', () => ({
        citas: 0, sobrecupos: 0, urgencias: 0, multicitaHorarios: 0, disponibles: 0, estado: 'sin-datos'
      }));
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.agenda-day-sindatos')!.textContent).toContain('Sin datos');
      const celdas = Array.from(fixture.nativeElement.querySelectorAll('.bloque-celda')) as HTMLElement[];
      expect(celdas.every(c => c.classList.contains('sin-datos-bloque') && !c.classList.contains('disponible'))).toBe(true);
      expect(fixture.nativeElement.textContent).not.toContain('+ Disponible');
    });

    it('con datos de disponibilidad informados no muestra el aviso "Sin datos"', () => {
      fixture.componentRef.setInput('diaResumenFn', () => ({
        citas: 0, sobrecupos: 0, urgencias: 0, multicitaHorarios: 0, disponibles: 2, estado: 'con-cupos'
      }));
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.agenda-day-sindatos')).toBeNull();
    });

    it('solo lectura (sin agenda.gestionar): no hay Nueva cita ni cancelar en la vista Día', () => {
      fixture.componentRef.setInput('puedeGestionarAgenda', false);
      fixture.componentRef.setInput('diaSeleccionado', '2026-09-17');
      fixture.componentRef.setInput('citasDiaSeleccionado', [
        { id: 1, hora: '08:00', estudiante: 'Ana', especialidad: 'Medicina', estado: 'pendiente' }
      ]);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).not.toContain('Nueva cita');
      expect(fixture.nativeElement.querySelector('.detalle-acciones')).toBeNull();
    });

    it('con agenda.gestionar la vista Día conserva Nueva cita y cancelar', () => {
      const cancelarSpy = vi.spyOn(component.cancelarCita, 'emit');
      fixture.componentRef.setInput('puedeGestionarAgenda', true);
      fixture.componentRef.setInput('diaSeleccionado', '2026-09-17');
      fixture.componentRef.setInput('citasDiaSeleccionado', [
        { id: 1, hora: '08:00', estudiante: 'Ana', especialidad: 'Medicina', estado: 'pendiente' }
      ]);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Nueva cita');
      (fixture.nativeElement.querySelector('.detalle-acciones button') as HTMLButtonElement).click();
      expect(cancelarSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('vista Mes', () => {
    // Sep 2026: martes 1 → una celda previa (31 ago) y 30 días del mes.
    const celdas = [
      { fecha: '2026-08-31', num: 31, enMes: false, esHoy: false },
      { fecha: '2026-09-01', num: 1, enMes: true, esHoy: false },
      { fecha: '2026-09-02', num: 2, enMes: true, esHoy: true },
      { fecha: '2026-09-03', num: 3, enMes: true, esHoy: false },
      { fecha: '2026-09-04', num: 4, enMes: true, esHoy: false }
    ];

    const resumenes: Record<string, any> = {
      '2026-09-01': { citas: 1, sobrecupos: 0, urgencias: 0, multicitaHorarios: 0, disponibles: 6, estado: 'con-cupos' },
      '2026-09-02': { citas: 3, sobrecupos: 1, urgencias: 2, multicitaHorarios: 2, disponibles: 0, estado: 'sin-cupos' },
      '2026-09-03': { citas: 0, sobrecupos: 0, urgencias: 0, multicitaHorarios: 0, disponibles: 0, estado: 'cerrado' },
      '2026-09-04': { citas: 0, sobrecupos: 0, urgencias: 0, multicitaHorarios: 0, disponibles: 0, estado: 'sin-datos' }
    };

    const celdaDe = (fecha: string): HTMLButtonElement =>
      Array.from(fixture.nativeElement.querySelectorAll('.agenda-month-cell') as NodeListOf<HTMLButtonElement>)
        .find(c => c.getAttribute('aria-label')?.includes(fecha))!;

    beforeEach(() => {
      fixture.componentRef.setInput('formatearFechaFn', (f: string) => f);
      fixture.componentRef.setInput('filtroProfesionalId', '10');
      fixture.componentRef.setInput('vista', 'mes');
      fixture.componentRef.setInput('mesCeldas', celdas);
      fixture.componentRef.setInput('periodoLabel', 'Septiembre 2026');
      fixture.componentRef.setInput('diaResumenFn', (f: string) => resumenes[f]);
    });

    it('renderiza los días del mes sin la grilla horaria y con los nombres de la semana', () => {
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.semana-grilla')).toBeNull();
      expect(fixture.nativeElement.querySelectorAll('.agenda-month-cell').length).toBe(5);
      const cabeceras = Array.from(
        fixture.nativeElement.querySelectorAll('.agenda-month-weekdays span') as NodeListOf<HTMLElement>
      ).map(e => e.textContent?.trim());
      expect(cabeceras).toEqual(['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']);
      expect(fixture.nativeElement.textContent).toContain('Vista mensual');
      expect(fixture.nativeElement.querySelector('[aria-label="Mes anterior"]')).toBeTruthy();
      expect(fixture.nativeElement.querySelector('[aria-label="Mes siguiente"]')).toBeTruthy();
    });

    it('muestra citas, sobrecupos, urgencias y cupos usando el resumen entregado por el padre', () => {
      fixture.detectChanges();

      const uno = celdaDe('2026-09-01').textContent as string;
      expect(uno).toContain('1 cita');
      expect(uno).not.toContain('1 citas');
      expect(uno).toContain('6 disponibles');

      const dos = celdaDe('2026-09-02').textContent as string;
      expect(dos).toContain('3 citas');
      expect(dos).toContain('1 sobrecupo');
      expect(dos).toContain('2 urgencias');
      expect(dos).toContain('Sin cupos');
      expect(celdaDe('2026-09-02').classList.contains('hoy')).toBe(true);

      expect(celdaDe('2026-09-03').textContent).toContain('Centro cerrado');
    });

    it('un día sin datos de disponibilidad se muestra como "Sin datos", nunca como disponible', () => {
      fixture.detectChanges();

      const texto = celdaDe('2026-09-04').textContent as string;
      expect(texto).toContain('Sin datos');
      expect(texto).not.toContain('disponible');
    });

    it('los días de relleno de otro mes están deshabilitados y no emiten nada', () => {
      const seleccionSpy = vi.spyOn(component.diaSeleccionadoChange, 'emit');
      fixture.detectChanges();

      const relleno = fixture.nativeElement.querySelector('.agenda-month-cell.fuera-mes') as HTMLButtonElement;
      expect(relleno.disabled).toBe(true);
      relleno.click();
      component.onSeleccionarDiaMes(celdas[0]);

      expect(seleccionSpy).not.toHaveBeenCalled();
      expect(relleno.textContent).not.toContain('disponible');
    });

    it('un clic selecciona el día y un doble clic abre la vista Día', () => {
      const seleccionSpy = vi.spyOn(component.diaSeleccionadoChange, 'emit');
      const abrirSpy = vi.spyOn(component.abrirDia, 'emit');
      fixture.detectChanges();

      const celda = celdaDe('2026-09-03');
      celda.click();
      celda.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));

      expect(seleccionSpy).toHaveBeenCalledWith('2026-09-03');
      expect(abrirSpy).toHaveBeenCalledWith('2026-09-03');
    });

    it('marca el día seleccionado y ofrece "Ver agenda del día" solo en la vista Mes', () => {
      const abrirSpy = vi.spyOn(component.abrirDia, 'emit');
      fixture.componentRef.setInput('diaSeleccionado', '2026-09-01');
      fixture.detectChanges();

      expect(celdaDe('2026-09-01').classList.contains('seleccionado')).toBe(true);

      const boton = Array.from(
        fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
      ).find(b => b.textContent?.includes('Ver agenda del día'))!;
      boton.click();
      expect(abrirSpy).toHaveBeenCalledWith('2026-09-01');

      fixture.componentRef.setInput('vista', 'semana');
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).not.toContain('Ver agenda del día');
    });

    it('multicita: el día muestra cuántos horarios tienen varias citas y no lo oculta detrás del conteo total', () => {
      fixture.detectChanges();

      const dos = celdaDe('2026-09-02');
      expect(dos.querySelector('.agenda-month-chip.multicita')!.textContent).toContain('2 horarios con varias citas');
      // un día con citas pero sin horarios repetidos no muestra el indicador
      expect(celdaDe('2026-09-01').querySelector('.agenda-month-chip.multicita')).toBeNull();

      fixture.componentRef.setInput('diaResumenFn', (f: string) => f === '2026-09-01'
        ? { ...resumenes[f], citas: 2, multicitaHorarios: 1 }
        : resumenes[f]);
      fixture.detectChanges();
      expect(celdaDe('2026-09-01').querySelector('.agenda-month-chip.multicita')!.textContent)
        .toContain('1 horario con varias citas');
    });

    it('urgencias y sobrecupos se muestran por separado del total de citas', () => {
      fixture.detectChanges();

      const dos = celdaDe('2026-09-02');
      expect(dos.querySelector('.agenda-month-chip.sobrecupo')!.textContent).toContain('1 sobrecupo');
      expect(dos.querySelector('.agenda-month-chip.urgencia')!.textContent).toContain('2 urgencias');
      expect(dos.querySelector('.agenda-month-chip.reservada')!.textContent).toContain('3 citas');
    });

    it('ninguna acción de gestión sale desde el Mes: clic, doble clic y "Ver agenda del día" no emiten bloqueClick, abrirNuevaCita ni cancelarCita', () => {
      fixture.componentRef.setInput('puedeGestionarAgenda', true);
      fixture.componentRef.setInput('diaSeleccionado', '2026-09-02');
      const bloqueSpy = vi.spyOn(component.bloqueClick, 'emit');
      const nuevaSpy = vi.spyOn(component.abrirNuevaCita, 'emit');
      const cancelarSpy = vi.spyOn(component.cancelarCita, 'emit');
      fixture.detectChanges();

      const celda = celdaDe('2026-09-02');
      celda.click();
      celda.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
      (Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>)
        .find(b => b.textContent?.includes('Ver agenda del día')))!.click();

      expect(bloqueSpy).not.toHaveBeenCalled();
      expect(nuevaSpy).not.toHaveBeenCalled();
      expect(cancelarSpy).not.toHaveBeenCalled();
    });

    it('solo lectura (sin agenda.gestionar): en el Mes no hay Nueva cita ni cancelar', () => {
      fixture.componentRef.setInput('puedeGestionarAgenda', false);
      fixture.componentRef.setInput('diaSeleccionado', '2026-09-02');
      fixture.componentRef.setInput('citasDiaSeleccionado', [
        { id: 1, hora: '09:00', estudiante: 'Ana', especialidad: 'Medicina', estado: 'pendiente' }
      ]);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).not.toContain('Nueva cita');
      expect(fixture.nativeElement.querySelector('.detalle-acciones')).toBeNull();
      // la consulta sí está disponible
      expect(celdaDe('2026-09-02')).toBeTruthy();
    });

    it('con agenda.gestionar el Mes conserva el botón Nueva cita del encabezado', () => {
      fixture.componentRef.setInput('puedeGestionarAgenda', true);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Nueva cita');
    });

    it('los indicadores cuentan solo las citas de días del mes visible', () => {
      fixture.componentRef.setInput('citasHorario', [
        { id: 1, fecha: '2026-09-02', hora: '08:00', estado: 'pendiente', sobrecupo: true },
        { id: 2, fecha: '2026-09-03', hora: '08:00', estado: 'completada' },
        { id: 3, fecha: '2026-08-31', hora: '08:00', estado: 'pendiente' },
        { id: 4, fecha: '2026-09-20', hora: '08:00', estado: 'pendiente' }
      ]);
      fixture.componentRef.setInput('diasCerrados', [{ fecha: '2026-09-03' }, { fecha: '2026-08-31' }]);
      fixture.detectChanges();

      // 08-31 es relleno del mes anterior; 09-20 no está entre las celdas del fixture.
      expect(component.citasProgramadasSemana).toBe(2);
      expect(component.atencionesRealizadasSemana).toBe(1);
      expect(component.sobrecuposSemana).toBe(1);
      expect(component.bloqueosSemana).toBe(1);
      expect(fixture.nativeElement.textContent).toContain('Mes visible');
    });
  });

  it('la vista Semana sigue mostrando los siete días recibidos', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('semanaLabel', 'Semana 14 – 20 Septiembre 2026');
    fixture.componentRef.setInput('horasGrilla', ['08:00']);
    fixture.componentRef.setInput('semanaActual', Array.from({ length: 7 }, (_, i) => ({
      nombre: ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'][i],
      num: 14 + i,
      fecha: `2026-09-${14 + i}`,
      esHoy: false
    })));

    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('.dia-col').length).toBe(7);
    expect(fixture.nativeElement.textContent).toContain('Semana 14 – 20 Septiembre 2026');
    expect(fixture.nativeElement.textContent).toContain('Vista semanal');
    expect(fixture.nativeElement.textContent).toContain('Semana visible');
    expect(fixture.nativeElement.querySelector('.agenda-week-grid')
      .classList.contains('agenda-day-grid')).toBe(false);
  });

  it('A.4.7A: el bloque ocupado con sobrecupo disponible recibe la clase derivada y su ícono de affordance, sin dejar de ser "ocupado"', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('bloqueEstadoFn', () => 'ocupado');
    fixture.componentRef.setInput('bloqueSobrecupoDisponibleFn', () => true);
    fixture.componentRef.setInput('horasGrilla', ['08:00']);
    fixture.componentRef.setInput('semanaActual', [{ fecha: '2026-09-07', nombre: 'Lun', num: 7, esHoy: false }]);
    fixture.detectChanges();

    const celda = fixture.nativeElement.querySelector('.bloque-celda') as HTMLElement;
    expect(celda.classList.contains('ocupado')).toBe(true);
    expect(celda.classList.contains('ocupado-sobrecupo-disponible')).toBe(true);
    expect(celda.querySelector('.agenda-sobrecupo-affordance')).toBeTruthy();
  });

  it('A.4.7A: un bloque ocupado SIN sobrecupo disponible no recibe la clase derivada ni el ícono', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('bloqueEstadoFn', () => 'ocupado');
    fixture.componentRef.setInput('bloqueSobrecupoDisponibleFn', () => false);
    fixture.componentRef.setInput('horasGrilla', ['08:00']);
    fixture.componentRef.setInput('semanaActual', [{ fecha: '2026-09-07', nombre: 'Lun', num: 7, esHoy: false }]);
    fixture.detectChanges();

    const celda = fixture.nativeElement.querySelector('.bloque-celda') as HTMLElement;
    expect(celda.classList.contains('ocupado')).toBe(true);
    expect(celda.classList.contains('ocupado-sobrecupo-disponible')).toBe(false);
    expect(celda.querySelector('.agenda-sobrecupo-affordance')).toBeFalsy();
  });

  it('A.4.7A.1 — un bloque con cita normal + sobrecupo en el mismo slot renderiza AMBAS en la misma bloque-celda', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('bloqueEstadoFn', () => 'sobrecupo');
    fixture.componentRef.setInput('bloqueSobrecupoDisponibleFn', () => false);
    fixture.componentRef.setInput('horasGrilla', ['08:00']);
    fixture.componentRef.setInput('semanaActual', [{ fecha: '2026-09-07', nombre: 'Lun', num: 7, esHoy: false }]);
    // El orden determinista (normal antes de sobrecupo) es responsabilidad
    // de buscarCitasEnBloque()/getBloqueCitas() en dashboard-admin.ts; acá
    // el componente solo debe iterar fielmente lo que bloqueCitasFn() le
    // entregue — se le pasa ya en el orden esperado, como lo entregaría el
    // padre real.
    fixture.componentRef.setInput('bloqueCitasFn', () => [
      { id: 1, estudiante: 'Diego Soto', sobrecupo: false, urgente: false },
      { id: 2, estudiante: 'Carlos Muñoz', sobrecupo: true, urgente: false }
    ]);
    fixture.detectChanges();

    const celdas = fixture.nativeElement.querySelectorAll('.bloque-celda');
    expect(celdas.length).toBe(1); // una sola celda para las 08:00 — no se duplica la hora
    const celda = celdas[0] as HTMLElement;

    expect(celda.classList.contains('multi-cita')).toBe(true);

    const lineasCita = celda.querySelectorAll('.bloque-info');
    expect(lineasCita.length).toBe(2); // exactamente dos elementos de cita, no más

    expect(celda.textContent).toContain('Diego Soto');
    expect(celda.textContent).toContain('Carlos Muñoz');
    expect(celda.textContent).toContain('(Sobrecupo)');

    // La marca "(Sobrecupo)" pertenece a la línea de Carlos, no a la de Diego.
    expect(lineasCita[0].textContent).toContain('Diego Soto');
    expect(lineasCita[0].textContent).not.toContain('Sobrecupo');
    expect(lineasCita[1].textContent).toContain('Carlos Muñoz');
    expect(lineasCita[1].textContent).toContain('Sobrecupo');
  });

  it('A.4.7A.1 — un bloque con una sola cita NO recibe la clase multi-cita', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('bloqueEstadoFn', () => 'ocupado');
    fixture.componentRef.setInput('bloqueSobrecupoDisponibleFn', () => false);
    fixture.componentRef.setInput('horasGrilla', ['08:00']);
    fixture.componentRef.setInput('semanaActual', [{ fecha: '2026-09-07', nombre: 'Lun', num: 7, esHoy: false }]);
    fixture.componentRef.setInput('bloqueCitasFn', () => [
      { id: 1, estudiante: 'Diego Soto', sobrecupo: false, urgente: false }
    ]);
    fixture.detectChanges();

    const celda = fixture.nativeElement.querySelector('.bloque-celda') as HTMLElement;
    expect(celda.classList.contains('multi-cita')).toBe(false);
    expect(celda.querySelectorAll('.bloque-info').length).toBe(1);
    expect(celda.textContent).toContain('Diego Soto');
    expect(celda.textContent).not.toContain('Sobrecupo');
  });

  it('A.4.7A v2: bloqueTitulo condiciona colación/fuera de jornada a bloqueSobrecupoDisponibleFn (no promete una acción sin permiso)', () => {
    fixture.componentRef.setInput('bloqueSobrecupoDisponibleFn', (_f: string, h: string) => h === '08:00');
    fixture.detectChanges();

    component.bloqueEstadoFn = () => 'ocupado';
    expect(component.bloqueTitulo('2026-09-07', '08:00')).toBe('Horario ocupado — clic para solicitar sobrecupo');

    component.bloqueEstadoFn = () => 'sin-datos';
    expect(component.bloqueTitulo('2026-09-07', '08:00')).toBe('Disponibilidad aún no disponible');

    component.bloqueEstadoFn = () => 'cerrado-centro';
    expect(component.bloqueTitulo('2026-09-07', '08:00')).toBe('El centro no atiende este día');

    // Con capacidad de sobrecupo (hora 08:00, según el mock de arriba):
    // el título SÍ promete la acción.
    component.bloqueEstadoFn = () => 'fuera-horario';
    expect(component.bloqueTitulo('2026-09-07', '08:00')).toBe('Fuera del horario habitual — clic para solicitar sobrecupo');

    component.bloqueEstadoFn = () => 'colacion';
    expect(component.bloqueTitulo('2026-09-07', '08:00')).toBe('Hora de colación — clic para solicitar sobrecupo');

    // Sin capacidad de sobrecupo (otra hora, bloqueSobrecupoDisponibleFn
    // devuelve false): el título describe el bloqueo, pero NO promete una
    // acción que clickBloque() ya no permitiría ejecutar.
    component.bloqueEstadoFn = () => 'fuera-horario';
    expect(component.bloqueTitulo('2026-09-07', '09:00')).toBe('Fuera del horario habitual del profesional');

    component.bloqueEstadoFn = () => 'colacion';
    expect(component.bloqueTitulo('2026-09-07', '09:00')).toBe('Hora de colación del profesional');

    component.bloqueEstadoFn = () => 'disponible';
    expect(component.bloqueTitulo('2026-09-07', '08:00')).toBe('');
  });

  it('AGENDA-A calcula KPIs semanales solo con datos operativos reales', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('semanaActual', [
      { fecha: '2026-09-07' },
      { fecha: '2026-09-08' },
      { fecha: '2026-09-09' },
      { fecha: '2026-09-10' },
      { fecha: '2026-09-11' },
      { fecha: '2026-09-12' },
      { fecha: '2026-09-13' }
    ]);
    fixture.componentRef.setInput('citasHorario', [
      { fecha: '2026-09-07', estado: 'pendiente', urgente: false, sobrecupo: false },
      { fecha: '2026-09-08', estado: 'completada', urgente: false, sobrecupo: false },
      { fecha: '2026-09-09', estado: 'pendiente', urgente: true, sobrecupo: false },
      { fecha: '2026-09-10', estado: 'pendiente', urgente: false, sobrecupo: true },
      { fecha: '2026-09-11', estado: 'cancelada', urgente: true, sobrecupo: true },
      { fecha: '2026-09-12', estado: 'inasistencia', urgente: false, sobrecupo: false },
      { fecha: '2026-09-20', estado: 'completada', urgente: true, sobrecupo: true }
    ]);
    fixture.componentRef.setInput('diasCerrados', [
      { fecha: '2026-09-10' },
      { fecha: '2026-09-10' },
      { fecha: '2026-09-25' }
    ]);

    fixture.detectChanges();

    expect(component.citasProgramadasSemana).toBe(4);
    expect(component.atencionesRealizadasSemana).toBe(1);
    expect(component.urgenciasSemana).toBe(1);
    expect(component.sobrecuposSemana).toBe(1);
    expect(component.bloqueosSemana).toBe(1);
  });

  it('AGENDA-A no inventa KPIs antes de seleccionar profesional', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '');
    fixture.componentRef.setInput('citasHorario', [
      { fecha: '2026-09-07', estado: 'completada' }
    ]);
    fixture.detectChanges();

    expect(component.citasProgramadasSemana).toBeNull();
    expect(component.atencionesRealizadasSemana).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Selecciona un profesional');
  });

  it('read-only bloquea handlers de mutación aunque se invoquen directamente', () => {
    const solicitud = { id: 40 };
    const cita = { id: 41, estado: 'pendiente' };
    const aprobarSpy = vi.spyOn(component.aprobarSolicitud, 'emit');
    const rechazarSpy = vi.spyOn(component.rechazarSolicitud, 'emit');
    const nuevaSpy = vi.spyOn(component.abrirNuevaCita, 'emit');
    const cancelarSpy = vi.spyOn(component.cancelarCita, 'emit');

    component.puedeGestionarAgenda = false;
    component.onAprobarSolicitud(solicitud);
    component.onRechazarSolicitud(solicitud);
    component.onAbrirNuevaCita();
    component.onCancelarCita(cita);

    expect(aprobarSpy).not.toHaveBeenCalled();
    expect(rechazarSpy).not.toHaveBeenCalled();
    expect(nuevaSpy).not.toHaveBeenCalled();
    expect(cancelarSpy).not.toHaveBeenCalled();
  });
  it('A.2B usa sin-datos como fallback seguro cuando no existe fuente de disponibilidad', () => {
    const aislado = new AdminHorarioComponent();
    expect(aislado.bloqueEstadoFn('2026-09-07', '08:00')).toBe('sin-datos');
  });

  it('A.2B representa sin-datos de forma neutra y no lo etiqueta como disponible', () => {
    fixture.componentRef.setInput('filtroProfesionalId', '10');
    fixture.componentRef.setInput('semanaActual', [
      { nombre: 'Lun', num: 7, fecha: '2026-09-07', esHoy: false }
    ]);
    fixture.componentRef.setInput('horasGrilla', ['08:00']);
    fixture.componentRef.setInput('bloqueEstadoFn', () => 'sin-datos');

    fixture.detectChanges();

    const bloque = fixture.nativeElement.querySelector('.bloque-celda') as HTMLDivElement;
    expect(bloque.classList.contains('sin-datos-bloque')).toBe(true);
    expect(bloque.classList.contains('disponible')).toBe(false);
    expect(bloque.getAttribute('aria-disabled')).toBe('true');
    expect(bloque.getAttribute('title')).toContain('Disponibilidad');
    expect(bloque.textContent).not.toContain('+ Disponible');
  });

});
