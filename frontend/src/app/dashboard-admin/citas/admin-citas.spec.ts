import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { vi } from 'vitest';

import { AdminCitasComponent } from './admin-citas';
import { indiceColorAvatar } from './admin-citas.utils';

/**
 * Cada respuesta HTTP se refleja en la vista recién cuando Angular corre un
 * ciclo de detección de cambios (zone.js lo hace solo en la app real; en un
 * test síncrono como este hay que pedirlo explícitamente). Por eso se llama
 * fixture.detectChanges() después de CADA flush, no solo al final.
 */
function flushInit(
  fixture: ComponentFixture<AdminCitasComponent>,
  httpMock: HttpTestingController,
  citas: any[] = [],
  profesionales: any[] = [],
): void {
  httpMock.expectOne((req) => req.url.includes('/agenda/citas')).flush(citas);
  fixture.detectChanges();
  httpMock.expectOne((req) => req.url.includes('/agenda/profesionales')).flush(profesionales);
  fixture.detectChanges();
}

describe('AdminCitasComponent', () => {
  let component: AdminCitasComponent;
  let fixture: ComponentFixture<AdminCitasComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminCitasComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminCitasComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    flushInit(fixture, httpMock);
    expect(component).toBeTruthy();
  });

  it('SA-10.2C usa lectura operacional /agenda/citas y no /admin/historial', () => {
    const req = httpMock.expectOne((r) => r.url.includes('/agenda/citas'));
    expect(req.request.url).not.toContain('/admin/historial');
    req.flush([]);
    fixture.detectChanges();
    httpMock.expectOne((r) => r.url.includes('/agenda/profesionales')).flush([]);
  });

  it('debe cargar y renderizar el listado de citas', () => {
    flushInit(fixture, httpMock, [
      {
        id: 1,
        estudiante: 'Ana Soto',
        rut: '11.111.111-1',
        especialidad: 'Psicología',
        profesional: 'Dr. Pérez',
        fecha: new Date().toISOString().slice(0, 10),
        hora: '10:00',
        estado: 'pendiente',
        urgente: false,
        iniciales: 'AS',
      },
    ]);

    expect(component.citasAdmin.length).toBe(1);
    const filas = fixture.nativeElement.querySelectorAll('tbody tr');
    expect(filas.length).toBe(1);
  });

  it('debe emitir cancelarCita con la cita correcta desde el menú de la fila', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    const cita = {
      id: 5,
      estudiante: 'Bruno Ríos',
      estado: 'pendiente',
      urgente: false,
      fecha: hoy,
      hora: '09:00',
    };
    flushInit(fixture, httpMock, [cita]);
    fixture.componentRef.setInput('puedeGestionarAgenda', true);
    fixture.detectChanges();

    let citaEmitida: any = null;
    component.cancelarCita.subscribe((c: any) => (citaEmitida = c));

    const btnMenu: HTMLButtonElement = fixture.nativeElement.querySelector('.citas-btn-menu');
    btnMenu.click();
    fixture.detectChanges();

    const btnCancelar: HTMLButtonElement = fixture.nativeElement.querySelector(
      '.citas-menu-item[data-accion="cancelar"]',
    );
    btnCancelar.click();

    expect(citaEmitida).toEqual(cita);
  });

  it('debe emitir marcarPrioridad con la cita y el flag urgente correctos desde el menú', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    const cita = {
      id: 7,
      estudiante: 'Carla Díaz',
      estado: 'pendiente',
      urgente: false,
      fecha: hoy,
      hora: '09:00',
    };
    flushInit(fixture, httpMock, [cita]);
    fixture.componentRef.setInput('puedeGestionarAgenda', true);
    fixture.detectChanges();

    let payload: any = null;
    component.marcarPrioridad.subscribe((p: any) => (payload = p));

    fixture.nativeElement.querySelector('.citas-btn-menu').click();
    fixture.detectChanges();
    fixture.nativeElement.querySelector('.citas-menu-item[data-accion="urgente"]').click();

    expect(payload).toEqual({ cita, urgente: true });
  });

  it('limpiarFiltrosCitas resetea los filtros y vuelve a cargar', () => {
    flushInit(fixture, httpMock);

    component.citasFiltroEstudiante = 'algo';
    component.citasFiltroEstado = 'pendiente';
    component.citasFiltroPrioridad = 'urgente';

    component.limpiarFiltrosCitas();

    expect(component.citasFiltroEstudiante).toBe('');
    expect(component.citasFiltroEstado).toBe('');
    expect(component.citasFiltroPrioridad).toBe('');
    expect(component.citasFiltroRango).toBe('ultimos30');

    httpMock.expectOne((r) => r.url.includes('/agenda/citas')).flush([]);
  });

  it('read-only oculta las acciones de mutación', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    flushInit(fixture, httpMock, [
      {
        id: 9,
        estudiante: 'Diego Mora',
        estado: 'pendiente',
        urgente: false,
        fecha: hoy,
        hora: '09:00',
      },
    ]);
    fixture.componentRef.setInput('puedeGestionarAgenda', false);
    fixture.detectChanges();

    // "Agendar cita" (acceso rápido lateral) requiere agenda.gestionar.
    expect(fixture.nativeElement.querySelector('.citas-accion.tono-mint')).toBeNull();

    // El botón "Acciones" sigue visible: "Ver detalles" es de solo lectura y
    // no requiere agenda.gestionar. Lo que debe faltar son las opciones de
    // mutación dentro del menú.
    const btnAcciones: HTMLButtonElement = fixture.nativeElement.querySelector('.citas-btn-menu');
    expect(btnAcciones).not.toBeNull();

    btnAcciones.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.citas-menu-item[data-accion="detalle"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.citas-menu-item[data-accion="urgente"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('.citas-menu-item[data-accion="cancelar"]')).toBeNull();
  });

  it('read-only bloquea handlers aunque se invoquen directamente', () => {
    flushInit(fixture, httpMock);
    const cita = { id: 10, estudiante: 'Elena Ruiz', estado: 'pendiente', urgente: false };
    const cancelarSpy = vi.spyOn(component.cancelarCita, 'emit');
    const prioridadSpy = vi.spyOn(component.marcarPrioridad, 'emit');
    const horarioSpy = vi.spyOn(component.irAHorario, 'emit');

    component.puedeGestionarAgenda = false;
    component.onCancelarCita(cita);
    component.onMarcarPrioridad(cita, true);
    component.onIrAHorario();

    expect(cancelarSpy).not.toHaveBeenCalled();
    expect(prioridadSpy).not.toHaveBeenCalled();
    expect(horarioSpy).not.toHaveBeenCalled();
  });

  it('las pestañas cuentan las citas del período por estado', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    flushInit(fixture, httpMock, [
      { id: 1, estudiante: 'A', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' },
      { id: 2, estudiante: 'B', estado: 'pendiente', urgente: false, fecha: hoy, hora: '10:00' },
      { id: 3, estudiante: 'C', estado: 'completada', urgente: false, fecha: hoy, hora: '11:00' },
    ]);

    expect(component.contar('')).toBe(3);
    expect(component.contar('pendiente')).toBe(2);
    expect(component.contar('completada')).toBe(1);
    expect(component.contar('cancelada')).toBe(0);
  });

  it('seleccionar una pestaña filtra el listado por ese estado', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    flushInit(fixture, httpMock, [
      { id: 1, estudiante: 'A', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' },
      { id: 2, estudiante: 'B', estado: 'completada', urgente: false, fecha: hoy, hora: '10:00' },
    ]);

    component.seleccionarEstado('completada');
    fixture.detectChanges();

    expect(component.citasFiltradas.length).toBe(1);
    expect(component.citasFiltradas[0].id).toBe(2);
  });

  it('la búsqueda filtra localmente por estudiante/RUT/profesional sin pedir nada nuevo al servidor', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    flushInit(fixture, httpMock, [
      { id: 1, estudiante: 'Ana Soto', rut: '11.111.111-1', profesional: 'Dr. Pérez', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' },
      { id: 2, estudiante: 'Bruno Ríos', rut: '22.222.222-2', profesional: 'Dra. Rojas', estado: 'pendiente', urgente: false, fecha: hoy, hora: '10:00' },
    ]);

    component.actualizarBusqueda('bruno');
    fixture.detectChanges();

    expect(component.citasFiltradas.length).toBe(1);
    expect(component.citasFiltradas[0].id).toBe(2);
    // Ninguna petición nueva: el filtro de búsqueda es local.
    httpMock.expectNone((r) => r.url.includes('/agenda/citas') || r.url.includes('/agenda/profesionales'));
  });

  it('el filtro de tipo de servicio filtra localmente sin pedir nada nuevo al servidor', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    flushInit(fixture, httpMock, [
      { id: 1, estudiante: 'A', especialidad: 'Odontología', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' },
      { id: 2, estudiante: 'B', especialidad: 'Nutrición', estado: 'pendiente', urgente: false, fecha: hoy, hora: '10:00' },
    ]);

    component.actualizarServicio('Nutrición');
    fixture.detectChanges();

    expect(component.citasFiltradas.length).toBe(1);
    expect(component.citasFiltradas[0].id).toBe(2);
    httpMock.expectNone((r) => r.url.includes('/agenda/citas') || r.url.includes('/agenda/profesionales'));
  });

  it('el KPI de citas totales no muestra variación cuando no hay período previo (rango "todas")', () => {
    flushInit(fixture, httpMock, [
      {
        id: 1,
        estudiante: 'A',
        estado: 'pendiente',
        urgente: false,
        fecha: '2020-01-01',
        hora: '09:00',
      },
    ]);
    component.cambiarRango('todas');
    httpMock
      .expectOne((r) => r.url.includes('/agenda/citas'))
      .flush([
        {
          id: 1,
          estudiante: 'A',
          estado: 'pendiente',
          urgente: false,
          fecha: '2020-01-01',
          hora: '09:00',
        },
      ]);
    fixture.detectChanges();

    const kpiTotal = component.kpis.find((k) => k.clave === 'total');
    expect(kpiTotal?.delta).toBeNull();
  });

  it('no inventa un porcentaje cuando el período previo no tuvo citas', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    // 60 días atrás cae fuera de la ventana previa de "últimos 30 días" (que
    // cubre los 30 días anteriores al período actual): la previa queda vacía.
    const lejos = new Date();
    lejos.setDate(lejos.getDate() - 60);
    flushInit(fixture, httpMock, [
      { id: 1, estudiante: 'A', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' },
    ]);

    const kpiTotal = component.kpis.find((k) => k.clave === 'total');
    expect(kpiTotal?.delta).toBeNull();
    expect(kpiTotal?.nota).toBe('Sin citas en el período anterior');
  });

  it('alternarSoloUrgentes filtra solo las citas urgentes', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    flushInit(fixture, httpMock, [
      { id: 1, estudiante: 'A', estado: 'pendiente', urgente: true, fecha: hoy, hora: '09:00' },
      { id: 2, estudiante: 'B', estado: 'pendiente', urgente: false, fecha: hoy, hora: '10:00' },
    ]);

    component.alternarSoloUrgentes();
    fixture.detectChanges();

    expect(component.citasFiltradas.length).toBe(1);
    expect(component.citasFiltradas[0].urgente).toBe(true);
  });

  it('la columna N.º numera las filas según su posición real en el listado filtrado', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    const citas = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      estudiante: `Estudiante ${i + 1}`,
      estado: 'pendiente',
      urgente: false,
      fecha: hoy,
      hora: '09:00',
    }));
    flushInit(fixture, httpMock, citas);

    // Página 1 (renderizada): números 1..8 (porPagina = 8).
    const celdas: HTMLElement[] = Array.from(fixture.nativeElement.querySelectorAll('td.col-num'));
    expect(celdas.map((td) => td.textContent?.trim())).toEqual(['1', '2', '3', '4', '5', '6', '7', '8']);

    // Página 2: numeroFila() debe continuar en 9, 10 — no reiniciar en 1.
    component.irAPagina(2);
    fixture.detectChanges();
    expect(component.pagCitas).toBe(2);
    expect(component.citasPaginadas.map((c: any) => c.id)).toEqual([9, 10]);
    expect(component.numeroFila(0)).toBe(9);
    expect(component.numeroFila(1)).toBe(10);
  });

  it('"Ver detalles" del menú "Acciones" emite verDetalle incluso en modo solo lectura', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    const cita = { id: 1, estudiante: 'A', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' };
    flushInit(fixture, httpMock, [cita]);
    fixture.componentRef.setInput('puedeGestionarAgenda', false);
    fixture.detectChanges();

    let citaEmitida: any = null;
    component.verDetalle.subscribe((c: any) => (citaEmitida = c));

    fixture.nativeElement.querySelector('.citas-btn-menu').click();
    fixture.detectChanges();
    fixture.nativeElement.querySelector('.citas-menu-item[data-accion="detalle"]').click();

    expect(citaEmitida).toBe(cita);
  });

  it('el menú se cierra si la fila deja de estar en la página visible', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    const cita = {
      id: 1,
      estudiante: 'A',
      estado: 'pendiente',
      urgente: false,
      fecha: hoy,
      hora: '09:00',
    };
    flushInit(fixture, httpMock, [cita]);
    fixture.componentRef.setInput('puedeGestionarAgenda', true);
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.citas-btn-menu').click();
    fixture.detectChanges();
    expect(component.menuCita).toBe(cita);

    // Filtrar por un estado que excluye a la cita saca la fila de la página
    // visible: el menú, que apuntaba a esa fila, debe cerrarse.
    component.seleccionarEstado('completada');
    fixture.detectChanges();

    expect(component.menuCita).toBeNull();
  });

  it('no recalcula en cada ciclo de detección de cambios: una mutación directa sin pasar por un método no se refleja sola', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    flushInit(fixture, httpMock, [
      { id: 1, estudiante: 'A', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' },
    ]);

    expect(component.citasFiltradas.length).toBe(1);

    // Mutación directa del arreglo, sin pasar por ningún método del
    // componente (equivalente a lo que antes "de rebote" capturaba
    // ngDoCheck en cualquier ciclo posterior). Varios ciclos de detección
    // de cambios NO deben reflejarla, porque ya no hay recálculo automático.
    component.citasAdmin.push({
      id: 2,
      estudiante: 'B',
      estado: 'pendiente',
      urgente: false,
      fecha: hoy,
      hora: '10:00',
    });
    fixture.detectChanges();
    fixture.detectChanges();
    fixture.detectChanges();

    expect(component.citasFiltradas.length).toBe(1);

    // Al llegar la señal explícita (citasVersion, la misma vía que usa el
    // shell tras cancelar/marcar urgente), sí se recalcula. El primer
    // setInput establece el valor inicial (equivalente a como queda ligado
    // en la plantilla real desde la creación); el segundo es el cambio real.
    fixture.componentRef.setInput('citasVersion', 0);
    fixture.detectChanges();
    fixture.componentRef.setInput('citasVersion', 1);
    fixture.detectChanges();

    expect(component.citasFiltradas.length).toBe(2);
  });

  it('A: Tipo de servicio, Estado y pestañas son 100% locales — nunca disparan HTTP ni "Cargando"', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    flushInit(fixture, httpMock, [
      { id: 1, estudiante: 'A', especialidad: 'Odontología', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' },
      { id: 2, estudiante: 'B', especialidad: 'Nutrición', estado: 'completada', urgente: true, fecha: hoy, hora: '10:00' },
    ]);

    expect(component.citasCargando).toBe(false);

    // Tipo de servicio (select)
    component.actualizarServicio('Nutrición');
    fixture.detectChanges();
    expect(component.citasCargando).toBe(false);
    expect(component.citasFiltradas.map((c: any) => c.id)).toEqual([2]);

    component.actualizarServicio('');
    fixture.detectChanges();
    expect(component.citasCargando).toBe(false);

    // Estado (select "Estado" y pestañas usan el mismo método)
    component.seleccionarEstado('completada');
    fixture.detectChanges();
    expect(component.citasCargando).toBe(false);
    expect(component.citasFiltradas.map((c: any) => c.id)).toEqual([2]);

    component.seleccionarEstado('');
    fixture.detectChanges();
    expect(component.citasCargando).toBe(false);

    // "Solo urgentes"
    component.alternarSoloUrgentes();
    fixture.detectChanges();
    expect(component.citasCargando).toBe(false);
    expect(component.citasFiltradas.map((c: any) => c.id)).toEqual([2]);

    // En todo este flujo, la ÚNICA petición pendiente/realizada sigue siendo
    // la de carga inicial (ya resuelta por flushInit): ninguna acción local
    // agregó una petición nueva.
    httpMock.expectNone((r) => r.url.includes('/agenda/citas') || r.url.includes('/agenda/profesionales'));
  });

  it('A: solo "Rango de fechas" dispara una nueva consulta HTTP (con su propio "Cargando")', () => {
    flushInit(fixture, httpMock, []);
    expect(component.citasCargando).toBe(false);

    component.cambiarRango('mes');

    // A diferencia de los filtros locales, este SÍ debe mostrar "Cargando"
    // mientras espera la respuesta del servidor.
    expect(component.citasCargando).toBe(true);

    const req = httpMock.expectOne((r) => r.url.includes('/agenda/citas'));
    req.flush([]);
    fixture.detectChanges();

    expect(component.citasCargando).toBe(false);
    // No hace falta (ni se dispara) una nueva consulta de profesionales al
    // cambiar el rango: ese catálogo no depende de la ventana de fechas.
  });

  it('claseAvatar usa estudiante_id (no el nombre) para elegir el color, tal como pide la regla de negocio', () => {
    const hoy = new Date().toISOString().slice(0, 10);
    // Mismo nombre, distinto id: si claseAvatar usara el nombre, ambas
    // citas tendrían la misma clase de color pese a ser estudiantes
    // distintos con id distinto.
    flushInit(fixture, httpMock, [
      { id: 1, estudiante_id: 501, estudiante: 'María González', estado: 'pendiente', urgente: false, fecha: hoy, hora: '09:00' },
      { id: 2, estudiante_id: 999, estudiante: 'María González', estado: 'pendiente', urgente: false, fecha: hoy, hora: '10:00' },
    ]);

    const [citaA, citaB] = component.citasFiltradas;
    // No se afirma que sean distintas (podrían coincidir por azar entre 6
    // colores), pero sí que la clase depende del id: se calcula igual que
    // llamar indiceColorAvatar directamente sobre cada estudiante_id.
    expect(component.claseAvatar(citaA)).toBe('av-' + indiceColorAvatar(501));
    expect(component.claseAvatar(citaB)).toBe('av-' + indiceColorAvatar(999));
  });
});
