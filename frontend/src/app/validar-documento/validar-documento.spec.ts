import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { describe, it, expect } from 'vitest';

import { ValidarDocumentoComponent } from './validar-documento';
import { environment } from '../config';

function crear(codigoEnUrl: string | null) {
  TestBed.configureTestingModule({
    imports: [ValidarDocumentoComponent],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: { get: () => codigoEnUrl } } } },
    ],
  });
  const fixture: ComponentFixture<ValidarDocumentoComponent> = TestBed.createComponent(ValidarDocumentoComponent);
  const http = TestBed.inject(HttpTestingController);
  return { fixture, component: fixture.componentInstance, http };
}

describe('ValidarDocumentoComponent', () => {
  it('valida el código ingresado y muestra el documento válido', () => {
    const { fixture, component, http } = crear(null);
    fixture.detectChanges();

    component.onCodigoChange('ses-4k9p-72qx-m8td');
    expect(component.codigo).toBe('SES-4K9P-72QX-M8TD');
    component.validar();

    const req = http.expectOne(`${environment.apiUrl}/documentos/validar/SES-4K9P-72QX-M8TD`);
    req.flush({ valido: true, estado: 'vigente', tipo: 'Receta médica', emitido_por: 'Dra. Ana Pérez',
                fecha_emision: '2026-10-09', estudiante: 'Valentina T. S.' });
    fixture.detectChanges();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Documento válido');
    expect(texto).toContain('Valentina T. S.');
    expect(texto).toContain('09 de octubre de 2026');
  });

  it('al abrir el QR (?codigo=) valida automáticamente', () => {
    const { component, http } = crear('SES-AAAA-BBBB-CCCC');
    component.ngOnInit();
    const req = http.expectOne(`${environment.apiUrl}/documentos/validar/SES-AAAA-BBBB-CCCC`);
    req.flush({ valido: false, estado: 'no_encontrado' });
    expect(component.titulo).toBe('Código no encontrado');
  });

  it('muestra aviso claro si se superó el límite de consultas', () => {
    const { component, http } = crear(null);
    component.codigo = 'SES-AAAA-BBBB-CCCC';
    component.validar();
    http.expectOne(() => true).flush({ detail: 'x' }, { status: 429, statusText: 'Too Many Requests' });
    expect(component.errorRed).toContain('demasiadas consultas');
  });

  it('extrae el código desde la URL del QR', () => {
    const { component } = crear(null);
    const extraer = (component as any).extraerCodigo.bind(component);
    expect(extraer('https://sesaes.cl/validar-documento?codigo=ses-1111-2222-3333')).toBe('SES-1111-2222-3333');
    expect(extraer(' ses-1111-2222-3333 ')).toBe('SES-1111-2222-3333');
  });
});
