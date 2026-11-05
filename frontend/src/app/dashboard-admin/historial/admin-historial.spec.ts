import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AdminHistorialComponent } from './admin-historial';

describe('AdminHistorialComponent', () => {
  let component: AdminHistorialComponent;
  let fixture: ComponentFixture<AdminHistorialComponent>;

  const crearHistorial = (cantidad: number) =>
    Array.from({ length: cantidad }, (_, i) => ({
      id: i + 1,
      iniciales: `E${i + 1}`,
      estudiante: `Estudiante ${i + 1}`,
      rut: `1${i + 1}.111.111-1`,
      carrera: 'Ingeniería Civil',
      especialidad: 'Medicina General',
      profesional: 'Profesional SESAES',
      fecha: '2026-08-31',
      hora: '10:00',
      estado: 'completada',
      tiene_pdf: i === 0
    }));

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminHistorialComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(AdminHistorialComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('especialidades', ['Medicina General', 'Psicología']);
    fixture.componentRef.setInput('cgrAniosDisponibles', [2026, 2025]);
    fixture.detectChanges();
  });

  it('debe crearse', () => {
    expect(component).toBeTruthy();
  });

  it('debe paginar el historial en bloques de 8 registros', () => {
    fixture.componentRef.setInput('historialAdmin', crearHistorial(10));
    fixture.detectChanges();

    expect(component.historialPaginado.length).toBe(8);
    expect(component.getPaginasHist()).toEqual([1, 2]);

    component.pagHist = 2;

    expect(component.historialPaginado.length).toBe(2);
  });

  it('debe volver a la primera página cuando cambia historialAdmin', () => {
    fixture.componentRef.setInput('historialAdmin', crearHistorial(10));
    fixture.detectChanges();
    component.pagHist = 2;

    fixture.componentRef.setInput('historialAdmin', crearHistorial(3));
    fixture.detectChanges();

    expect(component.pagHist).toBe(1);
  });

  it('debe mostrar el estado vacío cuando no hay registros', () => {
    fixture.componentRef.setInput('historialAdmin', []);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('No hay registros con los filtros aplicados');
    expect(texto).toContain('Mostrando 0–0 de 0 resultados');
  });

  it('muestra la carrera y calcula las iniciales desde el nombre del estudiante', () => {
    const historial = [{
      ...crearHistorial(1)[0],
      estudiante: 'Carlos Muñoz',
      iniciales: 'VR',
      carrera: 'Ingeniería en Informática'
    }];

    fixture.componentRef.setInput('historialAdmin', historial);
    fixture.detectChanges();

    const avatar = fixture.nativeElement.querySelector('.mini-avatar') as HTMLElement;
    const texto = fixture.nativeElement.textContent as string;

    expect(avatar.textContent?.trim()).toBe('CM');
    expect(texto).toContain('Ingeniería en Informática');
  });

  it('debe emitir aplicarFiltros al presionar el botón correspondiente', () => {
    const emitSpy = vi.spyOn(component.aplicarFiltros, 'emit');
    fixture.detectChanges();

    const boton = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
    ).find((b) => b.textContent?.includes('Aplicar Filtros'));

    expect(boton).toBeTruthy();
    boton!.click();

    expect(emitSpy).toHaveBeenCalledTimes(1);
  });

  it('debe emitir verDetalle con la cita seleccionada', () => {
    const historial = crearHistorial(1);
    const emitSpy = vi.spyOn(component.verDetalle, 'emit');

    fixture.componentRef.setInput('historialAdmin', historial);
    fixture.detectChanges();

    const boton = fixture.nativeElement.querySelector(
      'button.btn-tabla.ver'
    ) as HTMLButtonElement;

    boton.click();

    expect(emitSpy).toHaveBeenCalledWith(historial[0]);
  });

  it('debe emitir descargarPdf con el id cuando la cita tiene PDF', () => {
    const historial = crearHistorial(1);
    const emitSpy = vi.spyOn(component.descargarPdf, 'emit');

    fixture.componentRef.setInput('historialAdmin', historial);
    fixture.detectChanges();

    const boton = fixture.nativeElement.querySelector(
      'button.btn-tabla.descargar'
    ) as HTMLButtonElement;

    expect(boton).toBeTruthy();
    boton.click();

    expect(emitSpy).toHaveBeenCalledWith(historial[0].id);
  });

  it('debe emitir las acciones de exportación sin ejecutar HTTP', () => {
    const pdfSpy = vi.spyOn(component.exportarHistorialPdf, 'emit');
    const excelSpy = vi.spyOn(component.exportarHistorialExcel, 'emit');
    const cgrSpy = vi.spyOn(component.exportarCgr, 'emit');
    const alumnosSpy = vi.spyOn(component.exportarAlumnos, 'emit');

        fixture.componentRef.setInput('puedeExportarCgr', true);
fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
    );

    botones.find((b) => b.textContent?.includes('Exportar PDF'))!.click();
    botones.find((b) => b.textContent?.includes('Exportar Excel'))!.click();
    botones.find((b) => b.textContent?.includes('Atenciones'))!.click();
    botones.find((b) => b.textContent?.includes('Listado de Alumnos'))!.click();

    expect(pdfSpy).toHaveBeenCalledTimes(1);
    expect(excelSpy).toHaveBeenCalledTimes(1);
    expect(cgrSpy).toHaveBeenCalledTimes(1);
    expect(alumnosSpy).toHaveBeenCalledTimes(1);
  });
});

describe('AdminHistorialComponent.inicialesEstudiante', () => {
  let component: AdminHistorialComponent;

  beforeEach(() => {
    component = new AdminHistorialComponent();
  });

  it('usa primer nombre + primer apellido en nombres compuestos (no el último apellido)', () => {
    expect(component.inicialesEstudiante('María Fernanda García López')).toBe('MG');
    expect(component.inicialesEstudiante('Juan Carlos Pérez')).toBe('JP');
  });

  it('usa primer nombre + apellido en nombres simples', () => {
    expect(component.inicialesEstudiante('Juan Pérez')).toBe('JP');
    expect(component.inicialesEstudiante('Camila Soto')).toBe('CS');
  });

  it('devuelve una sola letra cuando solo hay un token', () => {
    expect(component.inicialesEstudiante('Juan')).toBe('J');
  });

  it('devuelve "?" cuando el nombre está vacío o ausente', () => {
    expect(component.inicialesEstudiante('')).toBe('?');
    expect(component.inicialesEstudiante(null)).toBe('?');
    expect(component.inicialesEstudiante(undefined)).toBe('?');
  });
});
