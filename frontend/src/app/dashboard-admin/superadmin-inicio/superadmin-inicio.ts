import { ChangeDetectorRef, Component, DestroyRef, EventEmitter, Input, OnInit, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable } from 'rxjs';

import { AuthService } from '../../auth.service';
import { Permission } from '../../shared/auth/permission.model';
import { SuperadminInicioCalendarioComponent } from './superadmin-inicio-calendario';
import {
  AccionInicio,
  AdministradorResumen,
  Bloque,
  DestinoInicioInstitucional,
  EspecialidadCitas,
  EstadoBloque,
  EventoAuditoria,
  GestionInicio,
  ProfesionalSolicitado,
  ResumenInicio,
  ResumenKpis,
  SolicitudPendiente,
  UsuarioReciente,
  bloqueCargando
} from './superadmin-inicio.models';
import { SuperadminInicioService } from './superadmin-inicio.service';
import {
  GraficoDonut,
  GraficoLinea,
  construirDonut,
  construirGraficoLinea,
  etiquetaMesLargo,
  etiquetaModulo,
  etiquetaRol,
  etiquetaTipoSolicitud,
  formatearFecha,
  formatearFechaCorta,
  formatearFechaDiaMesAnio,
  formatearFechaHora,
  inicial,
  nombreConTratamiento,
  tiempoRelativo,
  truncar
} from './superadmin-inicio.utils';

/**
 * Permisos EFECTIVOS que habilitan cada bloque. Es solo la decisión de
 * "intentar o no" del frontend: el backend valida de nuevo y es la única
 * fuente de verdad (fail-closed). No hay ningún atajo por rol.
 *
 * ROLES_GESTIONAR y AUDITORIA_VER son permisos reservados de SUPERADMIN.
 */
export const PERMISOS_BLOQUE = {
  resumen: ['roles.gestionar', 'reportes.ver'],
  especialidades: ['reportes.ver'],
  gestion: ['roles.gestionar', 'usuarios.ver', 'agenda.gestionar'],
  administradores: ['roles.gestionar'],
  auditoria: ['auditoria.ver']
} as const satisfies Record<string, readonly Permission[]>;

/** Filas de cada lista corta. */
export const FILAS_AUDITORIA_TABLA = 8;
export const FILAS_ACTIVIDAD = 5;
export const FILAS_ADMINISTRADORES = 5;

export type TonoKpi = 'teal' | 'blue' | 'amber' | 'violet' | 'rose' | 'orange';

export interface KpiCard {
  clave: string;
  etiqueta: string;
  icono: string;
  tono: TonoKpi;
  /** Texto ya formateado; '—' cuando el dato no está disponible. */
  valor: string;
  nota: string;
  /** Definición explícita de la métrica (se muestra como tooltip). */
  definicion: string;
  disponible: boolean;
}

export type BloqueClave = keyof typeof PERMISOS_BLOQUE;

/**
 * Acciones de navegación del Inicio → módulo de detalle. Destinos
 * verificados contra el código real del shell (ver navegarA):
 *
 *  · Citas por mes           → Historial (tiene Desde/Hasta, estado,
 *                              especialidad, paginación y exportación).
 *                              Reportes hoy NO tiene reporte mensual ni
 *                              filtro de período; cuando exista, basta
 *                              cambiar `destino` aquí.
 *  · Citas por especialidad  → Reportes (tarjeta homónima con Excel).
 *  · Solicitudes de horario  → Horario (tarjeta con aprobar/rechazar).
 *  · Administradores         → Administradores.
 *  · Auditoría / Actividad   → Configuración › Seguridad.
 *
 * SIN acción a propósito (no existe un destino equivalente; no se simula):
 *  · Profesionales más solicitados: no hay reporte de ranking por
 *    profesional ni filtro por profesional en Historial/Reportes.
 *  · Últimos usuarios: lista mezclada de roles; no existe un listado
 *    unificado de usuarios (solo Estudiantes / Profesionales /
 *    Administradores por separado).
 */
export const ACCIONES_INICIO = {
  citasMes: { clave: 'citasMes', destino: 'historial', etiqueta: 'Ver historial' },
  especialidad: { clave: 'especialidad', destino: 'reportes', etiqueta: 'Ver reporte' },
  solicitudes: { clave: 'solicitudes', destino: 'horario', etiqueta: 'Ver solicitudes' },
  administradores: { clave: 'administradores', destino: 'administradores', etiqueta: 'Ver administradores' },
  auditoria: { clave: 'auditoria', destino: 'auditoria', etiqueta: 'Ver auditoría' },
  actividad: { clave: 'actividad', destino: 'auditoria', etiqueta: 'Ver auditoría' }
} as const satisfies Record<string, AccionInicio>;

export const ETIQUETA_INCIDENCIAS = 'Incidencias (eventos de error/denegación)';

/**
 * Inicio institucional de SUPERADMIN.
 *
 * Dueño de su propio HTTP y de sus estados (mismo patrón que
 * AdminAdministradoresComponent / AdminCitasComponent): el shell solo lo
 * monta. Cada bloque carga, falla y se reintenta de forma independiente.
 */
@Component({
  selector: 'app-superadmin-inicio',
  standalone: true,
  imports: [CommonModule, SuperadminInicioCalendarioComponent],
  templateUrl: './superadmin-inicio.html',
  styleUrl: './superadmin-inicio.css'
})
export class SuperadminInicioComponent implements OnInit {
  private readonly service = inject(SuperadminInicioService);
  private readonly auth = inject(AuthService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);

  // ── Estado por bloque ────────────────────────────────────────
  resumen: Bloque<ResumenInicio> = bloqueCargando();
  especialidades: Bloque<EspecialidadCitas[]> = bloqueCargando();
  gestion: Bloque<GestionInicio> = bloqueCargando();
  administradores: Bloque<AdministradorResumen[]> = bloqueCargando();
  auditoria: Bloque<EventoAuditoria[]> = bloqueCargando();

  // ── Derivados de los datos cargados ──────────────────────────
  kpis: KpiCard[] = [];
  graficoMes: GraficoLinea | null = null;
  graficoDonut: GraficoDonut | null = null;
  periodoEspecialidades = '';
  periodoTop = '';
  adminsActivos: AdministradorResumen[] = [];
  eventosTabla: EventoAuditoria[] = [];
  eventosActividad: EventoAuditoria[] = [];

  /**
   * El shell decide si el actor puede entrar a cada destino (mismos
   * permisos que el sidebar). Por defecto NADA es navegable: fail-closed.
   */
  @Input() puedeIrA: (destino: DestinoInicioInstitucional) => boolean = () => false;

  /** Pide al shell abrir un módulo de detalle. */
  @Output() navegar = new EventEmitter<DestinoInicioInstitucional>();

  readonly acciones = ACCIONES_INICIO;

  /** Helpers de formato expuestos a la plantilla. */
  readonly etiquetaIncidencias = ETIQUETA_INCIDENCIAS;
  readonly etiquetaRol = etiquetaRol;
  readonly etiquetaModulo = etiquetaModulo;
  readonly etiquetaTipoSolicitud = etiquetaTipoSolicitud;
  readonly formatearFecha = formatearFecha;
  readonly formatearFechaHora = formatearFechaHora;
  readonly tiempoRelativo = (iso: string | null) => tiempoRelativo(iso);
  readonly truncar = truncar;
  readonly inicial = inicial;

  ngOnInit(): void {
    this.cargarTodo();
  }

  cargarTodo(): void {
    this.cargarResumen();
    this.cargarEspecialidades();
    this.cargarGestion();
    this.cargarAdministradores();
    this.cargarAuditoria();
  }

  /** Derivar a un módulo de detalle (solo si el shell lo permite). */
  ir(destino: DestinoInicioInstitucional): void {
    if (!this.puedeIrA(destino)) return;
    this.navegar.emit(destino);
  }

  /** Reintenta SOLO el bloque que falló; los demás no se tocan. */
  reintentar(clave: BloqueClave): void {
    switch (clave) {
      case 'resumen': return this.cargarResumen();
      case 'especialidades': return this.cargarEspecialidades();
      case 'gestion': return this.cargarGestion();
      case 'administradores': return this.cargarAdministradores();
      case 'auditoria': return this.cargarAuditoria();
    }
  }

  // ── Carga por bloque ─────────────────────────────────────────
  cargarResumen(): void {
    this.cargarBloque(
      PERMISOS_BLOQUE.resumen,
      () => this.service.getResumen(),
      (estado, datos) => {
        this.resumen = { estado, datos };
        this.kpis = datos ? this.construirKpis(datos.kpis) : [];
        this.graficoMes = datos && datos.citas_por_mes.meses.some(m => m.cantidad > 0)
          ? construirGraficoLinea(datos.citas_por_mes.meses)
          : null;
        this.periodoTop = datos
          ? `Últimos ${datos.profesionales_mas_solicitados.dias} días `
            + `(${formatearFechaCorta(datos.profesionales_mas_solicitados.desde)} – `
            + `${formatearFechaDiaMesAnio(datos.profesionales_mas_solicitados.hasta)})`
          : '';
      }
    );
  }

  cargarEspecialidades(): void {
    const hoy = new Date();
    const mes = hoy.getMonth() + 1;
    const anio = hoy.getFullYear();
    this.periodoEspecialidades = etiquetaMesLargo(`${anio}-${String(mes).padStart(2, '0')}`);

    this.cargarBloque(
      PERMISOS_BLOQUE.especialidades,
      () => this.service.getCitasPorEspecialidad(mes, anio),
      (estado, datos) => {
        const donut = datos ? construirDonut(datos) : null;
        this.graficoDonut = donut && donut.total > 0 ? donut : null;
        this.especialidades = {
          estado: estado === 'listo' && !this.graficoDonut ? 'vacio' : estado,
          datos
        };
      }
    );
  }

  cargarGestion(): void {
    this.cargarBloque(
      PERMISOS_BLOQUE.gestion,
      () => this.service.getGestion(),
      (estado, datos) => {
        this.gestion = { estado, datos };
      }
    );
  }

  cargarAdministradores(): void {
    this.cargarBloque(
      PERMISOS_BLOQUE.administradores,
      () => this.service.getAdministradores(),
      (estado, datos) => {
        this.adminsActivos = (datos ?? [])
          .filter(a => a.activo)
          .sort((a, b) =>
            (a.rol === b.rol ? 0 : a.rol === 'superadmin' ? -1 : 1)
            || (a.nombre ?? a.correo).localeCompare(b.nombre ?? b.correo)
          );
        this.administradores = {
          estado: estado === 'listo' && this.adminsActivos.length === 0 ? 'vacio' : estado,
          datos
        };
      }
    );
  }

  cargarAuditoria(): void {
    this.cargarBloque(
      PERMISOS_BLOQUE.auditoria,
      () => this.service.getAuditoriaReciente(),
      (estado, datos) => {
        this.eventosTabla = (datos ?? []).slice(0, FILAS_AUDITORIA_TABLA);
        this.eventosActividad = (datos ?? []).slice(0, FILAS_ACTIVIDAD);
        this.auditoria = {
          estado: estado === 'listo' && (datos ?? []).length === 0 ? 'vacio' : estado,
          datos
        };
      }
    );
  }

  /**
   * Núcleo común: sin permiso efectivo NO se hace la petición
   * ('sin_permiso'); un 403 del backend también se muestra como
   * 'sin_permiso'; cualquier otro fallo es 'error' visible y reintentable.
   */
  private cargarBloque<T>(
    permisos: readonly Permission[],
    fuente: () => Observable<T>,
    aplicar: (estado: EstadoBloque, datos: T | null) => void
  ): void {
    if (!permisos.every(p => this.auth.hasPermission(p))) {
      aplicar('sin_permiso', null);
      this.cdr.detectChanges();
      return;
    }

    aplicar('cargando', null);

    fuente().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: datos => {
        aplicar('listo', datos);
        this.cdr.detectChanges();
      },
      error: (err: unknown) => {
        const prohibido = err instanceof HttpErrorResponse && err.status === 403;
        aplicar(prohibido ? 'sin_permiso' : 'error', null);
        this.cdr.detectChanges();
      }
    });
  }

  // ── Estados compuestos (bloques que comparten una petición) ──
  get estadoSerieMensual(): EstadoBloque {
    return this.resumen.estado === 'listo' && !this.graficoMes ? 'vacio' : this.resumen.estado;
  }

  get estadoTopProfesionales(): EstadoBloque {
    const r = this.resumen;
    return r.estado === 'listo' && r.datos!.profesionales_mas_solicitados.items.length === 0
      ? 'vacio'
      : r.estado;
  }

  get estadoUltimosUsuarios(): EstadoBloque {
    const g = this.gestion;
    return g.estado === 'listo' && g.datos!.ultimos_usuarios.length === 0 ? 'vacio' : g.estado;
  }

  get estadoSolicitudes(): EstadoBloque {
    const g = this.gestion;
    return g.estado === 'listo' && g.datos!.solicitudes_pendientes.items.length === 0
      ? 'vacio'
      : g.estado;
  }

  get topProfesionales(): ProfesionalSolicitado[] {
    return this.resumen.datos?.profesionales_mas_solicitados.items ?? [];
  }

  get maximoTop(): number {
    return Math.max(1, ...this.topProfesionales.map(p => p.cantidad));
  }

  get ultimosUsuarios(): UsuarioReciente[] {
    return this.gestion.datos?.ultimos_usuarios ?? [];
  }

  get solicitudes(): SolicitudPendiente[] {
    return this.gestion.datos?.solicitudes_pendientes.items ?? [];
  }

  get solicitudesTotal(): number {
    return this.gestion.datos?.solicitudes_pendientes.total ?? 0;
  }

  get adminsVisibles(): AdministradorResumen[] {
    return this.adminsActivos.slice(0, FILAS_ADMINISTRADORES);
  }

  get adminsOcultos(): number {
    return Math.max(0, this.adminsActivos.length - FILAS_ADMINISTRADORES);
  }

  // ── Presentación ─────────────────────────────────────────────
  nombreProfesional(p: ProfesionalSolicitado): string {
    return nombreConTratamiento(p);
  }

  nombreUsuario(u: UsuarioReciente): string {
    return u.nombre?.trim() || 'Sin nombre';
  }

  nombreAdministrador(a: AdministradorResumen): string {
    return a.nombre?.trim() || a.correo;
  }

  actorEvento(e: EventoAuditoria): string {
    return e.actor_nombre?.trim() || etiquetaRol(e.actor_rol);
  }

  fechaCreacionUsuario(u: UsuarioReciente): string {
    // Cuentas anteriores al registro de fechas: no hay dato real → "—".
    return u.fecha_creacion ? formatearFecha(u.fecha_creacion) : '—';
  }

  fechaSolicitud(s: SolicitudPendiente): string {
    return formatearFecha(s.fecha_solicitud);
  }

  claseResultado(resultado: string): string {
    return resultado === 'exito' ? 'ok' : resultado === 'denegado' ? 'warn' : 'err';
  }

  etiquetaResultado(resultado: string): string {
    switch (resultado) {
      case 'exito': return 'Éxito';
      case 'denegado': return 'Denegado';
      case 'error': return 'Error';
      default: return resultado;
    }
  }

  iconoResultado(resultado: string): string {
    return resultado === 'exito' ? 'task_alt' : resultado === 'denegado' ? 'block' : 'error';
  }

  trackPorIndice(indice: number): number {
    return indice;
  }

  trackPorClave(_: number, item: { clave: string }): string {
    return item.clave;
  }

  // ── KPIs ─────────────────────────────────────────────────────
  private construirKpis(k: ResumenKpis): KpiCard[] {
    const incidencias = k.incidencias;

    return [
      {
        clave: 'estudiantes', etiqueta: 'Estudiantes registrados', icono: 'school', tono: 'teal',
        valor: String(k.estudiantes_registrados), nota: 'Cuentas de estudiantes', disponible: true,
        definicion: 'Cuentas registradas con rol estudiante.'
      },
      {
        clave: 'profesionales', etiqueta: 'Profesionales activos', icono: 'medical_services', tono: 'blue',
        valor: String(k.profesionales_activos), nota: 'Estado "activo"', disponible: true,
        definicion: 'Profesionales cuyo estado actual es "activo" (excluye licencia e inasistencia).'
      },
      {
        clave: 'citas', etiqueta: 'Citas este mes', icono: 'event_available', tono: 'violet',
        valor: String(k.citas_mes), nota: 'Programadas y atendidas', disponible: true,
        definicion: 'Citas del mes en curso con estado pendiente o completada. No incluye canceladas ni inasistencias.'
      },
      {
        clave: 'especialidades', etiqueta: 'Especialidades', icono: 'category', tono: 'amber',
        valor: String(k.especialidades), nota: 'Distintas en profesionales', disponible: true,
        definicion: 'Cantidad de especialidades distintas registradas en los profesionales. '
          + 'No existe un catálogo de especialidades: se cuentan los valores del campo, '
          + 'ignorando mayúsculas y espacios sobrantes (no unifica variantes con y sin tilde).'
      },
      {
        clave: 'solicitudes', etiqueta: 'Solicitudes pendientes', icono: 'pending_actions', tono: 'orange',
        valor: String(k.solicitudes_pendientes), nota: 'Solicitudes de horario', disponible: true,
        definicion: 'Solicitudes de cambio de horario o colación de profesionales en estado pendiente.'
      },
      {
        clave: 'incidencias', etiqueta: ETIQUETA_INCIDENCIAS, icono: 'warning', tono: 'rose',
        valor: incidencias ? String(incidencias.total) : '—',
        nota: incidencias ? `Últimos ${incidencias.dias} días` : 'No disponible para tu acceso',
        definicion: 'Eventos de auditoría con resultado denegado o error en los últimos 30 días. '
          + 'No es un módulo formal de incidencias.',
        disponible: incidencias !== null
      }
    ];
  }
}
