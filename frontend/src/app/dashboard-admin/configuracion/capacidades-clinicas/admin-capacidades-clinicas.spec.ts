import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { describe, it, expect, beforeEach } from 'vitest';

import { AdminCapacidadesClinicasComponent } from './admin-capacidades-clinicas';
import { environment } from '../../../config';

const API = `${environment.apiUrl}/admin/capacidades-clinicas`;
const CATALOGO = [
  { valor: 'emitir_receta', nombre: 'Receta médica', descripcion: 'd', activa_en_sistema: true },
  { valor: 'emitir_justificativo', nombre: 'Justificativo médico', descripcion: 'd', activa_en_sistema: true },
  { valor: 'emitir_certificado', nombre: 'Certificado', descripcion: 'd', activa_en_sistema: false },
];

function crear() {
  const fixture = TestBed.createComponent(AdminCapacidadesClinicasComponent);
  const http = TestBed.inject(HttpTestingController);
  fixture.detectChanges();
  http.expectOne(API).flush({
    catalogo: CATALOGO,
    especialidades: [{ clave: 'medicina general', nombre: 'Medicina General', profesionales: 2, incluidas: ['emitir_receta'], capacidades: ['emitir_receta'] }],
  });
  fixture.detectChanges();
  return { fixture, c: fixture.componentInstance, http };
}

describe('AdminCapacidadesClinicasComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({
    imports: [AdminCapacidadesClinicasComponent],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  }));

  it('muestra las especialidades con lo que ya tienen marcado', () => {
    const { fixture, c } = crear();
    expect(c.filas).toHaveLength(1);
    expect(c.marcada(c.filas[0], 'emitir_receta')).toBe(true);
    expect(c.marcada(c.filas[0], 'emitir_justificativo')).toBe(false);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Medicina General');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Próximamente');
  });

  it('detecta cambios y guarda solo cuando hay algo distinto', () => {
    const { c, http } = crear();
    const f = c.filas[0];
    expect(c.modificada(f)).toBe(false);
    c.guardar(f);
    http.expectNone(`${API}/medicina%20general`);

    c.alternar(f, 'emitir_justificativo');
    expect(c.modificada(f)).toBe(true);
    c.alternar(f, 'emitir_justificativo');
    expect(c.modificada(f)).toBe(false);          // volver al estado original deja de ser un cambio

    c.alternar(f, 'emitir_justificativo');
    c.guardar(f);
    const req = http.expectOne(`${API}/medicina%20general`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.capacidades.sort()).toEqual(['emitir_justificativo', 'emitir_receta']);
    req.flush({ clave: 'medicina general', nombre: 'Medicina General', profesionales: 2, incluidas: ['emitir_receta'], capacidades: ['emitir_justificativo', 'emitir_receta'] });
    expect(f.mensaje).toBe('Cambios guardados.');
    expect(c.modificada(f)).toBe(false);
  });

  it('si el servidor rechaza, muestra el motivo y conserva la selección', () => {
    const { c, http } = crear();
    const f = c.filas[0];
    c.alternar(f, 'emitir_justificativo');
    c.guardar(f);
    http.expectOne(`${API}/medicina%20general`).flush({ detail: 'No tienes permiso.' }, { status: 403, statusText: 'Forbidden' });
    expect(f.error).toBe('No tienes permiso.');
    expect(c.marcada(f, 'emitir_justificativo')).toBe(true);
    expect(f.guardando).toBe(false);
  });

  it('lo que trae la especialidad de fábrica se muestra incluido y no se puede quitar', () => {
    const { fixture, c } = crear();
    const f = c.filas[0];
    expect(c.deFabrica(f, 'emitir_receta')).toBe(true);
    c.alternar(f, 'emitir_receta');
    expect(c.marcada(f, 'emitir_receta')).toBe(true);
    expect(c.modificada(f)).toBe(false);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Incluida por la especialidad');
  });

  it('avisa si no se pudo cargar', () => {
    const fixture = TestBed.createComponent(AdminCapacidadesClinicasComponent);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne(API).flush({}, { status: 403, statusText: 'Forbidden' });
    expect(fixture.componentInstance.errorCarga).toContain('No tienes permiso');
  });
});
