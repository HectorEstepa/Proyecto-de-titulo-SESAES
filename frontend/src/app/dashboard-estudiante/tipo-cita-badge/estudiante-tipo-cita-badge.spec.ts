import { ComponentFixture, TestBed } from '@angular/core/testing';
import { EstudianteTipoCitaBadgeComponent } from './estudiante-tipo-cita-badge';

describe('EstudianteTipoCitaBadgeComponent', () => {
  let fixture: ComponentFixture<EstudianteTipoCitaBadgeComponent>;
  const el = () => fixture.nativeElement as HTMLElement;
  const con = (tipo: string | null | undefined) => {
    fixture.componentRef.setInput('tipo', tipo);
    fixture.detectChanges();
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [EstudianteTipoCitaBadgeComponent] }).compileComponents();
    fixture = TestBed.createComponent(EstudianteTipoCitaBadgeComponent);
  });

  it('un sobrecupo se marca como "Sobrecupo" con su propia clase de color', () => {
    con('sobrecupo');
    const marca = el().querySelector('.tipo-cita') as HTMLElement;
    expect(marca.textContent?.trim()).toBe('Sobrecupo');
    expect(marca.classList).toContain('sobrecupo');
    expect(marca.title).toBe('Cita agendada como sobrecupo');
  });

  it('una urgencia se marca como "Urgente" con su propia clase de color', () => {
    con('urgente');
    const marca = el().querySelector('.tipo-cita') as HTMLElement;
    expect(marca.textContent?.trim()).toBe('Urgente');
    expect(marca.classList).toContain('urgente');
    expect(marca.classList).not.toContain('sobrecupo');
  });

  it('una cita normal, o sin dato, no muestra nada', () => {
    for (const t of ['normal', null, undefined, '', 'otro']) {
      con(t);
      expect(el().querySelector('.tipo-cita')).toBeNull();
    }
  });
});
