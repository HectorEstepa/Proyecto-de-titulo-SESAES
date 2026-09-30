import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

export interface HorarioBloqueClick {
  fecha: string;
  hora: string;
}

// Vista temporal de la agenda. La fuente de verdad del estado vive en el
// padre (DashboardAdminComponent); este componente solo la presenta y
// emite el cambio solicitado.
export type AgendaVista = 'dia' | 'semana' | 'mes';

// Celda de la vista Mes. `enMes=false` son los días de relleno del mes
// anterior/siguiente para completar las semanas: se muestran atenuados y
// no son interactivos (la disponibilidad solo se consulta para el mes
// visible).
export interface AgendaMesCelda {
  fecha: string;
  num: number;
  enMes: boolean;
  esHoy: boolean;
}

// Resumen de un día para la vista Mes. Lo calcula el padre a partir de
// las citas reales y de la disponibilidad que entrega backend; este
// componente no deriva ninguna regla de negocio.
export interface AgendaDiaResumen {
  citas: number;
  sobrecupos: number;
  urgencias: number;
  // Cantidad de horarios del día que tienen 2 o más citas operativas
  // (multicita, A.4.7A.1). La vista Mes no puede ocultar este caso.
  multicitaHorarios: number;
  disponibles: number;
  estado: 'con-cupos' | 'sin-cupos' | 'cerrado' | 'bloqueado' | 'pasado' | 'sin-datos';
}

const RESUMEN_DIA_VACIO: AgendaDiaResumen = {
  citas: 0,
  sobrecupos: 0,
  urgencias: 0,
  multicitaHorarios: 0,
  disponibles: 0,
  estado: 'sin-datos'
};

@Component({
  selector: 'app-admin-horario',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-horario.html',
  styleUrls: ['./admin-horario.css']
})
export class AdminHorarioComponent {
  @Input() puedeGestionarAgenda = false;
  @Input() solicitudesHorarioAdmin: any[] = [];

  // Reutilización en "Mi Agenda" del profesional (dashboard-profesional):
  // oculta el selector de profesional/especialidad, que no tiene sentido
  // cuando la vista ya está fija a un solo profesional (uno mismo).
  @Input() ocultarFiltros = false;

  // Reutilización en "Mi Agenda" del profesional: a diferencia del admin
  // (que cancela), el propio profesional acepta/rechaza sus citas
  // pendientes — ver PATCH /profesional/{id}/citas/{id}/aceptar|rechazar.
  // Independiente de puedeGestionarAgenda (que sigue gateando SOLO las
  // acciones administrativas: nueva cita, cancelar, aprobar/rechazar
  // solicitudes de horario).
  @Input() puedeAceptarRechazarPropio = false;
  @Output() aceptarCita = new EventEmitter<any>();
  @Output() rechazarCita = new EventEmitter<any>();

  onAceptarCita(cita: any): void {
    if (!this.puedeAceptarRechazarPropio) return;
    this.aceptarCita.emit(cita);
  }

  onRechazarCita(cita: any): void {
    if (!this.puedeAceptarRechazarPropio) return;
    this.rechazarCita.emit(cita);
  }

  @Input() especialidades: string[] = [];
  @Input() profesionalesFiltrados: any[] = [];

  @Input() filtroEspecialidad = '';
  @Output() filtroEspecialidadChange = new EventEmitter<string>();

  @Input() filtroProfesionalId: string | number = '';
  @Output() filtroProfesionalIdChange = new EventEmitter<string | number>();

  @Input() profesionalActual: any = null;
  @Input() profesionalActualBloqueado = false;

  @Input() semanaActual: any[] = [];
  @Input() semanaLabel = '';

  // Vista temporal (Día / Semana / Mes). Por defecto Semana, que es el
  // comportamiento previo del componente.
  @Input() vista: AgendaVista = 'semana';
  @Output() vistaChange = new EventEmitter<AgendaVista>();

  // Vista Día: un único día (misma forma que los elementos de
  // semanaActual: { nombre, num, fecha, esHoy }).
  @Input() diaActual: any = null;

  // Vista Mes: celdas del calendario mensual y resumen por día.
  @Input() mesCeldas: AgendaMesCelda[] = [];
  @Input() diaResumenFn: (fecha: string) => AgendaDiaResumen =
    () => RESUMEN_DIA_VACIO;

  // Etiqueta del período visible. Si el padre no la informa (compatibilidad
  // con el uso anterior, solo semanal) se usa semanaLabel.
  @Input() periodoLabel = '';
  @Input() horasGrilla: string[] = [];

  @Input() diaSeleccionado: string | null = null;
  @Output() diaSeleccionadoChange = new EventEmitter<string | null>();

  @Input() citasDiaSeleccionado: any[] = [];

  @Input() citasHorario: any[] = [];
  @Input() diasCerrados: any[] = [];

  @Input() bloqueEstadoFn: (fecha: string, hora: string) => string =
    () => 'sin-datos';

  @Input() bloqueInfoFn: (fecha: string, hora: string) => string =
    () => '';

  // A.4.7A.1 — la grilla necesita el arreglo completo de citas del
  // bloque (no un solo resumen en texto) para poder pintar cada una por
  // separado cuando hay más de una en el mismo slot (p. ej. una cita
  // normal + una sobrecupo forzada encima).
  @Input() bloqueCitasFn: (fecha: string, hora: string) => any[] =
    () => [];

  // A.4.7A v2 — capacidad de sobrecupo real (unificada para ocupado,
  // colación y fuera de jornada). El dominio de bloqueEstadoFn no
  // cambia; esto es presentación pura: informa si ADEMÁS existe la
  // posibilidad de un sobrecupo real sobre ese slot.
  @Input() bloqueSobrecupoDisponibleFn: (fecha: string, hora: string) => boolean =
    () => false;

  // A.4.7A v2 — título/aria comprensible por estado. Para colación y
  // fuera de jornada, el texto ahora depende de si el usuario realmente
  // tiene capacidad de sobrecupo (bloqueSobrecupoDisponibleFn, unificado
  // en dashboard-admin.ts): antes siempre decía "clic para forzar
  // sobrecupo" aunque a la cuenta le faltara agenda.sobrecupo, prometiendo
  // una acción que clickBloque() ya no permite ejecutar.
  bloqueTitulo(fecha: string, hora: string): string {
    const estado = this.bloqueEstadoFn(fecha, hora);
    if (estado === 'sin-datos') return 'Disponibilidad aún no disponible';
    if (estado === 'cerrado-centro') return 'El centro no atiende este día';
    if (estado === 'fuera-horario') {
      return this.bloqueSobrecupoDisponibleFn(fecha, hora)
        ? 'Fuera del horario habitual — clic para solicitar sobrecupo'
        : 'Fuera del horario habitual del profesional';
    }
    if (estado === 'colacion') {
      return this.bloqueSobrecupoDisponibleFn(fecha, hora)
        ? 'Hora de colación — clic para solicitar sobrecupo'
        : 'Hora de colación del profesional';
    }
    if (estado === 'ocupado' && this.bloqueSobrecupoDisponibleFn(fecha, hora)) {
      return 'Horario ocupado — clic para solicitar sobrecupo';
    }
    return '';
  }

  @Input() formatearFechaFn: (fecha: string) => string =
    fecha => fecha;

  @Input() esFeriadoFn: (fecha: string | undefined) => boolean =
    () => false;

  @Input() nombreFeriadoFn: (fecha: string | undefined) => string =
    () => '';

  @Output() aprobarSolicitud = new EventEmitter<any>();
  @Output() rechazarSolicitud = new EventEmitter<any>();

  @Output() filtrar = new EventEmitter<void>();
  @Output() recargarHorario = new EventEmitter<void>();

  @Output() abrirNuevaCita = new EventEmitter<void>();
  @Output() imprimir = new EventEmitter<void>();

  // Vista Mes: abrir la vista Día de una fecha concreta.
  @Output() abrirDia = new EventEmitter<string>();

  @Output() anterior = new EventEmitter<void>();
  @Output() siguiente = new EventEmitter<void>();
  @Output() hoy = new EventEmitter<void>();

  @Output() bloqueClick = new EventEmitter<HorarioBloqueClick>();
  @Output() cancelarCita = new EventEmitter<any>();


  get tieneProfesionalSeleccionado(): boolean {
    return String(this.filtroProfesionalId ?? '').trim().length > 0;
  }

  readonly nombresDiasSemana = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

  // Días que muestra la grilla horaria: uno en la vista Día, siete en
  // Semana. La vista Mes usa mesCeldas y no esta grilla.
  get diasGrilla(): any[] {
    if (this.vista === 'dia') return this.diaActual ? [this.diaActual] : [];
    return this.semanaActual ?? [];
  }

  get etiquetaPeriodo(): string {
    return this.periodoLabel || this.semanaLabel;
  }

  get tituloVista(): string {
    if (this.vista === 'dia') return 'Vista diaria';
    if (this.vista === 'mes') return 'Vista mensual';
    return 'Vista semanal';
  }

  // Textos del período visible, usados por los KPI y la navegación.
  get periodoNombre(): string {
    if (this.vista === 'dia') return 'el día';
    if (this.vista === 'mes') return 'el mes';
    return 'la semana';
  }

  get periodoVisibleTexto(): string {
    if (this.vista === 'dia') return 'Día visible';
    if (this.vista === 'mes') return 'Mes visible';
    return 'Semana visible';
  }

  get navegacionAnteriorLabel(): string {
    if (this.vista === 'dia') return 'Día anterior';
    if (this.vista === 'mes') return 'Mes anterior';
    return 'Semana anterior';
  }

  get navegacionSiguienteLabel(): string {
    if (this.vista === 'dia') return 'Día siguiente';
    if (this.vista === 'mes') return 'Mes siguiente';
    return 'Semana siguiente';
  }

  // Fechas del período que se está mostrando. Todos los KPI se calculan
  // sobre este conjunto, para que coincidan con lo que hay en pantalla.
  private get fechasVisibles(): Set<string> {
    if (this.vista === 'dia') {
      const fecha = String(this.diaActual?.fecha ?? '');
      return new Set(fecha ? [fecha] : []);
    }
    if (this.vista === 'mes') {
      return new Set(
        (this.mesCeldas ?? []).filter(celda => celda?.enMes).map(celda => String(celda.fecha))
      );
    }
    return new Set((this.semanaActual ?? []).map(dia => String(dia?.fecha ?? '')));
  }

  private get citasSemana(): any[] {
    const fechas = this.fechasVisibles;
    return (this.citasHorario ?? []).filter(cita => fechas.has(String(cita?.fecha ?? '')));
  }

  private esCitaOperativa(cita: any): boolean {
    const estado = String(cita?.estado ?? '').toLowerCase();
    return estado !== 'cancelada' && estado !== 'inasistencia';
  }

  get citasProgramadasSemana(): number | null {
    if (!this.tieneProfesionalSeleccionado) return null;
    return this.citasSemana.filter(cita => this.esCitaOperativa(cita)).length;
  }

  get atencionesRealizadasSemana(): number | null {
    if (!this.tieneProfesionalSeleccionado) return null;
    return this.citasSemana.filter(
      cita => String(cita?.estado ?? '').toLowerCase() === 'completada'
    ).length;
  }

  get sobrecuposSemana(): number | null {
    if (!this.tieneProfesionalSeleccionado) return null;
    return this.citasSemana.filter(
      cita => this.esCitaOperativa(cita) && !!cita?.sobrecupo
    ).length;
  }

  get urgenciasSemana(): number | null {
    if (!this.tieneProfesionalSeleccionado) return null;
    return this.citasSemana.filter(
      cita => this.esCitaOperativa(cita) && !!cita?.urgente
    ).length;
  }

  get bloqueosSemana(): number | null {
    if (!this.tieneProfesionalSeleccionado) return null;
    const fechas = this.fechasVisibles;
    return new Set(
      (this.diasCerrados ?? [])
        .map(dia => String(dia?.fecha ?? ''))
        .filter(fecha => fechas.has(fecha))
    ).size;
  }

  get citasProgramadasDia(): number {
    return (this.citasDiaSeleccionado ?? []).filter(cita => this.esCitaOperativa(cita)).length;
  }

  get atencionesRealizadasDia(): number {
    return (this.citasDiaSeleccionado ?? []).filter(
      cita => String(cita?.estado ?? '').toLowerCase() === 'completada'
    ).length;
  }

  get sobrecuposDia(): number {
    return (this.citasDiaSeleccionado ?? []).filter(
      cita => this.esCitaOperativa(cita) && !!cita?.sobrecupo
    ).length;
  }

  get urgenciasDia(): number {
    return (this.citasDiaSeleccionado ?? []).filter(
      cita => this.esCitaOperativa(cita) && !!cita?.urgente
    ).length;
  }

  cambiarVista(vista: AgendaVista): void {
    if (vista === this.vista) return;
    this.vistaChange.emit(vista);
  }

  resumenDia(fecha: string): AgendaDiaResumen {
    return this.diaResumenFn(fecha) ?? RESUMEN_DIA_VACIO;
  }

  onSeleccionarDiaMes(celda: AgendaMesCelda): void {
    if (!celda?.enMes) return;
    this.diaSeleccionadoChange.emit(celda.fecha);
  }

  onAbrirDia(fecha: string | null): void {
    if (!fecha) return;
    this.abrirDia.emit(fecha);
  }

  onAprobarSolicitud(solicitud: any): void {
    if (!this.puedeGestionarAgenda) return;
    this.aprobarSolicitud.emit(solicitud);
  }

  onRechazarSolicitud(solicitud: any): void {
    if (!this.puedeGestionarAgenda) return;
    this.rechazarSolicitud.emit(solicitud);
  }

  onAbrirNuevaCita(): void {
    if (!this.puedeGestionarAgenda) return;
    this.abrirNuevaCita.emit();
  }

  onCancelarCita(cita: any): void {
    if (!this.puedeGestionarAgenda) return;
    this.cancelarCita.emit(cita);
  }
}