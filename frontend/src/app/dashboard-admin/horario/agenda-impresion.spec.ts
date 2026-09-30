import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  construirDocumentoImpresion,
  imprimirAgendaAislada,
  OpcionesImpresionAgenda
} from './agenda-impresion';

// Página simulada: dashboard completo con sidebar, filtros, KPI y panel
// lateral, además del calendario. Solo el calendario debe salir impreso.
function grillaHtml(filas: number, columnas: number): string {
  const horas = Array.from({ length: filas }, (_, i) => `<div class="hora-celda" _ngcontent-abc>${String(8 + i).padStart(2, '0')}:00</div>`).join('');
  const dia = Array.from({ length: filas }, (_, i) => i === 0
    ? '<div class="bloque-celda ocupado multi-cita" _ngcontent-abc title="multi"><span class="bloque-info">Diego Soto</span><span class="bloque-info">Carlos Muñoz</span></div>'
    : '<div class="bloque-celda disponible" _ngcontent-abc><span class="agenda-slot-available">+ Disponible</span></div>').join('');
  const cols = Array.from({ length: columnas }, (_, c) => `<div class="dia-col"><div class="dia-header" _ngcontent-abc><span class="dia-nombre">D${c}</span></div>${dia}</div>`).join('');
  return `<div class="semana-grilla agenda-week-grid"><div class="hora-col"><div class="hora-celda header" _ngcontent-abc>Hora</div>${horas}</div>${cols}</div>`;
}

function montarPagina(filas = 10, columnas = 7): { tarjeta: HTMLElement; leyenda: HTMLElement; limpiar: () => void } {
  const shell = document.createElement('div');
  shell.className = 'dashboard admin-shell tema-oscuro sidebar-abierta';
  shell.setAttribute('_ngcontent-shell', '');
  shell.innerHTML = `
    <aside class="sidebar">MENU-LATERAL</aside>
    <header class="topbar">BARRA-SUPERIOR</header>
    <main class="main-content">
      <app-admin-horario _nghost-abc>
        <section class="agenda-page" _ngcontent-abc>
          <div class="agenda-toolbar">FILTROS-Y-BOTONES</div>
          <div class="agenda-kpi-grid">INDICADORES</div>
          <div class="agenda-legend" _ngcontent-abc><span>Disponible</span></div>
          <div class="agenda-layout">
            <div class="card agenda-calendar-card" _ngcontent-abc>
              <div class="agenda-calendar-heading">CABECERA-DEL-CALENDARIO</div>
              CONTENIDO-DEL-CALENDARIO
              ${grillaHtml(filas, columnas)}
            </div>
            <aside class="agenda-context-panel">PANEL-CONTEXTUAL</aside>
          </div>
        </section>
      </app-admin-horario>
    </main>`;
  document.body.appendChild(shell);

  return {
    tarjeta: shell.querySelector('.agenda-calendar-card') as HTMLElement,
    leyenda: shell.querySelector('.agenda-legend') as HTMLElement,
    limpiar: () => shell.remove()
  };
}

function opciones(pagina: { tarjeta: HTMLElement; leyenda: HTMLElement }, extra: Partial<OpcionesImpresionAgenda> = {}): OpcionesImpresionAgenda {
  return {
    tarjeta: pagina.tarjeta,
    leyenda: pagina.leyenda,
    profesional: 'Dra. Pérez — Medicina General',
    vistaNombre: 'Semana',
    periodo: 'Semana 14 – 20 Septiembre 2026',
    orientacion: 'landscape',
    fechaImpresion: new Date(2026, 8, 19, 14, 32),
    ...extra
  };
}

describe('agenda-impresion', () => {
  afterEach(() => {
    vi.useRealTimers();
    document.querySelectorAll('iframe').forEach(f => f.remove());
  });

  describe('construirDocumentoImpresion', () => {
    it('incluye únicamente el calendario, sin sidebar, barra superior, filtros, KPI ni panel', () => {
      const pagina = montarPagina();
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina));
      const texto = destino.body.textContent ?? '';

      expect(texto).toContain('CONTENIDO-DEL-CALENDARIO');
      for (const ajeno of ['MENU-LATERAL', 'BARRA-SUPERIOR', 'FILTROS-Y-BOTONES', 'INDICADORES', 'PANEL-CONTEXTUAL']) {
        expect(texto).not.toContain(ajeno);
      }
      pagina.limpiar();
    });

    it('agrega encabezado con profesional, vista, período y fecha de impresión', () => {
      const pagina = montarPagina();
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina));
      const encabezado = destino.querySelector('.agenda-impresion-encabezado')!.textContent!;

      expect(encabezado).toContain('SESAES · Agenda clínica');
      expect(encabezado).toContain('Dra. Pérez — Medicina General');
      expect(encabezado).toContain('Semana');
      expect(encabezado).toContain('Semana 14 – 20 Septiembre 2026');
      expect(encabezado).toContain('Impreso');
      expect(destino.title).toContain('Dra. Pérez');
      pagina.limpiar();
    });

    it('escribe el nombre del profesional como texto, no como HTML', () => {
      const pagina = montarPagina();
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina, {
        profesional: '<img src=x onerror=alert(1)> Dr. X'
      }));

      expect(destino.querySelector('.agenda-impresion-encabezado img')).toBeNull();
      expect(destino.querySelector('.agenda-impresion-encabezado')!.textContent).toContain('<img src=x');
      pagina.limpiar();
    });

    it('conserva los contenedores de estilos (shell, host, página) sin el tema oscuro ni la sidebar abierta', () => {
      const pagina = montarPagina();
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina));

      const shell = destino.querySelector('.admin-shell')!;
      expect(shell.classList.contains('tema-oscuro')).toBe(false);
      expect(shell.classList.contains('sidebar-abierta')).toBe(false);
      expect(shell.querySelector('app-admin-horario .agenda-page .agenda-calendar-card')).toBeTruthy();
      // La grilla de dos columnas del layout NO se replica: el calendario no comparte fila con el panel.
      expect(destino.querySelector('.agenda-layout')).toBeNull();
      pagina.limpiar();
    });

    it('incluye la leyenda cuando se entrega', () => {
      const pagina = montarPagina();
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina));
      expect(destino.querySelector('.agenda-legend')!.textContent).toContain('Disponible');

      const sinLeyenda = document.implementation.createHTMLDocument('');
      construirDocumentoImpresion(sinLeyenda, document, opciones(pagina, { leyenda: null }));
      expect(sinLeyenda.querySelector('.agenda-legend')).toBeNull();
      pagina.limpiar();
    });

    it('copia los estilos de la aplicación y agrega las reglas de impresión', () => {
      const pagina = montarPagina();
      const estilo = document.createElement('style');
      estilo.setAttribute('data-prueba', 'estilo-app');
      estilo.textContent = '.agenda-calendar-card { color: red; }';
      document.head.appendChild(estilo);
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina, { orientacion: 'portrait' }));
      const reglas = Array.from(destino.head.querySelectorAll('style')).map(e => e.textContent).join('\n');

      expect(destino.head.querySelector('style[data-prueba="estilo-app"]')).toBeTruthy();
      expect(reglas).toContain('@page { size: A4 portrait;');
      expect(reglas).toContain('.agenda-calendar-heading { display: none !important; }');
      expect(reglas).toContain('.material-symbols-outlined { display: none !important; }');
      estilo.remove();
      pagina.limpiar();
    });

    it('la grilla horaria se imprime como tabla: cabecera de días en <thead> (se repite en cada página) y una fila por hora', () => {
      const pagina = montarPagina(10, 7);
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina));
      const reglas = Array.from(destino.head.querySelectorAll('style')).map(e => e.textContent).join('\n');
      const tabla = destino.querySelector('table.agenda-impresion-tabla')!;

      expect(tabla).toBeTruthy();
      // cabecera: "Hora" + 7 días; se repite por página porque el thead es table-header-group
      const cabeceras = Array.from(tabla.querySelectorAll('thead th'));
      expect(cabeceras).toHaveLength(8);
      expect(cabeceras[0].textContent).toContain('Hora');
      expect(cabeceras.slice(1).map(th => th.textContent!.trim())).toEqual(['D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6']);
      expect(reglas).toContain('.agenda-impresion-tabla thead { display: table-header-group; }');
      expect(reglas).toContain('.agenda-impresion-tabla tr { break-inside: avoid; }');
      // una fila por hora, la primera celda es la hora y luego un bloque por día
      const filas = Array.from(tabla.querySelectorAll('tbody tr'));
      expect(filas).toHaveLength(10);
      filas.forEach((fila, i) => {
        const celdas = Array.from(fila.children);
        expect(celdas).toHaveLength(8);
        expect(celdas[0].textContent).toBe(`${String(8 + i).padStart(2, '0')}:00`);
      });
      // ya no queda la estructura de columnas flex que no se puede partir entre páginas
      expect(destino.querySelector('.hora-col, .dia-col')).toBeNull();
      pagina.limpiar();
    });

    it('las celdas conservan sus clases, atributos de encapsulación, título y todas las citas (multicita no se pierde)', () => {
      const pagina = montarPagina(4, 2);
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina));
      const primera = destino.querySelector('tbody tr td.bloque-celda') as HTMLElement;

      expect(primera.tagName).toBe('TD');
      expect(primera.classList.contains('ocupado')).toBe(true);
      expect(primera.classList.contains('multi-cita')).toBe(true);
      expect(primera.hasAttribute('_ngcontent-abc')).toBe(true);
      expect(primera.getAttribute('title')).toBe('multi');
      expect(Array.from(primera.querySelectorAll('.bloque-info')).map(e => e.textContent))
        .toEqual(['Diego Soto', 'Carlos Muñoz']);
      // el número de celdas impresas es exactamente el mostrado: 4 horas × 2 días
      expect(destino.querySelectorAll('td.bloque-celda')).toHaveLength(8);
      expect(destino.querySelectorAll('th.dia-header')).toHaveLength(2);
      pagina.limpiar();
    });

    it('la vista Día (una sola columna de día) también se imprime como tabla con su cabecera', () => {
      const pagina = montarPagina(10, 1);
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina, { orientacion: 'portrait', vistaNombre: 'Día' }));

      expect(destino.querySelectorAll('thead th')).toHaveLength(2); // Hora + 1 día
      expect(destino.querySelectorAll('tbody tr')).toHaveLength(10);
      pagina.limpiar();
    });

    it('una agenda larga (30 min) no se comprime: alto mínimo de pantalla, filas que crecen con sus citas y nombres sin recortar', () => {
      const pagina = montarPagina(20, 7);
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina));
      const reglas = Array.from(destino.head.querySelectorAll('style')).map(e => e.textContent).join('\n');

      expect(destino.querySelectorAll('tbody tr')).toHaveLength(20);
      // height en una celda de tabla es un mínimo: crece con el contenido; nunca se fuerza menos que en pantalla (48 px)
      expect(reglas).toContain('.agenda-impresion-tabla td { height: 48px !important;');
      expect(reglas).not.toMatch(/height:\s*(1\d|2\d|3\d|4[0-7])px\s*!important/);
      expect(reglas).toContain('.agenda-impresion-tabla .bloque-info { white-space: normal !important;');
      pagina.limpiar();
    });

    it('si la estructura de la grilla no es la esperada, la deja como está en vez de imprimir una tabla incompleta', () => {
      const pagina = montarPagina(4, 2);
      pagina.tarjeta.querySelector('.dia-col')!.lastElementChild!.remove(); // una columna con una fila menos
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina));

      expect(destino.querySelector('table.agenda-impresion-tabla')).toBeNull();
      expect(destino.querySelector('.semana-grilla')!.classList.contains('agenda-impresion-grilla-tabla')).toBe(false);
      expect(destino.querySelectorAll('.dia-col')).toHaveLength(2);
      pagina.limpiar();
    });

    it('en la vista Mes (sin grilla horaria) no se genera tabla', () => {
      const pagina = montarPagina(0, 0);
      pagina.tarjeta.querySelector('.semana-grilla')?.remove();
      const destino = document.implementation.createHTMLDocument('');

      construirDocumentoImpresion(destino, document, opciones(pagina, { vistaNombre: 'Mes' }));

      expect(destino.querySelector('table')).toBeNull();
      pagina.limpiar();
    });

    it('no modifica la página original', () => {
      const pagina = montarPagina();
      const destino = document.implementation.createHTMLDocument('');
      const antes = document.body.innerHTML;

      construirDocumentoImpresion(destino, document, opciones(pagina));

      expect(document.body.innerHTML).toBe(antes);
      pagina.limpiar();
    });
  });

  describe('imprimirAgendaAislada', () => {
    it('imprime desde un iframe oculto y nunca llama a window.print de la página', async () => {
      const pagina = montarPagina();
      const printPagina = vi.spyOn(window, 'print').mockImplementation(() => undefined);
      const imprimir = vi.fn();

      const iframe = imprimirAgendaAislada(opciones(pagina, { esperaMaximaMs: 0, imprimir }));
      await new Promise(resolver => setTimeout(resolver, 10));

      expect(iframe.getAttribute('aria-hidden')).toBe('true');
      expect(iframe.contentDocument!.body.textContent).toContain('CONTENIDO-DEL-CALENDARIO');
      expect(iframe.contentDocument!.body.textContent).not.toContain('MENU-LATERAL');
      expect(imprimir).toHaveBeenCalledTimes(1);
      expect(imprimir).toHaveBeenCalledWith(iframe.contentWindow);
      expect(printPagina).not.toHaveBeenCalled();

      printPagina.mockRestore();
      pagina.limpiar();
    });

    it('elimina el iframe al terminar la impresión (afterprint)', async () => {
      const pagina = montarPagina();
      const iframe = imprimirAgendaAislada(opciones(pagina, { esperaMaximaMs: 0, imprimir: vi.fn() }));
      await new Promise(resolver => setTimeout(resolver, 10));
      expect(iframe.isConnected).toBe(true);

      iframe.contentWindow!.dispatchEvent(new Event('afterprint'));

      expect(iframe.isConnected).toBe(false);
      pagina.limpiar();
    });

    it('si el iframe ya no existe al terminar la espera, no imprime', async () => {
      const pagina = montarPagina();
      const imprimir = vi.fn();

      const iframe = imprimirAgendaAislada(opciones(pagina, { esperaMaximaMs: 0, imprimir }));
      iframe.remove();
      await new Promise(resolver => setTimeout(resolver, 10));

      expect(imprimir).not.toHaveBeenCalled();
      pagina.limpiar();
    });
  });
});
