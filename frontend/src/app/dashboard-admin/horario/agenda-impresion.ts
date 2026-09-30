// Impresión aislada de la Agenda Admin.
//
// Problema que resuelve: imprimir con window.print() sobre la página
// imprime TODO el dashboard (sidebar, topbar, filtros, KPI, panel). Acá
// se arma un documento aparte (iframe oculto) que contiene únicamente el
// calendario visible de la agenda, con un encabezado propio, y solo ese
// documento se manda a imprimir. La pantalla del usuario no se modifica.
//
// Los estilos de la aplicación se copian al documento de impresión para
// que el calendario se vea igual que en pantalla (los componentes usan
// encapsulación de Angular, así que también se conservan los atributos
// de los contenedores).

export type OrientacionImpresion = 'landscape' | 'portrait';

export interface OpcionesImpresionAgenda {
  /** Tarjeta del calendario (.agenda-calendar-card). Se clona; no se mueve. */
  tarjeta: HTMLElement;
  /** Leyenda de estados (.agenda-legend). Opcional. */
  leyenda?: HTMLElement | null;
  /** Texto del profesional, p. ej. "Dra. Pérez — Medicina General". */
  profesional: string;
  /** Nombre de la vista: "Día", "Semana" o "Mes". */
  vistaNombre: string;
  /** Período visible, p. ej. "Semana 14 – 20 Septiembre 2026". */
  periodo: string;
  orientacion: OrientacionImpresion;
  /** Fecha que figura como "Impreso"; por defecto, ahora. */
  fechaImpresion?: Date;
  /** Espera máxima por hojas de estilo/fuentes antes de imprimir. */
  esperaMaximaMs?: number;
  /** Sustituible en pruebas; por defecto enfoca el iframe y llama a print(). */
  imprimir?: (ventanaImpresion: Window) => void;
}

const CLASES_A_QUITAR_DEL_SHELL = ['tema-oscuro', 'sidebar-abierta'];

// La grilla de pantalla son columnas flex apiladas (una columna de horas y un
// .dia-col por día). Ese layout no se puede partir bien entre páginas: no hay
// forma de repetir la cabecera de días en cada hoja y las columnas se cortan
// en puntos distintos. Para imprimir, las MISMAS celdas ya renderizadas se
// reubican como una tabla: <thead> (cabecera de días, que el navegador repite
// en cada página) y una fila <tr> por hora, de modo que una agenda larga
// continúa en la página siguiente por filas completas, con su cabecera y cada
// hora alineada a sus bloques. No se crean ni se recalculan datos: cada celda
// conserva sus clases y atributos (incluida la encapsulación de Angular) y sus
// hijos; solo cambia el elemento contenedor (div → td/th).
function comoCelda(destino: Document, origen: Element, etiqueta: 'td' | 'th'): HTMLElement {
  const celda = destino.createElement(etiqueta);
  for (const atributo of Array.from(origen.attributes)) {
    celda.setAttribute(atributo.name, atributo.value);
  }
  while (origen.firstChild) celda.appendChild(origen.firstChild);
  return celda;
}

function grillaATabla(destino: Document, grilla: HTMLElement): HTMLTableElement | null {
  const hijos = Array.from(grilla.children);
  const horaCol = hijos.find(el => el.classList.contains('hora-col'));
  const diaCols = hijos.filter(el => el.classList.contains('dia-col'));
  if (!horaCol || diaCols.length === 0) return null;

  // columnas[c][r]: r = 0 es la cabecera; r >= 1 son las filas horarias.
  const columnas = [horaCol, ...diaCols].map(col => Array.from(col.children));
  const filas = columnas[0].length;
  if (filas < 2 || columnas.some(col => col.length !== filas)) return null;

  const tabla = destino.createElement('table');
  tabla.className = 'agenda-impresion-tabla';

  const grupoColumnas = destino.createElement('colgroup');
  columnas.forEach((_, indice) => {
    const columna = destino.createElement('col');
    if (indice === 0) columna.className = 'col-hora';
    grupoColumnas.appendChild(columna);
  });
  tabla.appendChild(grupoColumnas);

  const encabezado = destino.createElement('thead');
  const filaEncabezado = destino.createElement('tr');
  columnas.forEach(col => filaEncabezado.appendChild(comoCelda(destino, col[0], 'th')));
  encabezado.appendChild(filaEncabezado);
  tabla.appendChild(encabezado);

  const cuerpo = destino.createElement('tbody');
  for (let fila = 1; fila < filas; fila++) {
    const tr = destino.createElement('tr');
    columnas.forEach(col => tr.appendChild(comoCelda(destino, col[fila], 'td')));
    cuerpo.appendChild(tr);
  }
  tabla.appendChild(cuerpo);
  return tabla;
}

function estilosImpresion(opciones: OpcionesImpresionAgenda): string {
  return `
@page { size: A4 ${opciones.orientacion}; margin: 10mm; }
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body { margin: 0; padding: 0; background: #fff !important; }
body { font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; color: #102E29; }

.admin-shell { display: block !important; min-height: 0 !important; height: auto !important; background: #fff !important; }
.agenda-page { display: block !important; }

.agenda-impresion-encabezado { margin: 0 0 8px; break-after: avoid; }
.agenda-impresion-encabezado h1 { margin: 0 0 4px; font-size: 16px; color: #102E29; }
.agenda-impresion-meta { display: flex; flex-wrap: wrap; gap: 2px 18px; font-size: 11px; color: #5C706D; }
.agenda-impresion-meta strong { color: #102E29; }

.agenda-legend { justify-content: flex-start !important; margin: 0 0 8px !important; }

.agenda-calendar-card { margin: 0 !important; overflow: visible !important; border: 1px solid #DCE5E2 !important; border-radius: 0 !important; box-shadow: none !important; }
.agenda-calendar-heading { display: none !important; }
.agenda-day-sindatos { margin: 8px 0 !important; }

.semana-grilla { overflow: visible !important; }
.semana-grilla.agenda-impresion-grilla-tabla { display: block !important; }
.agenda-week-grid { min-width: 0 !important; }

/* Grilla horaria como tabla: la cabecera de días se repite en cada página. */
.agenda-impresion-tabla { width: 100%; border-collapse: collapse; table-layout: fixed; }
.agenda-impresion-tabla col.col-hora { width: 60px; }
.agenda-impresion-tabla thead { display: table-header-group; }
.agenda-impresion-tabla tr { break-inside: avoid; }
.agenda-impresion-tabla th, .agenda-impresion-tabla td { display: table-cell !important; box-sizing: border-box; padding: 0 6px; margin: 0; vertical-align: middle; text-align: center; }
.agenda-impresion-tabla th { height: 62px !important; }
.agenda-impresion-tabla td { height: 48px !important; overflow: visible !important; cursor: default !important; }
.agenda-impresion-tabla th:not(:first-child), .agenda-impresion-tabla td:not(:first-child) { border-left: 1px solid #F6F8FB; }
.agenda-impresion-tabla .hora-celda { text-align: right; padding-right: 8px; }
.agenda-impresion-tabla .hora-celda.header { text-align: center; }
.agenda-impresion-tabla .dia-header > span, .agenda-impresion-tabla .bloque-info { display: block !important; }
.agenda-impresion-tabla .bloque-info { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }
.agenda-impresion-tabla .bloque-celda.ocupado.ocupado-sobrecupo-disponible { box-shadow: none !important; }

.agenda-month { overflow: visible !important; padding: 8px !important; }
.agenda-month-weekdays, .agenda-month-body { min-width: 0 !important; }
.agenda-month-body { grid-auto-rows: minmax(84px, auto); }
.agenda-month-cell { min-height: 0 !important; cursor: default !important; box-shadow: none !important; break-inside: avoid; }
.agenda-month-cell.seleccionado { border-color: #DCE5E2 !important; }
.agenda-month-chip { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }

.material-symbols-outlined { display: none !important; }
`;
}

function crearEncabezado(destino: Document, opciones: OpcionesImpresionAgenda): HTMLElement {
  const encabezado = destino.createElement('header');
  encabezado.className = 'agenda-impresion-encabezado';

  const titulo = destino.createElement('h1');
  titulo.textContent = 'SESAES · Agenda clínica';
  encabezado.appendChild(titulo);

  const meta = destino.createElement('div');
  meta.className = 'agenda-impresion-meta';

  const agregar = (etiqueta: string, valor: string): void => {
    const linea = destino.createElement('span');
    const fuerte = destino.createElement('strong');
    fuerte.textContent = `${etiqueta}: `;
    linea.appendChild(fuerte);
    linea.appendChild(destino.createTextNode(valor));
    meta.appendChild(linea);
  };

  const impreso = (opciones.fechaImpresion ?? new Date()).toLocaleString('es-CL', {
    dateStyle: 'short',
    timeStyle: 'short'
  });

  agregar('Profesional', opciones.profesional);
  agregar('Vista', opciones.vistaNombre);
  agregar('Período', opciones.periodo);
  agregar('Impreso', impreso);

  encabezado.appendChild(meta);
  return encabezado;
}

// Copia superficial (sin hijos) de un contenedor, conservando clases y
// atributos de encapsulación de Angular para que sus estilos sigan
// aplicando al calendario clonado.
function copiaSuperficial(destino: Document, origen: Element | null): HTMLElement | null {
  if (!origen) return null;
  const copia = destino.importNode(origen, false) as HTMLElement;
  for (const clase of CLASES_A_QUITAR_DEL_SHELL) copia.classList.remove(clase);
  copia.removeAttribute('id');
  return copia;
}

/**
 * Rellena `destino` con el documento de impresión: estilos copiados de
 * `origen`, encabezado, leyenda y el calendario clonado. No toca `origen`.
 */
export function construirDocumentoImpresion(
  destino: Document,
  origen: Document,
  opciones: OpcionesImpresionAgenda
): void {
  destino.title = `Agenda — ${opciones.profesional} — ${opciones.periodo}`;

  origen.querySelectorAll('style, link[rel="stylesheet"]').forEach(nodo => {
    const copia = destino.importNode(nodo, true) as HTMLElement;
    if (copia.tagName === 'LINK') {
      // href absoluto: el documento de impresión no comparte la base.
      copia.setAttribute('href', (nodo as HTMLLinkElement).href);
    }
    destino.head.appendChild(copia);
  });

  const estilos = destino.createElement('style');
  estilos.textContent = estilosImpresion(opciones);
  destino.head.appendChild(estilos);

  const { tarjeta } = opciones;
  const shell = copiaSuperficial(destino, tarjeta.closest('.admin-shell'));
  const host = copiaSuperficial(destino, tarjeta.closest('app-admin-horario'));
  const pagina = copiaSuperficial(destino, tarjeta.closest('.agenda-page'))
    ?? destino.createElement('section');

  pagina.appendChild(crearEncabezado(destino, opciones));
  if (opciones.leyenda) {
    pagina.appendChild(destino.importNode(opciones.leyenda, true));
  }
  const tarjetaClonada = destino.importNode(tarjeta, true) as HTMLElement;
  const grilla = tarjetaClonada.querySelector('.semana-grilla') as HTMLElement | null;
  const tabla = grilla ? grillaATabla(destino, grilla) : null;
  if (grilla && tabla) {
    grilla.replaceChildren(tabla);
    grilla.classList.add('agenda-impresion-grilla-tabla');
  }
  pagina.appendChild(tarjetaClonada);

  // shell > host > página > contenido. Se omiten los contenedores de
  // layout intermedios (sidebar, main, grilla de dos columnas) a propósito.
  let raiz: HTMLElement = pagina;
  if (host) { host.appendChild(raiz); raiz = host; }
  if (shell) { shell.appendChild(raiz); raiz = shell; }
  destino.body.appendChild(raiz);
}

function esperarRecursos(documento: Document, ventana: Window, maxMs: number): Promise<void> {
  const enlaces = Array.from(documento.querySelectorAll('link[rel="stylesheet"]'));
  const pendientes: Promise<unknown>[] = enlaces.map(enlace => new Promise<void>(resolver => {
    enlace.addEventListener('load', () => resolver());
    enlace.addEventListener('error', () => resolver());
  }));

  const fuentes = (documento as Document & { fonts?: { ready?: Promise<unknown> } }).fonts?.ready;
  if (fuentes) pendientes.push(fuentes.catch(() => undefined));

  const limite = new Promise<void>(resolver => ventana.setTimeout(resolver, maxMs));
  return Promise.race([Promise.all(pendientes).then(() => undefined), limite]);
}

/**
 * Imprime solo el calendario de la agenda usando un iframe oculto.
 * Devuelve el iframe (útil para pruebas); se elimina solo al terminar.
 */
export function imprimirAgendaAislada(
  opciones: OpcionesImpresionAgenda,
  ventanaOrigen: Window = window
): HTMLIFrameElement {
  const origen = ventanaOrigen.document;
  const iframe = origen.createElement('iframe');
  iframe.setAttribute('aria-hidden', 'true');
  iframe.setAttribute('title', 'Vista de impresión de la agenda');
  iframe.tabIndex = -1;
  iframe.setAttribute(
    'style',
    'visibility: hidden; position: fixed; right: 0; bottom: 0; width: 0; height: 0; border: 0;'
  );
  origen.body.appendChild(iframe);

  const ventana = iframe.contentWindow;
  const documento = iframe.contentDocument;
  if (!ventana || !documento) {
    iframe.remove();
    throw new Error('No se pudo preparar el documento de impresión de la agenda.');
  }

  documento.open();
  documento.write('<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"></head><body></body></html>');
  documento.close();

  construirDocumentoImpresion(documento, origen, opciones);

  const limpiar = (): void => { iframe.remove(); };
  ventana.addEventListener('afterprint', limpiar, { once: true });
  // Respaldo por si el navegador nunca dispara afterprint.
  ventanaOrigen.setTimeout(limpiar, 10 * 60 * 1000);

  const imprimir = opciones.imprimir ?? ((v: Window) => { v.focus(); v.print(); });
  void esperarRecursos(documento, ventana, opciones.esperaMaximaMs ?? 2500).then(() => {
    if (iframe.isConnected) imprimir(ventana);
  });

  return iframe;
}
