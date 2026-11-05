import { describe, it, expect, vi } from 'vitest';
import { AdminInicioComponent } from './admin-inicio';

/**
 * AdminInicioComponent no tiene dependencias inyectadas en su constructor,
 * así que se puede instanciar directamente para probar sus métodos puros
 * sin necesidad de TestBed.
 */
describe('AdminInicioComponent.nombreConTratamiento', () => {
  const componente = new AdminInicioComponent();

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

  it('no antepone nada si no hay tratamiento (null)', () => {
    const resultado = componente.nombreConTratamiento({
      nombre: 'Carlos Muñoz',
      tratamiento: null
    });
    expect(resultado).toBe('Carlos Muñoz');
  });

  it('no antepone nada si no hay tratamiento (undefined / campo ausente)', () => {
    const resultado = componente.nombreConTratamiento({
      nombre: 'Carlos Muñoz'
    });
    expect(resultado).toBe('Carlos Muñoz');
  });

  it('no antepone nada si tratamiento es cadena vacía', () => {
    const resultado = componente.nombreConTratamiento({
      nombre: 'Carlos Muñoz',
      tratamiento: ''
    });
    expect(resultado).toBe('Carlos Muñoz');
  });

  it('reconoce otros prefijos históricos además de Dr./Dra. (Psic., Klgo., Nut.)', () => {
    expect(componente.nombreConTratamiento({ nombre: 'Psic. Roberto Fuentes', tratamiento: 'Psic.' }))
      .toBe('Psic. Roberto Fuentes');
    expect(componente.nombreConTratamiento({ nombre: 'Klgo. Diego Soto', tratamiento: 'Klgo.' }))
      .toBe('Klgo. Diego Soto');
    expect(componente.nombreConTratamiento({ nombre: 'Nut. Carlos Muñoz', tratamiento: 'Nut.' }))
      .toBe('Nut. Carlos Muñoz');
  });

  it('recorta espacios sobrantes del nombre antes de anteponer', () => {
    const resultado = componente.nombreConTratamiento({
      nombre: '  Ana Martínez  ',
      tratamiento: 'Dra.'
    });
    expect(resultado).toBe('Dra. Ana Martínez');
  });
});

describe('AdminInicioComponent — SA-10.2B read-only vs gestionar', () => {
  it('sin agenda.gestionar no emite inasistencia ni cancelación aunque se invoquen los handlers', () => {
    const componente = new AdminInicioComponent();
    const cita = { id: 21, estudiante: 'Ana Soto' };
    const inasistenciaSpy = vi.spyOn(componente.marcarInasistenciaCita, 'emit');
    const cancelarSpy = vi.spyOn(componente.cancelarCita, 'emit');

    componente.puedeGestionarAgenda = false;
    componente.marcarInasistencia(cita);
    componente.cancelarCitaAdmin(cita);

    expect(inasistenciaSpy).not.toHaveBeenCalled();
    expect(cancelarSpy).not.toHaveBeenCalled();
  });

  it('con agenda.gestionar sí emite las intenciones de inasistencia y cancelación', () => {
    const componente = new AdminInicioComponent();
    const cita = { id: 22, estudiante: 'Bruno Ríos' };
    const inasistenciaSpy = vi.spyOn(componente.marcarInasistenciaCita, 'emit');
    const cancelarSpy = vi.spyOn(componente.cancelarCita, 'emit');

    componente.puedeGestionarAgenda = true;
    componente.marcarInasistencia(cita);
    componente.cancelarCitaAdmin(cita);

    expect(inasistenciaSpy).toHaveBeenCalledWith(cita);
    expect(cancelarSpy).toHaveBeenCalledWith(cita);
  });
});

describe('AdminInicioComponent — SA-10.2C agenda.ver', () => {
  it('sin agenda.ver no emite navegación ni refresh de disponibilidad', () => {
    const componente = new AdminInicioComponent();
    const agendaSpy = vi.spyOn(componente.verAgenda, 'emit');
    const refreshSpy = vi.spyOn(componente.actualizarDisponibilidad, 'emit');

    componente.puedeVerAgenda = false;
    componente.navegarA('horario');
    componente.refrescarDisponibilidad();

    expect(agendaSpy).not.toHaveBeenCalled();
    expect(refreshSpy).not.toHaveBeenCalled();
  });

  it('con agenda.ver permite navegación y refresh sin requerir agenda.gestionar', () => {
    const componente = new AdminInicioComponent();
    const agendaSpy = vi.spyOn(componente.verAgenda, 'emit');
    const refreshSpy = vi.spyOn(componente.actualizarDisponibilidad, 'emit');

    componente.puedeVerAgenda = true;
    componente.puedeGestionarAgenda = false;
    componente.navegarA('horario');
    componente.refrescarDisponibilidad();

    expect(agendaSpy).toHaveBeenCalledTimes(1);
    expect(refreshSpy).toHaveBeenCalledTimes(1);
  });
});
