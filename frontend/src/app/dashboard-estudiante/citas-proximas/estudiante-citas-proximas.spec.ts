import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { EstudianteCitasProximasComponent } from './estudiante-citas-proximas';

describe('EstudianteCitasProximasComponent', () => {
  let component: EstudianteCitasProximasComponent;
  let fixture: ComponentFixture<EstudianteCitasProximasComponent>;

  // Fecha de referencia fija para todos los cálculos de "horas para cancelar".
  const AHORA = new Date('2026-08-31T10:00:00');

  const crearCita = (overrides: Partial<any> = {}) => ({
    id: 1,
    iniciales: 'JP',
    especialidad: 'Psicología',
    profesional: 'Juana Pérez',
    fecha: '31/08/2026',
    fecha_raw: '2026-08-31',
    hora: '10:00',
    urgente: false,
    estado: 'pendiente',
    ...overrides
  });

  const crearCitas = (cantidad: number) =>
    Array.from({ length: cantidad }, (_, i) => crearCita({
      id: i + 1,
      profesional: `Profesional ${i + 1}`
    }));

  beforeEach(async () => {
    vi.useFakeTimers();
    vi.setSystemTime(AHORA);

    // No se provee HttpClient/HttpTestingController a propósito: si el
    // componente intentara inyectar HttpClient, esta configuración
    // fallaría al crear el fixture. Que el test pase así confirma que
    // EstudianteCitasProximasComponent no hace HTTP propio.
    await TestBed.configureTestingModule({
      imports: [EstudianteCitasProximasComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(EstudianteCitasProximasComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('debe crearse', () => {
    expect(component).toBeTruthy();
  });

  it('no realiza llamadas HTTP propias', () => {
    // El componente no declara HttpClient como dependencia — no hay
    // ningún import de @angular/common/http en este archivo, y el
    // TestBed de arriba tampoco lo provee.
    expect((component as any).http).toBeUndefined();
  });

  it('renderiza una tarjeta por cada cita recibida por @Input', () => {
    const citas = crearCitas(3);
    fixture.componentRef.setInput('citas', citas);
    fixture.detectChanges();

    const tarjetas = fixture.nativeElement.querySelectorAll('.cita-card');
    expect(tarjetas.length).toBe(3);
    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Profesional 1');
    expect(texto).toContain('Profesional 3');
  });

  it('muestra el estado vacío cuando citas=[]', () => {
    fixture.componentRef.setInput('citas', []);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('.cita-card').length).toBe(0);
    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('No tienes citas próximas');
  });

  it('el botón del estado vacío emite solicitarNueva', () => {
    fixture.componentRef.setInput('citas', []);
    fixture.detectChanges();
    const emitSpy = vi.spyOn(component.solicitarNueva, 'emit');

    const boton = fixture.nativeElement.querySelector('.btn-reagendar') as HTMLElement;
    boton.click();

    expect(emitSpy).toHaveBeenCalled();
  });

  describe('puedeCancelar', () => {
    it('permite cancelar cuando faltan más de 5 horas', () => {
      // AHORA = 10:00 → la cita a las 16:00 está a 6 horas.
      const cita = crearCita({ hora: '16:00' });
      expect(component.puedeCancelar(cita)).toBe(true);
    });

    it('NO permite cancelar dentro de la ventana de 5 horas', () => {
      // AHORA = 10:00 → la cita a las 13:00 está a 3 horas.
      const cita = crearCita({ hora: '13:00' });
      expect(component.puedeCancelar(cita)).toBe(false);
    });

    it('NO permite cancelar exactamente en el límite de 5 horas (diff === 5)', () => {
      // AHORA = 10:00 → la cita a las 15:00 está a exactamente 5 horas.
      // La implementación original usa "diff > 5" (estrictamente mayor),
      // por lo que el límite exacto de 5h cae dentro de la ventana bloqueada.
      const cita = crearCita({ hora: '15:00' });
      expect(component.puedeCancelar(cita)).toBe(false);
    });

    it('permite cancelar si la cita ya pasó (diff negativo)', () => {
      // AHORA = 10:00 → la cita a las 08:00 ya pasó.
      const cita = crearCita({ hora: '08:00' });
      expect(component.puedeCancelar(cita)).toBe(true);
    });

    it('permite cancelar cuando no hay fecha_raw/hora (diff null)', () => {
      const cita = crearCita({ fecha_raw: undefined, hora: undefined });
      expect(component.puedeCancelar(cita)).toBe(true);
    });
  });

  describe('citaPendienteVencida', () => {
    it('es true cuando la cita ya pasó su hora', () => {
      const cita = crearCita({ hora: '08:00' });
      expect(component.citaPendienteVencida(cita)).toBe(true);
    });

    it('es false cuando la cita todavía no ocurre', () => {
      const cita = crearCita({ hora: '16:00' });
      expect(component.citaPendienteVencida(cita)).toBe(false);
    });

    it('es false cuando no hay fecha_raw/hora (diff null)', () => {
      const cita = crearCita({ fecha_raw: undefined, hora: undefined });
      expect(component.citaPendienteVencida(cita)).toBe(false);
    });
  });

  describe('avisoCancelacion', () => {
    it('conserva el comportamiento original: solo devuelve vacío si diff es null o diff <= 0, incluso cuando puedeCancelar() ya es true', () => {
      // AHORA = 10:00 → cita a las 16:00 = 6 horas. puedeCancelar() es true
      // (diff > 5), pero avisoCancelacion() en la implementación heredada
      // (previa a la extracción) solo retorna '' cuando diff es null o
      // diff <= 0 — no cuando puedeCancelar() es true. Es el template quien
      // oculta este texto mediante *ngIf="!puedeCancelar(cita)", no el método.
      const cita = crearCita({ hora: '16:00' });
      expect(component.puedeCancelar(cita)).toBe(true);
      expect(component.avisoCancelacion(cita)).toBe('Faltan 6h, no se puede cancelar');
    });

    it('devuelve cadena vacía cuando la cita ya pasó', () => {
      const cita = crearCita({ hora: '08:00' });
      expect(component.avisoCancelacion(cita)).toBe('');
    });

    it('formatea horas y minutos cuando faltan ambos', () => {
      // AHORA = 10:00 → cita a las 13:30 = 3h 30min.
      const cita = crearCita({ hora: '13:30' });
      expect(component.avisoCancelacion(cita)).toBe('Faltan 3h 30min, no se puede cancelar');
    });

    it('formatea solo horas cuando los minutos son 0', () => {
      // AHORA = 10:00 → cita a las 13:00 = 3h exactas.
      const cita = crearCita({ hora: '13:00' });
      expect(component.avisoCancelacion(cita)).toBe('Faltan 3h, no se puede cancelar');
    });

    it('formatea solo minutos cuando faltan menos de 1 hora', () => {
      // AHORA = 10:00 → cita a las 10:45 = 45 min.
      const cita = crearCita({ hora: '10:45' });
      expect(component.avisoCancelacion(cita)).toBe('Faltan 45 min, no se puede cancelar');
    });
  });

  it('deshabilita el botón Cancelar cuando puedeCancelar es false', () => {
    const cita = crearCita({ hora: '13:00' }); // dentro de la ventana de 5h
    fixture.componentRef.setInput('citas', [cita]);
    fixture.detectChanges();

    const boton = fixture.nativeElement.querySelector('.btn-cancelar') as HTMLButtonElement;
    expect(boton.disabled).toBe(true);
    const aviso = fixture.nativeElement.querySelector('.cita-aviso-cancelacion');
    expect(aviso?.textContent).toContain('no se puede cancelar');
  });

  it('para una cita fuera de la ventana de 5h: botón Cancelar habilitado y sin aviso de cancelación en el DOM', () => {
    // AHORA = 10:00 → cita a las 16:00 = 6 horas. Aunque avisoCancelacion()
    // devuelva texto (ver bloque 'avisoCancelacion' arriba), el *ngIf del
    // template lo condiciona a "!puedeCancelar(cita)", así que no debe
    // renderizarse ningún elemento .cita-aviso-cancelacion.
    const cita = crearCita({ hora: '16:00' });
    fixture.componentRef.setInput('citas', [cita]);
    fixture.detectChanges();

    const boton = fixture.nativeElement.querySelector('.btn-cancelar') as HTMLButtonElement;
    expect(boton.disabled).toBe(false);
    expect(fixture.nativeElement.querySelector('.cita-aviso-cancelacion')).toBeNull();
  });

  it('habilita el botón Cancelar cuando puedeCancelar es true y emite { index, cita }', () => {
    const cita = crearCita({ hora: '16:00' }); // fuera de la ventana de 5h
    fixture.componentRef.setInput('citas', [cita]);
    fixture.detectChanges();
    const emitSpy = vi.spyOn(component.cancelar, 'emit');

    const boton = fixture.nativeElement.querySelector('.btn-cancelar') as HTMLButtonElement;
    expect(boton.disabled).toBe(false);
    boton.click();

    expect(emitSpy).toHaveBeenCalledWith({ index: 0, cita });
  });

  it('emite el índice correcto dentro de una lista con varias citas', () => {
    const citas = [
      crearCita({ id: 1, hora: '16:00' }),
      crearCita({ id: 2, hora: '17:00' }),
      crearCita({ id: 3, hora: '18:00' })
    ];
    fixture.componentRef.setInput('citas', citas);
    fixture.detectChanges();
    const emitSpy = vi.spyOn(component.cancelar, 'emit');

    const botones = fixture.nativeElement.querySelectorAll('.btn-cancelar');
    (botones[2] as HTMLButtonElement).click();

    expect(emitSpy).toHaveBeenCalledWith({ index: 2, cita: citas[2] });
  });

  it('muestra la clase y el aviso visual de cita vencida', () => {
    const cita = crearCita({ hora: '08:00' }); // ya pasó
    fixture.componentRef.setInput('citas', [cita]);
    fixture.detectChanges();

    const tarjeta = fixture.nativeElement.querySelector('.cita-card');
    expect(tarjeta.classList).toContain('cita-card-vencida');
    const aviso = fixture.nativeElement.querySelector('.cita-aviso-vencida');
    expect(aviso).toBeTruthy();
    expect(aviso.textContent).toContain('ya pasó');
  });

  describe('tipo de cita', () => {
    const marcas = () => Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('.tipo-cita')) as HTMLElement[];

    beforeEach(() => {
      fixture = TestBed.createComponent(EstudianteCitasProximasComponent);
      component = fixture.componentInstance;
    });

    it('una cita de sobrecupo agendada por el administrador se reconoce como sobrecupo', () => {
      fixture.componentRef.setInput('citas', [crearCita({ tipo: 'sobrecupo', sobrecupo: true })]);
      fixture.detectChanges();
      expect(marcas().map(m => m.textContent?.trim())).toEqual(['Sobrecupo']);
      expect(marcas()[0].classList).toContain('sobrecupo');
    });

    it('una urgencia se reconoce como urgente y sigue mostrando su especialidad', () => {
      fixture.componentRef.setInput('citas', [crearCita({ tipo: 'urgente', urgente: true })]);
      fixture.detectChanges();
      expect(marcas().map(m => m.textContent?.trim())).toEqual(['Urgente']);
      expect((fixture.nativeElement as HTMLElement).querySelector('.cita-badge')?.textContent?.trim()).toBe('Psicología');
    });

    it('una cita normal no lleva marca', () => {
      fixture.componentRef.setInput('citas', [crearCita({ tipo: 'normal' }), crearCita({ id: 2 })]);
      fixture.detectChanges();
      expect(marcas().length).toBe(0);
    });
  });
});
