import { describe, it, expect, vi } from 'vitest';
import { AdminProfesionalesComponent } from './admin-profesionales';

/**
 * AdminProfesionalesComponent no tiene dependencias inyectadas en su
 * constructor, así que se puede instanciar directamente para probar sus
 * métodos puros sin necesidad de TestBed.
 */
describe('AdminProfesionalesComponent.nombreConTratamiento', () => {
  const componente = new AdminProfesionalesComponent();

  it('antepone el tratamiento cuando el nombre no lo trae', () => {
    const resultado = componente.nombreConTratamiento({
      nombre: 'Eduardo Carvajal',
      tratamiento: 'Dr.'
    });
    expect(resultado).toBe('Dr. Eduardo Carvajal');
  });

  it('no duplica el tratamiento si el nombre ya lo trae (dato histórico)', () => {
    const resultado = componente.nombreConTratamiento({
      nombre: 'Dr. Eduardo Carvajal',
      tratamiento: 'Dr.'
    });
    expect(resultado).toBe('Dr. Eduardo Carvajal');
  });

  it('no antepone nada si no hay tratamiento', () => {
    const resultado = componente.nombreConTratamiento({
      nombre: 'Carlos Muñoz',
      tratamiento: null
    });
    expect(resultado).toBe('Carlos Muñoz');
  });
});

describe('AdminProfesionalesComponent.colorDeProfesional', () => {
  const componente = new AdminProfesionalesComponent();

  it('usa el color propio del profesional si existe', () => {
    expect(componente.colorDeProfesional({ especialidad: 'Nutrición', color_identificador: '#4F8EF7' }))
      .toBe('#4F8EF7');
  });

  it('usa el fallback por especialidad si no tiene color propio', () => {
    expect(componente.colorDeProfesional({ especialidad: 'Odontología', color_identificador: null }))
      .toBe('#7FB8A6');
  });

  it('dos profesionales con la misma especialidad pueden tener colores distintos', () => {
    const a = componente.colorDeProfesional({ especialidad: 'Nutrición', color_identificador: '#C75B5B' });
    const b = componente.colorDeProfesional({ especialidad: 'Nutrición', color_identificador: '#8B5CF6' });
    expect(a).not.toBe(b);
  });

  it('usa un neutro si no hay color propio ni fallback conocido para la especialidad', () => {
    expect(componente.colorDeProfesional({ especialidad: 'Especialidad Nueva Sin Mapeo', color_identificador: null }))
      .toBe('#5C706D');
  });
});

describe('AdminProfesionalesComponent — chips de las cards (datos reales, sin inventar significado)', () => {
  it('textoPorcentajeActivos refleja activos/total, no "capacidad"', () => {
    const componente = new AdminProfesionalesComponent();
    componente.profesionales = [{}, {}, {}, {}, {}, {}, {}]; // 7 total
    componente.profesionalesActivos = 5;
    expect(componente.textoPorcentajeActivos).toBe('71% activos');
  });

  it('textoActivosChip usa "activos", nunca "en turno"', () => {
    const componente = new AdminProfesionalesComponent();
    componente.profesionalesActivos = 7;
    expect(componente.textoActivosChip).toBe('7 activos');
    componente.profesionalesActivos = 1;
    expect(componente.textoActivosChip).toBe('1 activo');
    componente.profesionalesActivos = 0;
    expect(componente.textoActivosChip).toBe('Sin profesionales activos');
  });

  it('textoIncidenciasChip usa "incidencias", nunca "reportes"', () => {
    const componente = new AdminProfesionalesComponent();
    componente.profesionalesConIncidencia = 0;
    expect(componente.textoIncidenciasChip).toBe('Sin incidencias');
    componente.profesionalesConIncidencia = 1;
    expect(componente.textoIncidenciasChip).toBe('1 incidencia');
    componente.profesionalesConIncidencia = 3;
    expect(componente.textoIncidenciasChip).toBe('3 incidencias');
  });

  it('especialidadesReales cuenta solo especialidades presentes en profesionales[], no la lista base', () => {
    const componente = new AdminProfesionalesComponent();
    componente.profesionales = [
      { especialidad: 'Nutrición' },
      { especialidad: 'Nutrición' },
      { especialidad: 'Kinesiología' }
    ];
    expect(componente.especialidadesReales.length).toBe(2);
  });
});

describe('AdminProfesionalesComponent — SA-10.2B read-only vs gestionar', () => {
  it('read-only no abre modales de gestión', () => {
    const componente = new AdminProfesionalesComponent();
    componente.puedeGestionarProfesionales = false;

    componente.abrirModalAgregar();
    componente.abrirModalAcciones({ id: 1, nombre: 'Profesional', estado: 'activo', duracion_min: 45 });

    expect(componente.modalProfAbierto).toBe(false);
    expect(componente.modalAccionesAbierto).toBe(false);
  });

  it('read-only bloquea todos los handlers que emiten mutaciones', () => {
    const componente = new AdminProfesionalesComponent();
    const profesional = {
      id: 2,
      nombre: 'Profesional Read Only',
      estado: 'activo',
      nuevoEstado: 'licencia',
      motivoCambio: 'test',
      duracion_min: 45,
      nuevoTratamiento: 'Dr.',
      nuevoColor: '#4F8EF7'
    };

    const crearSpy = vi.spyOn(componente.crearProfesional, 'emit');
    const estadoSpy = vi.spyOn(componente.cambiarEstado, 'emit');
    const duracionSpy = vi.spyOn(componente.cambiarDuracion, 'emit');
    const tratamientoSpy = vi.spyOn(componente.cambiarTratamiento, 'emit');
    const colorSpy = vi.spyOn(componente.cambiarColorIdentificador, 'emit');
    const eliminarSpy = vi.spyOn(componente.eliminarProfesional, 'emit');

    componente.puedeGestionarProfesionales = false;
    componente.profSeleccionado = profesional;
    componente.confirmarCrearProf();
    componente.guardarEstadoProfesional();
    componente.guardarDuracionProfesional();
    componente.guardarTratamientoProfesional();
    componente.guardarColorProfesional();
    componente.eliminarProfesionalDesdeModal();

    expect(crearSpy).not.toHaveBeenCalled();
    expect(estadoSpy).not.toHaveBeenCalled();
    expect(duracionSpy).not.toHaveBeenCalled();
    expect(tratamientoSpy).not.toHaveBeenCalled();
    expect(colorSpy).not.toHaveBeenCalled();
    expect(eliminarSpy).not.toHaveBeenCalled();
  });
});
