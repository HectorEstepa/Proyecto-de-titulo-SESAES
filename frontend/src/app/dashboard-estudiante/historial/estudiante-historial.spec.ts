import { ComponentFixture, TestBed } from '@angular/core/testing';
import { EstudianteHistorialComponent } from './estudiante-historial';

describe('EstudianteHistorialComponent — Mis atenciones', () => {
  let component: EstudianteHistorialComponent;
  let fixture: ComponentFixture<EstudianteHistorialComponent>;

  const doc = (id: number, tipo = 'receta', estado = 'vigente') =>
    ({ id, tipo, nombre_tipo: tipo === 'receta' ? 'Receta médica' : 'Justificativo médico', folio: `F-${id}`, estado });

  const crearHistorial = (): any[] => [
    { id: 1, iniciales: 'CM', profesional: 'Carlos Muñoz', especialidad: 'Nutrición', fecha: '2026-07-20', fechaRaw: '2026-07-20', hora: '06:45', estado: 'completada', tiene_pdf: true, documentos: [doc(10), doc(11, 'justificativo')] },
    { id: 2, iniciales: 'AM', profesional: 'Dra. Ana Martínez', especialidad: 'Medicina General', fecha: '2026-07-30', fechaRaw: '2026-07-30', hora: '13:15', estado: 'completada', tiene_pdf: true, documentos: [] },
    { id: 3, iniciales: 'VR', profesional: 'Dra. Valentina Rojas', especialidad: 'Odontología', fecha: '2026-07-29', fechaRaw: '2026-07-29', hora: '12:30', estado: 'cancelada', tiene_pdf: false, documentos: [] },
    { id: 4, iniciales: 'DS', profesional: 'Diego Soto', especialidad: 'Kinesiología', fecha: '2026-07-31', fechaRaw: '2026-07-31', hora: '13:15', estado: 'inasistencia', tiene_pdf: false, documentos: [doc(12, 'receta', 'anulado')] }
  ];

  const el = () => fixture.nativeElement as HTMLElement;

  beforeEach(async () => {
    // No se provee HttpClient a propósito: si el componente intentara inyectarlo,
    // crear el fixture fallaría. Que pase confirma que no hace HTTP propio.
    await TestBed.configureTestingModule({
      imports: [EstudianteHistorialComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(EstudianteHistorialComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('especialidadesDisponibles', ['Nutrición', 'Medicina General', 'Odontología', 'Kinesiología']);
    fixture.componentRef.setInput('historial', crearHistorial());
    fixture.detectChanges();
  });

  it('no realiza llamadas HTTP propias', () => {
    expect((component as any).http).toBeUndefined();
  });

  describe('indicadores', () => {
    it('muestra total, completadas, canceladas y documentos emitidos', () => {
      const nums = Array.from(el().querySelectorAll('.atenciones-kpi-num')).map(n => n.textContent?.trim());
      expect(nums).toEqual(['4', '2', '1', '3']);
      const labels = Array.from(el().querySelectorAll('.atenciones-kpi-label')).map(n => n.textContent?.trim());
      expect(labels).toEqual(['Total de atenciones', 'Completadas', 'Canceladas', 'Documentos emitidos']);
    });

    it('con historial vacío todo queda en cero y se avisa que no hay atenciones', () => {
      fixture.componentRef.setInput('historial', []);
      fixture.detectChanges();
      const nums = Array.from(el().querySelectorAll('.atenciones-kpi-num')).map(n => n.textContent?.trim());
      expect(nums).toEqual(['0', '0', '0', '0']);
      expect(el().textContent).toContain('Aún no tienes atenciones registradas.');
      expect(el().querySelector('table')).toBeNull();
    });
  });

  describe('tabla', () => {
    it('muestra fecha corta, profesional, especialidad y estado de cada atención', () => {
      const filas = el().querySelectorAll('tbody tr');
      expect(filas.length).toBe(4);
      const primera = filas[0].textContent ?? '';
      expect(primera).toContain('20 jul 2026');
      expect(primera).toContain('06:45');
      expect(primera).toContain('Carlos Muñoz');
      expect(primera).toContain('Nutrición');
      expect(filas[2].querySelector('.estado-badge')?.classList).toContain('cancelada');
    });

    it('cada documento es un icono descargable y la atención sin documentos muestra un guion', () => {
      const filas = el().querySelectorAll('tbody tr');
      expect(filas[0].querySelectorAll('.doc-icono').length).toBe(2);
      expect(filas[1].querySelectorAll('.doc-icono').length).toBe(0);
      expect(filas[1].querySelector('.sin-documentos')?.textContent).toContain('—');
    });

    it('el documento anulado se distingue pero sigue disponible', () => {
      const icono = el().querySelectorAll('tbody tr')[3].querySelector('.doc-icono') as HTMLButtonElement;
      expect(icono.classList).toContain('anulado');
      expect(icono.title).toContain('anulado');
    });

    it('descargar un documento emite el documento al shell', () => {
      const emitido: any[] = [];
      component.descargarDocumento.subscribe(d => emitido.push(d));
      (el().querySelectorAll('tbody tr')[0].querySelector('.doc-icono') as HTMLButtonElement).click();
      expect(emitido.length).toBe(1);
      expect(emitido[0].id).toBe(10);
    });

    it('"Ver detalle" emite la atención completa', () => {
      const emitido: any[] = [];
      component.verDetalle.subscribe(h => emitido.push(h));
      (el().querySelectorAll('tbody tr')[1].querySelector('.atencion-btn-detalle') as HTMLButtonElement).click();
      expect(emitido[0].id).toBe(2);
    });

    it('el menú ofrece PDF solo en completadas con PDF y Reagendar solo en canceladas', () => {
      const filas = el().querySelectorAll('tbody tr');
      expect(filas[0].querySelector('.atencion-menu-lista')?.textContent).toContain('Descargar PDF');
      expect(filas[0].querySelector('.atencion-menu-lista')?.textContent).not.toContain('Reagendar');
      expect(filas[2].querySelector('.atencion-menu-lista')?.textContent).toContain('Reagendar');
      expect(filas[2].querySelector('.atencion-menu-lista')?.textContent).not.toContain('Descargar PDF');
      expect(filas[3].querySelector('.atencion-menu')).toBeNull();
    });

    it('PDF y Reagendar emiten sus eventos', () => {
      const pdf: number[] = [];
      const reag: any[] = [];
      component.descargarPdf.subscribe(id => pdf.push(id));
      component.reagendar.subscribe(h => reag.push(h));
      const filas = el().querySelectorAll('tbody tr');
      (filas[0].querySelector('.atencion-menu-lista button') as HTMLButtonElement).click();
      (filas[2].querySelector('.atencion-menu-lista button') as HTMLButtonElement).click();
      expect(pdf).toEqual([1]);
      expect(reag[0].id).toBe(3);
    });
  });

  describe('tipo de cita', () => {
    const filas = () => Array.from(el().querySelectorAll('tbody tr')) as HTMLElement[];

    beforeEach(() => {
      const base = crearHistorial();
      base[0] = { ...base[0], tipo: 'sobrecupo', sobrecupo: true };
      base[1] = { ...base[1], tipo: 'urgente', urgente: true };
      base[2] = { ...base[2], tipo: 'sobrecupo', sobrecupo: true };   // cancelada: conserva su tipo
      base[3] = { ...base[3], tipo: 'normal' };
      fixture.componentRef.setInput('historial', base);
      fixture.detectChanges();
    });

    it('una atención de sobrecupo con documentos sigue marcada como sobrecupo y con sus documentos', () => {
      const f = filas()[0];
      expect(f.querySelector('.tipo-cita')?.textContent?.trim()).toBe('Sobrecupo');
      expect(f.querySelectorAll('.doc-icono').length).toBe(2);
      expect(f.classList).toContain('tipo-sobrecupo');
    });

    it('una urgencia se marca como urgente', () => {
      expect(filas()[1].querySelector('.tipo-cita')?.textContent?.trim()).toBe('Urgente');
      expect(filas()[1].classList).toContain('tipo-urgente');
    });

    it('una cancelada de sobrecupo conserva la marca', () => {
      expect(filas()[2].querySelector('.tipo-cita')?.textContent?.trim()).toBe('Sobrecupo');
    });

    it('una atención normal no lleva marca ni barra de color', () => {
      expect(filas()[3].querySelector('.tipo-cita')).toBeNull();
      expect(filas()[3].classList).not.toContain('tipo-sobrecupo');
      expect(filas()[3].classList).not.toContain('tipo-urgente');
    });
  });

  describe('filtros', () => {
    const aplicar = () => { component.filtrar(); fixture.detectChanges(); };

    it('la búsqueda de texto coincide con profesional o con especialidad, sin tildes ni mayúsculas', () => {
      component.filtroBusqueda = 'nutricion';
      aplicar();
      expect(component.historialMostrado.map(h => h.id)).toEqual([1]);
      component.filtroBusqueda = 'ana martinez';
      aplicar();
      expect(component.historialMostrado.map(h => h.id)).toEqual([2]);
    });

    it('filtra por especialidad y por fecha', () => {
      component.filtroEspecialidad = 'Odontología';
      aplicar();
      expect(component.historialMostrado.map(h => h.id)).toEqual([3]);
      component.filtroEspecialidad = '';
      component.filtroFecha = '2026-07-31';
      aplicar();
      expect(component.historialMostrado.map(h => h.id)).toEqual([4]);
    });

    it('los filtros no cambian los indicadores y el conteo muestra cuántos se ven', () => {
      component.filtroEspecialidad = 'Nutrición';
      aplicar();
      expect(el().querySelector('.atenciones-kpi-num')?.textContent?.trim()).toBe('4');
      expect(el().querySelector('.atenciones-conteo')?.textContent).toContain('Mostrando 1 de 4 registros');
    });

    it('sin coincidencias avisa y oculta la tabla', () => {
      component.filtroBusqueda = 'zzz';
      aplicar();
      expect(el().textContent).toContain('No hay atenciones que coincidan con tu búsqueda.');
      expect(el().querySelector('table')).toBeNull();
    });

    it('Limpiar restaura todo el historial', () => {
      component.filtroBusqueda = 'nutricion';
      aplicar();
      component.limpiarFiltros();
      fixture.detectChanges();
      expect(component.historialMostrado.length).toBe(4);
      expect(component.filtroBusqueda).toBe('');
    });

    it('si el historial se recarga con un filtro activo, el filtro se mantiene', () => {
      component.filtroEspecialidad = 'Nutrición';
      aplicar();
      fixture.componentRef.setInput('historial', [...crearHistorial(), { id: 5, iniciales: 'XX', profesional: 'Otra', especialidad: 'Nutrición', fecha: '2026-08-01', fechaRaw: '2026-08-01', hora: '09:00', estado: 'completada', documentos: [] }]);
      fixture.detectChanges();
      expect(component.historialMostrado.map(h => h.id)).toEqual([1, 5]);
    });
  });
});
