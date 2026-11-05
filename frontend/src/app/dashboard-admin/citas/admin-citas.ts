import {
  ChangeDetectorRef,
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnChanges,
  OnDestroy,
  OnInit,
  Output,
  SimpleChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../config';
import { normalizarTexto } from '../../shared/text-normalization';
import {
  ItemPagina,
  OPCIONES_RANGO,
  RANGO_POR_DEFECTO,
  RangoCitas,
  TOTAL_COLORES_AVATAR,
  VentanasRango,
  fechaEnVentana,
  indiceColorAvatar,
  inicialesDe,
  paginasVisibles,
  variacionPorcentual,
  ventanasRango,
} from './admin-citas.utils';

const API = environment.apiUrl;

export type EstadoCitaFiltro = '' | 'pendiente' | 'completada' | 'cancelada' | 'inasistencia';
export type PrioridadFiltro = '' | 'urgente' | 'normal';

export interface CitasKpiDelta {
  texto: string;
  direccion: 'sube' | 'baja' | 'igual';
  /** bueno = verde, malo = rojo, neutro = gris. */
  tono: 'bueno' | 'malo' | 'neutro';
}

export interface CitasKpi {
  clave: 'total' | 'canceladas' | 'pendientes' | 'urgentes' | 'sobrecupo' | 'profesionales';
  etiqueta: string;
  valor: string;
  icono: string;
  delta: CitasKpiDelta | null;
  nota: string;
}

interface TabEstado {
  valor: EstadoCitaFiltro;
  etiqueta: string;
}

const TABS: ReadonlyArray<TabEstado> = [
  { valor: '', etiqueta: 'Todas' },
  { valor: 'pendiente', etiqueta: 'Pendientes' },
  { valor: 'completada', etiqueta: 'Completadas' },
  { valor: 'cancelada', etiqueta: 'Canceladas' },
  { valor: 'inasistencia', etiqueta: 'Inasistencias' },
];

const ETIQUETA_ESTADO: Record<string, string> = {
  pendiente: 'Pendiente',
  completada: 'Completada',
  cancelada: 'Cancelada',
  inasistencia: 'Inasistencia',
};

/**
 * Gestión de Citas — vista Admin / SUPERADMIN.
 *
 * Este componente es dueño de su listado, filtros, KPIs, paginación y carga de
 * datos. Las acciones que también usan otras secciones del shell (ver detalle,
 * marcar/quitar urgencia, cancelar) NO se implementan aquí: se emiten como
 * Outputs y el shell (DashboardAdminComponent) las ejecuta, porque él es dueño
 * del modal de detalle y de proximasCitas / citasHorario.
 *
 * Datos: una sola consulta a GET /agenda/citas (agenda.ver, con alcance
 * administrativo aplicado por el backend) que cubre el período visible y el
 * período previo. Los filtros de texto, servicio, estado y prioridad se
 * aplican en el cliente para que las pestañas puedan mostrar conteos reales.
 * Ninguna cifra se inventa: si no hay período previo comparable, no se muestra
 * variación.
 */
@Component({
  selector: 'app-admin-citas',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-citas.html',
  styleUrls: ['./admin-citas.css'],
})
export class AdminCitasComponent implements OnInit, OnChanges, OnDestroy {
  /** agenda.gestionar. Lectura (agenda.ver) la controla el shell. */
  @Input() puedeGestionarAgenda = false;
  /** profesionales.ver: habilita el acceso rápido a Profesionales. */
  @Input() puedeVerProfesionales = false;
  /**
   * El shell muta directamente `cita.estado`/`cita.urgente` sobre el MISMO
   * objeto que este componente tiene en `citasAdmin` (se lo pasa por
   * referencia al emitir `cancelarCita`/`marcarPrioridad`). Como ese cambio
   * ocurre fuera de este componente, no hay ningún método propio que lo
   * detecte. En vez de recalcular en cada ciclo de detección de cambios
   * "por si acaso", el shell incrementa este contador cada vez que termina
   * de mutar una cita, y este único punto (ngOnChanges) es el que dispara el
   * recálculo — así el costo es proporcional a las mutaciones reales, no a
   * la frecuencia de la detección de cambios.
   */
  @Input() citasVersion = 0;

  @Output() verDetalle = new EventEmitter<any>();
  @Output() marcarPrioridad = new EventEmitter<{ cita: any; urgente: boolean }>();
  @Output() cancelarCita = new EventEmitter<any>();
  /** "Agendar cita": requiere agenda.gestionar. */
  @Output() irAHorario = new EventEmitter<void>();
  /** "Ver agenda": solo lectura, basta agenda.ver. */
  @Output() irAAgenda = new EventEmitter<void>();
  @Output() irAProfesionales = new EventEmitter<void>();

  readonly porPagina = 8;
  readonly opcionesRango = OPCIONES_RANGO;
  readonly coloresAvatar = Array.from({ length: TOTAL_COLORES_AVATAR }, (_, i) => i);

  // ── Datos ──
  citasAdmin: any[] = [];
  citasPrevias: any[] = [];
  profesionalesCatalogo: any[] = [];
  citasCargando = false;
  citasCargadas = false;
  citasError = false;

  // ── Filtros ──
  citasFiltroEstudiante = '';
  citasFiltroServicio = '';
  citasFiltroRango: RangoCitas = RANGO_POR_DEFECTO;
  citasFiltroEstado: EstadoCitaFiltro = '';
  citasFiltroPrioridad: PrioridadFiltro = '';
  pagCitas = 1;

  // ── Derivados (se recalculan en ngDoCheck) ──
  citasFiltradas: any[] = [];
  citasPaginadas: any[] = [];
  conteos: Record<string, number> = {
    todas: 0,
    pendiente: 0,
    completada: 0,
    cancelada: 0,
    inasistencia: 0,
  };
  tabsVisibles: TabEstado[] = TABS.slice(0, 4) as TabEstado[];
  especialidades: string[] = [];
  kpis: CitasKpi[] = [];
  paginas: ItemPagina[] = [];
  totalPaginas = 1;
  desde = 0;
  hasta = 0;

  // ── Menú contextual por fila ──
  menuCita: any | null = null;
  menuPos: { top: number | null; bottom: number | null; right: number } = {
    top: 0,
    bottom: null,
    right: 0,
  };
  private menuDisparador: HTMLElement | null = null;

  private ventana: VentanasRango = ventanasRango(RANGO_POR_DEFECTO);
  private cargaSeq = 0;
  private firmaFiltros = '';
  private indiceBusqueda = new WeakMap<object, { texto: string; rut: string }>();
  private readonly alHacerScroll = () => this.cerrarMenu();

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
    private host: ElementRef<HTMLElement>,
  ) {}

  ngOnInit(): void {
    document.addEventListener('scroll', this.alHacerScroll, true);
    // Deriva el estado inicial (pestañas en 0, KPIs en "—") antes de que
    // lleguen los datos, para que la primera pintura no quede en blanco.
    this.recalcular();
    this.cargarCitas();
    this.cargarProfesionales();
  }

  ngOnDestroy(): void {
    document.removeEventListener('scroll', this.alHacerScroll, true);
    this.cargaSeq++; // invalida respuestas en vuelo
  }

  /**
   * Único disparador de recálculo por mutación externa: ver el comentario
   * de `citasVersion` más arriba. No se usa ngDoCheck a propósito: con
   * miles de citas, recalcular en cada ciclo de detección de cambios
   * (que puede ocurrir decenas de veces por segundo) sería un costo
   * innecesario. Aquí el costo es proporcional a las mutaciones reales.
   */
  ngOnChanges(changes: SimpleChanges): void {
    if (changes['citasVersion'] && !changes['citasVersion'].firstChange) {
      this.recalcular();
    }
  }

  // ═══════════════ Carga ═══════════════

  cargarCitas(): void {
    const seq = ++this.cargaSeq;
    const ventana = ventanasRango(this.citasFiltroRango);
    this.citasCargando = true;
    this.citasError = false;
    this.cerrarMenu();

    const params: string[] = [];
    if (ventana.actual) {
      // Actual y previa son contiguas: una sola consulta cubre ambas.
      params.push(`fecha_inicio=${(ventana.previa ?? ventana.actual).inicio}`);
      params.push(`fecha_fin=${ventana.actual.fin}`);
    }
    const url = `${API}/agenda/citas${params.length ? '?' + params.join('&') : ''}`;

    this.http.get<any[]>(url).subscribe({
      next: (data) => {
        if (seq !== this.cargaSeq) return;
        const todas = data ?? [];
        this.ventana = ventana;
        if (ventana.actual) {
          const actual = ventana.actual;
          this.citasAdmin = todas.filter((c) => fechaEnVentana(c.fecha, actual));
          const previa = ventana.previa;
          this.citasPrevias = previa ? todas.filter((c) => fechaEnVentana(c.fecha, previa)) : [];
        } else {
          this.citasAdmin = todas;
          this.citasPrevias = [];
        }
        this.pagCitas = 1;
        this.citasCargando = false;
        this.citasCargadas = true;
        // Recalcula una sola vez, con los datos ya asignados, en vez de
        // dejarlo a merced del próximo ciclo de detección de cambios.
        this.recalcular();
        // Fuerza el repintado inmediato: no depender de que zone.js decida
        // por sí solo cuándo aplicar el cambio (con eventCoalescing activo,
        // eso a veces queda pendiente hasta la próxima interacción del
        // usuario, dejando la pantalla pegada en "Cargando...").
        this.cdr.detectChanges();
      },
      error: () => {
        if (seq !== this.cargaSeq) return;
        this.citasCargando = false;
        this.citasError = true;
        this.cdr.detectChanges();
      },
    });
  }

  private cargarProfesionales(): void {
    this.http.get<any[]>(`${API}/agenda/profesionales`).subscribe({
      next: (data) => {
        this.profesionalesCatalogo = data ?? [];
        // Afecta el KPI de "profesionales activos" y las opciones del
        // filtro de especialidad: se recalcula una vez, al llegar el dato.
        this.recalcular();
        this.cdr.detectChanges();
      },
      error: () => {
        // Sin catálogo: el KPI de profesionales muestra "—" y el filtro de
        // servicio se arma solo con las especialidades presentes en las citas.
      },
    });
  }

  cambiarRango(rango: RangoCitas): void {
    this.citasFiltroRango = rango;
    this.cargarCitas();
  }

  get hayFiltrosActivos(): boolean {
    return (
      !!this.citasFiltroEstudiante.trim() ||
      !!this.citasFiltroServicio ||
      !!this.citasFiltroEstado ||
      !!this.citasFiltroPrioridad ||
      this.citasFiltroRango !== RANGO_POR_DEFECTO
    );
  }

  limpiarFiltrosCitas(): void {
    this.citasFiltroEstudiante = '';
    this.citasFiltroServicio = '';
    this.citasFiltroEstado = '';
    this.citasFiltroPrioridad = '';
    this.citasFiltroRango = RANGO_POR_DEFECTO;
    this.cargarCitas();
  }

  seleccionarEstado(estado: EstadoCitaFiltro): void {
    this.citasFiltroEstado = estado;
    this.recalcular();
  }

  alternarSoloUrgentes(): void {
    this.citasFiltroPrioridad = this.citasFiltroPrioridad === 'urgente' ? '' : 'urgente';
    this.recalcular();
  }

  verTodasLasFechas(): void {
    this.cambiarRango('todas');
  }

  irAPagina(pagina: number): void {
    if (pagina < 1 || pagina > this.totalPaginas) return;
    this.pagCitas = pagina;
    this.paginar();
    this.cerrarMenu();
  }

  /** Búsqueda por estudiante/RUT/profesional: filtro local, sin llamada al servidor. */
  actualizarBusqueda(valor: string): void {
    this.citasFiltroEstudiante = valor;
    this.recalcular();
  }

  /** Filtro de especialidad/tipo de servicio: local, sin llamada al servidor. */
  actualizarServicio(valor: string): void {
    this.citasFiltroServicio = valor;
    this.recalcular();
  }

  // ═══════════════ Cálculo de derivados ═══════════════

  /**
   * Recalcula todo lo derivado de citasAdmin/filtros: pestañas, conteos,
   * especialidades y KPIs, y termina paginando. Se llama explícitamente
   * (carga de datos, cambio de filtro, mutación externa vía citasVersion),
   * nunca en cada ciclo de detección de cambios.
   */
  private recalcular(): void {
    this.refiltrar();
    this.paginar();
  }

  /** Filtra citasAdmin según búsqueda/servicio/estado/prioridad y arma pestañas, KPIs y especialidades. */
  private refiltrar(): void {
    const consulta = normalizarTexto(this.citasFiltroEstudiante);
    const consultaRut = consulta.replace(/[.\-\s]/g, '');

    // Si cambia cualquier filtro, se vuelve a la primera página.
    const firma = [
      consulta,
      this.citasFiltroServicio,
      this.citasFiltroEstado,
      this.citasFiltroPrioridad,
    ].join('|');
    if (firma !== this.firmaFiltros) {
      this.firmaFiltros = firma;
      this.pagCitas = 1;
    }

    // Base: todos los filtros salvo el estado, para que cada pestaña cuente
    // exactamente lo que mostraría al seleccionarla.
    const base = this.citasAdmin.filter(
      (c) =>
        (!this.citasFiltroServicio || c.especialidad === this.citasFiltroServicio) &&
        this.coincidePrioridad(c) &&
        this.coincideBusqueda(c, consulta, consultaRut),
    );

    const conteos: Record<string, number> = {
      todas: base.length,
      pendiente: 0,
      completada: 0,
      cancelada: 0,
      inasistencia: 0,
    };
    for (const c of base) {
      if (c.estado in conteos) conteos[c.estado]++;
    }
    this.conteos = conteos;
    this.tabsVisibles = TABS.filter(
      (t) =>
        t.valor !== 'inasistencia' ||
        conteos['inasistencia'] > 0 ||
        this.citasFiltroEstado === 'inasistencia',
    ) as TabEstado[];

    this.citasFiltradas = this.citasFiltroEstado
      ? base.filter((c) => c.estado === this.citasFiltroEstado)
      : base;

    this.especialidades = this.armarEspecialidades();
    this.kpis = this.armarKpis();
  }

  /**
   * Solo repagina citasFiltradas (ya calculado por refiltrar()). Se usa al
   * cambiar de página, donde no hace falta rehacer la búsqueda ni los KPIs.
   */
  private paginar(): void {
    this.totalPaginas = Math.max(1, Math.ceil(this.citasFiltradas.length / this.porPagina));
    if (this.pagCitas > this.totalPaginas) this.pagCitas = this.totalPaginas;
    if (this.pagCitas < 1) this.pagCitas = 1;

    const inicio = (this.pagCitas - 1) * this.porPagina;
    this.citasPaginadas = this.citasFiltradas.slice(inicio, inicio + this.porPagina);
    this.desde = this.citasFiltradas.length === 0 ? 0 : inicio + 1;
    this.hasta = Math.min(inicio + this.porPagina, this.citasFiltradas.length);
    this.paginas = paginasVisibles(this.pagCitas, this.totalPaginas);

    // "Ver detalles" siempre está disponible, así que el menú en sí sigue
    // siendo válido aunque la cita cambie de estado; solo se cierra si la
    // fila abierta ya no está en la página visible (cambió de filtro/página).
    if (this.menuCita && !this.citasPaginadas.includes(this.menuCita)) {
      this.cerrarMenu();
    }
  }

  private coincidePrioridad(c: any): boolean {
    if (!this.citasFiltroPrioridad) return true;
    return !!c.urgente === (this.citasFiltroPrioridad === 'urgente');
  }

  private coincideBusqueda(c: any, consulta: string, consultaRut: string): boolean {
    if (!consulta) return true;
    let indice = this.indiceBusqueda.get(c);
    if (!indice) {
      indice = {
        texto: normalizarTexto(`${c.estudiante ?? ''} ${c.rut ?? ''} ${c.profesional ?? ''}`),
        rut: normalizarTexto(c.rut).replace(/[.\-\s]/g, ''),
      };
      this.indiceBusqueda.set(c, indice);
    }
    return indice.texto.includes(consulta) || (!!consultaRut && indice.rut.includes(consultaRut));
  }

  private armarEspecialidades(): string[] {
    const set = new Set<string>();
    for (const p of this.profesionalesCatalogo) if (p?.especialidad) set.add(p.especialidad);
    for (const c of this.citasAdmin)
      if (c?.especialidad && c.especialidad !== '?') set.add(c.especialidad);
    return [...set].sort((a, b) => a.localeCompare(b, 'es'));
  }

  /**
   * KPIs del período visible. Solo dependen del rango de fechas (no de la
   * búsqueda ni de las pestañas) para poder compararse con el período previo.
   */
  private armarKpis(): CitasKpi[] {
    const cargadas = this.citasCargadas;
    const formato = (n: number) => (cargadas ? n.toLocaleString('es-CL') : '—');
    const contar = (lista: any[], estado: string) =>
      lista.filter((c) => c.estado === estado).length;

    const hayComparacion = cargadas && this.ventana.previa !== null;
    const nota = (delta: CitasKpiDelta | null): string => {
      if (!cargadas) return '';
      if (!hayComparacion) return this.ventana.actual ? '' : 'Todas las fechas';
      return delta ? this.ventana.comparacion : 'Sin citas en el período anterior';
    };
    const delta = (actual: number, previo: number, masEsMejor: boolean): CitasKpiDelta | null => {
      if (!hayComparacion) return null;
      const pct = variacionPorcentual(actual, previo);
      if (pct === null) return null;
      if (pct === 0) return { texto: '0%', direccion: 'igual', tono: 'neutro' };
      const sube = pct > 0;
      const tono = masEsMejor ? (sube ? 'bueno' : 'neutro') : sube ? 'malo' : 'bueno';
      return { texto: `${Math.abs(pct)}%`, direccion: sube ? 'sube' : 'baja', tono };
    };

    const total = this.citasAdmin.length;
    const canceladas = contar(this.citasAdmin, 'cancelada');
    const pendientes = contar(this.citasAdmin, 'pendiente');
    const urgentes = this.citasAdmin.filter((c) => c.urgente).length;
    const sobrecupos = this.citasAdmin.filter((c) => c.sobrecupo).length;
    const dTotal = delta(total, this.citasPrevias.length, true);
    const dCanceladas = delta(canceladas, contar(this.citasPrevias, 'cancelada'), false);
    const dPendientes = delta(pendientes, contar(this.citasPrevias, 'pendiente'), false);
    const dUrgentes = delta(
      urgentes,
      this.citasPrevias.filter((c) => c.urgente).length,
      false,
    );
    const dSobrecupos = delta(
      sobrecupos,
      this.citasPrevias.filter((c) => c.sobrecupo).length,
      false,
    );

    const activos = this.profesionalesCatalogo.filter(
      (p) => (p?.estado ?? 'activo') === 'activo',
    ).length;
    const catalogoListo = this.profesionalesCatalogo.length > 0;

    return [
      {
        clave: 'total',
        etiqueta: 'Citas totales',
        valor: formato(total),
        icono: 'calendar_month',
        delta: dTotal,
        nota: nota(dTotal),
      },
      {
        clave: 'canceladas',
        etiqueta: 'Citas canceladas',
        valor: formato(canceladas),
        icono: 'cancel',
        delta: dCanceladas,
        nota: nota(dCanceladas),
      },
      {
        clave: 'pendientes',
        etiqueta: 'Citas pendientes',
        valor: formato(pendientes),
        icono: 'schedule',
        delta: dPendientes,
        nota: nota(dPendientes),
      },
      {
        clave: 'urgentes',
        etiqueta: 'Citas urgentes',
        valor: formato(urgentes),
        icono: 'warning',
        delta: dUrgentes,
        nota: nota(dUrgentes),
      },
      {
        clave: 'sobrecupo',
        etiqueta: 'Sobrecupo',
        valor: formato(sobrecupos),
        icono: 'event_repeat',
        delta: dSobrecupos,
        nota: nota(dSobrecupos),
      },
      {
        clave: 'profesionales',
        etiqueta: 'Profesionales activos',
        valor: catalogoListo ? activos.toLocaleString('es-CL') : '—',
        icono: 'person',
        delta: null,
        nota: catalogoListo ? 'Con estado activo' : '',
      },
    ];
  }

  // ═══════════════ Presentación ═══════════════

  contar(estado: EstadoCitaFiltro): number {
    return estado ? (this.conteos[estado] ?? 0) : this.conteos['todas'];
  }

  etiquetaEstado(estado: string): string {
    return ETIQUETA_ESTADO[estado] ?? estado;
  }

  iniciales(nombre: string): string {
    return inicialesDe(nombre);
  }

  claseAvatar(cita: any): string {
    return 'av-' + indiceColorAvatar(cita.estudiante_id ?? cita.estudiante);
  }

  iconoDelta(direccion: CitasKpiDelta['direccion']): string {
    return direccion === 'sube'
      ? 'arrow_upward'
      : direccion === 'baja'
        ? 'arrow_downward'
        : 'remove';
  }

  trackKpi = (_: number, k: CitasKpi) => k.clave;
  trackCita = (_: number, c: any) => c.id;
  trackPagina = (i: number, p: ItemPagina) => (p.elipsis ? 'e' + i : p.num);
  trackTab = (_: number, t: TabEstado) => t.valor;

  /**
   * Número de fila mostrado en la primera columna: sigue la posición real
   * dentro del listado filtrado, no solo dentro de la página (así en la
   * página 2 continúa en 9, 10, 11… en vez de reiniciar en 1).
   */
  numeroFila(indiceEnPagina: number): number {
    return (this.pagCitas - 1) * this.porPagina + indiceEnPagina + 1;
  }

  // ═══════════════ Menú por fila ═══════════════

  /** Controla solo las opciones de mutación (urgente/cancelar) dentro del menú; "Ver detalles" siempre está disponible. */
  tieneAccionesMutables(cita: any): boolean {
    return this.puedeGestionarAgenda && cita?.estado === 'pendiente';
  }

  alternarMenu(cita: any, evento: MouseEvent): void {
    if (this.menuCita === cita) {
      this.cerrarMenu();
      return;
    }
    const boton = evento.currentTarget as HTMLElement;
    const r = boton.getBoundingClientRect();
    const derecha = window.innerWidth - r.right;
    // Si no hay espacio abajo, el menú se abre hacia arriba.
    this.menuPos =
      window.innerHeight - r.bottom < 190
        ? { top: null, bottom: window.innerHeight - r.top + 6, right: derecha }
        : { top: r.bottom + 6, bottom: null, right: derecha };
    this.menuCita = cita;
    this.menuDisparador = boton;
  }

  cerrarMenu(devolverFoco = false): void {
    if (devolverFoco) this.menuDisparador?.focus();
    this.menuCita = null;
    this.menuDisparador = null;
  }

  @HostListener('document:click', ['$event'])
  alHacerClicFuera(evento: MouseEvent): void {
    if (!this.menuCita) return;
    const objetivo = evento.target as HTMLElement | null;
    if (
      objetivo?.closest('.citas-menu, .citas-btn-menu') &&
      this.host.nativeElement.contains(objetivo)
    )
      return;
    this.cerrarMenu();
  }

  @HostListener('document:keydown.escape')
  alPresionarEscape(): void {
    if (this.menuCita) this.cerrarMenu(true);
  }

  @HostListener('window:resize')
  alCambiarTamano(): void {
    this.cerrarMenu();
  }

  // ═══════════════ Acciones ═══════════════
  // Lectura: agenda.ver (el shell controla el render de la sección).
  // Mutaciones: agenda.gestionar, reforzado también en estos handlers.

  onVerDetalle(cita: any): void {
    this.cerrarMenu();
    this.verDetalle.emit(cita);
  }

  onMarcarPrioridad(cita: any, urgente: boolean): void {
    if (!this.puedeGestionarAgenda) return;
    this.cerrarMenu();
    this.marcarPrioridad.emit({ cita, urgente });
  }

  onCancelarCita(cita: any): void {
    if (!this.puedeGestionarAgenda) return;
    this.cerrarMenu();
    this.cancelarCita.emit(cita);
  }

  onIrAHorario(): void {
    if (!this.puedeGestionarAgenda) return;
    this.irAHorario.emit();
  }

  onIrAAgenda(): void {
    this.irAAgenda.emit();
  }

  onIrAProfesionales(): void {
    if (!this.puedeVerProfesionales) return;
    this.irAProfesionales.emit();
  }
}
