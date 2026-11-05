import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../config';
import { PhotoCropperComponent } from '../shared/photo-cropper/photo-cropper';
import { PhotoViewerComponent } from '../shared/photo-viewer/photo-viewer';
import { obtenerFeriado } from '../shared/feriados-chile';
import { obtenerDiasInternacionales } from '../shared/dias-internacionales';
import { ToastService } from '../shared/toast/toast.service';
import { ProfessionalAyudaComponent } from './ayuda/professional-ayuda';
import { evaluarPassword, type PasswordChecklist } from '../shared/password-validation';
import { coincideBusqueda } from '../shared/text-normalization';
import { AuthService } from '../auth.service';
import { inicialesDe } from '../dashboard-admin/citas/admin-citas.utils';
import { CompletarAtencionComponent, type DocumentoEmitido, type PacienteAtencion } from './completar-atencion/completar-atencion';
import { DocumentosCitaComponent } from '../shared/documentos-cita/documentos-cita';
import { CuestionarioOpcionalComponent } from './cuestionario-opcional/cuestionario-opcional';
import { AdminHorarioComponent } from '../dashboard-admin/horario/admin-horario';
import { imprimirAgendaAislada } from '../dashboard-admin/horario/agenda-impresion';

const API = environment.apiUrl;

@Component({
  selector: 'app-dashboard-profesional',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, PhotoCropperComponent, PhotoViewerComponent, ProfessionalAyudaComponent, CompletarAtencionComponent, DocumentosCitaComponent, CuestionarioOpcionalComponent, AdminHorarioComponent],
  templateUrl: './dashboard-profesional.html',
  styleUrl: './dashboard-profesional.css'
})
export class DashboardProfesionalComponent implements OnInit {

  seccionActiva = 'inicio';
  sidebarMovilAbierto = false;

toggleSidebarMovil(): void {
  this.sidebarMovilAbierto = !this.sidebarMovilAbierto;
}
  temaOscuro    = false;

  private _mensajeExito = '';
  set mensajeExito(valor: string) { this._mensajeExito = valor; if (valor) this.toast.success(valor); }
  get mensajeExito(): string { return this._mensajeExito; }

  private _mensajeError = '';
  set mensajeError(valor: string) { this._mensajeError = valor; if (valor) this.toast.error(valor); }
  get mensajeError(): string { return this._mensajeError; }

  // Profesional.id se resuelve desde la identidad Usuario de la sesión.
  // Nunca se persiste en localStorage: evita mezclar identidades entre pestañas.
  private profesionalId = 0;

  get profDbId(): number {
    return this.profesionalId;
  }

  perfil: any = {
    nombre: '', especialidad: '', iniciales: '',
    descripcion: '', correo: '', rut: '',
    estado: 'activo', foto_url: null,
    duracion_min: 45, tema_oscuro: false
  };

  get tituloSeccion(): string {
    const map: Record<string, string> = {
      inicio:            'Inicio',
      horario:            'Agenda',
      pacientes:          'Pacientes',
      'historial-clinico': 'Historial Clínico',
      solicitudes:        'Solicitudes',
      perfil:             'Configuración',
      ayuda:              'Ayuda'
    };
    return map[this.seccionActiva] ?? 'SESAES';
  }

  // Sub-pestaña dentro de "Mi Horario": agenda semanal o configuración de jornada/colación
  horarioTab: 'agenda' | 'configuracion' = 'agenda';
  cambiarHorarioTab(tab: 'agenda' | 'configuracion'): void {
    this.horarioTab = tab;
    if (tab === 'agenda') this.cargarCitasSemana();
  }

  constructor(
    private router: Router,
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
    private toast: ToastService,
    private auth: AuthService
  ) {}

  ngOnInit(): void {
    const temaGuardado = localStorage.getItem('prof_tema_oscuro');
    if (temaGuardado === 'true') this.temaOscuro = true;

    this.resolverIdentidadProfesional();
  }

  private resolverIdentidadProfesional(): void {
    const usuarioId = this.auth.getUsuarioId();

    if (
      this.auth.getRol() !== 'profesional' ||
      usuarioId === null
    ) {
      this.mensajeError = 'No se pudo validar la sesión profesional.';
      this.auth.logout();
      void this.router.navigate(['/login']);
      return;
    }

    this.http.get<{ id: number }>(
      `${API}/profesional/buscar-por-usuario/${usuarioId}`
    ).subscribe({
      next: (profesional) => {
        const profesionalId = Number(profesional?.id);

        if (
          !Number.isInteger(profesionalId) ||
          profesionalId <= 0
        ) {
          this.mensajeError = 'La cuenta profesional no tiene un perfil válido asociado.';
          return;
        }

        this.profesionalId = profesionalId;
        this.cargarDatos();
        this.cargarCitasSinCerrar();
        this.cdr.detectChanges();
      },
      error: () => {
        this.mensajeError = 'Tu cuenta de profesional no está vinculada correctamente. Contacta al administrador.';
        this.cdr.detectChanges();
      }
    });
  }

  // ══════════════════════════════════════
  // CITAS SIN CERRAR (fecha ya pasó, siguen "pendiente")
  // ══════════════════════════════════════
  citasSinCerrar: any[] = [];
  cargarCitasSinCerrar(): void {
    this.http.get<any[]>(`${API}/profesional/${this.profDbId}/citas-sin-cerrar`).subscribe({
      next: (data) => { this.citasSinCerrar = data ?? []; this.cdr.detectChanges(); },
      error: () => {}
    });
  }

  cargarDatos(): void {
    this.cargarPerfil();
    this.cargarEstadisticasDia();
    this.cargarDocumentosHoy();
    this.cargarCitasHoy();
    this.cargarProximasSemana();
    this.cargarNotificaciones();
    this.generarSemanaActual();
    this.generarCalendarioInicio();
    this.cargarSolicitudesHorario();
    this.cargarDiasCerrados();
    this.cargarCitasPendientes();
    this.cargarAtenciones();
    this.cargarPacientesHistorial();
    this.cargarCitasSemana();
  }

  navegarA(seccion: string): void {
  if (seccion === 'historial-clinico' && this.pacienteSeleccionado) {
    if (!this.confirmarSalidaFicha()) return;
    this.cerrarFichaPaciente();
  }
  this.seccionActiva     = seccion;
  this.mensajeExito      = '';
  this.mensajeError      = '';
  this.notifPanelAbierto = false;
  this.sidebarMovilAbierto = false;
  if (seccion === 'horario') {
    this.horarioTab = 'agenda';
    this.cargarCitasSemana();
  }
  if (seccion === 'pacientes') this.cargarAtenciones();
  if (seccion === 'historial-clinico') this.cargarPacientesHistorial();
  if (seccion === 'solicitudes') {
    this.cargarCitasPendientes();
    this.cargarSolicitudesHorario();
  }
}
  cerrarSesion(): void {
    this.auth.logout();
    void this.router.navigate(['/login']);
  }

  toggleTema(): void {
    this.temaOscuro = !this.temaOscuro;
    localStorage.setItem('prof_tema_oscuro', String(this.temaOscuro));
    this.http.patch(`${API}/profesional/${this.profDbId}/perfil`, { tema_oscuro: this.temaOscuro }).subscribe({ error: () => {} });
  }

  // ══════════════════════════════════════
  // HELPERS DE FECHA (español, sin DatePipe)
  // ══════════════════════════════════════

  private hoyStr(): string {
    const hoy = new Date();
    return `${hoy.getFullYear()}-${String(hoy.getMonth()+1).padStart(2,'0')}-${String(hoy.getDate()).padStart(2,'0')}`;
  }

  formatearDiaSeleccionado(fecha: string | null): string {
    if (!fecha) return '';
    const dias  = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
    const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
    const [anio, mes, dia] = fecha.split('-').map(Number);
    const d = new Date(anio, mes - 1, dia);
    const nombreDia = dias[d.getDay()];
    return `${nombreDia.charAt(0).toUpperCase() + nombreDia.slice(1)} ${dia} de ${meses[mes - 1]}`;
  }

  // ══════════════════════════════════════
  // NOTIFICACIONES
  // ══════════════════════════════════════

  notificaciones: any[] = [];
  notifPanelAbierto     = false;
  notifNoLeidas         = 0;

  cargarNotificaciones(): void {
    this.http.get<any[]>(`${API}/profesional/${this.profDbId}/notificaciones`).subscribe({
      next: (data) => {
        this.notificaciones = data ?? [];
        this.notifNoLeidas  = this.notificaciones.filter(n => !n.leida).length;
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  toggleNotificaciones(): void { this.notifPanelAbierto = !this.notifPanelAbierto; }

  marcarLeida(n: any): void {
    if (n.leida) return;
    this.http.patch(`${API}/notificaciones/${n.id}/leer`, {}).subscribe({
      next: () => {
        n.leida = true;
        this.notifNoLeidas = Math.max(0, this.notifNoLeidas - 1);
        this.cdr.detectChanges();
      }
    });
  }

  marcarTodasLeidas(): void {
    this.http.patch(`${API}/notificaciones/leer-todas/${this.perfil.usuario_id || 0}`, {}).subscribe({
      next: () => {
        this.notificaciones.forEach(n => n.leida = true);
        this.notifNoLeidas = 0;
        this.cdr.detectChanges();
      }
    });
  }
notifSeleccionadas = new Set<number>();

get notifHaySeleccionadas(): boolean {
  return this.notifSeleccionadas.size > 0;
}

get notifTodasSeleccionadas(): boolean {
  return this.notificaciones.length > 0 && this.notifSeleccionadas.size === this.notificaciones.length;
}

toggleSeleccionNotif(n: any): void {
  if (this.notifSeleccionadas.has(n.id)) this.notifSeleccionadas.delete(n.id);
  else this.notifSeleccionadas.add(n.id);
}

toggleSeleccionarTodasNotif(): void {
  if (this.notifTodasSeleccionadas) {
    this.notifSeleccionadas.clear();
  } else {
    this.notificaciones.forEach(n => this.notifSeleccionadas.add(n.id));
  }
}

marcarSeleccionadasLeidas(): void {
  const ids = Array.from(this.notifSeleccionadas);
  ids.forEach(id => {
    this.http.patch(`${API}/notificaciones/${id}/leer`, {}).subscribe({
      next: () => {
        const n = this.notificaciones.find(x => x.id === id);
        if (n && !n.leida) { n.leida = true; this.notifNoLeidas = Math.max(0, this.notifNoLeidas - 1); }
        this.cdr.detectChanges();
      }
    });
  });
  this.notifSeleccionadas.clear();
}

eliminarNotificacion(n: any): void {
  this.http.delete(`${API}/notificaciones/${n.id}`).subscribe({
    next: () => {
      this.notificaciones = this.notificaciones.filter(x => x.id !== n.id);
      this.notifSeleccionadas.delete(n.id);
      if (!n.leida) this.notifNoLeidas = Math.max(0, this.notifNoLeidas - 1);
      this.cdr.detectChanges();
    },
    error: () => {
      this.mensajeError = 'No se pudo eliminar la notificación.';
      setTimeout(() => { this.mensajeError = ''; this.cdr.detectChanges(); }, 3000);
    }
  });
}

eliminarSeleccionadas(): void {
  const ids = Array.from(this.notifSeleccionadas);
  ids.forEach(id => {
    this.http.delete(`${API}/notificaciones/${id}`).subscribe({
      next: () => {
        const n = this.notificaciones.find(x => x.id === id);
        this.notificaciones = this.notificaciones.filter(x => x.id !== id);
        if (n && !n.leida) this.notifNoLeidas = Math.max(0, this.notifNoLeidas - 1);
        this.cdr.detectChanges();
      }
    });
  });
  this.notifSeleccionadas.clear();
}
  // ══════════════════════════════════════
  // PERFIL
  // ══════════════════════════════════════

  cargarPerfil(): void {
    this.http.get<any>(`${API}/profesional/${this.profDbId}/perfil`).subscribe({
      next: (data) => {
        this.perfil = data;
        this.sincronizarCitasAgenda();
        this.perfilOriginalFotoUrl = data.foto_url || null;   // ← agregar esta línea
        this.temaOscuro = data.tema_oscuro || false;
        this.configPerfil.nombre      = data.nombre || '';
        this.configPerfil.descripcion = data.descripcion || '';
        this.charCount = (data.descripcion || '').length;
        this.precargarBloquesAprobados(data.bloques_semanales);
        this.generarHorasGrilla();
        this.cdr.detectChanges();
      },
      error: (err) => { console.error('[cargarPerfil] Error al cargar el perfil del profesional:', err); }
    });
}

  // ¿Hay cambios sin guardar en el formulario de perfil?
  get perfilModificado(): boolean {
    return this.configPerfil.nombre !== (this.perfil.nombre || '')
        || this.configPerfil.descripcion !== (this.perfil.descripcion || '')
        || this.perfil.foto_url !== this.perfilOriginalFotoUrl;  
}

  // ¿Hay datos suficientes para intentar el cambio de contraseña?
  get passwordModificada(): boolean {
    return !!this.configPerfil.contrasena_actual
        || !!this.configPerfil.contrasena_nueva
        || !!this.configPerfil.contrasena_conf;
  }

  get passwordChecklist(): PasswordChecklist {
    return evaluarPassword(this.configPerfil.contrasena_nueva);
  }

  get passwordCumpleReglas(): boolean {
    return this.passwordChecklist.valida;
  }

  // ══════════════════════════════════════
  // INICIO
  // ══════════════════════════════════════

  estadisticasDia = { total_hoy: 0, completadas: 0, pendientes: 0, inasistencias: 0 };

  // ── Tarjetas resumen del dashboard ──
  get pacientesActivosCount(): number { return this.pacientesHistorial.length; }

  get solicitudesPendientesTotal(): number {
    return this.citasPendientes.length + this.solicitudesHorario.filter(s => s.estado === 'pendiente').length;
  }

  // ── Agenda de hoy: bloques horarios reales (disponible / ocupado / colación / cerrado) ──
  // Reutiliza la misma lógica de la grilla semanal de "Mi Horario" (getBloqueEstado/Info),
  // por lo que requiere que citasSemana esté cargado (se pide también en cargarDatos()).

  get fechaHoyStr(): string {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  get centroCerradoHoy(): boolean { return this.esDiaCerrado(this.fechaHoyStr); }

  // Heurística de tipo de atención usando el historial completo de citas del profesional
  // (no solo las de la ficha de un paciente): la primera cita histórica del estudiante
  // se etiqueta "Primera consulta", el resto "Seguimiento".
  tipoAtencionGlobal(cita: any): string {
    if (!cita || !cita.estudiante_id) return 'Consulta';
    const mismoPaciente = this.atenciones.filter(a => a.estudiante_id === cita.estudiante_id);
    if (mismoPaciente.length === 0) return 'Consulta';
    const masAntigua = [...mismoPaciente].sort((a, b) => (a.fecha + a.hora).localeCompare(b.fecha + b.hora))[0];
    return (masAntigua.fecha === cita.fecha && masAntigua.hora === cita.hora) ? 'Primera consulta' : 'Seguimiento';
  }

  // ── Datos para el nuevo orden del Inicio (agenda+calendario, alertas, pacientes recientes, actividad) ──


  get fichasSinCompletarCount(): number { return this.pacientesHistorial.filter(p => !p.tiene_ficha).length; }

  get pacientesRecientes(): any[] {
    return [...this.pacientesHistorial]
      .sort((a, b) => (a.dias_desde_ultima_visita ?? Infinity) - (b.dias_desde_ultima_visita ?? Infinity))
      .slice(0, 4);
  }

  irAFichaPacienteReciente(p: any): void {
    this.seccionActiva = 'historial-clinico';
    this.abrirFichaPaciente(p);
  }

  // Buscador global del topbar → filtra en "Mis Pacientes" por nombre, RUT o carrera
  busquedaGlobal = '';
  buscarGlobal(): void {
    const termino = this.busquedaGlobal.trim();
    if (!termino) return;
    this.filtroBusquedaAt = termino;
    this.busquedaGlobal = '';
    this.navegarA('pacientes');
  }

  irAFichasSinCompletar(): void {
    this.navegarA('historial-clinico');
    this.filtroEstadoHistorial = 'sin_completar';
  }

  citasHoy: any[] = [];
  citaEnAtencion: any = null;   // cita con la que se inició la atención actual
  documentosHoy = { total: 0, recetas: 0, justificativos: 0 };   // documentos emitidos hoy (Inicio)

  cargarEstadisticasDia(): void {
    this.http.get<any>(`${API}/profesional/${this.profDbId}/estadisticas-dia`).subscribe({
      next: (data) => {
        this.estadisticasDia = data;
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  cargarDocumentosHoy(): void {
    this.http.get<{ total: number; recetas: number; justificativos: number }>(`${API}/documentos/profesional/${this.profDbId}/hoy`).subscribe({
      next: (d) => { this.documentosHoy = d; this.cdr.detectChanges(); },
      error: () => {}
    });
  }

  /** Citas de hoy ordenadas por hora (agenda del Inicio). */
  get agendaHoyCitas(): any[] {
    return [...this.citasHoy].sort((a, b) => this.convertirA24h(a.hora).localeCompare(this.convertirA24h(b.hora)));
  }

  /** La próxima cita pendiente de hoy que este profesional puede completar. */
  get proximaAtencionPendiente(): any {
    return this.agendaHoyCitas.find(c => c.estado === 'pendiente' && this.puedeGestionarCita(c)) || null;
  }

  get fechaHoyLarga(): string {
    return new Date().toLocaleDateString('es-CL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  }

  // ── Inicio: avance del día ──
  get atencionesHoyTotal(): number { return this.citasHoy.filter(c => c.estado !== 'cancelada').length; }
  get atencionesHoyRealizadas(): number { return this.citasHoy.filter(c => c.estado === 'completada').length; }
  get avanceHoyPct(): number {
    const total = this.atencionesHoyTotal;
    return total ? Math.round((this.atencionesHoyRealizadas / total) * 100) : 0;
  }

  /** La primera cita pendiente de hoy está "En espera"; las siguientes, "Programadas". */
  esEnEspera(c: any): boolean { return c.estado === 'pendiente' && this.proximaAtencionPendiente?.id === c.id; }

  claseEstadoAgenda(c: any): string {
    if (c.estado === 'pendiente') return this.esEnEspera(c) ? 'espera' : 'programada';
    return c.estado;
  }

  etiquetaEstadoAgenda(c: any): string {
    switch (this.claseEstadoAgenda(c)) {
      case 'completada':   return 'Completada';
      case 'espera':       return 'En espera';
      case 'inasistencia': return 'Inasistencia';
      case 'cancelada':    return 'Cancelada';
      default:             return 'Programada';
    }
  }

  iniciales(nombre: string | null | undefined): string { return inicialesDe(nombre); }

  textoUltimaAtencion(p: any): string {
    const d = p?.dias_desde_ultima_visita;
    if (d === null || d === undefined) return 'Sin visitas';
    if (d === 0) return 'Hoy';
    if (d === 1) return 'Ayer';
    return `Hace ${d} días`;
  }

  private haceDias(fecha: string): string {
    const dias = Math.round((new Date(this.hoyStr() + 'T00:00:00').getTime() - new Date(fecha + 'T00:00:00').getTime()) / 86400000);
    if (dias <= 0) return 'Hoy';
    return dias === 1 ? 'Ayer' : `Hace ${dias} días`;
  }

  /** Lo que conviene revisar hoy, con datos reales: citas sin cerrar, fichas incompletas y solicitudes. */
  get pendientesPorRevisar(): { icono: string; titulo: string; detalle: string; etiqueta: string; tono: string; accion: () => void }[] {
    const lista: { icono: string; titulo: string; detalle: string; etiqueta: string; tono: string; accion: () => void }[] = [];
    for (const c of this.citasSinCerrar.slice(0, 2)) {
      lista.push({ icono: 'pending_actions', titulo: 'Cita sin cerrar', detalle: `${c.estudiante} · ${c.carrera || '—'}`,
                   etiqueta: this.haceDias(c.fecha), tono: 'rojo', accion: () => this.iniciarAtencion(c) });
    }
    for (const p of this.pacientesHistorial.filter(x => !x.tiene_ficha).slice(0, 2)) {
      lista.push({ icono: 'description', titulo: 'Ficha clínica incompleta', detalle: `${p.nombre} · ${p.carrera || '—'}`,
                   etiqueta: this.textoUltimaAtencion(p), tono: 'naranjo', accion: () => this.irAFichaPacienteReciente(p) });
    }
    const n = this.solicitudesPendientesTotal;
    if (n > 0) {
      lista.push({ icono: 'inbox', titulo: `${n} solicitud${n === 1 ? '' : 'es'} pendiente${n === 1 ? '' : 's'}`,
                   detalle: 'Revisa y gestiona nuevas solicitudes', etiqueta: 'Pendiente', tono: '', accion: () => this.navegarA('solicitudes') });
    }
    return lista.slice(0, 4);
  }

  // El recordatorio se puede cerrar y no vuelve a aparecer en este navegador.
  recuerdaVisible = (() => { try { return localStorage.getItem('prof_recuerda_cerrado') !== '1'; } catch { return true; } })();
  cerrarRecuerda(): void {
    this.recuerdaVisible = false;
    try { localStorage.setItem('prof_recuerda_cerrado', '1'); } catch { /* sin almacenamiento: solo se oculta ahora */ }
  }

  // ── Flujo de atención: Inicio → historial del paciente → "Registrar atención" ──
  /** Abre el historial del paciente con el contexto de la cita; desde ahí se registra la atención. */
  iniciarAtencion(cita: any): void {
    if (!cita?.estudiante_id) return;
    const fichaAbierta = this.pacienteSeleccionado;
    this.navegarA('historial-clinico');
    if (fichaAbierta && this.pacienteSeleccionado === fichaAbierta) return;   // decidió quedarse con cambios sin guardar
    this.citaEnAtencion = cita;
    this.abrirFichaPaciente({ estudiante_id: cita.estudiante_id, nombre: cita.estudiante });
  }

  /** Vuelve al buscador de pacientes (pide confirmación solo si hay antecedentes sin guardar). */
  volverAPacientes(): void {
    if (!this.confirmarSalidaFicha()) return;
    this.cerrarFichaPaciente();
  }

  get fichaTieneCambios(): boolean {
    return this.fichaEnEdicion && JSON.stringify(this.fichaRespuestas) !== this.fichaRespuestasInicial;
  }

  private confirmarSalidaFicha(): boolean {
    return !this.fichaTieneCambios || window.confirm('Tienes cambios sin guardar en los antecedentes. ¿Salir sin guardar?');
  }

  get puedeRegistrarAtencion(): boolean {
    const pendiente = this.fichaCitaPendienteActual;
    return !!pendiente && this.puedeGestionarCita(pendiente);
  }

  get motivoSinAtencion(): string {
    const pendiente = this.fichaCitaPendienteActual;
    if (!pendiente) return 'No hay una cita pendiente con este estudiante. Podrás registrar la atención cuando tenga una hora agendada.';
    if (!this.puedeGestionarCita(pendiente)) return `La cita es el ${pendiente.fecha.split('-').reverse().join('/')}; podrás registrar la atención desde ese día.`;
    return '';
  }

  /** La cita con la que se inició la atención, mientras siga pendiente y sea de este paciente. */
  get citaContextoAtencion(): any {
    const c = this.citaEnAtencion;
    if (!c || !this.pacienteSeleccionado || c.estudiante_id !== this.pacienteSeleccionado.estudiante_id) return null;
    return this.fichaCitas.find(x => x.id === c.id && x.estado === 'pendiente') || (this.fichaCitas.length === 0 ? c : null);
  }

  etiquetaCitaContexto(c: any): string {
    return `Atención ${c.fecha === this.hoyStr() ? 'de hoy' : 'del ' + c.fecha.split('-').reverse().join('/')} · ${c.hora}`;
  }

  cargarCitasHoy(): void {
    const fechaStr = this.hoyStr();
    this.http.get<any[]>(`${API}/profesional/${this.profDbId}/citas?fecha=${fechaStr}`).subscribe({
      next: (data) => {
        this.citasHoy = data ?? [];
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  // Próximas citas de la semana (más allá de hoy) — para el widget de Inicio
  proximasSemana: any[] = [];

  private sumarDias(fechaStr: string, dias: number): string {
    const [anio, mes, dia] = fechaStr.split('-').map(Number);
    const d = new Date(anio, mes - 1, dia);
    d.setDate(d.getDate() + dias);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  cargarProximasSemana(): void {
    const hoy    = this.hoyStr();
    const limite = this.sumarDias(hoy, 6);
    this.http.get<any[]>(`${API}/profesional/${this.profDbId}/citas?estado=pendiente`).subscribe({
      next: (data) => {
        this.proximasSemana = (data ?? [])
          .filter(c => c.fecha > hoy && c.fecha <= limite)
          .sort((a, b) => a.fecha === b.fecha ? a.hora.localeCompare(b.hora) : a.fecha.localeCompare(b.fecha))
          .slice(0, 6);
        this.cdr.detectChanges();
      },
      error: () => {
        this.proximasSemana = [];
        this.cdr.detectChanges();
      }
    });
  }

  // Solo se puede completar/marcar inasistencia si la cita ya llegó a su fecha (no citas futuras)
  puedeGestionarCita(cita: any): boolean {
    return cita.fecha <= this.hoyStr();
  }

  // ══════════════════════════════════════
  // CALENDARIO DE INICIO (solo visual — mes completo, sin seleccion de dia)
  // ══════════════════════════════════════

  readonly NOMBRES_MES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
    'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

  calMesVisible  = new Date().getMonth();
  calAnioVisible = new Date().getFullYear();
  calDiasMes: any[] = [];

  get calNombreMesVisible(): string {
    return `${this.NOMBRES_MES[this.calMesVisible]} ${this.calAnioVisible}`;
  }

  generarCalendarioInicio(): void {
    const anio = this.calAnioVisible;
    const mes  = this.calMesVisible;
    const hoy  = this.hoyStr();
    const fecha = (a: number, m: number, d: number) => `${a}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const ultimoDia = new Date(anio, mes + 1, 0).getDate();
    const offset    = (new Date(anio, mes, 1).getDay() + 6) % 7;      // lunes = 0
    const ultimoPrev = new Date(anio, mes, 0).getDate();
    const celdas: any[] = [];
    // Días del mes anterior y del siguiente completan la primera y la última semana (en gris).
    for (let i = offset - 1; i >= 0; i--) {
      const d = ultimoPrev - i;
      const f = mes === 0 ? fecha(anio - 1, 11, d) : fecha(anio, mes - 1, d);
      celdas.push({ num: d, fecha: f, esHoy: f === hoy, otroMes: true });
    }
    for (let d = 1; d <= ultimoDia; d++) {
      const f = fecha(anio, mes, d);
      celdas.push({ num: d, fecha: f, esHoy: f === hoy, otroMes: false });
    }
    for (let d = 1; celdas.length % 7 !== 0; d++) {
      const f = mes === 11 ? fecha(anio + 1, 0, d) : fecha(anio, mes + 1, d);
      celdas.push({ num: d, fecha: f, esHoy: f === hoy, otroMes: true });
    }
    this.calDiasMes = celdas;
  }

  calMesAnterior(): void {
    this.calMesVisible--;
    if (this.calMesVisible < 0) { this.calMesVisible = 11; this.calAnioVisible--; }
    this.generarCalendarioInicio();
  }

  calMesSiguiente(): void {
    this.calMesVisible++;
    if (this.calMesVisible > 11) { this.calMesVisible = 0; this.calAnioVisible++; }
    this.generarCalendarioInicio();
  }

  diaSeleccionadoInfo: string | null = null;
  seleccionarDiaInfo(dia: any): void {
    if (!dia) return;
    this.diaSeleccionadoInfo = this.diaSeleccionadoInfo === dia.fecha ? null : dia.fecha;
  }
  infoDelDia(fecha: string | undefined): string[] {
    if (!fecha) return [];
    const info: string[] = [];
    const feriado = obtenerFeriado(fecha);
    if (feriado) info.push(`Feriado: ${feriado.nombre}`);
    for (const d of obtenerDiasInternacionales(fecha)) info.push(d.nombre);
    return info;
  }

  // ══════════════════════════════════════
  // MI AGENDA
  // ══════════════════════════════════════

  semanaActual: any[] = [];
  semanaLabel         = '';
  diaSeleccionado: string | null = null;
  citasSemana: any[]  = [];
  horasGrilla: string[] = [];

  // ── Agenda compartida con el panel Administrador ──────────────────
  // El Profesional reutiliza AdminHorarioComponent en modo consulta. Estas
  // listas vacías y el flag puedeGestionarAgenda=false garantizan que NO
  // se rendericen filtros de terceros, solicitudes ni acciones de gestión.
  readonly agendaSolicitudesAdmin: any[] = [];
  readonly agendaEspecialidades: string[] = [];
  readonly agendaProfesionales: any[] = [];

  // Citas de la semana enriquecidas con la especialidad del profesional,
  // que el panel contextual de la agenda compartida muestra bajo el nombre.
  citasAgenda: any[] = [];

  get perfilBloqueado(): boolean {
    const estado = String(this.perfil?.estado ?? '').toLowerCase();
    return !!estado && estado !== 'activo';
  }

  // Horario personalizado = agenda semanal por bloques ya aprobada por el
  // administrador. Si no existe, rige el horario institucional
  // predeterminado (Lun-Jue 09:00-17:30, Vie 09:00-16:30).
  get tieneHorarioPersonalizadoAprobado(): boolean {
    return (this.perfil?.bloques_semanales ?? []).length > 0;
  }

  get horarioVigenteEtiqueta(): string {
    if (this.solicitudBloquesPendiente) return 'Cambio de horario pendiente';
    if (this.tieneHorarioPersonalizadoAprobado) return 'Horario personalizado aprobado';
    return 'Horario predeterminado';
  }

  get horarioVigenteTexto(): string {
    if (this.solicitudBloquesPendiente) {
      return 'Tu solicitud está pendiente. Hasta que el administrador la apruebe, sigue vigente el horario actual.';
    }
    if (this.tieneHorarioPersonalizadoAprobado) {
      return 'Tu horario semanal personalizado fue aprobado por el administrador y ya está aplicado en la agenda.';
    }
    return 'Estás usando el horario predeterminado: lunes a jueves de 09:00 a 17:30 y viernes de 09:00 a 16:30.';
  }

  get agendaPeriodoLabel(): string {
    const dias = this.semanaActual;
    // La agenda del profesional muestra lunes a viernes; el período se
    // rotula hasta el viernes, no hasta el domingo.
    if (dias.length < 5) return this.semanaLabel;
    const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
    const partes = (fecha: string) => ({
      anio: Number(fecha.slice(0, 4)),
      mes: Number(fecha.slice(5, 7)),
      dia: Number(fecha.slice(8, 10))
    });
    const desde = partes(dias[0].fecha);
    const hasta = partes(dias[4].fecha);
    if (desde.anio === hasta.anio && desde.mes === hasta.mes) {
      return `${desde.dia} – ${hasta.dia} de ${meses[hasta.mes - 1]} ${hasta.anio}`;
    }
    if (desde.anio === hasta.anio) {
      return `${desde.dia} ${meses[desde.mes - 1]} – ${hasta.dia} ${meses[hasta.mes - 1]} ${hasta.anio}`;
    }
    return `${desde.dia} ${meses[desde.mes - 1]} ${desde.anio} – ${hasta.dia} ${meses[hasta.mes - 1]} ${hasta.anio}`;
  }

  // Firmas estables: el componente compartido las usa en ngDoCheck.
  readonly agendaBloqueEstadoFn = (fecha: string, hora: string): string =>
    this.estadoAgendaCompartida(fecha, hora);

  readonly agendaBloqueCitasFn = (fecha: string, hora: string): any[] =>
    this.citasEnBloqueAgenda(fecha, hora);

  // El profesional no puede solicitar sobrecupos desde esta vista.
  readonly agendaSobrecupoDisponibleFn = (): boolean => false;

  readonly agendaFormatearFechaFn = (fecha: string): string =>
    this.formatearDiaSeleccionado(fecha);

  readonly agendaEsFeriadoFn = (fecha: string | undefined): boolean =>
    this.esFeriado(fecha);

  readonly agendaNombreFeriadoFn = (fecha: string | undefined): string =>
    this.nombreFeriado(fecha);

  // Genera la grilla de horas según la duración de atención configurada por el profesional
  // (antes estaba fijo a pasos de 60 min, por lo que las citas de 45 min no calzaban con ninguna fila)
  private horaAMinutos(hora: string, fallback: number): number {
    if (!hora) return fallback;
    const [h, m] = hora.split(':').map(Number);
    return h * 60 + m;
  }

  // Posición horizontal (%) de una cita dentro de la línea "Pulso de hoy",
  // según la jornada laboral aprobada del profesional (horario_inicio–horario_fin).
  // NO puede ser private: el template la llama directamente con
  // [style.left.%]="horaAPosicionPct(cita.hora)".
  horaAPosicionPct(hora: string): number {
    const { inicioMin, finMin } = this.rangoJornadaMin();
    const horaMin   = this.horaAMinutos(hora, inicioMin);

    const rango = finMin - inicioMin;
    if (rango <= 0) return 0;

    const pct = ((horaMin - inicioMin) / rango) * 100;
    return Math.min(100, Math.max(0, pct)); // clamp 0–100
  }

  // Día de la semana 0=Lunes ... 6=Domingo, a partir de la fecha local.
  private diaSemana(fecha: string): number {
    return (this.parseDateStrLocal(fecha).getDay() + 6) % 7;
  }

  // Jornada simple vigente, acotada al horario institucional. Los registros
  // antiguos pueden traer 08:00 (el horario anterior del centro); para el
  // profesional la atención nunca empieza antes de las 09:00 ni termina
  // después de las 17:30.
  private jornadaSimpleEfectiva(): { inicioMin: number; finMin: number } | null {
    if (!this.perfil.horario_inicio || !this.perfil.horario_fin) return null;
    const inicioMin = Math.max(9 * 60, this.horaAMinutos(this.perfil.horario_inicio, 9 * 60));
    const finMin    = Math.min(17 * 60 + 30, this.horaAMinutos(this.perfil.horario_fin, 17 * 60 + 30));
    return inicioMin < finMin ? { inicioMin, finMin } : null;
  }

  // Jornada vigente de un día concreto:
  //   1. Agenda por bloques aprobada: solo los tramos "disponible" de ese día.
  //   2. Jornada simple aprobada (horario_inicio/horario_fin), acotada al
  //      horario institucional.
  //   3. Horario institucional predeterminado (Lun-Jue 09:00-17:30,
  //      Vie 09:00-16:30). Sábado y domingo no tienen atención.
  // Devuelve null cuando ese día no tiene jornada (fin de semana o día sin
  // bloques dentro de una agenda por bloques).
  private jornadaDelDia(fecha: string): { inicioMin: number; finMin: number } | null {
    const dia = this.diaSemana(fecha);
    if (dia > 4) return null; // el centro no atiende fines de semana

    const [inicioInstitucional, finInstitucional] = this.RANGO_INSTITUCIONAL[dia] ?? ['09:00', '17:30'];
    const piso = this.horaAMinutos(inicioInstitucional, 9 * 60);
    const techo = this.horaAMinutos(finInstitucional, 17 * 60 + 30);

    const bloques: any[] = this.perfil.bloques_semanales ?? [];
    if (bloques.length) {
      const disp = bloques.filter(b => b.dia_semana === dia && b.tipo === 'disponible');
      if (!disp.length) return null;
      return {
        inicioMin: Math.max(piso, Math.min(...disp.map(b => this.horaAMinutos(b.hora_inicio, piso)))),
        finMin:    Math.min(techo, Math.max(...disp.map(b => this.horaAMinutos(b.hora_fin, techo)))),
      };
    }

    const simple = this.jornadaSimpleEfectiva();
    if (simple) {
      return {
        inicioMin: Math.max(piso, simple.inicioMin),
        finMin:    Math.min(techo, simple.finMin),
      };
    }

    return { inicioMin: piso, finMin: techo };
  }

  // Rango de la jornada en minutos: con agenda por bloques, desde el primer
  // bloque disponible hasta el ultimo; si no, horario_inicio/horario_fin o
  // el horario institucional predeterminado. Siempre acotado a 09:00-17:30.
  private rangoJornadaMin(): { inicioMin: number; finMin: number } {
    const disp = (this.perfil.bloques_semanales ?? []).filter((b: any) => b.tipo === 'disponible');
    if (disp.length) {
      return {
        inicioMin: Math.max(9 * 60, Math.min(...disp.map((b: any) => this.horaAMinutos(b.hora_inicio, 9 * 60)))),
        finMin:    Math.min(17 * 60 + 30, Math.max(...disp.map((b: any) => this.horaAMinutos(b.hora_fin, 17 * 60 + 30)))),
      };
    }
    return this.jornadaSimpleEfectiva() ?? { inicioMin: 9 * 60, finMin: 17 * 60 + 30 };
  }

  generarHorasGrilla(): void {
    const pasoMin   = this.perfil.duracion_min || 60;
    const { inicioMin, finMin } = this.rangoJornadaMin();
    const horas: string[] = [];
    let min = inicioMin;
    while (min < finMin) {
      const h = Math.floor(min / 60).toString().padStart(2,'0');
      const m = (min % 60).toString().padStart(2,'0');
      horas.push(`${h}:${m}`);
      min += pasoMin;
    }
    this.horasGrilla = horas;
  }
  generarSemanaActual(): void {
    const hoy = new Date();
    const lunes = new Date(hoy);
    lunes.setDate(hoy.getDate() - ((hoy.getDay() + 6) % 7));
    this.buildSemana(lunes);
  }

  private buildSemana(lunes: Date): void {
    const nombres = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
    const hoyStr  = this.toDateStr(new Date());
    this.semanaActual = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(lunes); d.setDate(lunes.getDate() + i);
      const f = this.toDateStr(d);
      return { nombre: nombres[i], num: d.getDate(), fecha: f, esHoy: f === hoyStr };
    });
    const meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
    const [anio, mes] = this.semanaActual[0].fecha.split('-').map(Number);
    this.semanaLabel  = `${meses[mes - 1]} ${anio}`;
  }

  private toDateStr(d: Date): string {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  // Convierte "YYYY-MM-DD" a Date usando la zona horaria LOCAL, no UTC.
  // new Date("YYYY-MM-DD") se interpreta como medianoche UTC y al convertir
  // a hora de Chile retrocede un día — por eso NUNCA se debe usar así.
  private parseDateStrLocal(fechaStr: string): Date {
    const [anio, mes, dia] = fechaStr.split('-').map(Number);
    return new Date(anio, mes - 1, dia);
  }

  semanaAnterior(): void { const l = this.parseDateStrLocal(this.semanaActual[0].fecha); l.setDate(l.getDate() - 7); this.buildSemana(l); this.cargarCitasSemana(); }
  semanaSiguiente(): void { const l = this.parseDateStrLocal(this.semanaActual[0].fecha); l.setDate(l.getDate() + 7); this.buildSemana(l); this.cargarCitasSemana(); }
  irAHoy(): void { this.generarSemanaActual(); this.cargarCitasSemana(); }

  cargarCitasSemana(): void {
    const fechaInicio = this.semanaActual[0]?.fecha;
    const fechaFin    = this.semanaActual[6]?.fecha;
    if (!fechaInicio) return;
    this.http.get<any[]>(`${API}/profesional/${this.profDbId}/citas`).subscribe({
      next: (data) => {
        this.citasSemana = (data ?? []).filter(c => c.fecha >= fechaInicio && c.fecha <= fechaFin);
        this.sincronizarCitasAgenda();
        this.cdr.detectChanges();
      },
      error: () => {
        this.citasSemana = [];
        this.citasAgenda = [];
        this.cdr.detectChanges();
      }
    });
  }

  // La agenda compartida muestra la especialidad bajo el nombre del paciente
  // en su panel contextual. El endpoint de citas propias no la envía, así que
  // se completa con la del perfil de la sesión (nunca con datos de terceros).
  private sincronizarCitasAgenda(): void {
    const especialidad = this.perfil?.especialidad ?? '';
    this.citasAgenda = this.citasSemana.map(cita => ({
      ...cita,
      especialidad: cita.especialidad || especialidad
    }));
  }

  // Con agenda por bloques: 'disponible', 'colacion' o 'fuera' (hora sin bloque
  // ese dia). null si el profesional no tiene bloques (usa su jornada simple).
  private estadoPorBloques(fecha: string, hora: string): 'disponible' | 'colacion' | 'fuera' | null {
    const bloques: any[] = this.perfil.bloques_semanales ?? [];
    if (!bloques.length) return null;
    const dia = this.diaSemana(fecha);
    const h = hora.substring(0, 5);
    const del_dia = bloques.filter(b => b.dia_semana === dia && h >= b.hora_inicio && h < b.hora_fin);
    if (del_dia.some(b => b.tipo === 'colacion')) return 'colacion';
    return del_dia.length ? 'disponible' : 'fuera';
  }

private esHoraDeColacion(hora: string): boolean {
    const inicio = this.perfil.hora_almuerzo_inicio;
    const fin    = this.perfil.hora_almuerzo_fin;
    if (!inicio || !fin) return false;
    const h = hora.substring(0, 5);
    return h >= inicio && h < fin;
  }
convertirA24h(hora: string): string {
    if (!hora) return '';
    if (!hora.includes('AM') && !hora.includes('PM')) return hora.substring(0,5);
    const [time, period] = hora.trim().split(' ');
    let [h, m] = time.split(':').map(Number);
    if (period === 'PM' && h !== 12) h += 12;
    if (period === 'AM' && h === 12) h = 0;
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`;
  }
  diasCerrados: any[] = [];
  cargarDiasCerrados(): void {
    this.http.get<any[]>(`${API}/dias-cerrados`).subscribe({
      next: (data) => { this.diasCerrados = data ?? []; this.cdr.detectChanges(); },
      error: () => {}
    });
  }
  esDiaCerrado(fecha: string): boolean { return this.diasCerrados.some(d => d.fecha === fecha); }

  getBloqueEstado(fecha: string, hora: string): string {
    if (this.diaSemana(fecha) > 4 || this.esDiaCerrado(fecha)) return 'cerrado-centro';
    const cita = this.citasSemana.find(c => c.fecha === fecha && this.convertirA24h(c.hora) === hora.substring(0,5));
    const porBloques = this.estadoPorBloques(fecha, hora);
    if (porBloques === null) {
      if (this.esHoraDeColacion(hora) || !this.esHoraDentroDeJornada(fecha, hora)) return 'bloqueado';
    } else if (porBloques !== 'disponible' && !cita) {
      return 'bloqueado';   // colacion u hora fuera de los bloques; una cita ya agendada igual se muestra
    }
    if (!cita) return 'libre';
    return cita.urgente ? 'urgente' : 'ocupado';
  }

  getBloqueInfo(fecha: string, hora: string): string {
    if (this.diaSemana(fecha) > 4 || this.esDiaCerrado(fecha)) return '';
    const porBloques = this.estadoPorBloques(fecha, hora);
    if (porBloques === 'colacion' || (porBloques === null && this.esHoraDeColacion(hora))) return 'Colación';
    const cita = this.citasSemana.find(c => c.fecha === fecha && this.convertirA24h(c.hora) === hora.substring(0,5));
    return cita ? cita.estudiante : '';
  }

  // ── Adaptadores para la agenda compartida del Administrador ────────
  // Traducen el dominio propio del profesional a los estados visuales de
  // AdminHorarioComponent, sin agregar reglas nuevas: los datos siguen
  // viniendo de los endpoints self-service ya autorizados.
  private citasEnBloqueAgenda(fecha: string, hora: string): any[] {
    return this.citasSemana.filter(cita => {
      if (cita.fecha !== fecha) return false;
      if (cita.estado === 'cancelada' || cita.estado === 'inasistencia') return false;
      return this.convertirA24h(cita.hora) === hora.substring(0, 5);
    });
  }

  private estadoAgendaCompartida(fecha: string, hora: string): string {
    // El centro no atiende sábado ni domingo: nunca se marcan como
    // disponibles, aunque no exista un DiaCerrado explícito.
    if (this.diaSemana(fecha) > 4) return 'cerrado-centro';
    if (this.esDiaCerrado(fecha)) return 'cerrado-centro';

    const citas = this.citasEnBloqueAgenda(fecha, hora);
    if (citas.some(cita => !!cita.urgente)) return 'urgente';
    if (citas.some(cita => !!cita.sobrecupo)) return 'sobrecupo';
    if (citas.length > 0) return 'ocupado';

    const porBloques = this.estadoPorBloques(fecha, hora);
    if (porBloques === 'colacion') return 'colacion';
    if (porBloques === 'fuera') return 'fuera-horario';
    if (porBloques === 'disponible') return 'disponible';

    // Sin agenda por bloques aprobada: se usa la jornada simple o, si
    // tampoco hay una jornada aprobada, el horario institucional
    // predeterminado de ese día (el viernes cierra a las 16:30).
    if (this.esHoraDeColacion(hora)) return 'colacion';
    return this.esHoraDentroDeJornada(fecha, hora) ? 'disponible' : 'fuera-horario';
  }

  private esHoraDentroDeJornada(fecha: string, hora: string): boolean {
    const jornada = this.jornadaDelDia(fecha);
    if (!jornada) return false;
    const horaMin = this.horaAMinutos(hora, jornada.inicioMin);
    return horaMin >= jornada.inicioMin && horaMin < jornada.finMin;
  }

  get citasDiaSeleccionado(): any[] {
    if (!this.diaSeleccionado) return [];
    return this.citasAgenda.filter(c => c.fecha === this.diaSeleccionado);
  }

  imprimirMiAgenda(): void {
    const host = document.querySelector<HTMLElement>(
      'app-dashboard-profesional app-admin-horario'
    );
    const tarjeta = host?.querySelector<HTMLElement>('.agenda-calendar-card');
    if (!tarjeta) {
      this.mensajeError = 'No se pudo preparar la agenda para imprimir.';
      return;
    }
    try {
      imprimirAgendaAislada({
        tarjeta,
        leyenda: host?.querySelector<HTMLElement>('.agenda-legend') ?? null,
        profesional: [this.perfil.nombre, this.perfil.especialidad]
          .filter(Boolean)
          .join(' — '),
        vistaNombre: 'Semana',
        periodo: this.agendaPeriodoLabel,
        orientacion: 'landscape'
      });
    } catch {
      this.mensajeError = 'No se pudo abrir la vista de impresión.';
    }
  }

  clickBloque(fecha: string, hora: string): void { this.diaSeleccionado = fecha; }

  // Desde la Agenda (u otras vistas): te lleva directo al Historial Clínico
  // y abre la ficha completa de ese paciente (con su historial de atenciones:
  // cuántas veces vino, cada cuánto, fecha, hora, motivo y medicamento).
  irAFichaDesdeAgenda(cita: any): void {
    if (!cita.estudiante_id) return;
    this.seccionActiva = 'historial-clinico';
    this.cargarPacientesHistorial();
    this.abrirFichaPaciente({ estudiante_id: cita.estudiante_id, nombre: cita.estudiante });
  }

  // Desde "Mis Pacientes": ir directo al Historial Clínico de ese paciente
  verHistorialPaciente(p: any): void {
    this.seccionActiva = 'historial-clinico';
    this.cargarPacientesHistorial();
    this.abrirFichaPaciente({ estudiante_id: p.estudiante_id, nombre: p.estudiante });
  }

  // ══════════════════════════════════════
  // SOLICITUDES — citas pendientes de confirmar (además de las
  // solicitudes de horario, que se cargan en cargarSolicitudesHorario)
  // ══════════════════════════════════════

  citasPendientes: any[] = [];

  cargarCitasPendientes(): void {
    this.http.get<any[]>(`${API}/profesional/${this.profDbId}/citas?estado=pendiente`).subscribe({
      next: (data) => { this.citasPendientes = data ?? []; this.cdr.detectChanges(); },
      error: () => { this.citasPendientes = []; this.cdr.detectChanges(); }
    });
  }

  // Tras completar/marcar inasistencia desde Solicitudes, refresca esta lista también
  private refrescarCitasPendientesSiCorresponde(): void {
    if (this.seccionActiva === 'solicitudes') this.cargarCitasPendientes();
  }

  // ══════════════════════════════════════
  // MIS ATENCIONES
  // ══════════════════════════════════════

  atenciones: any[]      = [];
  pagAtenciones          = 1;
  filtroEstadoAt         = '';
  filtroBusquedaAt       = '';
  modalCompletarAbierto  = false;
  citaParaCompletar: any = null;

  cargarAtenciones(): void {
    let url = `${API}/profesional/${this.profDbId}/citas`;
    if (this.filtroEstadoAt) url += `?estado=${this.filtroEstadoAt}`;
    this.http.get<any[]>(url).subscribe({
      next: (data) => {
        this.atenciones = data ?? [];
        this.pagAtenciones = 1;
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }
limpiarFiltrosAtenciones(): void {
  this.filtroBusquedaAt = '';
  this.filtroEstadoAt = '';
  this.cargarAtenciones();
}
  get atencionesFiltradas(): any[] {
    return this.atenciones.filter(a =>
      coincideBusqueda(
        this.filtroBusquedaAt,
        a.estudiante,
        a.rut,
        a.carrera,
      )
    );
  }

  get atencionesPaginadas(): any[] { return this.atencionesFiltradas.slice((this.pagAtenciones-1)*8, this.pagAtenciones*8); }

  getPaginasAt(): number[] {
    const total = Math.ceil(this.atencionesFiltradas.length / 8);
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  minVal(a: number, b: number): number { return Math.min(a, b); }

  // La pantalla "Completar atención" vive en su propio componente
  // (completar-atencion/): aquí solo se abre, se cierra y se refrescan las listas.
  abrirModalCompletar(cita: any): void {
    if (!this.puedeGestionarCita(cita)) return;
    this.citaParaCompletar = cita;
    this.modalCompletarAbierto = true;
  }

  cerrarModalCompletar(): void { this.modalCompletarAbierto = false; this.citaParaCompletar = null; }

  /** Datos del paciente para la pantalla: desde la cita (listas) o desde la ficha abierta. */
  get pacienteParaCompletar(): PacienteAtencion {
    const c = this.citaParaCompletar;
    if (c?.estudiante) return { nombre: c.estudiante, rut: c.rut, carrera: c.carrera };
    return {
      nombre: this.pacienteSeleccionado?.nombre || '—',
      rut: this.fichaEstudianteRut,
      carrera: this.fichaEstudianteCarrera
    };
  }

  onAtencionCompletada(documentos: DocumentoEmitido[]): void {
    this.cerrarModalCompletar();
    this.cargarAtenciones();
    this.cargarEstadisticasDia();
    this.cargarDocumentosHoy();
    this.cargarCitasHoy();
    this.cargarCitasSinCerrar();
    this.refrescarCitasPendientesSiCorresponde();
    this.mensajeExito = documentos.length
      ? `Atención completada. Se emitió${documentos.length > 1 ? 'ron' : ''} ${documentos.map(d => d.nombre_tipo.toLowerCase()).join(' y ')} y se envió al estudiante.`
      : 'Atención completada correctamente.';
    this.cdr.detectChanges();
    setTimeout(() => { this.mensajeExito = ''; this.cdr.detectChanges(); }, 4000);
  }

  marcarInasistencia(cita: any): void {
    if (!this.puedeGestionarCita(cita)) return;
    if (!confirm(`¿Marcar inasistencia de ${cita.estudiante}?`)) return;
    this.http.patch(`${API}/profesional/${this.profDbId}/citas/${cita.id}/inasistencia`, {}).subscribe({
      next: () => {
        this.cargarAtenciones();
        this.cargarEstadisticasDia();
        this.cargarCitasHoy();
        this.cargarCitasSinCerrar();
        this.refrescarCitasPendientesSiCorresponde();
        this.mensajeExito = 'Inasistencia registrada.';
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeExito = ''; this.cdr.detectChanges(); }, 3000);
      },
      error: () => {
        this.mensajeError = 'No se pudo registrar.';
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeError = ''; this.cdr.detectChanges(); }, 3000);
      }
    });
  }

  // ══════════════════════════════════════
  // PERFIL Y CONFIGURACIÓN
  // ══════════════════════════════════════

  configPerfil = { nombre: '', descripcion: '', contrasena_actual: '', contrasena_nueva: '', contrasena_conf: '' };
  charCount = 0;
  mostrarContrasenaActual = false;
  mostrarContrasenaaNueva  = false;
  mostrarContrasenaConf   = false;

  // Edición de Perfil / Contraseña: campos bloqueados hasta que se presiona "Editar"
  perfilEnEdicion   = false;
  passwordEnEdicion = false;
  private perfilOriginalFotoUrl: string | null = null;
  habilitarEdicionPerfil(): void { this.perfilEnEdicion = true; }

  cancelarEdicionPerfil(): void {
    this.perfilEnEdicion = false;
    this.configPerfil.nombre      = this.perfil.nombre || '';
    this.configPerfil.descripcion = this.perfil.descripcion || '';
    this.charCount = (this.perfil.descripcion || '').length;
  }

  habilitarEdicionPassword(): void { this.passwordEnEdicion = true; }

  cancelarEdicionPassword(): void {
    this.passwordEnEdicion = false;
    this.configPerfil.contrasena_actual = '';
    this.configPerfil.contrasena_nueva  = '';
    this.configPerfil.contrasena_conf   = '';
  }

  onDescripcionChange(): void { this.charCount = (this.configPerfil.descripcion || '').length; }

  imagenParaRecortar: string | null = null;
  verFotoAmpliada = false;

  onFotoSeleccionada(event: any): void {
    if (!this.perfilEnEdicion) return;
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e: any) => {
      this.imagenParaRecortar = e.target.result;
      this.cdr.detectChanges();
    };
    reader.readAsDataURL(file);
    event.target.value = '';
  }

  onFotoRecortada(dataUrl: string): void {
    this.perfil.foto_url    = dataUrl;
    this.imagenParaRecortar = null;
    this.cdr.detectChanges();
  }

  esFeriado(fecha: string | undefined): boolean {
    return !!fecha && !!obtenerFeriado(fecha);
  }

  nombreFeriado(fecha: string | undefined): string {
    if (!fecha) return '';
    const f = obtenerFeriado(fecha);
    return f ? `Feriado: ${f.nombre}` : '';
  }

  guardarPerfil(): void {
    if (!this.perfilModificado) return;
    this.http.patch(`${API}/profesional/${this.profDbId}/perfil`, {
      nombre: this.configPerfil.nombre, descripcion: this.configPerfil.descripcion, foto_url: this.perfil.foto_url
    }).subscribe({
      next: () => {
    this.perfil.nombre = this.configPerfil.nombre;
    this.perfil.descripcion = this.configPerfil.descripcion;
    this.perfilOriginalFotoUrl = this.perfil.foto_url;   // ← agregar esta línea
    this.perfilEnEdicion = false;
    this.mensajeExito = 'Perfil actualizado correctamente.';
    this.cdr.detectChanges();
    setTimeout(() => { this.mensajeExito = ''; this.cdr.detectChanges(); }, 3000);
},
      error: (err) => {
        this.mensajeError = err?.error?.detail || 'No se pudo guardar.';
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeError = ''; this.cdr.detectChanges(); }, 3000);
      }
    });
  }

  cambiarPassword(): void {
    if (!this.passwordModificada) return;
    if (!this.configPerfil.contrasena_actual) { this.mensajeError = 'Ingresa tu contraseña actual.'; setTimeout(() => this.mensajeError = '', 3000); return; }
    if (!this.configPerfil.contrasena_nueva)  { this.mensajeError = 'Ingresa la nueva contraseña.'; setTimeout(() => this.mensajeError = '', 3000); return; }
    if (!this.passwordCumpleReglas) { this.mensajeError = 'La nueva contraseña no cumple todos los requisitos de seguridad.'; setTimeout(() => this.mensajeError = '', 3000); return; }
    if (this.configPerfil.contrasena_nueva === this.configPerfil.contrasena_actual) { this.mensajeError = 'La nueva contraseña debe ser diferente a la contraseña actual.'; setTimeout(() => this.mensajeError = '', 3000); return; }
    if (this.configPerfil.contrasena_nueva !== this.configPerfil.contrasena_conf) { this.mensajeError = 'Las contraseñas no coinciden.'; setTimeout(() => this.mensajeError = '', 3000); return; }
    this.http.patch(`${API}/profesional/${this.profDbId}/cambiar-password`, {
      contrasena_actual: this.configPerfil.contrasena_actual, contrasena_nueva: this.configPerfil.contrasena_nueva
    }).subscribe({
      next: () => {
        this.configPerfil.contrasena_actual = ''; this.configPerfil.contrasena_nueva = ''; this.configPerfil.contrasena_conf = '';
        this.passwordEnEdicion = false;
        this.mensajeExito = 'Contraseña actualizada correctamente.';
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeExito = ''; this.cdr.detectChanges(); }, 3000);
      },
      error: (err) => {
        this.mensajeError = err?.error?.detail || 'Contraseña actual incorrecta.';
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeError = ''; this.cdr.detectChanges(); }, 3000);
      }
    });
  }
  // ══════════════════════════════════════
  // MI HORARIO: solicitudes de horario (agenda semanal por bloques)
  // ══════════════════════════════════════

  solicitudesHorario: any[] = [];

  get solicitudBloquesPendiente(): any {
    return this.solicitudesHorario.find(s => s.tipo === 'bloques' && s.estado === 'pendiente');
  }

  cargarSolicitudesHorario(): void {
    this.http.get<any[]>(`${API}/profesional/${this.profDbId}/solicitudes-horario`).subscribe({
      next: (data) => {
        this.solicitudesHorario = data ?? [];
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  // ══════════════════════════════════════
  // AGENDA SEMANAL POR BLOQUES
  // Grilla de celdas de 30 minutos que el profesional pinta como
  // "disponible" o "colacion". Horario institucional: Lun-Jue 09:00 a
  // 17:30, Vie 09:00 a 16:30 (mismo rango que app/reglas_horario.py en el
  // backend; si cambia uno, cambia el otro).
  // ══════════════════════════════════════

  readonly DIAS_BLOQUES = [
    { valor: 0, nombre: 'Lunes' }, { valor: 1, nombre: 'Martes' }, { valor: 2, nombre: 'Miércoles' },
    { valor: 3, nombre: 'Jueves' }, { valor: 4, nombre: 'Viernes' },
  ];
  private readonly RANGO_INSTITUCIONAL: Record<number, [string, string]> = {
    0: ['09:00', '17:30'], 1: ['09:00', '17:30'], 2: ['09:00', '17:30'],
    3: ['09:00', '17:30'], 4: ['09:00', '16:30'],
  };
  private readonly HORA_COLACION_DEFECTO: [string, string] = ['13:00', '14:00'];

  bloquesSeleccion: Record<string, 'disponible' | 'colacion'> = {};
  bloquesModoPincel: 'disponible' | 'colacion' = 'disponible';
  enviandoBloques = false;

  private sumarMinutos(hora: string, minutos: number): string {
    const total = this.horaAMinutos(hora, 0) + minutos;
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  }

  /** Inicio de cada celda de 30 minutos del dia, dentro del horario institucional. */
  slotsDelDia(dia: number): string[] {
    const [inicio, fin] = this.RANGO_INSTITUCIONAL[dia];
    const slots: string[] = [];
    for (let h = inicio; h < fin; h = this.sumarMinutos(h, 30)) slots.push(h);
    return slots;
  }

  claveBloque(dia: number, hora: string): string { return `${dia}-${hora}`; }

  estadoCelda(dia: number, hora: string): 'disponible' | 'colacion' | null {
    return this.bloquesSeleccion[this.claveBloque(dia, hora)] ?? null;
  }

  clickCeldaBloque(dia: number, hora: string): void {
    if (this.solicitudBloquesPendiente) return;
    const clave = this.claveBloque(dia, hora);
    if (this.bloquesSeleccion[clave] === this.bloquesModoPincel) delete this.bloquesSeleccion[clave];
    else this.bloquesSeleccion[clave] = this.bloquesModoPincel;
  }

  get bloquesSeleccionVacia(): boolean { return Object.keys(this.bloquesSeleccion).length === 0; }

  limpiarSeleccionBloques(): void { this.bloquesSeleccion = {}; }

  /** Horario institucional completo con colacion de 13:00 a 14:00 todos los dias. */
  aplicarHorarioPorDefecto(): void {
    if (this.solicitudBloquesPendiente) return;
    const [ini, fin] = this.HORA_COLACION_DEFECTO;
    const nueva: Record<string, 'disponible' | 'colacion'> = {};
    for (const dia of this.DIAS_BLOQUES) {
      for (const hora of this.slotsDelDia(dia.valor)) {
        nueva[this.claveBloque(dia.valor, hora)] = hora >= ini && hora < fin ? 'colacion' : 'disponible';
      }
    }
    this.bloquesSeleccion = nueva;
  }

  /** Pinta la grilla con la agenda por bloques ya aprobada (perfil.bloques_semanales). */
  precargarBloquesAprobados(bloques: any[] | undefined): void {
    const sel: Record<string, 'disponible' | 'colacion'> = {};
    for (const b of bloques ?? []) {
      if (!this.RANGO_INSTITUCIONAL[b.dia_semana]) continue;
      for (const hora of this.slotsDelDia(b.dia_semana)) {
        if (hora >= b.hora_inicio && hora < b.hora_fin) sel[this.claveBloque(b.dia_semana, hora)] = b.tipo;
      }
    }
    this.bloquesSeleccion = sel;
  }

  /** Celdas pintadas -> bloques contiguos del mismo tipo (menos filas al guardar). */
  private bloquesDesdeSeleccion(): { dia_semana: number; hora_inicio: string; hora_fin: string; tipo: string }[] {
    const bloques: { dia_semana: number; hora_inicio: string; hora_fin: string; tipo: string }[] = [];
    for (const dia of this.DIAS_BLOQUES) {
      let actual: { tipo: string; ini: string; fin: string } | null = null;
      for (const hora of this.slotsDelDia(dia.valor)) {
        const tipo = this.estadoCelda(dia.valor, hora);
        if (tipo && actual && actual.tipo === tipo && actual.fin === hora) {
          actual.fin = this.sumarMinutos(hora, 30);
          continue;
        }
        if (actual) bloques.push({ dia_semana: dia.valor, hora_inicio: actual.ini, hora_fin: actual.fin, tipo: actual.tipo });
        actual = tipo ? { tipo, ini: hora, fin: this.sumarMinutos(hora, 30) } : null;
      }
      if (actual) bloques.push({ dia_semana: dia.valor, hora_inicio: actual.ini, hora_fin: actual.fin, tipo: actual.tipo });
    }
    return bloques;
  }

  enviarSolicitudBloques(): void {
    if (this.bloquesSeleccionVacia || this.enviandoBloques) return;
    const bloques = this.bloquesDesdeSeleccion();
    if (!bloques.some(b => b.tipo === 'disponible')) {
      this.mensajeError = 'Marca al menos un bloque como disponible.';
      return;
    }
    this.enviandoBloques = true;
    this.http.post<any>(`${API}/profesional/${this.profDbId}/solicitar-bloques-horario`, { bloques }).subscribe({
      next: () => {
        this.mensajeExito = 'Solicitud enviada. Queda pendiente de aprobación del administrador.';
        this.enviandoBloques = false;
        this.cargarSolicitudesHorario();
      },
      error: (err) => {
        this.mensajeError = err?.error?.detail || 'No se pudo enviar la solicitud de horario.';
        this.enviandoBloques = false;
        this.cdr.detectChanges();
      }
    });
  }

  solicitudesSeleccionadas = new Set<number>();

get solicitudesHaySeleccionadas(): boolean {
  return this.solicitudesSeleccionadas.size > 0;
}

get solicitudesTodasSeleccionadas(): boolean {
  return this.solicitudesHorario.length > 0 && this.solicitudesSeleccionadas.size === this.solicitudesHorario.length;
}

toggleSeleccionSolicitud(s: any): void {
  if (this.solicitudesSeleccionadas.has(s.id)) this.solicitudesSeleccionadas.delete(s.id);
  else this.solicitudesSeleccionadas.add(s.id);
}

toggleSeleccionarTodasSolicitudes(): void {
  if (this.solicitudesTodasSeleccionadas) {
    this.solicitudesSeleccionadas.clear();
  } else {
    this.solicitudesHorario.forEach(s => this.solicitudesSeleccionadas.add(s.id));
  }
}

eliminarSolicitud(s: any): void {
  this.http.delete(`${API}/solicitudes-horario/${s.id}`).subscribe({
    next: () => {
      this.solicitudesHorario = this.solicitudesHorario.filter(x => x.id !== s.id);
      this.solicitudesSeleccionadas.delete(s.id);
      this.cdr.detectChanges();
    },
    error: () => {
      this.mensajeError = 'No se pudo eliminar la solicitud.';
      setTimeout(() => { this.mensajeError = ''; this.cdr.detectChanges(); }, 3000);
    }
  });
}

eliminarSolicitudesSeleccionadas(): void {
  const ids = Array.from(this.solicitudesSeleccionadas);
  ids.forEach(id => {
    this.http.delete(`${API}/solicitudes-horario/${id}`).subscribe({
      next: () => {
        this.solicitudesHorario = this.solicitudesHorario.filter(x => x.id !== id);
        this.cdr.detectChanges();
      }
    });
  });
  this.solicitudesSeleccionadas.clear();
}

  // ══════════════════════════════════════
  // HISTORIAL CLÍNICO
  // ══════════════════════════════════════

  pacientesHistorial: any[] = [];
  busquedaPaciente = '';
  filtroAnioHistorial = '';
  filtroCarreraHistorial = '';
  filtroEstadoHistorial: '' | 'completa' | 'sin_completar' | 'por_revisar' = '';
  cargandoPacientesHistorial = false;

  pacienteSeleccionado: any = null;   // { estudiante_id, nombre, ... }
  fichaPreguntas: any[] = [];
  fichaRespuestas: any = {};
  fichaExiste = false;
  fichaRespuestasInicial = '';   // para saber si hay antecedentes sin guardar
  fichaCuestionarioSolicitado = false;   // ¿este estudiante recibirá el cuestionario previo?
  fichaEnEdicion = false;
  fichaFechaModificacion: string | null = null;
  fichaCompletadoPor: string | null = null;
  fichaRevisada = true;
  guardandoFicha = false;

  // Datos del estudiante + su historial de citas con este profesional
  // (para la vista "ver todas sus atenciones" al hacer clic en el paciente)
  fichaEstudianteRut = '';
  fichaEstudianteCarrera = '';
  fichaEstudianteCorreo = '';
  fichaEstudianteFotoUrl: string | null = null;
  fichaFotoError = false;
  fichaCitas: any[] = [];
  fichaTotalAtenciones = 0;
  fichaUltimaVisita: string | null = null;
  fichaDiasDesdeUltimaVisita: number | null = null;
  fichaTab: 'timeline' | 'resumen' | 'ficha' | 'citas' = 'timeline';

  gestionarPlantillaAbierto = false;
  plantillaPreguntasEdit: any[] = [];
  guardandoPlantilla = false;

  get aniosHistorialDisponibles(): number[] {
    const actual = new Date().getFullYear();
    return [actual, actual - 1, actual - 2, actual - 3];
  }

  get pacientesHistorialFiltrados(): any[] {
    let lista = this.pacientesHistorial;
    if (this.busquedaPaciente.trim()) {
      lista = lista.filter(p =>
        coincideBusqueda(
          this.busquedaPaciente,
          p.nombre,
          p.rut,
          p.correo,
        )
      );
    }
    if (this.filtroEstadoHistorial === 'completa')      lista = lista.filter(p => p.tiene_ficha);
    if (this.filtroEstadoHistorial === 'sin_completar') lista = lista.filter(p => !p.tiene_ficha);
    if (this.filtroEstadoHistorial === 'por_revisar')   lista = lista.filter(p => p.pendiente_revision);
    return lista;
  }

  get carrerasHistorialDisponibles(): string[] {
    const set = new Set<string>();
    this.pacientesHistorial.forEach(p => { if (p.carrera) set.add(p.carrera); });
    return Array.from(set).sort();
  }

  // ── Tarjetas resumen de Historial Clínico (datos reales, sin cifras inventadas) ──
  get consultasTotalesHistorial(): number {
    return this.pacientesHistorial.reduce((sum, p) => sum + (p.total_atenciones || 0), 0);
  }

  get fichasCompletadasPctHistorial(): number {
    const total = this.pacientesHistorial.length;
    if (total === 0) return 0;
    const completas = this.pacientesHistorial.filter(p => p.tiene_ficha).length;
    return Math.round((completas / total) * 100);
  }

  cargarPacientesHistorial(): void {
    this.cargandoPacientesHistorial = true;
    let params = new HttpParams();
    if (this.filtroAnioHistorial)   params = params.set('anio', this.filtroAnioHistorial);
    if (this.filtroCarreraHistorial) params = params.set('carrera', this.filtroCarreraHistorial);
    this.http.get<any[]>(`${API}/historial-clinico/${this.profDbId}/pacientes`, { params }).subscribe({
      next: (data) => { this.pacientesHistorial = data; this.cargandoPacientesHistorial = false; this.cdr.detectChanges(); },
      error: () => { this.pacientesHistorial = []; this.cargandoPacientesHistorial = false; this.cdr.detectChanges(); }
    });
  }

  limpiarFiltrosHistorial(): void {
    this.busquedaPaciente = '';
    this.filtroAnioHistorial = '';
    this.filtroCarreraHistorial = '';
    this.filtroEstadoHistorial = '';
    this.cargarPacientesHistorial();
  }

  abrirFichaPaciente(paciente: any): void {
    this.pacienteSeleccionado = paciente;
    this.fichaEnEdicion = false;
    this.fichaTab = 'resumen';
    this.fichaFotoError = false;
    this.http.get<any>(`${API}/historial-clinico/${this.profDbId}/${paciente.estudiante_id}`).subscribe({
      next: (data) => {
        this.fichaPreguntas   = data.preguntas;
        this.fichaRespuestas  = { ...data.respuestas };
        this.fichaRespuestasInicial = JSON.stringify(this.fichaRespuestas);
        this.fichaExiste      = data.existe;
        this.fichaCuestionarioSolicitado = data.cuestionario_solicitado ?? false;
        this.fichaFechaModificacion = data.fecha_modificacion;
        this.fichaCompletadoPor     = data.completado_por;
        this.fichaRevisada          = data.revisado_por_profesional ?? true;
        this.fichaEnEdicion   = !data.existe; // primera vez → entra directo en modo edición

        this.fichaEstudianteRut     = data.estudiante_rut || '';
        this.fichaEstudianteCarrera = data.estudiante_carrera || '';
        this.fichaEstudianteCorreo  = data.estudiante_correo || '';
        this.fichaEstudianteFotoUrl = data.estudiante_foto_url || null;
        this.fichaCitas             = data.citas || [];
        this.fichaTotalAtenciones   = data.total_atenciones || 0;
        this.fichaUltimaVisita      = data.ultima_visita;
        this.fichaDiasDesdeUltimaVisita = data.dias_desde_ultima_visita;

        this.cdr.detectChanges();
      },
      error: () => {
        this.mensajeError = 'No se pudo cargar la ficha del paciente.';
        this.pacienteSeleccionado = null;
        this.cdr.detectChanges();
      }
    });
  }

  cerrarFichaPaciente(): void {
    this.pacienteSeleccionado = null;
    this.citaEnAtencion = null;
    this.fichaPreguntas  = [];
    this.fichaRespuestas = {};
    this.fichaCitas = [];
    this.fichaTab = 'resumen';
  }

  // ── Datos derivados para la vista de ficha estilo "Historial clínico" ──

  /** Vuelve a cargar la ficha abierta (tras anular un documento o decidir el cuestionario) sin cambiar de pestaña. */
  recargarFicha(): void {
    if (!this.pacienteSeleccionado) return;
    const pestana = this.fichaTab;
    this.abrirFichaPaciente(this.pacienteSeleccionado);
    this.fichaTab = pestana;   // abrirFichaPaciente la reinicia
  }

  get fichaCitasCompletadas(): any[] {
    return this.fichaCitas.filter(c => c.estado === 'completada');
  }

  get fichaUltimaAtencion(): any {
    return this.fichaCitasCompletadas[0] || null; // fichaCitas viene ordenado desc por fecha/hora
  }

  get fichaProximaCita(): any {
    const hoy = new Date().toISOString().slice(0, 10);
    const futuras = this.fichaCitas.filter(c => c.estado === 'pendiente' && c.fecha >= hoy);
    if (futuras.length === 0) return null;
    return futuras.reduce((min, c) => ((c.fecha + c.hora) < (min.fecha + min.hora) ? c : min));
  }

  get fichaCitaPendienteActual(): any {
    const enAtencion = this.citaEnAtencion
      ? this.fichaCitas.find(c => c.id === this.citaEnAtencion.id && c.estado === 'pendiente')
      : null;
    return enAtencion || this.fichaCitas.find(c => c.estado === 'pendiente') || null;
  }

  // Heurística: la cita más antigua de este paciente con este profesional es "Primera consulta"
  tipoAtencionCita(cita: any): string {
    if (this.fichaCitas.length === 0) return 'Consulta';
    const masAntigua = [...this.fichaCitas].sort((a, b) => (a.fecha + a.hora).localeCompare(b.fecha + b.hora))[0];
    return masAntigua === cita ? 'Primera consulta' : 'Seguimiento psicológico';
  }

  // Color del punto en la línea de tiempo, según el tipo de atención
  colorTipoAtencion(cita: any): string {
    const tipo = this.tipoAtencionCita(cita);
    if (tipo === 'Primera consulta') return 'morado';
    if (tipo === 'Seguimiento psicológico') return 'azul';
    return 'verde';
  }

  // Atenciones completadas del paciente, agrupadas por año (para la línea de tiempo)
  get fichaCitasCompletadasPorAnio(): { anio: string; atenciones: any[] }[] {
    const grupos: Record<string, any[]> = {};
    this.fichaCitasCompletadas.forEach(c => {
      const anio = (c.fecha || '').slice(0, 4) || 'Sin fecha';
      if (!grupos[anio]) grupos[anio] = [];
      grupos[anio].push(c);
    });
    return Object.keys(grupos)
      .sort((a, b) => b.localeCompare(a))
      .map(anio => ({ anio, atenciones: grupos[anio] }));
  }

  // % de preguntas de la ficha de antecedentes que ya tienen respuesta guardada
  get fichaCompletitudPct(): number {
    const total = this.fichaPreguntas.length;
    if (total === 0) return 0;
    const respondidas = this.fichaPreguntas.filter(p => {
      const v = this.fichaRespuestas[p.id];
      return v !== undefined && v !== null && String(v).trim() !== '';
    }).length;
    return Math.round((respondidas / total) * 100);
  }

  registrarNuevaAtencionDesdeFicha(): void {
    const pendiente = this.fichaCitaPendienteActual;
    if (pendiente && this.puedeGestionarCita(pendiente)) {
      this.abrirModalCompletar(pendiente);
    } else {
      this.mensajeError = 'No hay una cita pendiente lista para registrar. El estudiante debe agendar una hora primero.';
    }
  }

  imprimirHistorial(): void {
    window.print();
  }

  habilitarEdicionFicha(): void { this.fichaEnEdicion = true; }

  cancelarEdicionFicha(): void {
    if (!this.fichaExiste) { this.cerrarFichaPaciente(); return; }
    this.abrirFichaPaciente(this.pacienteSeleccionado);
  }

  guardarFicha(): void {
    if (this.guardandoFicha) return;
    this.guardandoFicha = true;
    this.http.put(`${API}/historial-clinico/${this.profDbId}/${this.pacienteSeleccionado.estudiante_id}`, {
      respuestas: this.fichaRespuestas
    }).subscribe({
      next: () => {
        this.fichaExiste = true;
        this.fichaEnEdicion = false;
        this.fichaRevisada = true;   // el profesional acaba de revisar/confirmar
        this.guardandoFicha = false;
        this.mensajeExito = 'Ficha guardada correctamente.';
        this.cargarPacientesHistorial();
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeExito = ''; this.cdr.detectChanges(); }, 3000);
      },
      error: () => {
        this.mensajeError = 'No se pudo guardar la ficha.';
        this.guardandoFicha = false;
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeError = ''; this.cdr.detectChanges(); }, 3000);
      }
    });
  }

  // ── Gestionar preguntas de la plantilla (por especialidad) ──

  abrirGestionPlantilla(): void {
    this.http.get<any>(`${API}/historial-clinico/plantilla/${this.profDbId}`).subscribe({
      next: (data) => {
        this.plantillaPreguntasEdit = data.preguntas.map((p: any) => ({ ...p }));
        this.gestionarPlantillaAbierto = true;
        this.cdr.detectChanges();
      },
      error: () => { this.mensajeError = 'No se pudo cargar la plantilla de preguntas.'; this.cdr.detectChanges(); }
    });
  }

  agregarPreguntaPlantilla(): void {
    this.plantillaPreguntasEdit.push({ id: null, etiqueta: '', tipo: 'texto', orden: this.plantillaPreguntasEdit.length });
  }

  eliminarPreguntaPlantilla(index: number): void {
    this.plantillaPreguntasEdit.splice(index, 1);
  }

  guardarPlantilla(): void {
    const preguntasValidas = this.plantillaPreguntasEdit.filter(p => p.etiqueta.trim());
    if (this.guardandoPlantilla) return;
    this.guardandoPlantilla = true;
    this.http.put(`${API}/historial-clinico/plantilla/${this.profDbId}`, { preguntas: preguntasValidas }).subscribe({
      next: () => {
        this.gestionarPlantillaAbierto = false;
        this.guardandoPlantilla = false;
        this.mensajeExito = 'Preguntas actualizadas correctamente.';
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeExito = ''; this.cdr.detectChanges(); }, 3000);
      },
      error: () => {
        this.mensajeError = 'No se pudo guardar la plantilla.';
        this.guardandoPlantilla = false;
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeError = ''; this.cdr.detectChanges(); }, 3000);
      }
    });
  }
}