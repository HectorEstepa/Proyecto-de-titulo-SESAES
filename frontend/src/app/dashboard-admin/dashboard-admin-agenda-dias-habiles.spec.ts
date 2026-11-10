import { ChangeDetectorRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { of } from 'rxjs';

import { AuthService } from '../auth.service';
import { Permission } from '../shared/auth/permission.model';
import { ToastService } from '../shared/toast/toast.service';
import { DashboardAdminComponent } from './dashboard-admin';

/**
 * Agenda Admin — días hábiles, horario institucional real y bloque
 * fantasma de un sobrecupo cancelado.
 *
 * Este archivo se mantiene separado de dashboard-admin.spec.ts porque ese
 * spec arrastra referencias a una función de "sobrecupo manual" que aún no
 * existe en el componente (ver CAMBIOS_PR.md) y hoy impide compilar la
 * suite completa. Estas pruebas cubren solo los tres arreglos de agenda y
 * no dependen de esa función.
 */
function crearShellYHttp(permisos: Permission[]) {
  const permitidos = new Set<Permission>(permisos);

  const auth = {
    hasPermission: vi.fn((permission: Permission) => permitidos.has(permission)),
    getNombre: vi.fn(() => null),
    getFotoUrl: vi.fn(() => null),
    getRol: vi.fn(() => null),
    getUsuarioId: vi.fn(() => null),
    cargarAccesoAdministrativo: vi.fn(() => of({}))
  } as unknown as AuthService;

  const http = {
    get: vi.fn((_url: string) => of([])),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  };
  const toast = { success: vi.fn(), error: vi.fn() } as unknown as ToastService;
  const router = {} as Router;
  const cdr = { detectChanges: vi.fn() } as unknown as ChangeDetectorRef;

  return {
    component: new DashboardAdminComponent(
      router,
      http as unknown as HttpClient,
      cdr,
      toast,
      auth
    ),
    http
  };
}

describe('DashboardAdminComponent — agenda de lunes a viernes y horario institucional', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const fijarHoy = (fecha: Date): void => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(fecha);
  };

  const crearAgendaAdmin = (duracionMin = 60) => {
    const { component, http } = crearShellYHttp(['agenda.ver', 'agenda.gestionar']);
    component.profesionales = [
      {
        id: 20,
        nombre: 'Dra. Pérez',
        especialidad: 'Medicina General',
        duracion_min: duracionMin,
        estado: 'activo'
      }
    ];
    component.filtroProfesionalId = '20';
    component.generarSemanaActual();
    return { component, http };
  };

  const urlsDisponibilidad = (http: { get: { mock: { calls: unknown[][] } } }): string[] =>
    http.get.mock.calls
      .map(call => String(call[0]))
      .filter(url => url.includes('/disponibilidad'));

  it('la grilla arranca a las 09:00 (no 08:00) y termina antes del cierre de 17:30', () => {
    fijarHoy(new Date(2026, 8, 16, 10, 0, 0));
    const { component } = crearAgendaAdmin(60);

    const horas = component.horasGrilla;

    expect(horas[0]).toBe('09:00');
    expect(horas).not.toContain('08:00');
    expect(horas).not.toContain('17:30');
    expect(horas).not.toContain('18:00');
    // Último bloque de 60 min que alcanza a empezar antes de las 17:30.
    expect(horas[horas.length - 1]).toBe('17:00');
  });

  it('respeta la duración de atención del profesional dentro del horario institucional', () => {
    fijarHoy(new Date(2026, 8, 16, 10, 0, 0));
    const { component } = crearAgendaAdmin(45);

    const horas = component.horasGrilla;

    expect(horas[0]).toBe('09:00');
    expect(horas[1]).toBe('09:45');
    expect(horas[horas.length - 1]).toBe('17:15');
    expect(horas.every(hora => hora >= '09:00' && hora < '17:30')).toBe(true);
  });

  it('el rótulo del período termina el viernes, pero la semana interna sigue siendo lunes a domingo', () => {
    // Miércoles 16 de septiembre de 2026 → semana del 14 al 20.
    fijarHoy(new Date(2026, 8, 16, 10, 0, 0));
    const { component, http } = crearAgendaAdmin();

    // Solo se nombra lunes a viernes: el rótulo no debe sugerir que la
    // grilla llega al domingo.
    expect(component.semanaActual[0].fecha).toBe('2026-09-14');
    expect(component.semanaLabel).toBe('Semana 14 – 18 Septiembre 2026');

    component.cargarHorarioProfesional();

    // El rango consultado no se recorta: sábado y domingo vuelven de
    // backend como 'fin_de_semana' y es la grilla la que no los pinta
    // (ver soloDiasLaborables en admin-horario).
    const urls = urlsDisponibilidad(http);
    expect(urls).toHaveLength(1);
    expect(urls[0]).toContain('fecha_inicio=2026-09-14');
    expect(urls[0]).toContain('fecha_fin=2026-09-20');
  });

  it('al cancelar un sobrecupo se vuelve a consultar la disponibilidad: el bloque no queda fantasma', () => {
    fijarHoy(new Date(2026, 8, 16, 10, 0, 0));
    const { component, http } = crearAgendaAdmin();

    // Mientras el sobrecupo existe, backend informa la hora como ocupada.
    // Después de cancelarlo, la misma hora queda disponible: lo que se
    // prueba es que la cancelación obliga a releer ese estado en vez de
    // conservar el que se calculó con el sobrecupo encima.
    let motivoSlot: string | null = 'slot_ocupado';
    (http.get as any).mockImplementation((url: string) => {
      if (!url.includes('/disponibilidad')) return of([]);
      return of({
        profesional_id: 20,
        fecha_inicio: '2026-09-14',
        fecha_fin: '2026-09-20',
        duracion_min: 60,
        dias: [{
          fecha: '2026-09-16',
          slots: [{
            hora: '10:00',
            disponible: motivoSlot === null,
            motivo: motivoSlot,
            overridable_con_sobrecupo: false
          }]
        }]
      });
    });

    component.cargarHorarioProfesional();
    expect(component.getBloqueEstado('2026-09-16', '10:00')).toBe('ocupado');

    motivoSlot = null;
    http.patch.mockReturnValue(of({ message: 'Cita cancelada y estudiante notificado' }));
    vi.stubGlobal('confirm', vi.fn(() => true));

    const llamadasAntes = http.get.mock.calls.length;
    component.cancelarCitaAdmin({
      id: 77,
      estudiante: 'Ana Torres',
      fecha: '2026-09-16',
      hora: '10:00',
      estado: 'pendiente',
      sobrecupo: true
    });

    expect(http.patch).toHaveBeenCalledWith(
      expect.stringContaining('/admin/citas/77/cancelar'),
      expect.objectContaining({ motivo: 'Cancelada por administrador' })
    );

    const urlsRefresco = http.get.mock.calls
      .slice(llamadasAntes)
      .map(call => String(call[0]));
    expect(urlsRefresco.some(url => url.includes('/agenda/profesional/20/citas'))).toBe(true);
    expect(urlsRefresco.some(url => url.includes('/disponibilidad'))).toBe(true);

    // La celda deja de mostrar el estado que tenía con el sobrecupo: ya no
    // hay ninguna cita y la disponibilidad real es "disponible".
    expect(component.getBloqueEstado('2026-09-16', '10:00')).toBe('disponible');
  });
});
