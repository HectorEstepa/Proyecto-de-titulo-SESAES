import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { describe, it, expect, beforeEach } from 'vitest';

import { CompletarAtencionComponent } from './completar-atencion';
import { environment } from '../../config';

const API = environment.apiUrl;
const CITA = { id: 7, fecha: '2026-10-09', hora: '10:30', medicamento: null, observaciones_atencion: null };
const TODAS = ['registrar_medicamento_suministrado', 'emitir_receta', 'emitir_justificativo'];

function crear(capacidades: string[] | 'error') {
  const fixture: ComponentFixture<CompletarAtencionComponent> = TestBed.createComponent(CompletarAtencionComponent);
  const c = fixture.componentInstance;
  c.cita = CITA;
  c.profId = 5;
  c.paciente = { nombre: 'Valentina Torres Silva', rut: '19.876.543-2', carrera: 'Estudiante' };
  fixture.detectChanges();

  const http = TestBed.inject(HttpTestingController);
  const req = http.expectOne(`${API}/profesional/capacidades-clinicas`);
  if (capacidades === 'error') req.flush({}, { status: 500, statusText: 'Error' });
  else req.flush({ capacidades });
  fixture.detectChanges();
  return { fixture, c, http };
}

describe('CompletarAtencionComponent', () => {
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      imports: [CompletarAtencionComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
  });

  it('solo ofrece receta y justificativo si la especialidad tiene la capacidad', () => {
    const { fixture } = crear(['emitir_justificativo']);
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Justificativo médico');
    expect(texto).not.toContain('¿Se emite receta');
  });

  it('sin capacidades (o si falla la consulta) no ofrece documentos: fail-closed', () => {
    const { c, fixture } = crear('error');
    expect(c.puedeReceta).toBe(false);
    expect(c.puedeJustificativo).toBe(false);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('no tiene habilitada la emisión');
  });

  it('sin documentos activos el payload solo lleva las observaciones', () => {
    const { c } = crear(TODAS);
    c.observaciones = '  Paciente estable  ';
    expect(c.construirPayload()).toEqual({ observaciones_atencion: 'Paciente estable', medicamento: null });
  });

  it('receta activa sin medicamento completo bloquea la revisión', () => {
    const { c } = crear(TODAS);
    c.recetaActiva = true;
    expect(c.problemas.length).toBe(1);
    expect(c.puedeRevisar).toBe(false);
    c.irARevisar();
    expect(c.paso).toBe('editar');

    c.items[0] = { ...c.items[0], medicamento: 'Amoxicilina 500 mg', dosis: '1 cápsula', frecuencia: 'Cada 8 horas', periodo: '7 días' };
    expect(c.problemas).toEqual([]);
    c.irARevisar();
    expect(c.paso).toBe('revisar');
  });

  it('el payload incluye la receta limpia y omite opcionales vacíos', () => {
    const { c } = crear(TODAS);
    c.recetaActiva = true;
    c.items = [
      { medicamento: ' Amoxicilina 500 mg ', dosis: '1 cápsula', via: 'Oral', frecuencia: 'Cada 8 horas', periodo: '7 días', cantidad: '', marca: '', indicacion: 'Con alimentos' },
      { medicamento: '', dosis: '', via: 'Oral', frecuencia: '', periodo: '', cantidad: '', marca: '', indicacion: '' },
    ];
    const body = c.construirPayload();
    expect(body.receta.medicamentos).toEqual([
      { medicamento: 'Amoxicilina 500 mg', dosis: '1 cápsula', via: 'Oral', frecuencia: 'Cada 8 horas', periodo: '7 días', cantidad: null, marca: null, indicacion: 'Con alimentos' },
    ]);
    expect(body.justificativo).toBeUndefined();
  });

  it('justificativo: el reposo exige fechas coherentes y calcula los días', () => {
    const { c } = crear(TODAS);
    c.justActiva = true;
    c.just.reposo = true;
    expect(c.problemas.length).toBe(1);

    c.just.reposo_desde = '2026-10-09';
    c.just.reposo_hasta = '2026-10-07';
    expect(c.problemas[0]).toContain('no puede ser anterior');

    c.just.reposo_hasta = '2026-10-11';
    expect(c.problemas).toEqual([]);
    expect(c.diasReposo).toBe(3);
    expect(c.construirPayload().justificativo).toMatchObject({ reposo: true, reposo_desde: '2026-10-09', reposo_hasta: '2026-10-11' });
  });

  it('lo desactivado no viaja aunque haya datos cargados', () => {
    const { c } = crear(TODAS);
    c.recetaActiva = false;
    c.items[0].medicamento = 'X'; c.items[0].dosis = '1'; c.items[0].frecuencia = '8h'; c.items[0].periodo = '3d';
    c.justActiva = false;
    const body = c.construirPayload();
    expect(body.receta).toBeUndefined();
    expect(body.justificativo).toBeUndefined();
  });

  it('guardar y completar envía el PATCH, emite los documentos y borra el borrador', () => {
    const { c, http } = crear(TODAS);
    let emitidos: any = null;
    c.completada.subscribe(d => (emitidos = d));

    c.justActiva = true;                                  // justificativo sin reposo
    c.guardarBorrador(true);
    expect(sessionStorage.getItem('sesaes_borrador_atencion_7')).not.toBeNull();

    c.irARevisar();
    c.guardarYCompletar();
    const req = http.expectOne(`${API}/profesional/5/citas/7/completar`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.justificativo.reposo).toBe(false);
    req.flush({ message: 'ok', documentos: [{ id: 1, tipo: 'justificativo', nombre_tipo: 'Justificativo médico', folio: 'SES-AAAA-BBBB-CCCC' }] });

    expect(emitidos).toHaveLength(1);
    expect(sessionStorage.getItem('sesaes_borrador_atencion_7')).toBeNull();
    c.ngOnDestroy();                                      // cerrar no debe resucitar el borrador
    expect(sessionStorage.getItem('sesaes_borrador_atencion_7')).toBeNull();
  });

  it('si el servidor rechaza, muestra el motivo, vuelve a editar y conserva lo escrito', () => {
    const { c, http } = crear(TODAS);
    c.observaciones = 'Importante';
    c.irARevisar();
    c.guardarYCompletar();
    http.expectOne(`${API}/profesional/5/citas/7/completar`)
      .flush({ detail: 'Esta atención ya tiene una receta vigente. Anúlala antes de emitir otra.' }, { status: 409, statusText: 'Conflict' });

    expect(c.error).toContain('ya tiene una receta vigente');
    expect(c.paso).toBe('editar');
    expect(c.observaciones).toBe('Importante');
    expect(c.enviando).toBe(false);
  });

  it('recupera el borrador al reabrir y permite empezar de cero', () => {
    const a = crear(TODAS);
    a.c.observaciones = 'Texto a medias';
    a.c.guardarBorrador(true);
    a.fixture.destroy();

    const b = crear(TODAS);
    expect(b.c.observaciones).toBe('Texto a medias');
    expect(b.c.borradorRecuperado).toBe(true);
    b.c.empezarDeCero();
    expect(b.c.observaciones).toBe('');
    expect(sessionStorage.getItem('sesaes_borrador_atencion_7')).toBeNull();
  });

  it('un borrador con receta activa no la reactiva si la capacidad ya no existe', () => {
    sessionStorage.setItem('sesaes_borrador_atencion_7', JSON.stringify({
      observaciones: '', medicamento: 'Ibuprofeno', recetaActiva: true,
      items: [{ medicamento: 'A', dosis: '1', via: 'Oral', frecuencia: '8h', periodo: '3d', cantidad: '', marca: '', indicacion: '' }],
      justActiva: true, just: {}
    }));
    const { c } = crear([]);
    expect(c.recetaActiva).toBe(false);
    expect(c.justActiva).toBe(false);
    expect(c.medicamento).toBe('');
    expect(c.construirPayload()).toEqual({ observaciones_atencion: null, medicamento: null });
  });
});
