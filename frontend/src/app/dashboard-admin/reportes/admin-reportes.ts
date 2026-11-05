import {
  Component,
  ElementRef,
  EventEmitter,
  Input,
  NgZone,
  AfterViewChecked,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
  inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Chart, registerables } from 'chart.js';
import * as XLSX from 'xlsx';
import { guardarBlob } from '../../shared/descarga-archivo';
import { libroAXlsxBlob } from './reportes-excel';

Chart.register(...registerables);

export type ReportesTab =
  | 'general' | 'citas' | 'sobrecupos' | 'cancelaciones'
  | 'demanda' | 'profesionales' | 'jornada';

/**
 * Contrato con GET /admin/reportes/resumen (ver
 * backend/app/routers/admin.py::_construir_resumen_reportes). Se declara
 * suelto (no todos los campos) para no acoplar el componente a cada detalle
 * del backend; los getters de abajo aplican valores por defecto seguros
 * (`?? []` / `?? 0`) para que loading/error/empty nunca exploten en el
 * template si algún bloque aún no llegó.
 */
export interface ResumenReportes {
  periodo: { fecha_inicio: string; fecha_fin: string };
  periodo_anterior: { fecha_inicio: string; fecha_fin: string; disponible: boolean };
  kpis: Record<'total_atenciones' | 'completadas' | 'canceladas' | 'urgentes' | 'sobrecupos' | 'estudiantes_atendidos',
    { valor: number; variacion_pct: number | null }>;
  citas_por_estado: { completada: number; cancelada: number; pendiente: number; inasistencia: number };
  evolucion_semanal: { semana_inicio: string; total: number; completadas: number; canceladas: number }[];
  por_especialidad: { especialidad: string; cantidad: number }[];
  por_carrera: { carrera: string; cantidad: number }[];
  sobrecupos_por_especialidad: { especialidad: string; cantidad: number }[];
  cancelaciones: { total: number; por_origen: { origen: string; cantidad: number }[] };
  profesionales: {
    profesional_id: number; profesional: string; especialidad: string; atenciones: number;
    citas: number; canceladas: number; inasistencias: number; sobrecupos: number; urgentes: number;
  }[];
  jornada: {
    por_dia_semana: { dia: string; cantidad: number }[];
    por_hora: { hora: string; cantidad: number }[];
    inasistencias_evolucion: { fecha: string; cantidad: number }[];
  };
  ultimas_atenciones: {
    fecha: string; hora: string; estudiante: string; profesional: string;
    especialidad: string; estado: string; urgente: boolean; sobrecupo: boolean;
  }[];
}

interface ProfesionalOpcion { id: number; nombre: string; }

/**
 * Colores de acento de los gráficos. Salen de la paleta cerrada ya definida
 * para el módulo (color_identificador de profesionales + --admin-primary):
 * no se introduce ninguna paleta nueva.
 */
const PALETA_GRAFICOS = {
  total: '#5E857D',
  completadas: '#4F8EF7',
  canceladas: '#C75B5B'
};
const PALETA_SERIES = ['#5E857D', '#4F8EF7', '#8B5CF6', '#D9A441', '#D96C8A', '#7FB8A6', '#E07A5F', '#60A5FA'];
const COLOR_OTRAS = '#A9B7B3';

export interface FilaDona { nombre: string; cantidad: number; pct: number; color: string; }

const TONOS_KPI: Record<string, string> = {
  total_atenciones: 'tono-primario',
  completadas: 'tono-azul',
  canceladas: 'tono-rojo',
  urgentes: 'tono-ambar',
  sobrecupos: 'tono-violeta',
  estudiantes_atendidos: 'tono-lila'
};

const ETIQUETAS_KPI: Record<string, string> = {
  total_atenciones: 'Total de atenciones',
  completadas: 'Completadas',
  canceladas: 'Canceladas',
  urgentes: 'Urgentes',
  sobrecupos: 'Sobrecupos',
  estudiantes_atendidos: 'Estudiantes atendidos'
};

const ICONOS_KPI: Record<string, string> = {
  total_atenciones: 'event_available',
  completadas: 'task_alt',
  canceladas: 'event_busy',
  urgentes: 'priority_high',
  sobrecupos: 'groups',
  estudiantes_atendidos: 'school'
};

const ICONOS_TAB: Record<ReportesTab, string> = {
  general: 'dashboard',
  citas: 'event_note',
  sobrecupos: 'groups',
  cancelaciones: 'event_busy',
  demanda: 'trending_up',
  profesionales: 'medical_information',
  jornada: 'schedule'
};

const TABS: { id: ReportesTab; etiqueta: string }[] = [
  { id: 'general', etiqueta: 'Vista general' },
  { id: 'citas', etiqueta: 'Citas' },
  { id: 'sobrecupos', etiqueta: 'Sobrecupos' },
  { id: 'cancelaciones', etiqueta: 'Cancelaciones' },
  { id: 'demanda', etiqueta: 'Demanda' },
  { id: 'profesionales', etiqueta: 'Profesionales' },
  { id: 'jornada', etiqueta: 'Jornada y asistencia' }
];

@Component({
  selector: 'app-admin-reportes',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-reportes.html',
  styleUrl: './admin-reportes.css'
})
export class AdminReportesComponent implements OnChanges, AfterViewChecked, OnDestroy {
  /** Chart.js se crea/actualiza SIEMPRE fuera de la zona de Angular (evita NG0103). */
  private readonly zone = inject(NgZone);
  private readonly host = inject(ElementRef<HTMLElement>);

  readonly tabs = TABS;
  readonly etiquetasKpi = ETIQUETAS_KPI;
  readonly iconosKpi = ICONOS_KPI;
  readonly iconosTab = ICONOS_TAB;
  readonly tonosKpi = TONOS_KPI;

  readonly opcionesEstado = [
    { value: '', label: 'Todos' },
    { value: 'pendiente', label: 'Pendiente' },
    { value: 'completada', label: 'Completada' },
    { value: 'cancelada', label: 'Cancelada' },
    { value: 'inasistencia', label: 'Inasistencia' }
  ];

  readonly opcionesPrioridad = [
    { value: '', label: 'Todas' },
    { value: 'urgente', label: 'Urgente' },
    { value: 'no_urgente', label: 'No urgente' }
  ];

  // ── Datos (el shell hace el HTTP; este componente solo presenta) ──
  @Input() reportesResumen: ResumenReportes | null = null;
  @Input() reportesCargando = false;
  @Input() reportesError: string | null = null;

  @Input() especialidades: string[] = [];
  @Input() listaProfesionales: ProfesionalOpcion[] = [];

  // ── Navegación (tabs arriba y panel lateral comparten el mismo estado) ──
  @Input() reportesTabActiva: ReportesTab = 'general';
  @Output() reportesTabActivaChange = new EventEmitter<ReportesTab>();

  seleccionarTab(tab: ReportesTab): void {
    this.reportesTabActiva = tab;
    this.reportesTabActivaChange.emit(tab);
  }

  // ── Filtros: TODOS requieren backend (afectan KPIs/gráficos/tabla), por
  // eso no se auto-aplican al tipear — solo al presionar "Aplicar filtros".
  // Cambiar de pestaña NO dispara petición: es 100% local, solo cambia qué
  // parte del mismo `reportesResumen` ya cargado se muestra. ──
  @Input() reportesFiltroFechaInicio = '';
  @Output() reportesFiltroFechaInicioChange = new EventEmitter<string>();

  @Input() reportesFiltroFechaFin = '';
  @Output() reportesFiltroFechaFinChange = new EventEmitter<string>();

  @Input() reportesFiltroEspecialidad = '';
  @Output() reportesFiltroEspecialidadChange = new EventEmitter<string>();

  @Input() reportesFiltroCarrera = '';
  @Output() reportesFiltroCarreraChange = new EventEmitter<string>();

  @Input() reportesFiltroProfesionalId: number | '' = '';
  @Output() reportesFiltroProfesionalIdChange = new EventEmitter<number | ''>();

  @Input() reportesFiltroEstado = '';
  @Output() reportesFiltroEstadoChange = new EventEmitter<string>();

  @Input() reportesFiltroPrioridad = '';
  @Output() reportesFiltroPrioridadChange = new EventEmitter<string>();

  @Output() aplicarFiltros = new EventEmitter<void>();
  @Output() limpiarFiltros = new EventEmitter<void>();
  @Output() reintentar = new EventEmitter<void>();
  @Output() irAHistorial = new EventEmitter<void>();

  // ── Exportaciones ──
  @Output() exportarReportesExcel = new EventEmitter<void>();
  @Output() exportarReportesPdf = new EventEmitter<void>();

  @Input() puedeExportarCgr = false;
  @Input() cgrAnio: number | string = new Date().getFullYear();
  @Output() cgrAnioChange = new EventEmitter<number | string>();
  @Input() cgrAniosDisponibles: number[] = [];
  @Input() cgrFechaFin = '';
  @Output() cgrFechaFinChange = new EventEmitter<string>();
  @Output() exportarCgr = new EventEmitter<void>();
  @Output() exportarAlumnos = new EventEmitter<void>();

  // ── Gráficos Chart.js ──
  // Cada canvas vive dentro de un *ngIf (carga/error/sin resumen), así que
  // puede aparecer y desaparecer. Un setter de @ViewChild crea el gráfico
  // cuando el canvas entra al DOM y lo destruye cuando sale; así nunca se
  // dibuja sobre un canvas desconectado ni se pierde el gráfico si el
  // resumen llega después de ngAfterViewInit.
  private chartEvolucion?: Chart;
  private chartEspecialidad?: Chart;
  private chartCancelaciones?: Chart;
  private chartSobrecupos?: Chart;

  @ViewChild('chartEvolucionRef') set chartEvolucionRef(ref: ElementRef<HTMLCanvasElement> | undefined) {
    this.destruir(this.chartEvolucion);
    this.chartEvolucion = ref ? this.crearChartEvolucion(ref.nativeElement) : undefined;
    this.actualizarChartEvolucion();
  }
  @ViewChild('chartEspecialidadRef') set chartEspecialidadRef(ref: ElementRef<HTMLCanvasElement> | undefined) {
    this.destruir(this.chartEspecialidad);
    this.chartEspecialidad = ref ? this.crearChartDona(ref.nativeElement) : undefined;
    this.actualizarChartEspecialidad();
  }
  @ViewChild('chartCancelacionesRef') set chartCancelacionesRef(ref: ElementRef<HTMLCanvasElement> | undefined) {
    this.destruir(this.chartCancelaciones);
    this.chartCancelaciones = ref ? this.crearChartDona(ref.nativeElement) : undefined;
    this.actualizarChartCancelaciones();
  }
  @ViewChild('chartSobrecuposRef') set chartSobrecuposRef(ref: ElementRef<HTMLCanvasElement> | undefined) {
    this.destruir(this.chartSobrecupos);
    this.chartSobrecupos = ref ? this.crearChartSobrecupos(ref.nativeElement) : undefined;
    this.actualizarChartSobrecupos();
  }

  // Firma de los datos ya volcados a cada gráfico. En cada ciclo de vista se
  // compara: si el canvas es nuevo (firma '') o los datos cambiaron, se
  // vuelven a aplicar. Así no importa en qué orden lleguen canvas y datos.
  private firmas = { evolucion: '', especialidad: '', cancelaciones: '', sobrecupos: '' };

  ngAfterViewChecked(): void {
    if (this.chartEvolucion && this.firmas.evolucion !== JSON.stringify(this.reportesResumen?.evolucion_semanal ?? [])) this.actualizarChartEvolucion();
    if (this.chartEspecialidad && this.firmas.especialidad !== JSON.stringify(this.especialidadesDona)) this.actualizarChartEspecialidad();
    if (this.chartCancelaciones && this.firmas.cancelaciones !== JSON.stringify(this.cancelacionesDona)) this.actualizarChartCancelaciones();
    if (this.chartSobrecupos && this.firmas.sobrecupos !== JSON.stringify(this.sobrecuposPorEspecialidad)) this.actualizarChartSobrecupos();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['reportesResumen']) {
      this.actualizarChartEvolucion();
      this.actualizarChartEspecialidad();
      this.actualizarChartCancelaciones();
      this.actualizarChartSobrecupos();
    }
  }

  // ══════════════════════════════════════════════════════════════
  // DESCARGAS E IMPRESIÓN — siguen la opción elegida en «Tipo de análisis»
  // «Todos» = reporte completo (Excel y PDF los arma el shell/backend, como antes).
  // Cualquier otra opción = solo esa sección, con los mismos filtros aplicados.
  // ══════════════════════════════════════════════════════════════

  get etiquetaTabActiva(): string {
    return this.reportesTabActiva === 'general'
      ? 'Todos'
      : (this.tabs.find(x => x.id === this.reportesTabActiva)?.etiqueta ?? '');
  }

  descargarExcel(): void {
    if (this.reportesTabActiva === 'general') { this.exportarReportesExcel.emit(); return; }
    if (!this.reportesResumen) return;
    const libro = XLSX.utils.book_new();
    this.hojaFiltros(libro);
    this.hojasDeSeccion(libro, this.reportesTabActiva);
    guardarBlob(libroAXlsxBlob(libro), `reporte_${this.reportesTabActiva}_sesaes.xlsx`);
  }

  descargarPdf(): void {
    if (this.reportesTabActiva === 'general') { this.exportarReportesPdf.emit(); return; }
    this.imprimirSeccion();
  }

  /** Texto legible de los filtros aplicados (para la hoja «Filtros» y el encabezado impreso). */
  private filtrosAplicados(): [string, string][] {
    const prof = this.listaProfesionales.find(p => p.id === this.reportesFiltroProfesionalId)?.nombre;
    const estado = this.opcionesEstado.find(o => o.value === this.reportesFiltroEstado)?.label;
    const prioridad = this.opcionesPrioridad.find(o => o.value === this.reportesFiltroPrioridad)?.label;
    const periodo = this.reportesFiltroFechaInicio || this.reportesFiltroFechaFin
      ? `${this.reportesFiltroFechaInicio || '…'} a ${this.reportesFiltroFechaFin || '…'}`
      : 'Todo el historial';
    return [
      ['Período', periodo],
      ['Especialidad', this.reportesFiltroEspecialidad || 'Todas'],
      ['Carrera', this.reportesFiltroCarrera || 'Todas'],
      ['Profesional', prof || 'Todos'],
      ['Estado de cita', this.reportesFiltroEstado ? (estado || this.reportesFiltroEstado) : 'Todos'],
      ['Prioridad', this.reportesFiltroPrioridad ? (prioridad || this.reportesFiltroPrioridad) : 'Todas']
    ];
  }

  private hoja(libro: XLSX.WorkBook, nombre: string, encabezados: string[], filas: (string | number)[][]): void {
    const ws = XLSX.utils.aoa_to_sheet([encabezados, ...filas]);
    ws['!cols'] = encabezados.map((h, i) => ({
      wch: Math.min(48, Math.max(h.length, ...filas.map(f => String(f[i] ?? '').length), 8) + 2)
    }));
    XLSX.utils.book_append_sheet(libro, ws, nombre.slice(0, 31));
  }

  private hojaFiltros(libro: XLSX.WorkBook): void {
    this.hoja(libro, 'Filtros', ['Filtro', 'Valor'], [['Sección', this.etiquetaTabActiva], ...this.filtrosAplicados()]);
  }

  private filasAtenciones(lista: any[]): (string | number)[][] {
    return lista.map(a => [
      a.fecha, a.hora, a.estudiante, a.profesional, a.especialidad,
      a.urgente ? 'Urgente' : a.sobrecupo ? 'Sobrecupo' : '—',
      this.etiquetaEstadoCita(a.estado)
    ]);
  }

  private readonly encabezadosAtenciones = ['Fecha', 'Hora', 'Estudiante', 'Profesional', 'Especialidad', 'Prioridad', 'Estado'];

  private hojasDeSeccion(libro: XLSX.WorkBook, tab: ReportesTab): void {
    switch (tab) {
      case 'citas':
        this.hoja(libro, 'Citas por estado', ['Estado', 'Cantidad', '%'],
          this.citasEstadoFilas.map(f => [f.nombre, f.cantidad, f.pct]));
        this.hoja(libro, 'Atenciones', this.encabezadosAtenciones, this.filasAtenciones(this.ultimasAtenciones));
        break;
      case 'sobrecupos':
        this.hoja(libro, 'Por profesional', ['Profesional', 'Sobrecupos'],
          this.sobrecuposPorProfesional.map(f => [f.nombre, f.cantidad]));
        this.hoja(libro, 'Últimos sobrecupos', this.encabezadosAtenciones, this.filasAtenciones(this.sobrecuposRecientes));
        break;
      case 'cancelaciones':
        this.hoja(libro, 'Resumen', ['Indicador', 'Valor'], [
          ['Cancelaciones en el período', this.cancelaciones.total],
          ['% de las citas del período', this.tasaCancelacion],
          ...this.cancelaciones.por_origen.map(o => [this.etiquetaOrigenCancelacion(o.origen), o.cantidad] as (string | number)[])
        ]);
        this.hoja(libro, 'Por profesional', ['Profesional', 'Cancelaciones'],
          this.cancelacionesPorProfesional.map(f => [f.nombre, f.cantidad]));
        this.hoja(libro, 'Últimas canceladas', this.encabezadosAtenciones, this.filasAtenciones(this.canceladasRecientes));
        break;
      case 'demanda':
        this.hoja(libro, 'Por especialidad', ['Especialidad', 'Cantidad', '%'],
          this.demandaPorEspecialidad.map(f => [f.nombre, f.cantidad, f.pct]));
        this.hoja(libro, 'Por carrera', ['Carrera', 'Citas'], this.porCarrera.map(f => [f.carrera, f.cantidad]));
        this.hoja(libro, 'Por franja horaria', ['Franja', 'Citas'], this.jornadaPorHora.map(f => [f.hora, f.cantidad]));
        break;
      case 'profesionales':
        this.hoja(libro, 'Profesionales',
          ['Profesional', 'Especialidad', 'Atenciones', 'Citas', 'Canceladas', 'Inasistencias', 'Sobrecupos', 'Urgentes'],
          this.profesionalesResumen.map(p => [p.profesional, p.especialidad, p.atenciones, p.citas, p.canceladas, p.inasistencias, p.sobrecupos, p.urgentes]));
        break;
      case 'jornada':
        this.hoja(libro, 'Resumen', ['Indicador', 'Valor'], [
          ['Inasistencias', this.totalInasistencias],
          ['% de las citas del período', this.tasaInasistencia]
        ]);
        this.hoja(libro, 'Por día de la semana', ['Día', 'Atenciones'], this.jornadaPorDia.map(f => [f.dia, f.cantidad]));
        this.hoja(libro, 'Inasistencias', ['Fecha', 'Cantidad'], this.jornadaInasistencias.map(f => [f.fecha, f.cantidad]));
        break;
    }
  }

  /**
   * Imprime solo la sección elegida (con sus gráficos) en un iframe aislado, sin menú
   * ni paneles. En el diálogo del navegador se puede elegir «Guardar como PDF».
   */
  imprimirSeccion(): void {
    const origen: HTMLElement | null = this.host.nativeElement.querySelector('.reportes-main');
    if (!origen) return;

    const copia = origen.cloneNode(true) as HTMLElement;
    const lienzos = Array.from(origen.querySelectorAll('canvas'));
    copia.querySelectorAll('canvas').forEach((c, i) => {
      const img = document.createElement('img');
      img.src = lienzos[i].toDataURL('image/png');
      img.style.cssText = 'width:100%;height:100%;object-fit:contain';
      c.replaceWith(img);
    });
    copia.querySelectorAll('.spinner, .btn-reporte, .enlace-ver-todas').forEach(e => e.remove());

    const estilos = Array.from(document.head.querySelectorAll('style, link[rel="stylesheet"]'))
      .map(e => e.outerHTML).join('\n');
    const filtros = this.filtrosAplicados().map(([k, v]) => `<b>${k}:</b> ${v}`).join(' · ');

    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0';
    document.body.appendChild(iframe);
    const doc = iframe.contentDocument;
    if (!doc) { iframe.remove(); return; }
    doc.open();
    doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Reporte SESAES — ${this.etiquetaTabActiva}</title>
      ${estilos}
      <style>
        body { margin: 16px; background: #fff; font-family: Inter, Arial, sans-serif; }
        .encabezado-impresion h2 { margin: 0 0 4px; font-size: 18px; }
        .encabezado-impresion p { margin: 0 0 14px; font-size: 11px; color: #5C706D; }
        .tabla-card, .grafico-card, .kpi-card { break-inside: avoid; }
        [hidden] { display: none !important; }
      </style></head><body>
      <div class="encabezado-impresion">
        <h2>Reporte SESAES — ${this.etiquetaTabActiva}</h2>
        <p>${filtros} · Generado: ${new Date().toLocaleString('es-CL')}</p>
      </div>
      <div class="reportes">${copia.outerHTML}</div></body></html>`);
    doc.close();

    setTimeout(() => {
      iframe.contentWindow?.focus();
      iframe.contentWindow?.print();
      setTimeout(() => iframe.remove(), 1500);
    }, 400);
  }

  ngOnDestroy(): void {
    this.destruir(this.chartEvolucion);
    this.destruir(this.chartEspecialidad);
    this.destruir(this.chartCancelaciones);
    this.destruir(this.chartSobrecupos);
  }

  /** Crea un Chart fuera de la zona: sus requestAnimationFrame/ResizeObserver no disparan detección de cambios. */
  private nuevoChart(canvas: HTMLCanvasElement, config: any): Chart {
    return this.zone.runOutsideAngular(() => new Chart(canvas, config));
  }

  /** Actualiza un Chart fuera de la zona. */
  private refrescar(chart: Chart): void {
    this.zone.runOutsideAngular(() => {
      chart.update('none');
      // El canvas puede medir 0 al crearse (oculto / dentro de *ngIf): se remide ya montado.
      setTimeout(() => { if (chart.canvas?.isConnected) { chart.resize(); chart.update('none'); } }, 0);
    });
  }

  /** Destruye un Chart fuera de la zona. */
  private destruir(chart?: Chart): void {
    if (chart) this.zone.runOutsideAngular(() => chart.destroy());
  }

  /** Lee un token --admin-* del DOM para que el gráfico siga la paleta del módulo. */
  private token(canvas: HTMLElement, nombre: string, respaldo: string): string {
    const v = getComputedStyle(canvas).getPropertyValue(nombre).trim();
    return v || respaldo;
  }

  private crearChartEvolucion(canvas: HTMLCanvasElement): Chart {
    const texto = this.token(canvas, '--admin-text-secondary', '#5C706D');
    const borde = this.token(canvas, '--admin-border', '#DCE5E2');
    const serie = (label: string, color: string, relleno: boolean) => ({
      label, data: [] as number[], borderColor: color, backgroundColor: color + '1f',
      fill: relleno, tension: 0.35, pointRadius: 3, pointBackgroundColor: color, borderWidth: 2
    });
    return this.nuevoChart(canvas, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          serie('Totales', PALETA_GRAFICOS.total, true),
          serie('Completadas', PALETA_GRAFICOS.completadas, false),
          serie('Canceladas', PALETA_GRAFICOS.canceladas, false)
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, color: texto } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: texto } },
          y: { beginAtZero: true, ticks: { precision: 0, color: texto }, grid: { color: borde } }
        }
      }
    });
  }

  private actualizarChartEvolucion(): void {
    if (!this.chartEvolucion) return;
    const evolucion = this.reportesResumen?.evolucion_semanal ?? [];
    this.chartEvolucion.data.labels = evolucion.map(e => this.formatearSemana(e.semana_inicio));
    this.chartEvolucion.data.datasets[0].data = evolucion.map(e => e.total);
    this.chartEvolucion.data.datasets[1].data = evolucion.map(e => e.completadas);
    this.chartEvolucion.data.datasets[2].data = evolucion.map(e => e.canceladas);
    this.firmas.evolucion = JSON.stringify(evolucion);
    this.refrescar(this.chartEvolucion);
  }

  private crearChartDona(canvas: HTMLCanvasElement): Chart {
    return this.nuevoChart(canvas, {
      type: 'doughnut',
      data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderWidth: 2, borderColor: 'transparent' }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        cutout: '68%',
        plugins: { legend: { display: false } }
      }
    });
  }

  private actualizarChartEspecialidad(): void {
    if (!this.chartEspecialidad) return;
    const filas = this.especialidadesDona;
    this.chartEspecialidad.data.labels = filas.map(f => f.nombre);
    this.chartEspecialidad.data.datasets[0].data = filas.map(f => f.cantidad);
    this.chartEspecialidad.data.datasets[0].backgroundColor = filas.map(f => f.color);
    this.firmas.especialidad = JSON.stringify(filas);
    this.refrescar(this.chartEspecialidad);
  }

  private actualizarChartCancelaciones(): void {
    if (!this.chartCancelaciones) return;
    const filas = this.cancelacionesDona;
    this.chartCancelaciones.data.labels = filas.map(f => f.nombre);
    this.chartCancelaciones.data.datasets[0].data = filas.map(f => f.cantidad);
    this.chartCancelaciones.data.datasets[0].backgroundColor = filas.map(f => f.color);
    this.firmas.cancelaciones = JSON.stringify(filas);
    this.refrescar(this.chartCancelaciones);
  }

  private crearChartSobrecupos(canvas: HTMLCanvasElement): Chart {
    const texto = this.token(canvas, '--admin-text-secondary', '#5C706D');
    const borde = this.token(canvas, '--admin-border', '#DCE5E2');
    return this.nuevoChart(canvas, {
      type: 'bar',
      data: { labels: [], datasets: [{ label: 'Sobrecupos', data: [], backgroundColor: PALETA_GRAFICOS.completadas, borderRadius: 6, maxBarThickness: 34 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: texto } },
          y: { beginAtZero: true, ticks: { precision: 0, color: texto }, grid: { color: borde } }
        }
      }
    });
  }

  private actualizarChartSobrecupos(): void {
    if (!this.chartSobrecupos) return;
    const filas = this.sobrecuposPorEspecialidad;
    this.chartSobrecupos.data.labels = filas.map(f => f.especialidad);
    this.chartSobrecupos.data.datasets[0].data = filas.map(f => f.cantidad);
    this.firmas.sobrecupos = JSON.stringify(filas);
    this.refrescar(this.chartSobrecupos);
  }

  private formatearSemana(fechaIso: string): string {
    const [, mes, dia] = fechaIso.split('-');
    return `${dia}-${mes}`;
  }

  // ── Getters de presentación (siempre con fallback seguro) ──

  get kpisFilas(): { clave: string; etiqueta: string; valor: number; variacion: number | null }[] {
    const kpis = this.reportesResumen?.kpis;
    if (!kpis) return [];
    return (Object.keys(ETIQUETAS_KPI) as (keyof typeof kpis)[]).map(clave => ({
      clave, etiqueta: ETIQUETAS_KPI[clave], valor: kpis[clave].valor, variacion: kpis[clave].variacion_pct
    }));
  }

  get citasPorEstado() {
    return this.reportesResumen?.citas_por_estado ?? { completada: 0, cancelada: 0, pendiente: 0, inasistencia: 0 };
  }

  get porEspecialidad() { return this.reportesResumen?.por_especialidad ?? []; }
  get porCarrera() { return this.reportesResumen?.por_carrera ?? []; }
  get sobrecuposPorEspecialidad() { return this.reportesResumen?.sobrecupos_por_especialidad ?? []; }
  get cancelaciones() { return this.reportesResumen?.cancelaciones ?? { total: 0, por_origen: [] }; }
  get profesionalesResumen() { return this.reportesResumen?.profesionales ?? []; }
  get jornadaPorDia() { return this.reportesResumen?.jornada?.por_dia_semana ?? []; }
  get jornadaPorHora() { return this.reportesResumen?.jornada?.por_hora ?? []; }
  get jornadaInasistencias() { return this.reportesResumen?.jornada?.inasistencias_evolucion ?? []; }
  get ultimasAtenciones() { return this.reportesResumen?.ultimas_atenciones ?? []; }

  /**
   * Dona "Atenciones por especialidad": las 5 mayores + "Otras" (suma real del
   * resto, nunca un valor inventado). Solo citas completadas, igual que el
   * resto del módulo (cita != atención).
   */
  get especialidadesDona(): FilaDona[] {
    const filas = this.porEspecialidad;
    const total = filas.reduce((a, f) => a + f.cantidad, 0);
    if (!total) return [];
    const principales = filas.slice(0, 5);
    const resto = filas.slice(5).reduce((a, f) => a + f.cantidad, 0);
    const base = principales.map((f, i) => ({ nombre: f.especialidad, cantidad: f.cantidad, color: PALETA_SERIES[i % PALETA_SERIES.length] }));
    if (resto > 0) base.push({ nombre: 'Otras', cantidad: resto, color: COLOR_OTRAS });
    return base.map(f => ({ ...f, pct: Math.round((f.cantidad / total) * 100) }));
  }

  get totalEspecialidades(): number {
    return this.porEspecialidad.reduce((a, f) => a + f.cantidad, 0);
  }

  /**
   * Dona de cancelaciones. SESAES guarda el motivo como texto libre, no como
   * categoría, así que NO se presentan "causas": se agrupa por origen real
   * (administración / estudiante).
   */
  get cancelacionesDona(): FilaDona[] {
    const { total, por_origen } = this.cancelaciones;
    if (!total) return [];
    return por_origen.map((o, i) => ({
      nombre: this.etiquetaOrigenCancelacion(o.origen),
      cantidad: o.cantidad,
      color: i === 0 ? PALETA_GRAFICOS.canceladas : PALETA_SERIES[3],
      pct: Math.round((o.cantidad / total) * 100)
    }));
  }

  /** Ranking "Profesionales más solicitados": top 5 por atenciones (el backend ya ordena). */
  get topProfesionales() {
    return this.profesionalesResumen.slice(0, 5);
  }

  get totalInasistencias(): number { return this.citasPorEstado.inasistencia; }

  // ── Datos propios de cada pestaña (cortes que NO se repiten en la vista general) ──

  get totalCitas(): number {
    const c = this.citasPorEstado;
    return c.completada + c.cancelada + c.pendiente + c.inasistencia;
  }

  private porcentaje(parte: number, total: number): number {
    return total ? Math.round((parte / total) * 100) : 0;
  }

  get tasaCancelacion(): number { return this.porcentaje(this.citasPorEstado.cancelada, this.totalCitas); }
  get tasaInasistencia(): number { return this.porcentaje(this.citasPorEstado.inasistencia, this.totalCitas); }

  /** Pestaña Citas: reparto de las citas por estado. */
  get citasEstadoFilas(): { nombre: string; cantidad: number; pct: number; clase: string }[] {
    const c = this.citasPorEstado;
    const total = this.totalCitas;
    return [
      { nombre: 'Completadas', cantidad: c.completada, clase: '' },
      { nombre: 'Pendientes', cantidad: c.pendiente, clase: 'barra-fill-alt' },
      { nombre: 'Canceladas', cantidad: c.cancelada, clase: 'barra-fill-alerta' },
      { nombre: 'Inasistencias', cantidad: c.inasistencia, clase: 'barra-fill-alerta' }
    ].map(f => ({ ...f, pct: this.porcentaje(f.cantidad, total) }));
  }

  /** Pestaña Sobrecupos: por profesional (entre los que entrega el backend). */
  get sobrecuposPorProfesional(): { nombre: string; cantidad: number }[] {
    return this.profesionalesResumen
      .filter(p => p.sobrecupos > 0)
      .map(p => ({ nombre: p.profesional, cantidad: p.sobrecupos }))
      .sort((a, b) => b.cantidad - a.cantidad);
  }
  get sobrecuposRecientes() { return this.ultimasAtenciones.filter(a => a.sobrecupo); }

  /** Pestaña Cancelaciones: por profesional y últimas canceladas. */
  get cancelacionesPorProfesional(): { nombre: string; cantidad: number }[] {
    return this.profesionalesResumen
      .filter(p => p.canceladas > 0)
      .map(p => ({ nombre: p.profesional, cantidad: p.canceladas }))
      .sort((a, b) => b.cantidad - a.cantidad);
  }
  get canceladasRecientes() { return this.ultimasAtenciones.filter(a => a.estado === 'cancelada'); }

  /** Pestaña Demanda: por especialidad completa (la dona de la vista general solo muestra las 5 mayores). */
  get demandaPorEspecialidad(): { nombre: string; cantidad: number; pct: number }[] {
    const total = this.totalEspecialidades;
    return this.porEspecialidad.map(f => ({ nombre: f.especialidad, cantidad: f.cantidad, pct: this.porcentaje(f.cantidad, total) }));
  }

  /** Iniciales = primera letra del nombre + primera del apellido, sin prefijo Dr./Dra. */
  inicialesProfesional(nombre: string): string {
    const partes = (nombre ?? '').replace(/^(dra?\.?|sr\.?|sra\.?)\s+/i, '').trim().split(/\s+/).filter(Boolean);
    if (partes.length >= 2) return `${partes[0][0]}${partes[1][0]}`.toUpperCase();
    return (partes[0] ?? '?').substring(0, 2).toUpperCase();
  }

  /** Color determinístico por profesional (misma paleta cerrada del proyecto). */
  colorProfesional(id: number): string {
    return PALETA_SERIES[Math.abs(id) % PALETA_SERIES.length];
  }

  /** Miles con punto (es-CL), igual que la referencia visual: 1.248. */
  fmt(n: number): string {
    // Manual (no toLocaleString): el locale es no agrupa los números de 4 dígitos.
    return String(Math.round(n ?? 0)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  /** Ancho de barra (%) proporcional al máximo de la serie — sin librerías, real. */
  anchoBarra(valor: number, serie: { cantidad: number }[]): number {
    const max = Math.max(1, ...serie.map(s => s.cantidad));
    return Math.round((valor / max) * 100);
  }

  etiquetaOrigenCancelacion(origen: string): string {
    return origen === 'admin' ? 'Cancelada por administración' : 'Cancelada por el/la estudiante';
  }

  etiquetaEstadoCita(estado: string): string {
    const mapa: Record<string, string> = {
      completada: 'Completada', cancelada: 'Cancelada', pendiente: 'Pendiente', inasistencia: 'Inasistencia'
    };
    return mapa[estado] ?? estado;
  }

  // ── Estados vacíos honestos (nunca inventan datos): por pestaña, según
  // lo que esa pestaña realmente necesita para tener algo que mostrar. ──
  get sinDatosGeneral(): boolean {
    const r = this.reportesResumen;
    if (!r) return true;
    return r.kpis.completadas.valor === 0 && r.kpis.canceladas.valor === 0 && r.ultimas_atenciones.length === 0;
  }
  get sinDatosCitas(): boolean {
    const c = this.citasPorEstado;
    return c.completada + c.cancelada + c.pendiente + c.inasistencia === 0;
  }
  get sinDatosSobrecupos(): boolean {
    return (this.reportesResumen?.kpis.sobrecupos.valor ?? 0) === 0;
  }
  get sinDatosCancelaciones(): boolean { return this.cancelaciones.total === 0; }
  get sinDatosDemanda(): boolean { return this.porEspecialidad.length === 0 && this.jornadaPorHora.length === 0; }
  get sinDatosProfesionales(): boolean { return this.profesionalesResumen.length === 0; }
  get sinDatosJornada(): boolean {
    return this.jornadaPorDia.every(d => d.cantidad === 0) && this.jornadaInasistencias.length === 0;
  }
}
