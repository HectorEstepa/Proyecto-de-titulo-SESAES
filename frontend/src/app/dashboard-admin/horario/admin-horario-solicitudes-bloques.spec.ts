import { TestBed } from '@angular/core/testing';
import { AdminHorarioComponent } from './admin-horario';

/** Admin: como se muestra una solicitud de agenda por bloques en la tabla de solicitudes. */
describe('AdminHorarioComponent: solicitudes de agenda por bloques', () => {
  let c: AdminHorarioComponent;

  beforeEach(() => {
    c = TestBed.createComponent(AdminHorarioComponent).componentInstance;
  });

  const dia = (d: number, fin: string) => [
    { dia_semana: d, hora_inicio: '09:00', hora_fin: '13:00', tipo: 'disponible' },
    { dia_semana: d, hora_inicio: '13:00', hora_fin: '14:00', tipo: 'colacion' },
    { dia_semana: d, hora_inicio: '14:00', hora_fin: fin, tipo: 'disponible' },
  ];

  it('nombra cada tipo de solicitud', () => {
    expect(c.tipoSolicitudLabel({ tipo: 'bloques' })).toBe('Horario semanal');
    expect(c.tipoSolicitudLabel({ tipo: 'colacion' })).toBe('Colación');
    expect(c.tipoSolicitudLabel({ tipo: 'jornada' })).toBe('Jornada');
  });

  it('jornada y colacion siguen mostrando inicio y fin', () => {
    expect(c.horarioSolicitado({ tipo: 'jornada', hora_inicio: '09:00', hora_fin: '17:00' })).toContain('09:00');
    expect(c.horarioSolicitado({ tipo: 'jornada', hora_inicio: '09:00', hora_fin: '17:00' })).toContain('17:00');
  });

  it('agrupa los dias que quedaron iguales en el resumen de bloques', () => {
    const bloques = [...dia(0, '17:30'), ...dia(1, '17:30'), ...dia(2, '17:30'), ...dia(3, '17:30'), ...dia(4, '16:30')];
    expect(c.horarioSolicitado({ tipo: 'bloques', bloques })).toBe(
      'Lun-Jue: 09:00-13:00, colación 13:00-14:00, 14:00-17:30 | Vie: 09:00-13:00, colación 13:00-14:00, 14:00-16:30'
    );
  });

  it('un dia distinto corta el grupo y los dias sin bloques no aparecen', () => {
    const bloques = [...dia(0, '17:30'), ...dia(2, '17:30')];
    expect(c.horarioSolicitado({ tipo: 'bloques', bloques })).toBe(
      'Lun: 09:00-13:00, colación 13:00-14:00, 14:00-17:30 | Mié: 09:00-13:00, colación 13:00-14:00, 14:00-17:30'
    );
  });
});
