import { CommonModule } from '@angular/common';
import { Component, DoCheck, EventEmitter, Input, Output } from '@angular/core';
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

// Minutos desde medianoche para "HH:MM", "HH:MM:SS" o "HH:MM AM/PM".
// Devuelve null si el texto no se puede leer (no se inventa una hora).
function minutosDeHora(texto: unknown): number | null {
  const m = /^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp])?\.?[Mm]?\.?\s*$/.exec(String(texto ?? ''));
  if (!m) return null;
  let h = Number(m[1]);
  const min = Number(m[2]);
  const ap = m[3]?.toLowerCase();
  if (ap === 'p' && h < 12) h += 12;
  if (ap === 'a' && h === 12) h = 0;
  return h > 23 || min > 59 ? null : h * 60 + min;
}

@Component({
  selector: 'app-admin-horario',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-horario.html',
  styleUrls: ['./admin-horario.css']
})
export class AdminHorarioComponent implements DoCheck {
  @Input() puedeGestionarAgenda = false;
  // Solicitar un sobrecupo desde el botón de la barra exige además el
  // permiso agenda.sobrecupo; el shell lo informa, la agenda no lo deduce.
  @Input() puedeSobrecupo = false;
  @Input() solicitudesHorarioAdmin: any[] = [];

  // Modo consulta propia (Profesional de Salud). La MISMA grilla y el mismo
  // diseño del panel administrativo se reutilizan, pero se sustituyen los
  // filtros de terceros por la identidad de la sesión y se oculta el cambio
  // de vista: el profesional solo consulta su propia semana.
  //
  // La seguridad NO depende de este flag: puedeGestionarAgenda=false ya
  // bloquea en TypeScript cada acción administrativa y el backend sigue
  // siendo la autoridad final (ownership + permisos).
  @Input() modoProfesional = false;

  // La agenda solo muestra de lunes a viernes: el centro no atiende fines
  // de semana, así que ni el panel Admin ni la agenda del Profesional de
  // Salud pintan columnas de sábado/domingo. El padre lo activa
  // explícitamente (dashboard-admin.html y dashboard-profesional.html);
  // el valor por defecto se mantiene en false para no alterar a otros
  // consumidores del componente.
  @Input() soloDiasLaborables = false;

  // Etiqueta corta del horario vigente ("Horario predeterminado",
  // "Horario personalizado aprobado", "Cambio pendiente"). Solo se pinta
  // en modo profesional, como parte de la identidad de la sesión.
  @Input() horarioVigenteLabel = '';

  // Permite abrir la ficha del paciente desde el panel contextual. Solo se
  // activa cuando el padre conecta (citaClick); en el panel admin queda
  // desactivado para no cambiar su comportamiento.
  @Input() citaClickable = false;
  @Output() citaClick = new EventEmitter<any>();

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
  @Output() abrirSobrecupo = new EventEmitter<void>();
  @Output() imprimir = new EventEmitter<void>();

  // Vista Mes: abrir la vista Día de una fecha concreta.
  @Output() abrirDia = new EventEmitter<string>();

  @Output() anterior = new EventEmitter<void>();
  @Output() siguiente = new EventEmitter<void>();
  @Output() hoy = new EventEmitter<void>();

  @Output() bloqueClick = new EventEmitter<HorarioBloqueClick>();
  @Output() cancelarCita = new EventEmitter<any>();


  // ¿El centro no atiende este día? Se considera cerrado cuando TODOS los
  // bloques del día vienen como 'cerrado-centro' desde la disponibilidad, o
  // cuando existe un cierre registrado para esa fecha (diasCerrados). No se
  // infiere nada más: un día sin datos NO se muestra como cerrado.
  diaCerrado(fecha: string): boolean {
    if ((this.diasCerrados ?? []).some(d => d?.fecha === fecha)) return true;
    return this.horasGrilla.length > 0
      && this.horasGrilla.every(h => this.bloqueEstadoFn(fecha, h) === 'cerrado-centro');
  }

  // Motivo visible de un día sin atención: primero el motivo del cierre
  // registrado, luego el nombre del feriado y, si no hay ninguno, el texto
  // genérico.
  motivoCierre(fecha: string): string {
    const cierre = (this.diasCerrados ?? []).find(d => d?.fecha === fecha);
    const motivo = String(cierre?.motivo ?? '').trim();
    if (motivo) return motivo;
    if (this.esFeriadoFn(fecha)) return this.nombreFeriadoFn(fecha) || 'Feriado';
    return 'Centro cerrado';
  }

  // Horas VIGENTES del profesional seleccionado (las que dejó aprobadas el
  // administrador). Si falta alguna, se dice y no se inventa un valor.
  get colacionTexto(): string {
    const ini = this.profesionalActual?.hora_almuerzo_inicio;
    const fin = this.profesionalActual?.hora_almuerzo_fin;
    return ini && fin ? `${ini} – ${fin}` : '';
  }

  get salidaTexto(): string {
    return this.profesionalActual?.horario_fin || '';
  }

  get tieneProfesionalSeleccionado(): boolean {
    return String(this.filtroProfesionalId ?? '').trim().length > 0;
  }

  readonly nombresDiasSemana = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

  // Días que muestra la grilla horaria: uno en la vista Día, siete en
  // Semana (o cinco si soloDiasLaborables). La vista Mes usa mesCeldas y
  // no esta grilla.
  get diasGrilla(): any[] {
    if (this.vista === 'dia') return this.diaActual ? [this.diaActual] : [];
    const dias = this.semanaActual ?? [];
    if (!this.soloDiasLaborables) return dias;
    return dias.filter(dia => this.esDiaLaborable(dia?.fecha));
  }

  private esDiaLaborable(fecha: string | undefined): boolean {
    const [anio, mes, dia] = String(fecha ?? '').split('-').map(Number);
    if (!anio || !mes || !dia) return true;
    const dow = new Date(anio, mes - 1, dia).getDay();
    return dow !== 0 && dow !== 6;
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
    return new Set(this.diasGrilla.map(dia => String(dia?.fecha ?? '')));
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

  /** Nombre legible del tipo de solicitud de horario. */
  tipoSolicitudLabel(s: any): string {
    return s.tipo === 'colacion' ? 'Colación' : s.tipo === 'bloques' ? 'Horario semanal' : 'Jornada';
  }

  /**
   * Horario pedido. Para una agenda por bloques arma un resumen por dia,
   * agrupando los dias que quedaron iguales: "Lun-Jue: 09:00-13:00, colación
   * 13:00-14:00, 14:00-17:30 | Vie: 09:00-13:00, ...".
   */
  horarioSolicitado(s: any): string {
    if (s.tipo !== 'bloques') return `${s.hora_inicio} a ${s.hora_fin}`;
    const nombres = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie'];
    const porDia = nombres.map((_, dia) =>
      (s.bloques ?? [])
        .filter((b: any) => b.dia_semana === dia)
        .sort((a: any, b: any) => a.hora_inicio.localeCompare(b.hora_inicio))
        .map((b: any) => `${b.tipo === 'colacion' ? 'colación ' : ''}${b.hora_inicio}-${b.hora_fin}`)
        .join(', ')
    );
    const grupos: { desde: number; hasta: number; texto: string }[] = [];
    porDia.forEach((texto, dia) => {
      if (!texto) return;
      const ultimo = grupos[grupos.length - 1];
      if (ultimo && ultimo.texto === texto && ultimo.hasta === dia - 1) ultimo.hasta = dia;
      else grupos.push({ desde: dia, hasta: dia, texto });
    });
    return grupos
      .map(g => `${g.desde === g.hasta ? nombres[g.desde] : nombres[g.desde] + '-' + nombres[g.hasta]}: ${g.texto}`)
      .join(' | ');
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

  onAbrirSobrecupo(): void {
    if (!this.puedeGestionarAgenda || !this.puedeSobrecupo) return;
    this.abrirSobrecupo.emit();
  }

  // Altura de cada hora de la grilla. Una hora con dos citas (normal +
  // sobrecupo) se muestra en dos recuadros apilados, así que esa fila crece
  // para TODOS los días y para la columna de horas a la vez: las columnas son
  // independientes y solo quedan alineadas si cada hora mide lo mismo en todas.
  private readonly ALTO_HORA_PX = 48;
  private readonly ALTO_ENCABEZADO_PX = 62;
  private alturas = new Map<string, number>();

  // Colación: un recuadro por cada día con atención, con el mismo estilo que
  // una cita, ubicado en la hora REAL de colación vigente (aprobada) del
  // profesional — no en las filas completas de la grilla, que pueden ser más
  // anchas. Una solicitud de cambio pendiente no lo mueve.
  bandaColacion: { top: number; alto: number } | null = null;
  fechasBandaColacion = new Set<string>();

  ngDoCheck(): void {
    const dias = this.diasGrilla;
    const horas = this.horasGrilla ?? [];
    this.alturas.clear();
    for (const h of horas) {
      let filas = 1;
      for (const dia of dias) {
        filas = Math.max(filas, Math.min(2, this.bloqueCitasFn(dia.fecha, h).length));
      }
      this.alturas.set(h, this.ALTO_HORA_PX * filas);
    }
    this.calcularBandaColacion(dias, horas);
  }

  private calcularBandaColacion(dias: any[], horas: string[]): void {
    this.bandaColacion = null;
    this.fechasBandaColacion = new Set<string>();

    // Solo con la colación VIGENTE del profesional seleccionado (la misma
    // lógica sirve para cualquier profesional: cada uno trae sus horas) y en
    // días con atención.
    const abiertos = dias.filter(d => !this.diaCerrado(d.fecha));
    if (!this.colacionTexto || abiertos.length === 0 || horas.length === 0) return;

    const topFila: number[] = [];
    let acumulado = this.ALTO_ENCABEZADO_PX;
    for (const h of horas) { topFila.push(acumulado); acumulado += this.alturaHora(h); }

    let top = 0;
    let fin = 0;
    let filasTapadas: number[] = [];

    // 1) Posición exacta según la hora de colación sobre la grilla real,
    //    sea cual sea su duración de bloque (30, 45, 60 min...).
    const ini = minutosDeHora(this.profesionalActual?.hora_almuerzo_inicio);
    const finMin = minutosDeHora(this.profesionalActual?.hora_almuerzo_fin);
    const starts = horas.map(h => minutosDeHora(h));
    const legible = ini !== null && finMin !== null && finMin > ini
      && starts.every((m, i) => m !== null && (i === 0 || m > (starts[i - 1] as number)));
    if (legible) {
      const st = starts as number[];
      const dur = st.map((m, i) => i < st.length - 1
        ? st[i + 1] - m
        : (st.length > 1 ? m - st[i - 1] : 45));
      const px = (t: number): number => {
        for (let i = 0; i < st.length; i++) {
          if (t < st[i]) return topFila[i];
          if (t < st[i] + dur[i]) {
            return topFila[i] + ((t - st[i]) / dur[i]) * this.alturaHora(horas[i]);
          }
        }
        return acumulado;
      };
      filasTapadas = st
        .map((m, i) => (m < (finMin as number) && m + dur[i] > (ini as number)) ? i : -1)
        .filter(i => i >= 0);
      top = px(ini as number);
      fin = px(finMin as number);
    }

    // 2) Si la colación no cae sobre la grilla (o sus horas no se pueden
    //    leer), se respetan las filas que el backend marcó como colación.
    if (filasTapadas.length === 0 || fin - top < 8) {
      const marcadas = horas.map(h => abiertos.some(d => this.bloqueEstadoFn(d.fecha, h) === 'colacion'));
      const primera = marcadas.indexOf(true);
      if (primera < 0) return;
      const ultima = marcadas.lastIndexOf(true);
      filasTapadas = [];
      for (let i = primera; i <= ultima; i++) filasTapadas.push(i);
      top = topFila[primera];
      fin = topFila[ultima] + this.alturaHora(horas[ultima]);
    }
    if (fin - top < 8) return;

    // La banda se ajusta a los bordes reales de las filas de la grilla.
    // Si la colación empieza a una hora que no coincide con un bloque
    // (p. ej. 13:00 con bloques de 45 min), antes quedaba flotando a mitad
    // de una celda; ahora ocupa las filas completas y queda encuadrada.
    if (filasTapadas.length > 0) {
      const primera = filasTapadas[0];
      const ultima = filasTapadas[filasTapadas.length - 1];
      top = topFila[primera];
      fin = topFila[ultima] + this.alturaHora(horas[ultima]);
    }

    this.bandaColacion = { top, alto: fin - top };

    // Un día con una cita dentro de la colación (p. ej. un sobrecupo) no
    // dibuja el recuadro, para no taparla.
    for (const d of abiertos) {
      const hayCita = filasTapadas.some(i => this.bloqueCitasFn(d.fecha, horas[i]).length > 0);
      if (!hayCita) this.fechasBandaColacion.add(d.fecha);
    }
    if (this.fechasBandaColacion.size === 0) this.bandaColacion = null;
  }

  // Columna central de la semana.
  get indiceColumnaCentro(): number {
    return Math.floor((this.diasGrilla.length - 1) / 2);
  }

  alturaHora(hora: string): number {
    return this.alturas.get(hora) ?? this.ALTO_HORA_PX;
  }

  onCancelarCita(cita: any): void {
    if (!this.puedeGestionarAgenda) return;
    this.cancelarCita.emit(cita);
  }

  onCitaClick(cita: any): void {
    if (!this.citaClickable) return;
    this.citaClick.emit(cita);
  }
}