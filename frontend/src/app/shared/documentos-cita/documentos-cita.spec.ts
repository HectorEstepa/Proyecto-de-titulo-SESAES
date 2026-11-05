import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { describe, it, expect, beforeEach } from 'vitest';

import { DocumentosCitaComponent, DocumentoResumen } from './documentos-cita';
import { environment } from '../../config';

const API = environment.apiUrl;
const docs = (): DocumentoResumen[] => [
  { id: 1, tipo: 'receta', nombre_tipo: 'Receta médica', folio: 'SES-AAAA-BBBB-CCCC', estado: 'vigente' },
  { id: 2, tipo: 'justificativo', nombre_tipo: 'Justificativo médico', folio: 'SES-DDDD-EEEE-FFFF', estado: 'anulado' },
];

function crear(modoProfesional: boolean) {
  const fixture = TestBed.createComponent(DocumentosCitaComponent);
  fixture.componentInstance.documentos = docs();
  fixture.componentInstance.modoProfesional = modoProfesional;
  fixture.detectChanges();
  return { fixture, c: fixture.componentInstance, http: TestBed.inject(HttpTestingController), el: fixture.nativeElement as HTMLElement };
}

describe('DocumentosCitaComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({
    imports: [DocumentosCitaComponent],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  }));

  it('el estudiante ve sus documentos, el folio y cuál está anulado, sin opción de anular', () => {
    const { el } = crear(false);
    expect(el.textContent).toContain('Receta médica');
    expect(el.textContent).toContain('SES-AAAA-BBBB-CCCC');
    expect(el.querySelectorAll('.dc-etiqueta')).toHaveLength(1);
    expect(el.textContent).not.toContain('Anular documento');
    expect(el.querySelectorAll('.dc-btn-peligro')).toHaveLength(0);
  });

  it('el profesional puede anular solo lo que sigue vigente', () => {
    const { el } = crear(true);
    expect(el.querySelectorAll('.dc-btn-peligro')).toHaveLength(1);
  });

  it('descarga el PDF con una petición autenticada (no con un enlace)', () => {
    const { c, http } = crear(false);
    c.descargar(c.documentos[0]);
    const req = http.expectOne(`${API}/documentos/1/pdf`);
    expect(req.request.method).toBe('GET');
    expect(req.request.responseType).toBe('blob');
  });

  it('un error de descarga muestra un mensaje claro', () => {
    const { c, http } = crear(false);
    c.descargar(c.documentos[0]);
    http.expectOne(`${API}/documentos/1/pdf`).flush(new Blob(), { status: 403, statusText: 'Forbidden' });
    expect(c.error).toContain('No tienes permisos');
    expect(c.descargando).toBeNull();
  });

  it('anular exige un motivo, llama al backend y avisa al padre', () => {
    const { c, http } = crear(true);
    let avisos = 0;
    c.cambio.subscribe(() => avisos++);

    c.pedirAnulacion(c.documentos[0]);
    c.motivo = 'ab';
    expect(c.motivoValido).toBe(false);
    c.confirmarAnulacion();
    http.expectNone(`${API}/documentos/1/anular`);

    c.motivo = '  error de dosis ';
    c.confirmarAnulacion();
    const req = http.expectOne(`${API}/documentos/1/anular`);
    expect(req.request.body).toEqual({ motivo: 'error de dosis' });
    req.flush({ message: 'Documento anulado', estado: 'anulado' });

    expect(c.documentos[0].estado).toBe('anulado');
    expect(c.anulando).toBeNull();
    expect(avisos).toBe(1);
  });

  it('si el servidor rechaza la anulación, muestra el motivo', () => {
    const { c, http } = crear(true);
    c.pedirAnulacion(c.documentos[0]);
    c.motivo = 'error de dosis';
    c.confirmarAnulacion();
    http.expectOne(`${API}/documentos/1/anular`).flush({ detail: 'El documento ya está anulado.' }, { status: 409, statusText: 'Conflict' });
    expect(c.error).toBe('El documento ya está anulado.');
    expect(c.documentos[0].estado).toBe('vigente');
  });
});
