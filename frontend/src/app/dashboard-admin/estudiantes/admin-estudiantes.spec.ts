import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AdminEstudiantesComponent } from './admin-estudiantes';

describe('AdminEstudiantesComponent', () => {
  let component: AdminEstudiantesComponent;
  let fixture: ComponentFixture<AdminEstudiantesComponent>;

  const estudiantes = [
    {
      id: 1,
      nombre: 'Ana Pérez',
      correo: 'ana@utem.cl',
      rut: '11.111.111-1',
      carrera: 'Derecho'
    },
    {
      id: 2,
      nombre: 'Luis Soto',
      correo: 'luis@utem.cl',
      rut: '22.222.222-2',
      carrera: 'Ingeniería'
    }
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminEstudiantesComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(AdminEstudiantesComponent);
    component = fixture.componentInstance;
  });

  it('debe crearse', () => {
    expect(component).toBeTruthy();
  });

  it('debe calcular las páginas según el total y tamaño de página', () => {
    fixture.componentRef.setInput('estudiantesTotal', 45);
    fixture.componentRef.setInput('estudiantesPorPagina', 20);
    fixture.detectChanges();

    expect(component.getPaginasEstudiantes()).toEqual([1, 2, 3]);
  });

  it('debe renderizar el listado de estudiantes', () => {
    fixture.componentRef.setInput('estudiantesAdmin', estudiantes);
    fixture.componentRef.setInput('estudiantesTotal', 2);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Ana Pérez');
    expect(texto).toContain('Luis Soto');
    expect(texto).toContain('Derecho');
  });

  it('debe mostrar el estado vacío cuando no hay estudiantes', () => {
    fixture.componentRef.setInput('estudiantesAdmin', []);
    fixture.componentRef.setInput('estudiantesTotal', 0);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(
      'No hay estudiantes con los filtros aplicados'
    );
  });

  it('debe mostrar el estado de carga', () => {
    fixture.componentRef.setInput('estudiantesCargando', true);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Cargando...');
    expect(fixture.nativeElement.querySelector('table.admin-tabla')).toBeNull();
  });

  it('debe emitir buscar y limpiar desde sus botones', () => {
    const buscarSpy = vi.spyOn(component.buscar, 'emit');
    const limpiarSpy = vi.spyOn(component.limpiar, 'emit');
    fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
    );

    botones.find(b => b.textContent?.trim() === 'Buscar')!.click();
    botones.find(b => b.textContent?.trim() === 'Limpiar')!.click();

    expect(buscarSpy).toHaveBeenCalledTimes(1);
    expect(limpiarSpy).toHaveBeenCalledTimes(1);
  });

  it('debe emitir la página solicitada', () => {
    const paginaSpy = vi.spyOn(component.cambiarPagina, 'emit');
    fixture.componentRef.setInput('estudiantesTotal', 45);
    fixture.componentRef.setInput('estudiantesPagina', 1);
    fixture.componentRef.setInput('estudiantesPorPagina', 20);
    fixture.detectChanges();

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button.btn-pag') as NodeListOf<HTMLButtonElement>
    );

    const pagina2 = botones.find(b => b.textContent?.trim() === '2');
    expect(pagina2).toBeTruthy();

    pagina2!.click();
    expect(paginaSpy).toHaveBeenCalledWith(2);
  });

  it('debe emitir verPerfil con el estudiante seleccionado', () => {
    const verSpy = vi.spyOn(component.verPerfil, 'emit');
    fixture.componentRef.setInput('estudiantesAdmin', [estudiantes[0]]);
    fixture.componentRef.setInput('estudiantesTotal', 1);
    fixture.detectChanges();

    const boton = fixture.nativeElement.querySelector(
      'button.btn-tabla-acciones'
    ) as HTMLButtonElement;

    boton.click();
    expect(verSpy).toHaveBeenCalledWith(estudiantes[0]);
  });

  it('debe renderizar la ficha y emitir cerrarPerfil', () => {
    const cerrarSpy = vi.spyOn(component.cerrarPerfil, 'emit');

    fixture.componentRef.setInput('modalPerfilEstudianteAbierto', true);
    fixture.componentRef.setInput('perfilEstudianteCargando', false);
    fixture.componentRef.setInput('fichaEstudianteSeleccionado', {
      id: 1,
      nombre: 'Ana Pérez',
      rut: '11.111.111-1',
      correo: 'ana@utem.cl',
      carrera: 'Derecho',
      telefono: null,
      foto_url: null,
      activo: true,
      citas_totales: 4,
      citas_atendidas: 3,
      citas_pendientes: 1,
      citas_canceladas: 0,
      ultimas_atenciones: [
        {
          fecha: '2026-08-20',
          hora: '10:00',
          profesional: 'Profesional SESAES',
          especialidad: 'Medicina General',
          tipo: 'normal',
          estado: 'completada'
        }
      ],
      historial: [
        {
          fecha: '2026-08-20',
          hora: '10:00',
          profesional: 'Profesional SESAES',
          especialidad: 'Medicina General',
          tipo: 'normal',
          estado: 'completada'
        }
      ],
      historial_total: 1,
      historial_pagina: 1,
      historial_por_pagina: 5
    });
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Ficha del estudiante');
    expect(texto).toContain('Ana Pérez');
    expect(texto).toContain('Profesional SESAES');

    const cerrar = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
    ).find(b => b.textContent?.trim() === 'Cerrar');

    expect(cerrar).toBeTruthy();
    cerrar!.click();

    expect(cerrarSpy).toHaveBeenCalledTimes(1);
  });
});

describe('AdminEstudiantesComponent.inicialesDe', () => {
  let component: AdminEstudiantesComponent;

  beforeEach(() => {
    component = new AdminEstudiantesComponent();
  });

  it('usa primer nombre + primer apellido en nombres compuestos (no el último apellido)', () => {
    expect(component.inicialesDe('María Fernanda García López')).toBe('MG');
    expect(component.inicialesDe('Juan Carlos Pérez')).toBe('JP');
  });

  it('usa primer nombre + apellido en nombres simples', () => {
    expect(component.inicialesDe('Juan Pérez')).toBe('JP');
    expect(component.inicialesDe('Camila Soto')).toBe('CS');
  });

  it('devuelve una sola letra cuando solo hay un token', () => {
    expect(component.inicialesDe('Juan')).toBe('J');
  });

  it('devuelve "?" cuando el nombre está vacío o ausente', () => {
    expect(component.inicialesDe('')).toBe('?');
    expect(component.inicialesDe(null)).toBe('?');
    expect(component.inicialesDe(undefined)).toBe('?');
  });
});