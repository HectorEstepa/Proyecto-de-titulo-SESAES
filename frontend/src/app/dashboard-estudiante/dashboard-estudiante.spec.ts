import { ChangeDetectorRef } from '@angular/core';
import { TestBed, ComponentFixture } from '@angular/core/testing';
import { vi } from 'vitest';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { DashboardEstudianteComponent } from './dashboard-estudiante';

/**
 * Dashboard del estudiante: Inicio (indicadores, accesos, próxima cita, recordatorios,
 * últimas atenciones, calendario y documentos recientes) y navegación entre secciones.
 */
const el_text = (e: Element): string => e.textContent ?? '';

describe('DashboardEstudianteComponent — Inicio', () => {
  let fixture: ComponentFixture<DashboardEstudianteComponent>;
  let c: DashboardEstudianteComponent;

  const render = () => {
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  };

  // El componente se pinta de nuevo solo cuando se lo marca (eventos o detectChanges propio);
  // en las pruebas que mutan su estado a mano hay que forzarlo.
  const repintar = () => fixture.debugElement.injector.get(ChangeDetectorRef).detectChanges();

  beforeEach(async () => {
    sessionStorage.clear();
    sessionStorage.setItem('usuario_id', '5');
    await TestBed.configureTestingModule({
      imports: [DashboardEstudianteComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();
    fixture = TestBed.createComponent(DashboardEstudianteComponent);
    c = fixture.componentInstance;
  });

  const doc = (id: number, estado = 'vigente', tipo = 'receta') =>
    ({ id, tipo, nombre_tipo: tipo === 'receta' ? 'Receta médica' : 'Justificativo médico', folio: `F-${id}`, estado });

  const atencion = (id: number, fechaRaw: string, estado: string, extra: object = {}) =>
    ({ id, fecha: fechaRaw, fechaRaw, hora: '10:00', especialidad: 'Nutrición', profesional: `Prof ${id}`, estado, documentos: [], ...extra });

  it('muestra el saludo, las frases y los accesos del Inicio', () => {
    const el = render();
    const texto = el.textContent ?? '';
    expect(texto).toContain('Aquí puedes gestionar tu atención de salud en SESAES.');
    expect(texto).toContain('Tu bienestar también es parte de tu vida universitaria');
    expect(texto).toContain('¿Qué necesitas hacer hoy?');
    expect(texto).toContain('Agendar una cita');
    expect(texto).toContain('Ver mis citas');
    expect(texto).toContain('Responder cuestionario');
    expect(texto).toContain('Ver documentos');
    expect(texto).toContain('Recordatorios y avisos');
    expect(texto).toContain('Documentos recientes');
    expect(texto).toContain('Tu salud importa');
  });

  it('el Inicio no muestra título en la barra superior', () => {
    const el = render();
    const titulo = el.querySelector('.topbar-title-est') as HTMLElement;
    expect(titulo.style.visibility).toBe('hidden');
    c.navegarA('atenciones');
    repintar();
    expect(titulo.style.visibility).toBe('visible');
  });

  describe('indicadores superiores', () => {
    const kpis = () => Array.from((render().querySelectorAll('.kpi-inicio-est')) as NodeListOf<HTMLElement>);

    it('son cuatro y se llaman como en el diseño', () => {
      const etiquetas = kpis().map(k => k.querySelector('small')?.textContent?.trim());
      expect(etiquetas).toEqual(['Próxima cita', 'Cuestionarios pendientes', 'Documentos disponibles', 'Atenciones realizadas']);
    });

    it('sin datos: sin cita, cero pendientes, cero documentos y cero atenciones', () => {
      const k = kpis();
      expect(k[0].textContent).toContain('Sin cita');
      expect(k[1].querySelector('strong')?.textContent?.trim()).toBe('0');
      expect(k[1].textContent).toContain('Estás al día');
      expect(k[2].querySelector('strong')?.textContent?.trim()).toBe('0');
      expect(k[3].querySelector('strong')?.textContent?.trim()).toBe('0');
    });

    it('con datos muestran la fecha de la próxima cita y los conteos reales', () => {
      c.proximasCitas = [{ id: 1, especialidad: 'Medicina General', fecha: '2026-07-20', hora: '10:30', profesional: 'Dra. Ana Martínez' }];
      c.cuestionariosPendientes = [{ profesional_id: 1 }];
      c.historialCompleto = [
        atencion(1, '2026-07-01', 'completada', { documentos: [doc(1), doc(2, 'anulado')] }),
        atencion(2, '2026-07-02', 'completada'),
        atencion(3, '2026-07-03', 'cancelada', { documentos: [doc(3)] })
      ];
      const k = kpis();
      expect(k[0].querySelector('strong')?.textContent?.trim()).toBe('20 jul 2026');
      expect(k[0].textContent).toContain('Medicina General');
      expect(k[1].querySelector('strong')?.textContent?.trim()).toBe('1');
      expect(k[1].textContent).toContain('Cuestionario por responder');
      // Solo cuentan los documentos vigentes de atenciones completadas
      expect(k[2].querySelector('strong')?.textContent?.trim()).toBe('1');
      expect(k[3].querySelector('strong')?.textContent?.trim()).toBe('2');
    });

    it('cada indicador lleva a su sección', () => {
      const k = kpis();
      k[0].click(); expect(c.seccionActiva).toBe('citas'); expect(c.citasTab).toBe('proximas');
      c.navegarA('inicio'); fixture.detectChanges();
      kpis()[1].click(); expect(c.seccionActiva).toBe('cuestionarios');
      c.navegarA('inicio'); fixture.detectChanges();
      kpis()[2].click(); expect(c.seccionActiva).toBe('atenciones');
      c.navegarA('inicio'); fixture.detectChanges();
      kpis()[3].click(); expect(c.seccionActiva).toBe('atenciones');
    });
  });

  describe('próxima cita', () => {
    it('sin citas próximas ofrece agendar', () => {
      c.proximasCitas = [];
      const el = render();
      expect(el.querySelector('.proxima-cita-est')).toBeNull();
      const texto = el.querySelector('.inicio-par-est')?.textContent ?? '';
      expect(texto).toContain('No tienes citas próximas');
      expect(el.querySelector('.inicio-par-est .resumen-card-boton-primario')?.textContent).toContain('Agendar cita');
    });

    it('con una cita muestra especialidad, profesional, fecha larga, hora y lugar', () => {
      c.infoCentro = { nombre_centro: 'SESAES UTEM', direccion: 'Av. Dieciocho 161, Santiago' };
      c.proximasCitas = [{ id: 7, especialidad: 'Medicina General', fecha: '2026-07-20', hora: '10:30', profesional: 'Dra. Ana Martínez', estado: 'pendiente' }];
      const t = render().querySelector('.proxima-cita-est')?.textContent ?? '';
      expect(t).toContain('Medicina General');
      expect(t).toContain('Confirmada');
      expect(t).toContain('Dra. Ana Martínez');
      expect(t).toContain('Lunes, 20 de julio de 2026');
      expect(t).toContain('10:30 hrs.');
      expect(t).toContain('Av. Dieciocho 161, Santiago');
    });

    it('sin dirección del centro no inventa un lugar', () => {
      c.infoCentro = { nombre_centro: 'SESAES', direccion: '' };
      c.proximasCitas = [{ id: 7, especialidad: 'Nutrición', fecha: '2026-10-05', hora: '10:00', profesional: 'Carlos Muñoz' }];
      expect(render().querySelector('.proxima-cita-datos .material-symbols-outlined:last-child')).toBeTruthy();
      expect(render().querySelector('.proxima-cita-datos')?.textContent).not.toContain('location_on');
      expect(render().querySelectorAll('.proxima-cita-datos li').length).toBe(2);
    });

    it('elige la cita más cercana aunque el backend las entregue desordenadas', () => {
      c.proximasCitas = [
        { id: 1, especialidad: 'Kinesiología', fecha: '2026-11-10', hora: '09:00', profesional: 'Tardía' },
        { id: 2, especialidad: 'Nutrición', fecha: '2026-10-20', hora: '16:00', profesional: 'Cercana' },
        { id: 3, especialidad: 'Odontología', fecha: '2026-10-20', hora: '08:00', profesional: 'Más temprano' }
      ];
      expect(c.proximaCita.id).toBe(3);
      expect(render().querySelector('.proxima-cita-est')?.textContent).toContain('Más temprano');
    });

    it('una cita recién agendada (fecha como texto) se ordena y se muestra con su fecha ISO', () => {
      c.proximasCitas = [
        { id: 1, especialidad: 'Kinesiología', fecha: '2026-11-10', hora: '09:00', profesional: 'Tardía' },
        { id: 2, especialidad: 'Nutrición', fecha: 'Martes 20 de octubre, 2026', fechaIso: '2026-10-20', hora: '10:30', profesional: 'Recién agendada' }
      ];
      expect(c.proximaCita.id).toBe(2);
      const el = render();
      expect(el.querySelector('.kpi-inicio-est strong')?.textContent?.trim()).toBe('20 oct 2026');
      expect(el.querySelector('.proxima-cita-datos')?.textContent).toContain('Martes, 20 de octubre de 2026');
    });

    it('"Reagendar cita" reagenda la próxima cita', () => {
      const cita = { id: 7, especialidad: 'Nutrición', fecha: '2026-10-05', hora: '10:00', profesional: 'Carlos Muñoz', estado: 'pendiente' };
      c.proximasCitas = [cita];
      const espia = vi.spyOn(c, 'reagendarCita').mockImplementation(() => {});
      (render().querySelector('.proxima-cita-acciones .resumen-card-boton-contorno') as HTMLButtonElement).click();
      expect(espia).toHaveBeenCalledWith(cita);
    });
  });

  describe('recordatorios y avisos', () => {
    const textos = () => Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('.recordatorio-est strong')).map(x => x.textContent?.trim());

    it('sin cita ni cuestionarios no hay recordatorios', () => {
      render();
      expect(textos()).toEqual([]);
      expect(render().textContent).toContain('No tienes recordatorios por ahora.');
    });

    it('con una cita próxima recuerda llegar antes y llevar identificación', () => {
      c.proximasCitas = [{ id: 1, fecha: '2026-10-05', hora: '10:00', especialidad: 'Nutrición', profesional: 'X' }];
      render();
      expect(textos()).toEqual(['Llega 10 minutos antes de tu cita', 'Recuerda llevar tu identificación']);
    });

    it('avisa de los cuestionarios pendientes, con singular y plural', () => {
      c.cuestionariosPendientes = [{ profesional_id: 1 }];
      render();
      expect(textos()).toEqual(['Tienes 1 cuestionario pendiente']);
      c.cuestionariosPendientes = [{ profesional_id: 1 }, { profesional_id: 2 }];
      repintar();
      expect(textos()).toEqual(['Tienes 2 cuestionarios pendientes']);
    });

    it('cada recordatorio se puede descartar', () => {
      c.cuestionariosPendientes = [{ profesional_id: 1 }];
      render();
      (fixture.nativeElement.querySelector('.recordatorio-cerrar') as HTMLButtonElement).click();
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelectorAll('.recordatorio-est').length).toBe(0);
    });
  });

  describe('últimas atenciones', () => {
    it('muestra solo las 3 más recientes, aunque el backend las entregue desordenadas', () => {
      c.historialCompleto = [
        atencion(1, '2026-01-01', 'completada', { especialidad: 'Antigua' }),
        atencion(2, '2026-09-21', 'cancelada', { especialidad: 'Kinesiología' }),
        atencion(3, '2026-07-30', 'completada', { especialidad: 'Nutrición' }),
        atencion(4, '2026-08-04', 'completada', { especialidad: 'Medicina General' })
      ];
      const filas = render().querySelectorAll('.tabla-inicio-est tbody tr');
      expect(filas.length).toBe(3);
      expect(filas[0].textContent).toContain('Kinesiología');
      expect(filas[0].textContent).toContain('21 sep 2026');
      expect(filas[0].querySelector('.estado-badge')?.classList).toContain('cancelada');
      expect(filas[2].textContent).toContain('Nutrición');
      expect(render().querySelector('.tabla-inicio-est')?.textContent).not.toContain('Antigua');
    });

    it('cada fila tiene "Ver detalle" que abre el detalle sin mostrar notas internas', () => {
      c.historialCompleto = [atencion(1, '2026-07-30', 'completada', { medicamento: 'Paracetamol', observaciones_atencion: 'NOTA INTERNA RESERVADA' })];
      (render().querySelector('.tabla-inicio-est tbody .enlace-inicio-est') as HTMLButtonElement).click();
      fixture.detectChanges();
      expect(c.detalleAtencionAbierto).toBe(true);
      const modal = fixture.nativeElement.querySelector('.modal-est')?.textContent ?? '';
      expect(modal).toContain('Paracetamol');
      expect(modal).not.toContain('NOTA INTERNA RESERVADA');
      expect(modal).not.toContain('Observaciones de la atención');
    });

    it('el detalle de una atención cancelada muestra el motivo y no el medicamento', () => {
      c.verDetalleAtencion(atencion(1, '2026-07-30', 'cancelada', { motivo_cancelacion: 'Cancelada por el estudiante' }));
      fixture.detectChanges();
      const modal = fixture.nativeElement.querySelector('.modal-est')?.textContent ?? '';
      expect(modal).toContain('Cancelada por el estudiante');
      expect(modal).not.toContain('Medicamento suministrado');
    });
  });

  describe('sobrecupo y urgencia en el dashboard del estudiante', () => {
    it('la próxima cita de sobrecupo se reconoce en el Inicio', () => {
      c.proximasCitas = [{ id: 1, especialidad: 'Medicina General', fecha: '2026-10-20', hora: '10:30', profesional: 'Dra. Ana Martínez', tipo: 'sobrecupo' }];
      const marca = render().querySelector('.proxima-cita-especialidad .tipo-cita') as HTMLElement;
      expect(marca.textContent?.trim()).toBe('Sobrecupo');
      expect(marca.classList).toContain('sobrecupo');
    });

    it('una cita normal no lleva marca en el Inicio', () => {
      c.proximasCitas = [{ id: 1, especialidad: 'Nutrición', fecha: '2026-10-20', hora: '10:30', profesional: 'Carlos Muñoz', tipo: 'normal' }];
      expect(render().querySelector('.proxima-cita-especialidad .tipo-cita')).toBeNull();
    });

    it('las últimas atenciones conservan la marca de sobrecupo y de urgencia aunque tengan documentos', () => {
      c.historialCompleto = [
        atencion(1, '2026-10-12', 'completada', { tipo: 'sobrecupo', documentos: [doc(1), doc(2, 'vigente', 'justificativo')] }),
        atencion(2, '2026-10-05', 'completada', { tipo: 'urgente', documentos: [doc(3)] })
      ];
      const marcas = Array.from(render().querySelectorAll('.tabla-inicio-est tbody .tipo-cita')).map(m => m.textContent?.trim());
      expect(marcas).toEqual(['Sobrecupo', 'Urgente']);
    });

    it('en el calendario del Inicio el día de una cita de sobrecupo queda marcado como día con cita', () => {
      const hoy = new Date();
      const iso = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`;
      c.proximasCitas = [{ id: 1, especialidad: 'Medicina General', fecha: iso, hora: '10:30', profesional: 'Dra. Ana Martínez', tipo: 'sobrecupo' }];
      const celdaHoy = c.calInicioDias.find((d: any) => d?.hoy);
      expect(celdaHoy?.conCita).toBe(true);
    });
  });

  describe('detalle de la atención: documentos y tipo', () => {
    const abrir = (h: any) => {
      c.verDetalleAtencion(h);
      fixture.detectChanges();
      return (fixture.nativeElement as HTMLElement).querySelector('.modal-est') as HTMLElement;
    };

    it('con receta y justificativo los lista juntos y no dice que falta la receta ni el medicamento', () => {
      const modal = abrir(atencion(1, '2026-10-12', 'completada', { documentos: [doc(10), doc(11, 'vigente', 'justificativo')] }));
      const texto = modal.textContent ?? '';
      expect(texto).toContain('Documentos emitidos');
      expect(texto).toContain('Receta médica · F-10');
      expect(texto).toContain('Justificativo médico · F-11');
      expect(texto).not.toContain('No se suministró medicamento');
      expect(texto).toContain('Sin medicamento suministrado en el centro.');
    });

    it('un documento anulado se indica como anulado', () => {
      const modal = abrir(atencion(1, '2026-10-12', 'completada', { documentos: [doc(10, 'anulado')] }));
      expect(modal.querySelector('.detalle-doc-est')?.textContent).toContain('(anulado)');
      expect(modal.querySelector('.detalle-doc-est')?.classList).toContain('anulado');
    });

    it('sin documentos dice "Ninguno"', () => {
      const modal = abrir(atencion(1, '2026-10-12', 'completada'));
      expect(modal.querySelector('.detalle-docs-est')?.textContent).toContain('Ninguno');
    });

    it('cada documento del detalle se puede descargar', () => {
      const espia = vi.spyOn(c, 'descargarDocumento').mockImplementation(() => {});
      const modal = abrir(atencion(1, '2026-10-12', 'completada', { documentos: [doc(10), doc(11, 'vigente', 'justificativo')] }));
      (modal.querySelectorAll('.detalle-doc-est')[1] as HTMLButtonElement).click();
      expect(espia).toHaveBeenCalledWith(expect.objectContaining({ id: 11 }));
    });

    it('un sobrecupo o una urgencia muestran su tipo de atención; una normal no', () => {
      expect(abrir(atencion(1, '2026-10-12', 'completada', { tipo: 'sobrecupo' })).textContent).toContain('Tipo de atención');
      expect(abrir(atencion(2, '2026-10-12', 'completada', { tipo: 'urgente' })).querySelector('.tipo-cita')?.textContent?.trim()).toBe('Urgente');
      expect(abrir(atencion(3, '2026-10-12', 'completada', { tipo: 'normal' })).textContent).not.toContain('Tipo de atención');
    });

    it('una atención cancelada no muestra documentos ni medicamento', () => {
      const texto = abrir(atencion(1, '2026-10-12', 'cancelada', { motivo_cancelacion: 'Cancelada por el estudiante' })).textContent ?? '';
      expect(texto).not.toContain('Documentos emitidos');
      expect(texto).not.toContain('Medicamento suministrado');
    });
  });

  describe('documentos recientes', () => {
    beforeEach(() => {
      c.historialCompleto = [
        atencion(1, '2026-07-01', 'completada', { especialidad: 'Nutrición', documentos: [doc(1)] }),
        atencion(2, '2026-08-01', 'completada', { especialidad: 'Medicina General', documentos: [doc(2, 'vigente', 'justificativo'), doc(3, 'anulado')] }),
        atencion(3, '2026-09-01', 'cancelada', { documentos: [doc(4)] }),
        atencion(4, '2026-06-01', 'completada', { documentos: [doc(5), doc(6), doc(7)] })
      ];
    });

    it('lista solo documentos vigentes de atenciones completadas, del más reciente al más antiguo', () => {
      expect(c.documentosDisponibles.map(x => x.doc.id)).toEqual([2, 1, 5, 6, 7]);
    });

    it('en el Inicio se ven como máximo 4', () => {
      expect(render().querySelectorAll('.doc-reciente-est').length).toBe(4);
      expect(render().querySelector('.doc-reciente-est')?.textContent).toContain('Justificativo médico');
      expect(render().querySelector('.doc-reciente-est')?.textContent).toContain('1 ago 2026');
    });

    it('el botón de descarga pide el PDF de ese documento', () => {
      const espia = vi.spyOn(c, 'descargarDocumento').mockImplementation(() => {});
      (render().querySelector('.doc-reciente-descarga') as HTMLButtonElement).click();
      expect(espia).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }));
    });

    it('sin documentos lo indica', () => {
      c.historialCompleto = [];
      expect(render().textContent).toContain('Aún no tienes documentos emitidos.');
    });
  });

  it('el Inicio ya no tiene la tarjeta de frase final ni las tarjetas de resumen antiguas', () => {
    const el = render();
    expect(el.querySelector('.frase-card-est')).toBeNull();
    expect(el.querySelector('.resumen-card-est')).toBeNull();
  });

  describe('menú y secciones', () => {
    it('el menú lateral tiene los accesos en el orden pedido', () => {
      const el = render();
      const items = Array.from(el.querySelectorAll('.sidebar-nav .nav-item')).map(x => x.textContent?.trim());
      expect(items).toEqual(['home Inicio', 'event_available Agendar cita', 'calendar_month Mis citas',
        'favorite Mis atenciones', 'assignment Cuestionarios', 'person Mi perfil']);
    });

    it('cada acceso activa su sección', () => {
      c.navegarA('atenciones');
      expect(c.seccionActiva).toBe('atenciones');
      expect(c.tituloSeccionEst).toBe('Mis Atenciones');
      c.navegarA('citas', 'proximas');
      expect(c.tituloSeccionEst).toBe('Mis Citas');
      c.navegarA('citas', 'solicitar');
      expect(c.tituloSeccionEst).toBe('Solicitar Nueva Cita');
      c.navegarA('cuestionarios');
      expect(c.tituloSeccionEst).toBe('Mis Cuestionarios');
    });

    it('Mis atenciones muestra la tabla con los datos del historial y queda activa en el menú', () => {
      c.historialCompleto = [atencion(1, '2026-07-20', 'completada', { documentos: [doc(1)] })];
      c.navegarA('atenciones');
      const el = render();
      expect(el.querySelector('app-estudiante-historial')).toBeTruthy();
      expect(el.querySelectorAll('app-estudiante-historial tbody tr').length).toBe(1);
      expect(el.querySelector('.sidebar-nav .nav-item.active')?.textContent).toContain('Mis atenciones');
    });

    it('Mis citas solo tiene "Próximas": sin pestañas ni historial', () => {
      c.navegarA('citas', 'proximas');
      const el = render();
      expect(el.querySelector('app-estudiante-citas-proximas')).toBeTruthy();
      expect(el.querySelector('app-estudiante-historial')).toBeNull();
      expect(el.querySelector('.tabs-ayuda')).toBeNull();
      expect(el.querySelector('.sidebar-nav .nav-item.active')?.textContent).toContain('Mis citas');
    });

  });

  describe('Mis cuestionarios', () => {
    const pendiente = (id: number, extra: object = {}) =>
      ({ profesional_id: id, profesional_nombre: `Dra. Pend ${id}`, especialidad: 'Medicina General', cita_id: id, fecha: '2026-07-30', hora: '13:15', ...extra });
    const respondido = (id: number, estado: string) =>
      ({ profesional_id: id, profesional_nombre: `Carlos Resp ${id}`, especialidad: 'Nutrición', fecha_respuesta: '2026-07-20T08:45:00', estado });
    const filas = () => Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('.fila-cuestionario-est')) as HTMLElement[];

    it('se llama "Mis Cuestionarios" y explica para qué sirve', () => {
      c.navegarA('cuestionarios');
      const el = render();
      expect(c.tituloSeccionEst).toBe('Mis Cuestionarios');
      expect(c.subtituloSeccionEst).toContain('Completa los formularios');
      expect(el.querySelector('.aviso-cuestionarios-est')?.textContent).toContain('Los cuestionarios solo aparecen cuando un profesional necesita recopilar información');
      expect(el.querySelector('.pasos-info-est')?.textContent).toContain('Confidencialidad');
    });

    it('es una lista única: primero los pendientes y después los respondidos', () => {
      c.cuestionariosPendientes = [pendiente(1), pendiente(2)];
      c.cuestionariosRespondidos = [respondido(3, 'respondido'), respondido(4, 'revisado')];
      c.navegarA('cuestionarios');
      render();
      expect(filas().map(f => f.querySelector('.estado-cuestionario-est')?.textContent?.trim()))
        .toEqual(['pendiente', 'pendiente', 'respondido', 'revisado']);
      expect(el_text(filas()[0])).toContain('Dra. Pend 1');
      expect(el_text(filas()[2])).toContain('Carlos Resp 3');
    });

    it('los indicadores cuentan pendientes y respondidos', () => {
      c.cuestionariosPendientes = [pendiente(1)];
      c.cuestionariosRespondidos = [respondido(3, 'respondido'), respondido(4, 'revisado')];
      c.navegarA('cuestionarios');
      const nums = Array.from(render().querySelectorAll('.cuestionarios-kpis-est strong')).map(n => n.textContent?.trim());
      expect(nums).toEqual(['1', '2']);
    });

    it('el pendiente muestra la fecha de su cita y se puede responder; el respondido no tiene acción', () => {
      c.cuestionariosPendientes = [pendiente(1)];
      c.cuestionariosRespondidos = [respondido(3, 'respondido')];
      c.navegarA('cuestionarios');
      render();
      expect(el_text(filas()[0])).toContain('30 jul 2026');
      expect(el_text(filas()[0])).toContain('13:15');
      expect(el_text(filas()[1])).toContain('20 jul 2026');
      expect(filas()[1].querySelector('.resumen-card-boton-primario')).toBeNull();
      const espia = vi.spyOn(c, 'abrirCuestionario').mockImplementation(() => {});
      (filas()[0].querySelector('.resumen-card-boton-primario') as HTMLButtonElement).click();
      expect(espia).toHaveBeenCalledWith(expect.objectContaining({ profesional_id: 1 }));
    });

    it('sin cuestionarios explica cuándo aparecerán', () => {
      c.navegarA('cuestionarios');
      const el = render();
      expect(filas().length).toBe(0);
      expect(el.querySelector('table.tabla-cuestionarios-est')).toBeNull();
      expect(el.textContent).toContain('No tienes cuestionarios por ahora.');
    });

    it('un pendiente y un respondido del mismo profesional conviven en la lista', () => {
      c.cuestionariosPendientes = [pendiente(1)];
      c.cuestionariosRespondidos = [respondido(1, 'respondido')];
      c.navegarA('cuestionarios');
      render();
      expect(filas().length).toBe(2);
    });
  });

  describe('Ayuda › Contacto', () => {
    const abrirContacto = () => {
      c.navegarA('ayuda');
      c.tabAyuda = 'contacto';
      return render();
    };

    it('muestra el correo, el teléfono y la ubicación configurados', () => {
      c.infoCentro = { nombre_centro: 'SESAES', correo_contacto: 'sesaes@utem.cl', telefono: '+56 2 2787 7000', direccion: 'Av. Dieciocho 161, Santiago', horario_atencion: '' };
      const el = abrirContacto();
      const datos = Array.from(el.querySelectorAll('.dato-inst')).map(d => [d.querySelector('span')?.textContent, d.querySelector('strong')?.textContent]);
      expect(datos).toEqual([['Correo', 'sesaes@utem.cl'], ['Teléfono', '+56 2 2787 7000'], ['Ubicación', 'Av. Dieciocho 161, Santiago']]);
      expect(el.querySelector('a.btn-cambiar')?.getAttribute('href')).toBe('mailto:sesaes@utem.cl');
    });

    it('no muestra filas vacías: solo los datos que existen', () => {
      c.infoCentro = { nombre_centro: 'SESAES', correo_contacto: '', telefono: '+56 2 2787 7000', direccion: '', horario_atencion: '' };
      const el = abrirContacto();
      expect(Array.from(el.querySelectorAll('.dato-inst span')).map(s => s.textContent)).toEqual(['Teléfono']);
      expect(el.querySelector('a.btn-cambiar')).toBeNull();
    });

    it('si no hay ningún dato configurado lo explica en vez de quedar en blanco', () => {
      c.infoCentro = { nombre_centro: 'SESAES', correo_contacto: '', telefono: '', direccion: '', horario_atencion: '' };
      const el = abrirContacto();
      expect(el.querySelectorAll('.dato-inst').length).toBe(0);
      expect(el.textContent).toContain('Los datos de contacto aún no están configurados.');
    });

    it('el texto no es blanco: la tarjeta de contacto es clara (el blanco es solo para Datos Institucionales)', () => {
      c.infoCentro = { nombre_centro: 'SESAES', correo_contacto: 'sesaes@utem.cl', telefono: '', direccion: '', horario_atencion: '' };
      const el = abrirContacto();
      const color = (sel: string) => getComputedStyle(el.querySelector(sel) as Element).color.replace(/\s/g, '');
      for (const sel of ['.dato-inst span', '.dato-inst strong']) {
        expect(['white', 'rgb(255,255,255)', 'rgba(255,255,255,0.7)']).not.toContain(color(sel));
      }
    });
  });

  describe('Agendar cita — profesionales', () => {
    const prof = (id: number, extra: object = {}) =>
      ({ id, nombre: `Prof ${id}`, especialidad: id % 2 ? 'Nutrición' : 'Odontología', iniciales: `P${id}`, descripcion: 'Atención integral.', foto_url: null, ...extra });
    const lista = (n: number) => Array.from({ length: n }, (_, i) => prof(i + 1));
    const el = () => fixture.nativeElement as HTMLElement;
    const tarjetas = () => Array.from(el().querySelectorAll('.profesional-card')) as HTMLElement[];
    const boton = (texto: string) => Array.from(el().querySelectorAll('.btn-pag')).find(b => b.textContent?.includes(texto)) as HTMLButtonElement;

    beforeEach(() => { c.navegarA('citas', 'solicitar'); });

    it('con 6 profesionales o menos no hay paginación', () => {
      c.profesionales = lista(6);
      render();
      expect(tarjetas().length).toBe(6);
      expect(el().querySelector('.paginacion')).toBeNull();
    });

    it('con más de 6 muestra 6 por página con Anterior y Siguiente', () => {
      c.profesionales = lista(8);
      render();
      expect(tarjetas().length).toBe(6);
      expect(el().querySelector('.paginacion')?.textContent).toContain('Mostrando 1–6 de 8 profesionales');
      expect(boton('Anterior').disabled).toBe(true);
      expect(boton('Siguiente').disabled).toBe(false);
    });

    it('Siguiente muestra el resto y Anterior vuelve a la primera página', () => {
      c.profesionales = lista(8);
      render();
      boton('Siguiente').click();
      fixture.detectChanges();
      expect(tarjetas().map(t => t.querySelector('.profesional-nombre')?.textContent?.trim())).toEqual(['Prof 7', 'Prof 8']);
      expect(el().querySelector('.paginacion')?.textContent).toContain('Mostrando 7–8 de 8 profesionales');
      expect(boton('Siguiente').disabled).toBe(true);
      boton('Anterior').click();
      fixture.detectChanges();
      expect(tarjetas().length).toBe(6);
      expect(tarjetas()[0].querySelector('.profesional-nombre')?.textContent?.trim()).toBe('Prof 1');
    });

    it('al buscar o filtrar vuelve a la primera página', () => {
      c.profesionales = lista(14);
      render();
      boton('Siguiente').click();
      fixture.detectChanges();
      expect(c.pagProf).toBe(1);
      const input = el().querySelector('.profesionales-zona')?.parentElement?.querySelector('input[type="text"]') as HTMLInputElement;
      input.value = 'Prof';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      expect(c.pagProf).toBe(0);
    });

    it('muestra la foto del profesional si la tiene y sus iniciales si no', () => {
      c.profesionales = [prof(1, { foto_url: 'https://fotos.test/ana.jpg' }), prof(2)];
      render();
      const [conFoto, sinFoto] = tarjetas();
      const img = conFoto.querySelector('img.prof-foto-card') as HTMLImageElement;
      expect(img.getAttribute('src')).toBe('https://fotos.test/ana.jpg');
      expect(img.alt).toBe('Foto de Prof 1');
      expect(conFoto.querySelector('.profesional-avatar-full')).toBeNull();
      expect(sinFoto.querySelector('img')).toBeNull();
      expect(sinFoto.querySelector('.profesional-avatar-full')?.textContent?.trim()).toBe('P2');
    });

    it('si la foto no carga, vuelve a mostrar las iniciales', () => {
      c.profesionales = [prof(1, { foto_url: 'https://fotos.test/rota.jpg' })];
      render();
      (tarjetas()[0].querySelector('img.prof-foto-card') as HTMLImageElement).dispatchEvent(new Event('error'));
      fixture.detectChanges();
      expect(tarjetas()[0].querySelector('img')).toBeNull();
      expect(tarjetas()[0].querySelector('.profesional-avatar-full')?.textContent?.trim()).toBe('P1');
    });

    it('elegir un profesional pasa al paso del horario', () => {
      c.profesionales = lista(2);
      render();
      const espia = vi.spyOn(c, 'seleccionarProfesional').mockImplementation(() => {});
      (tarjetas()[1].querySelector('.btn-agendar') as HTMLButtonElement).click();
      expect(espia).toHaveBeenCalled();
      expect(espia.mock.calls[0][0].id).toBe(2);
    });
  });

  describe('calendario del Inicio', () => {
    it('marca el día de hoy y los días con cita', () => {
      const hoy = new Date();
      const iso = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`;
      c.proximasCitas = [{ fecha: iso }];
      const dias = c.calInicioDias.filter(d => d !== null);
      expect(dias.filter(d => d!.hoy).length).toBe(1);
      expect(dias.find(d => d!.hoy)!.conCita).toBe(true);
    });

    it('la semana empieza en lunes y navega entre meses', () => {
      const primera = c.calInicioDias.findIndex(d => d?.num === 1);
      const ref = new Date(); ref.setDate(1);
      expect(primera).toBe((ref.getDay() + 6) % 7);
      const titulo = c.calInicioTitulo;
      c.calInicioMesSiguiente();
      expect(c.calInicioTitulo).not.toBe(titulo);
      c.calInicioMesAnterior();
      expect(c.calInicioTitulo).toBe(titulo);
    });
  });

  it('usa Material Symbols y modo claro/oscuro con tokens (sin SVG inline)', () => {
    const el = render();
    expect(el.querySelectorAll('svg').length).toBe(0);
    expect(el.querySelectorAll('.material-symbols-outlined').length).toBeGreaterThan(10);
  });
});
