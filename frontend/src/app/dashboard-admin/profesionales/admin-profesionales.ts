import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { normalizarTexto } from '../../shared/text-normalization';

/**
 * Fase 3.4C — extracción de la sección "Gestión de Profesionales" del
 * dashboard-admin.
 *
 * A diferencia de AdminCitasComponent (Fase 3.4B), `profesionales[]` NO es
 * exclusivo de esta vista: también lo usan Inicio, Horario y Configuración
 * dentro de DashboardAdminComponent. Por eso este componente NO carga sus
 * propios datos ni mantiene su propia copia del arreglo: recibe la lista (y
 * los valores derivados que también usa el shell en otras secciones) por
 * @Input y emite las intenciones de CRUD al shell mediante @Output, que es
 * quien sigue ejecutando las llamadas HTTP y actualizando profesionales[].
 *
 * Estado que SÍ vive aquí (exclusivo/visual de esta vista): búsqueda local,
 * paginación, los dos modales (nuevo profesional / gestionar profesional) y
 * sus formularios temporales.
 */
@Component({
  selector: 'app-admin-profesionales',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-profesionales.html'
})
export class AdminProfesionalesComponent {
  @Input() puedeGestionarProfesionales = false;

  // ── Datos recibidos del shell (fuente de verdad: DashboardAdminComponent) ──
  @Input() profesionales: any[] = [];
  @Input() especialidades: string[] = [];
  @Input() profesionalesActivos = 0;
  @Input() profesionalesConIncidencia = 0;

  // ── Intenciones emitidas al shell (el shell ejecuta el CRUD real) ──
  @Output() crearProfesional  = new EventEmitter<any>();
  @Output() cambiarEstado     = new EventEmitter<{ profesional: any; nuevoEstado: string; motivo: string }>();
  @Output() cambiarDuracion   = new EventEmitter<{ profesional: any; duracionMin: number }>();
  @Output() cambiarTratamiento = new EventEmitter<{ profesional: any; tratamiento: string | null }>();
  @Output() cambiarColorIdentificador = new EventEmitter<{ profesional: any; color: string | null }>();
  @Output() eliminarProfesional = new EventEmitter<any>();
  @Output() errorValidacion   = new EventEmitter<string>();

  // ══════════════════════════════════════
  // CARDS SUPERIORES — textos derivados de datos reales
  // (nunca "capacidad" ni "en turno": no tenemos un dato real de turno/
  // horario-hoy, solo el estado general del profesional en la ficha)
  // ══════════════════════════════════════

  /** Especialidades realmente presentes en profesionales[], sin mezclar
   * con la lista base usada como opciones del <select> de creación. */
  get especialidadesReales(): string[] {
    return Array.from(new Set(this.profesionales.map(p => p.especialidad).filter(Boolean)));
  }

  get porcentajeActivos(): number {
    if (!this.profesionales.length) return 0;
    return Math.round((this.profesionalesActivos / this.profesionales.length) * 100);
  }

  get textoPorcentajeActivos(): string {
    return `${this.porcentajeActivos}% activos`;
  }

  get textoActivosChip(): string {
    if (this.profesionalesActivos === 0) return 'Sin profesionales activos';
    if (this.profesionalesActivos === 1) return '1 activo';
    return `${this.profesionalesActivos} activos`;
  }

  get textoIncidenciasChip(): string {
    if (this.profesionalesConIncidencia === 0) return 'Sin incidencias';
    if (this.profesionalesConIncidencia === 1) return '1 incidencia';
    return `${this.profesionalesConIncidencia} incidencias`;
  }

  // ══════════════════════════════════════
  // COLOR IDENTIFICADOR
  // ══════════════════════════════════════

  /** Paleta cerrada — debe coincidir exactamente con COLORES_PERMITIDOS
   * del backend (schemas.py). Si se agrega/quita un color, cambiar en
   * ambos lados. */
  readonly coloresDisponibles = [
    '#5E857D', '#7FB8A6', '#8B5CF6', '#A78BFA', '#4F8EF7',
    '#60A5FA', '#D9A441', '#E07A5F', '#D96C8A', '#C75B5B'
  ];

  /** Fallback discreto por especialidad para profesionales que aún no
   * tienen color_identificador propio (dato antiguo = null). Es solo un
   * valor visual por defecto — nunca se persiste ni se confunde con el
   * color real elegido por cada profesional. Todos los valores están
   * tomados de coloresDisponibles. */
  private readonly colorFallbackPorEspecialidad: Record<string, string> = {
    'Odontología': '#7FB8A6',
    'Salud Mental': '#8B5CF6',
    'Psicología': '#A78BFA',
    'Kinesiología': '#D9A441',
    'Nutrición': '#D96C8A',
    'Medicina General': '#4F8EF7',
    'Oftalmología': '#60A5FA',
    'Psicopedagogía': '#E07A5F'
  };
  private readonly colorFallbackNeutro = '#5C706D'; // = var(--admin-text-secondary), nunca reemplaza la paleta base

  /** Color a usar para el badge de un profesional: su color propio si lo
   * tiene, si no un fallback por especialidad, si no un neutro. Cada
   * profesional puede tener un color distinto aunque compartan
   * especialidad — el color pertenece al profesional, no a la
   * especialidad. */
  colorDeProfesional(prof: any): string {
    return prof?.color_identificador || this.colorFallbackPorEspecialidad[prof?.especialidad] || this.colorFallbackNeutro;
  }

  seleccionarColor(color: string | null): void {
    this.profNuevoDatos.color_identificador = color;
  }

  // ══════════════════════════════════════
  // BÚSQUEDA / PAGINACIÓN (estado local/visual)
  // ══════════════════════════════════════
  busquedaProfesional = '';
  pagProf = 1;

  get profesionalesFiltradosBusqueda(): any[] {
    const q = normalizarTexto(this.busquedaProfesional);
    return !q ? this.profesionales : this.profesionales.filter(p =>
      normalizarTexto(p.nombre).includes(q) || normalizarTexto(p.especialidad).includes(q)
    );
  }

  get profesionalesPaginados(): any[] {
    return this.profesionalesFiltradosBusqueda.slice((this.pagProf - 1) * 6, this.pagProf * 6);
  }

  getPaginasProf(): number[] {
    const total = Math.ceil(this.profesionalesFiltradosBusqueda.length / 6);
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  minVal(a: number, b: number): number { return Math.min(a, b); }

  // ══════════════════════════════════════
  // MODAL: NUEVO PROFESIONAL (estado y validación local)
  // ══════════════════════════════════════
  modalProfAbierto = false;
  mostrarConfirmacionProf = false;
  profNuevoDatos: any = { nombre: '', tratamiento: '', especialidad: '', especialidadNueva: '', correo: '', rut: '', estado: 'activo', password: 'prof123', color_identificador: null };
  readonly tratamientosDisponibles = ['Dr.', 'Dra.'];
  rutValido = true;
  correoValido = true;
  duracionNumero = 45;
  duracionUnidad = 'minutos';

  get duracionEnMinutos(): number {
    return this.duracionUnidad === 'horas' ? this.duracionNumero * 60 : this.duracionNumero;
  }

  abrirModalAgregar(): void {
    if (!this.puedeGestionarProfesionales) return;
    this.profNuevoDatos = { nombre: '', tratamiento: '', especialidad: '', especialidadNueva: '', correo: '', rut: '', estado: 'activo', password: 'prof123', color_identificador: null };
    this.duracionNumero = 45; this.duracionUnidad = 'minutos';
    this.mostrarConfirmacionProf = false; this.rutValido = true; this.correoValido = true;
    this.modalProfAbierto = true;
  }

  validarRut(rut: string): boolean {
    const rutLimpio = rut.replace(/\./g, '').replace(/-/g, '');
    if (rutLimpio.length < 2) return false;
    const cuerpo = rutLimpio.slice(0, -1); const dv = rutLimpio.slice(-1).toUpperCase();
    let suma = 0, multi = 2;
    for (let i = cuerpo.length - 1; i >= 0; i--) { suma += parseInt(cuerpo[i]) * multi; multi = multi === 7 ? 2 : multi + 1; }
    const dvEsperado = 11 - (suma % 11);
    const dvCalc = dvEsperado === 11 ? '0' : dvEsperado === 10 ? 'K' : String(dvEsperado);
    return dv === dvCalc;
  }

  onRutChange(): void { this.rutValido = !this.profNuevoDatos.rut || this.validarRut(this.profNuevoDatos.rut); }
  onCorreoChange(): void { this.correoValido = !this.profNuevoDatos.correo || /^[a-zA-Z0-9._%+\-]+@utem\.cl$/.test(this.profNuevoDatos.correo); }

  /**
   * Validación local: no dispara HTTP, solo avanza a la pantalla de
   * confirmación. Preserva exactamente los mensajes que antes de la
   * extracción mostraba DashboardAdminComponent.continuarCrearProf()
   * (vía mensajeError + toast), ahora emitidos por errorValidacion para
   * que el shell los muestre (Corrección previa a aprobación, Fase 3.4C).
   */
  continuarCrearProf(): boolean {
    if (!this.puedeGestionarProfesionales) return false;
    if (!this.profNuevoDatos.nombre.trim()) { this.errorValidacion.emit('El nombre es obligatorio.'); return false; }
    if (!this.profNuevoDatos.especialidad)  { this.errorValidacion.emit('Selecciona una especialidad.'); return false; }
    if (!this.profNuevoDatos.correo.trim()) { this.errorValidacion.emit('El correo es obligatorio.'); return false; }
    if (!this.correoValido) { this.errorValidacion.emit('El correo debe ser @utem.cl.'); return false; }
    if (this.profNuevoDatos.rut && !this.rutValido) { this.errorValidacion.emit('El RUT ingresado no es válido.'); return false; }
    this.mostrarConfirmacionProf = true;
    return true;
  }

  volverFormProf(): void { this.mostrarConfirmacionProf = false; }

  /** Emite la intención final al shell; el shell ejecuta el POST real. */
  confirmarCrearProf(): void {
    if (!this.puedeGestionarProfesionales) return;
    const especialidadFinal = this.profNuevoDatos.especialidad === 'otra' ? this.profNuevoDatos.especialidadNueva : this.profNuevoDatos.especialidad;
    this.crearProfesional.emit({
      nombre: this.profNuevoDatos.nombre, tratamiento: this.profNuevoDatos.tratamiento || null,
      especialidad: especialidadFinal,
      correo: this.profNuevoDatos.correo, rut: this.profNuevoDatos.rut,
      duracion_min: this.duracionEnMinutos, estado: 'activo', password: 'prof123',
      color_identificador: this.profNuevoDatos.color_identificador || null
    });
  }

  /** Público: el shell lo invoca (vía ViewChild) al confirmar la creación con éxito. */
  cerrarModal(): void { this.modalProfAbierto = false; this.mostrarConfirmacionProf = false; }

  // ══════════════════════════════════════
  // MODAL: ACCIONES / GESTIONAR PROFESIONAL
  // ══════════════════════════════════════
  modalAccionesAbierto = false;
  profSeleccionado: any = null;

  abrirModalAcciones(p: any): void {
    if (!this.puedeGestionarProfesionales) return;
    this.profSeleccionado = { ...p, nuevoEstado: p.estado, motivoCambio: '', nuevoTratamiento: p.tratamiento || '', nuevoColor: p.color_identificador || null };
    this.duracionNumero = p.duracion_min <= 60 ? p.duracion_min : Math.round(p.duracion_min / 60);
    this.duracionUnidad = p.duracion_min > 60 ? 'horas' : 'minutos';
    this.modalAccionesAbierto = true;
  }

  /**
   * Construye "[tratamiento] [nombre]" de forma segura para el modal
   * (misma lógica que AdminInicioComponent.nombreConTratamiento — no
   * antepone el tratamiento si el nombre ya trae un prefijo histórico).
   */
  nombreConTratamiento(p: { nombre: string; tratamiento?: string | null }): string {
    const nombre = p?.nombre?.trim() || '';
    const tratamiento = p?.tratamiento?.trim();
    if (!tratamiento) return nombre;
    const yaTienePrefijo = /^(dr|dra|psic|klgo|klga|nut|enf)\.?\s/i.test(nombre);
    return yaTienePrefijo ? nombre : `${tratamiento} ${nombre}`;
  }

  /** Público: el shell lo invoca (vía ViewChild) tras completar una acción con éxito. */
  cerrarModalAcciones(): void { this.modalAccionesAbierto = false; this.profSeleccionado = null; }

  get estadoCambioRequiereMotivo(): boolean {
    return this.profSeleccionado && ['licencia', 'inasistencia'].includes(this.profSeleccionado.nuevoEstado);
  }

  /** Emite la intención al shell; el shell decide si confirma cancelación de citas y ejecuta el PATCH. */
  guardarEstadoProfesional(): void {
    if (!this.puedeGestionarProfesionales) return;
    if (!this.profSeleccionado) return;
    this.cambiarEstado.emit({
      profesional: this.profSeleccionado,
      nuevoEstado: this.profSeleccionado.nuevoEstado,
      motivo: this.profSeleccionado.motivoCambio || ''
    });
  }

  /** Emite la intención al shell; el shell ejecuta el PATCH real. */
  guardarDuracionProfesional(): void {
    if (!this.puedeGestionarProfesionales) return;
    if (!this.profSeleccionado) return;
    this.cambiarDuracion.emit({ profesional: this.profSeleccionado, duracionMin: this.duracionEnMinutos });
  }

  /**
   * Emite la intención al shell; el shell ejecuta el PATCH real.
   * '' (Sin tratamiento) se emite como null explícito, no como campo
   * omitido, para que el backend pueda distinguir "limpiar" de "no tocar".
   */
  guardarTratamientoProfesional(): void {
    if (!this.puedeGestionarProfesionales) return;
    if (!this.profSeleccionado) return;
    this.cambiarTratamiento.emit({
      profesional: this.profSeleccionado,
      tratamiento: this.profSeleccionado.nuevoTratamiento || null
    });
  }

  /**
   * Emite la intención al shell; el shell ejecuta el PATCH real.
   * null explícito = "sin color" (vuelve al fallback por especialidad),
   * distinto de no tocar el campo.
   */
  guardarColorProfesional(): void {
    if (!this.puedeGestionarProfesionales) return;
    if (!this.profSeleccionado) return;
    this.cambiarColorIdentificador.emit({
      profesional: this.profSeleccionado,
      color: this.profSeleccionado.nuevoColor || null
    });
  }

  /** Emite la intención al shell; el shell confirma y ejecuta el DELETE real. */
  eliminarProfesionalDesdeModal(): void {
    if (!this.puedeGestionarProfesionales) return;
    if (!this.profSeleccionado) return;
    this.eliminarProfesional.emit(this.profSeleccionado);
  }

  // Permission esperado: profesionales.gestionar
  // (documentado únicamente; el guard de permisos no se conecta en esta fase)
}
