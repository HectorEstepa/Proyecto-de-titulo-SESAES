import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { describe, it, expect, beforeEach } from 'vitest';

import { CuestionarioOpcionalComponent } from './cuestionario-opcional';
import { environment } from '../../config';

const API = environment.apiUrl;
const CONFIG = `${API}/historial-clinico/config-cuestionario/5`;
const DECISION = `${API}/historial-clinico/5/99/cuestionario`;

function crear(solicitado = false, yaExiste = false, porDefecto = false) {
  const fixture = TestBed.createComponent(CuestionarioOpcionalComponent);
  const c = fixture.componentInstance;
  c.profId = 5; c.estudianteId = 99; c.solicitado = solicitado; c.yaExiste = yaExiste;
  const http = TestBed.inject(HttpTestingController);
  fixture.detectChanges();
  http.expectOne(CONFIG).flush({ enviar_por_defecto: porDefecto });
  fixture.detectChanges();
  return { fixture, c, http, el: fixture.nativeElement as HTMLElement };
}

describe('CuestionarioOpcionalComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({
    imports: [CuestionarioOpcionalComponent],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  }));

  it('por defecto el cuestionario NO se envía y se puede enviar', () => {
    const { c, http, el } = crear();
    expect(el.textContent).toContain('No se enviará');
    let avisos = 0; c.cambio.subscribe(() => avisos++);
    c.enviar();
    const req = http.expectOne(DECISION);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ solicitar: true });
    req.flush({ cuestionario_solicitado: true });
    expect(avisos).toBe(1);
  });

  it('si está solicitado se puede omitir, y volver al ajuste general borra la decisión puntual', () => {
    const { c, http, el } = crear(true);
    expect(el.textContent).toContain('Se enviará al estudiante');

    c.noEnviar();
    const omitir = http.expectOne(DECISION);
    expect(omitir.request.body).toEqual({ solicitar: false });
    omitir.flush({ cuestionario_solicitado: false });

    c.usarAjusteGeneral();
    const quitar = http.expectOne(DECISION);
    expect(quitar.request.method).toBe('DELETE');
    quitar.flush({ cuestionario_solicitado: false });
  });

  it('el ajuste general se guarda y se refleja', () => {
    const { c, http } = crear(false, false, false);
    c.cambiarAjusteGeneral(true);
    const req = http.expectOne(CONFIG);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ enviar_por_defecto: true });
    req.flush({ enviar_por_defecto: true });
    expect(c.porDefecto).toBe(true);
  });

  it('si el estudiante ya tiene ficha no ofrece enviar nada', () => {
    const { el } = crear(false, true);
    expect(el.textContent).toContain('Ya completado');
    expect(el.textContent).not.toContain('Enviar cuestionario');
  });

  it('un error del servidor se muestra y no se pierde el estado', () => {
    const { c, http } = crear();
    c.enviar();
    http.expectOne(DECISION).flush({ detail: 'Este estudiante ya tiene su ficha de antecedentes.' }, { status: 400, statusText: 'Bad Request' });
    expect(c.error).toBe('Este estudiante ya tiene su ficha de antecedentes.');
    expect(c.guardando).toBe(false);
  });
});
