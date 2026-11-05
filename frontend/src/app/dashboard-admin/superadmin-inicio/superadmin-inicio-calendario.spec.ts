import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SuperadminInicioCalendarioComponent } from './superadmin-inicio-calendario';

describe('SuperadminInicioCalendarioComponent', () => {
  let fixture: ComponentFixture<SuperadminInicioCalendarioComponent>;
  let component: SuperadminInicioCalendarioComponent;
  let el: HTMLElement;

  beforeEach(async () => {
    // Solo se simula Date: no interfiere con los timers de Angular.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 8, 19, 10, 0, 0)); // sáb 19-sep-2026

    await TestBed.configureTestingModule({
      imports: [SuperadminInicioCalendarioComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(SuperadminInicioCalendarioComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    el = fixture.nativeElement;
  });

  afterEach(() => vi.useRealTimers());

  const celdas = () => Array.from(el.querySelectorAll<HTMLButtonElement>('button.cal-celda'));
  const celdaDelDia = (n: number) => celdas().find(c => c.textContent?.trim() === String(n))!;

  it('muestra el mes actual y todos sus días', () => {
    expect(el.querySelector('[data-testid="cal-mes"]')?.textContent).toContain('Septiembre 2026');
    expect(celdas()).toHaveLength(30);
  });

  it('alinea el día 1 en la columna correcta (semana desde lunes)', () => {
    // 1-sep-2026 es martes → una celda vacía antes.
    expect(el.querySelectorAll('.cal-celda.vacia')).toHaveLength(1);
  });

  it('marca el día de hoy', () => {
    const hoy = el.querySelectorAll('.cal-celda.hoy');
    expect(hoy).toHaveLength(1);
    expect(hoy[0].textContent?.trim()).toBe('19');
  });

  it('marca feriados chilenos reales y expone su nombre accesible', () => {
    const fiestas = celdaDelDia(18);
    expect(fiestas.classList.contains('feriado')).toBe(true);
    expect(fiestas.getAttribute('aria-label')).toContain('Fiestas Patrias');
    expect(celdaDelDia(10).classList.contains('feriado')).toBe(false);
  });

  it('marca días internacionales que no son feriado', () => {
    // 08-sep: Día Internacional de la Alfabetización.
    expect(celdaDelDia(8).classList.contains('internacional')).toBe(true);
  });

  it('navega entre meses, cruzando el cambio de año', () => {
    const [anterior, siguiente] = Array.from(el.querySelectorAll<HTMLButtonElement>('.cal-nav-btn'));

    for (let i = 0; i < 9; i++) anterior.click(); // sep → dic 2025
    fixture.detectChanges();
    expect(component.tituloMes).toBe('Diciembre 2025');

    for (let i = 0; i < 13; i++) siguiente.click(); // dic 2025 → ene 2027
    fixture.detectChanges();
    expect(component.tituloMes).toBe('Enero 2027');
  });

  it('al seleccionar un día muestra su información y al repetir el clic la oculta', () => {
    celdaDelDia(18).click();
    fixture.detectChanges();

    const info = el.querySelector('[data-testid="cal-info"]');
    expect(info?.textContent).toContain('Feriado: Fiestas Patrias');
    expect(info?.textContent).toContain('18 de septiembre');

    celdaDelDia(18).click();
    fixture.detectChanges();
    expect(el.querySelector('[data-testid="cal-info"]')).toBeNull();
  });

  it('informa cuando el día seleccionado no tiene efemérides', () => {
    celdaDelDia(10).click();
    fixture.detectChanges();
    expect(el.querySelector('[data-testid="cal-info"]')?.textContent)
      .toContain('Sin feriados ni efemérides registradas.');
  });

  it('cambiar de mes limpia el día seleccionado', () => {
    celdaDelDia(18).click();
    fixture.detectChanges();
    el.querySelectorAll<HTMLButtonElement>('.cal-nav-btn')[1].click();
    fixture.detectChanges();
    expect(component.diaSeleccionado).toBeNull();
  });

  it('es solo informativo: no depende de Agenda ni hace HTTP', () => {
    // Sin providers de HttpClient: si el componente pidiera datos, fallaría al crearse.
    expect(component).toBeTruthy();
  });
});
