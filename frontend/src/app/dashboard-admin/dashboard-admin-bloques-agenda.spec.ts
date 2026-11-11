import { ChangeDetectorRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { describe, expect, it, vi } from 'vitest';
import { of } from 'rxjs';

import { AuthService } from '../auth.service';
import { Permission } from '../shared/auth/permission.model';
import { ToastService } from '../shared/toast/toast.service';
import { DashboardAdminComponent } from './dashboard-admin';

/**
 * Agenda compartida (Admin / Super Admin) — horario semanal POR BLOQUES
 * aprobado como bloqueo ESTRICTO.
 *
 * Cubre solo la capa de presentación/decisión del shell:
 *   - el flag `bloqueado_por_horario_aprobado` (calculado en backend)
 *     se traduce a los estados visuales 'bloqueado-horario' /
 *     'colacion-aprobada';
 *   - las celdas bloqueadas no abren el formulario de nueva cita ni el
 *     flujo de sobrecupo, aunque el usuario tenga agenda.gestionar +
 *     agenda.sobrecupo;
 *   - una hora escrita a mano en el modal tampoco se envía.
 *
 * La regla real (qué es "horario aprobado") NO se reimplementa acá: se
 * prueba en backend (tests/test_agenda_bloques.py).
 */

const FUTURA = '2099-11-10';           // fecha siempre futura
const FUTURA_SABADO = '2099-11-14';

type Permiso = Permission;

function crearShell(permisos: Permiso[]) {
  const permitidos = new Set<Permiso>(permisos);
  const auth = {
    hasPermission: vi.fn((permission: Permiso) => permitidos.has(permission)),
    getNombre: vi.fn(() => null),
    getFotoUrl: vi.fn(() => null),
    getRol: vi.fn(() => null),
    getUsuarioId: vi.fn(() => null),
    cargarAccesoAdministrativo: vi.fn(() => of({}))
  } as unknown as AuthService;

  const http = {
    get: vi.fn((url: string) => of([])),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  };
  const toast = { success: vi.fn(), error: vi.fn() } as unknown as ToastService;
  const router = {} as Router;
  const cdr = { detectChanges: vi.fn() } as unknown as ChangeDetectorRef;

  const component = new DashboardAdminComponent(
    router,
    http as unknown as HttpClient,
    cdr,
    toast,
    auth
  );

  return { component, http };
}

function cargarSlots(
  component: DashboardAdminComponent,
  fecha: string,
  slots: Record<string, Partial<{
    disponible: boolean;
    motivo: string | null;
    overridable_con_sobrecupo: boolean;
    bloqueado_por_horario_aprobado: boolean;
  }>>
): void {
  const mapa: Record<string, any> = {};
  for (const [hora, slot] of Object.entries(slots)) {
    mapa[hora] = {
      hora,
      disponible: false,
      motivo: null,
      overridable_con_sobrecupo: false,
      bloqueado_por_horario_aprobado: false,
      ...slot
    };
  }
  (component as any).disponibilidadPorFecha = { [fecha]: mapa };
}

describe('DashboardAdminComponent — horario aprobado por bloques (bloqueo estricto)', () => {
  it('traduce el flag de backend a los estados visuales de bloqueo', () => {
    const { component } = crearShell(['agenda.ver']);
    cargarSlots(component, FUTURA, {
      '09:00': { disponible: true },
      '10:00': { motivo: 'fuera_de_jornada', bloqueado_por_horario_aprobado: true },
      '13:00': { motivo: 'en_colacion', bloqueado_por_horario_aprobado: true },
    });

    expect(component.getBloqueEstado(FUTURA, '09:00')).toBe('disponible');
    expect(component.getBloqueEstado(FUTURA, '10:00')).toBe('bloqueado-horario');
    expect(component.getBloqueEstado(FUTURA, '13:00')).toBe('colacion-aprobada');
  });

  it('sin el flag, la jornada simple conserva sus estados de siempre', () => {
    const { component } = crearShell(['agenda.ver']);
    cargarSlots(component, FUTURA, {
      '10:00': { motivo: 'fuera_de_jornada', overridable_con_sobrecupo: true },
      '13:00': { motivo: 'en_colacion', overridable_con_sobrecupo: true },
    });

    expect(component.getBloqueEstado(FUTURA, '10:00')).toBe('fuera-horario');
    expect(component.getBloqueEstado(FUTURA, '13:00')).toBe('colacion');
  });

  it('las celdas bloqueadas no abren el modal de nueva cita', () => {
    const { component } = crearShell(['agenda.ver', 'agenda.gestionar', 'agenda.sobrecupo']);
    component.filtroProfesionalId = '20';
    cargarSlots(component, FUTURA, {
      '10:00': { motivo: 'fuera_de_jornada', bloqueado_por_horario_aprobado: true },
      '13:00': { motivo: 'en_colacion', bloqueado_por_horario_aprobado: true },
    });

    component.clickBloque(FUTURA, '10:00');
    component.clickBloque(FUTURA, '13:00');

    expect(component.modalCitaAbierto).toBe(false);
    expect(component.sobrecupoConfirmAbierto).toBe(false);
  });

  it('ni admin ni super admin pueden solicitar sobrecupo sobre el horario aprobado', () => {
    const { component } = crearShell(['agenda.ver', 'agenda.gestionar', 'agenda.sobrecupo']);
    component.filtroProfesionalId = '20';
    cargarSlots(component, FUTURA, {
      '10:00': { motivo: 'fuera_de_jornada', bloqueado_por_horario_aprobado: true },
      '13:00': { motivo: 'en_colacion', bloqueado_por_horario_aprobado: true },
    });

    expect(component.puedeSolicitarSobrecupo(FUTURA, '10:00')).toBe(false);
    expect(component.puedeSolicitarSobrecupo(FUTURA, '13:00')).toBe(false);
  });

  it('abrirModalNuevaCitaConFechaHora rechaza una hora bloqueada del horario aprobado', () => {
    const { component } = crearShell(['agenda.ver', 'agenda.gestionar', 'agenda.sobrecupo']);
    component.filtroProfesionalId = '20';
    cargarSlots(component, FUTURA, {
      '10:00': { motivo: 'fuera_de_jornada', bloqueado_por_horario_aprobado: true },
    });

    component.abrirModalNuevaCitaConFechaHora(FUTURA, '10:00', false);
    component.abrirModalNuevaCitaConFechaHora(FUTURA, '10:00', true);

    expect(component.modalCitaAbierto).toBe(false);
  });

  it('crearCitaDesdeHorario no envía la petición si la hora escrita cae en el bloqueo', () => {
    const { component, http } = crearShell(['agenda.ver', 'agenda.gestionar', 'agenda.sobrecupo']);
    component.filtroProfesionalId = '20';
    cargarSlots(component, FUTURA, {
      '10:00': { motivo: 'en_colacion', bloqueado_por_horario_aprobado: true },
    });
    component.nuevaCita = {
      fecha: FUTURA, hora: '10:00', estudiante_id: 5, profesional_id: 20,
      observaciones: '', urgente: false, sobrecupo: false
    };

    component.crearCitaDesdeHorario();

    expect(http.post).not.toHaveBeenCalled();
    expect(component.mensajeError).toContain('horario semanal aprobado');
  });

  it('crearCitaDesdeHorario normaliza horas escritas sin cero de relleno', () => {
    const { component, http } = crearShell(['agenda.ver', 'agenda.gestionar']);
    component.filtroProfesionalId = '20';
    cargarSlots(component, FUTURA, {
      '09:00': { motivo: 'fuera_de_jornada', bloqueado_por_horario_aprobado: true },
    });
    component.nuevaCita = {
      fecha: FUTURA, hora: '9:00', estudiante_id: 5, profesional_id: 20,
      observaciones: '', urgente: false, sobrecupo: false
    };

    component.crearCitaDesdeHorario();

    expect(http.post).not.toHaveBeenCalled();
  });

  it('la hora libre del mismo profesional sigue abriendo el modal', () => {
    const { component } = crearShell(['agenda.ver', 'agenda.gestionar']);
    component.filtroProfesionalId = '20';
    cargarSlots(component, FUTURA, {
      '09:00': { disponible: true },
      '10:00': { motivo: 'fuera_de_jornada', bloqueado_por_horario_aprobado: true },
    });

    component.clickBloque(FUTURA, '09:00');

    expect(component.modalCitaAbierto).toBe(true);
    expect(component.nuevaCita.hora).toBe('09:00');
    expect(component.nuevaCita.sobrecupo).toBe(false);
  });

  it('un día cerrado del centro conserva su estado, aunque el profesional no tenga bloques ese día', () => {
    const { component } = crearShell(['agenda.ver']);
    cargarSlots(component, FUTURA_SABADO, {
      '10:00': { motivo: 'fin_de_semana', bloqueado_por_horario_aprobado: false },
    });

    expect(component.getBloqueEstado(FUTURA_SABADO, '10:00')).toBe('cerrado-centro');
  });

  it('la grilla del admin es la MISMA serie que evalúa backend (duración 45 por defecto)', () => {
    const { component } = crearShell(['agenda.ver']);
    (component as any).profesionales = [{ id: 20, nombre: 'Dra. X', duracion_min: 45 }];
    component.filtroProfesionalId = '20';

    const horas = component.horasGrilla;

    // Backend: 08:00 + k·45. Desde las 09:00 con paso 45 no coincidiría
    // ninguna hora y la disponibilidad nunca se reflejaría.
    expect(horas[0]).toBe('09:30');
    expect(horas.every(hora => {
      const [h, m] = hora.split(':').map(Number);
      return (h * 60 + m - 8 * 60) % 45 === 0;
    })).toBe(true);
  });

  it('usa las horas que devolvió backend y refleja su disponibilidad', () => {
    const { component, http } = crearShell(['agenda.ver']);
    (component as any).profesionales = [{ id: 20, nombre: 'Dra. X', duracion_min: 45 }];
    component.generarSemanaActual();
    const lunes = component.semanaActual[0].fecha;
    const domingo = component.semanaActual[6].fecha;

    const respuesta = {
      profesional_id: 20, fecha_inicio: lunes, fecha_fin: domingo, duracion_min: 45,
      dias: [{
        fecha: lunes,
        slots: [
          { hora: '09:30', disponible: false, motivo: 'fuera_de_jornada',
            overridable_con_sobrecupo: false, bloqueado_por_horario_aprobado: true },
          { hora: '10:15', disponible: true, motivo: null,
            overridable_con_sobrecupo: false, bloqueado_por_horario_aprobado: false },
        ]
      }]
    };
    (http.get as any).mockImplementation((url: string) =>
      of(url.includes('/disponibilidad') ? respuesta : [])
    );

    component.filtroProfesionalId = '20';
    component.cargarHorarioProfesional();

    expect(component.horasGrilla).toEqual(['09:30', '10:15']);
    expect(component.getBloqueEstado(lunes, '09:30')).toBe('bloqueado-horario');
    expect(component.getBloqueEstado(lunes, '10:15')).toBe('disponible');
  });
});
