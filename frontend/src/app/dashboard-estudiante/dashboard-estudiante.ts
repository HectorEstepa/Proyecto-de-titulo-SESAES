import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

import { environment } from '../config';
import { PhotoCropperComponent } from '../shared/photo-cropper/photo-cropper';
import { PhotoViewerComponent } from '../shared/photo-viewer/photo-viewer';
import { obtenerFeriado } from '../shared/feriados-chile';
import { obtenerDiasInternacionales } from '../shared/dias-internacionales';
import { ToastService } from '../shared/toast/toast.service';
import { EstudianteHistorialComponent } from './historial/estudiante-historial';
import { EstudianteCitasProximasComponent } from './citas-proximas/estudiante-citas-proximas';
import { evaluarPassword, type PasswordChecklist } from '../shared/password-validation';
import { coincideBusqueda } from '../shared/text-normalization';
const API = environment.apiUrl;

@Component({
  selector: 'app-dashboard-estudiante',
  standalone: true,
  imports: [CommonModule, FormsModule, PhotoCropperComponent, PhotoViewerComponent, EstudianteHistorialComponent, EstudianteCitasProximasComponent],
  templateUrl: './dashboard-estudiante.html',
  styleUrl: './dashboard-estudiante.css'
})
export class DashboardEstudianteComponent implements OnInit {
  seccionActiva  = 'inicio';
  sidebarMovilAbierto = false;
  toggleSidebarMovil(): void {
  this.sidebarMovilAbierto = !this.sidebarMovilAbierto;
}
  pasoAgendar    = 1;
  busqueda       = '';
  filtroArea     = '';
  horaSeleccionada   = '';
  observaciones      = '';
  profesionalSeleccionado: any = null;
  cargando       = false;

  private _mensajeExito = '';
  set mensajeExito(valor: string) { this._mensajeExito = valor; if (valor) this.toast.success(valor); }
  get mensajeExito(): string { return this._mensajeExito; }

  private _mensajeError = '';
  set mensajeError(valor: string) { this._mensajeError = valor; if (valor) this.toast.error(valor); }
  get mensajeError(): string { return this._mensajeError; }

  // Paginación de profesionales
  pagProf       = 0;
  profPorPagina = 6;

  // OJO: sin fallback a un id fijo. Si no hay 'usuario_id' en sessionStorage
  // (sesión corrupta o inexistente), se devuelve 0 -- un id inválido que el
  // backend rechazará -- en vez de caer silenciosamente en los datos de otro
  // estudiante real. El authGuard ya debería impedir llegar aquí sin sesión.
  get estudianteId(): number {
    return Number(sessionStorage.getItem('usuario_id')) || 0;
  }
  get estudianteNombre(): string {
    return this.estudianteData?.nombre || 'Estudiante';
  }
  get tituloSeccionEst(): string {
  if (this.seccionActiva === 'citas') {
    const map: Record<string, string> = {
      proximas:  'Mis Citas',
      solicitar: 'Solicitar Nueva Cita',
      historial: 'Historial de Citas'
    };
    return map[this.citasTab] ?? 'Mis Citas';
  }
  const map: Record<string, string> = {
    configuracion: 'Mi Perfil',
    ayuda:         'Ayuda'
  };
  return map[this.seccionActiva] ?? 'SESAES';
}

get subtituloSeccionEst(): string {
  if (this.seccionActiva === 'citas') {
    const map: Record<string, string> = {
      proximas:  'Gestiona tus próximas atenciones médicas.',
      solicitar: 'Sigue los pasos para confirmar tu atención médica.',
      historial: 'Consulta el registro de todas tus atenciones médicas.'
    };
    return map[this.citasTab] ?? '';
  }
  const map: Record<string, string> = {
    inicio:        'Gestiona tus atenciones en SESAES.',
    configuracion: 'Gestiona tu información personal y seguridad de tu cuenta.',
    ayuda:         'Mapa de SESAES, preguntas frecuentes y contacto.'
  };
  return map[this.seccionActiva] ?? '';
}
  get estudianteIniciales(): string {
    const nombre = this.estudianteNombre;
    const partes = nombre.split(' ');
    return partes.length >= 2
      ? partes[0][0] + partes[1][0]
      : nombre.substring(0, 2).toUpperCase();
  }

  constructor(
    private router: Router,
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
    private sanitizer: DomSanitizer,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.cargarProfesionales();
    this.cargarDatosEstudiante();
    this.cargarNotificaciones();
    this.cargarInfoCentro();
    this.cargarCuestionariosPendientes();
    this.cargarDiasCerrados();

    // Cuenta creada con contraseña temporal (ej. carga masiva) — se le
    // pide cambiarla o mantenerla antes de dejarlo usar el resto del sistema.
    if (sessionStorage.getItem('debe_cambiar_password') === 'true') {
      this.modalPrimerAccesoAbierto = true;
    }
  }

  // ══════════════════════════════════════
  // PRIMER ACCESO (contraseña temporal)
  // ══════════════════════════════════════
  modalPrimerAccesoAbierto = false;
  nuevaPasswordPrimerAcceso = '';
  confirmarPasswordPrimerAcceso = '';
  errorPrimerAcceso = '';
  procesandoPrimerAcceso = false;

  private resolverPrimerAcceso(nuevaPassword: string | null): void {
    if (this.procesandoPrimerAcceso) return;
    this.procesandoPrimerAcceso = true;
    this.errorPrimerAcceso = '';

    this.http.patch(`${API}/estudiante/${this.estudianteId}/primer-acceso`, {
      nueva_password: nuevaPassword
    }).subscribe({
      next: () => {
        sessionStorage.setItem('debe_cambiar_password', 'false');
        this.modalPrimerAccesoAbierto = false;
        this.procesandoPrimerAcceso = false;
        this.mensajeExito = 'Listo, ya puedes usar SESAES con normalidad.';
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.procesandoPrimerAcceso = false;
        this.errorPrimerAcceso = err?.error?.detail || 'No se pudo procesar tu solicitud.';
        this.cdr.detectChanges();
      }
    });
  }

  mantenerPasswordActual(): void {
    this.resolverPrimerAcceso(null);
  }

  cambiarPasswordPrimerAcceso(): void {
    const nueva = this.nuevaPasswordPrimerAcceso;
    if (!evaluarPassword(nueva).valida) {
      this.errorPrimerAcceso =
        'La nueva contraseña no cumple todos los requisitos de seguridad.';
      return;
    }
    if (nueva !== this.confirmarPasswordPrimerAcceso) {
      this.errorPrimerAcceso = 'Las contraseñas no coinciden.';
      return;
    }
    this.resolverPrimerAcceso(nueva);
  }

  // ══════════════════════════════════════
  // CUESTIONARIO DE ANTECEDENTES (primera atención con un profesional)
  // ══════════════════════════════════════
  cuestionariosPendientes: any[] = [];
  cuestionarioModalAbierto = false;
  cuestionarioActual: any = null;          // { profesional_id, profesional_nombre, especialidad, preguntas }
  respuestasCuestionario: Record<string, string> = {};
  enviandoCuestionario = false;
  errorCuestionario = '';

  cargarCuestionariosPendientes(): void {
    this.http.get<any[]>(`${API}/historial-clinico/cuestionarios-pendientes/${this.estudianteId}`).subscribe({
      next: (data) => {
        this.cuestionariosPendientes = data ?? [];
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  abrirCuestionario(item: any): void {
    this.errorCuestionario = '';
    this.http.get<any>(`${API}/historial-clinico/cuestionario-estudiante/${item.profesional_id}`).subscribe({
      next: (data) => {
        this.cuestionarioActual = { profesional_id: item.profesional_id, ...data };
        this.respuestasCuestionario = {};
        this.cuestionarioModalAbierto = true;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.mensajeError = err?.error?.detail || 'No se pudo cargar el cuestionario.';
        this.cdr.detectChanges();
      }
    });
  }

  cerrarCuestionario(): void {
    this.cuestionarioModalAbierto = false;
    this.cuestionarioActual = null;
    this.respuestasCuestionario = {};
    this.errorCuestionario = '';
  }

  enviarCuestionario(): void {
    if (!this.cuestionarioActual) return;

    const faltantes = (this.cuestionarioActual.preguntas || [])
      .filter((p: any) => !this.respuestasCuestionario[p.id]?.toString().trim());
    if (faltantes.length > 0) {
      this.errorCuestionario = 'Por favor responde todas las preguntas antes de enviar.';
      return;
    }

    this.enviandoCuestionario = true;
    this.http.post(`${API}/historial-clinico/cuestionario-estudiante/${this.cuestionarioActual.profesional_id}`, {
      respuestas: this.respuestasCuestionario
    }).subscribe({
      next: () => {
        this.enviandoCuestionario = false;
        this.cerrarCuestionario();
        this.mensajeExito = 'Cuestionario enviado correctamente.';
        this.cargarCuestionariosPendientes();
        this.cdr.detectChanges();
        setTimeout(() => { this.mensajeExito = ''; this.cdr.detectChanges(); }, 4000);
      },
      error: (err) => {
        this.enviandoCuestionario = false;
        this.errorCuestionario = err?.error?.detail || 'No se pudo enviar el cuestionario.';
        this.cdr.detectChanges();
      }
    });
  }

  // ══════════════════════════════════════
  // INFORMACIÓN DEL CENTRO
  // ══════════════════════════════════════

  infoCentro: any = {
    nombre_centro:    'SESAES',
    direccion:        '',
    telefono:         '',
    correo_contacto:  '',
    horario_atencion: ''
  };

  cargarInfoCentro(): void {
    this.http.get<any>(`${API}/configuracion-centro`).subscribe({
      next: (data) => {
        this.infoCentro = data ?? this.infoCentro;
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  // ══════════════════════════════════════
  // NOTIFICACIONES
  // ══════════════════════════════════════
  notificaciones: any[] = [];
  notifPanelAbierto     = false;
  notifNoLeidas         = 0;
  notifSeleccionadas    = new Set<number>();

  cargarNotificaciones(): void {
    this.http.get<any[]>(`${API}/notificaciones/${this.estudianteId}`).subscribe({
      next: (data) => {
        this.notificaciones = data ?? [];
        this.notifNoLeidas  = this.notificaciones.filter(n => !n.leida).length;
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  toggleNotificaciones(): void { this.notifPanelAbierto = !this.notifPanelAbierto; }

  marcarNotifLeida(n: any): void {
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
    this.http.patch(`${API}/notificaciones/leer-todas/${this.estudianteId}`, {}).subscribe({
      next: () => {
        this.notificaciones.forEach(n => n.leida = true);
        this.notifNoLeidas = 0;
        this.cdr.detectChanges();
      }
    });
  }

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
        if (!n.leida) this.notifNoLeidas = Math.max(0, this.notifNoLeidas - 1);
        this.notificaciones = this.notificaciones.filter(x => x.id !== n.id);
        this.notifSeleccionadas.delete(n.id);
        this.cdr.detectChanges();
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
        },
        error: (err) => { this.mensajeError = err?.error?.detail || 'No se pudo eliminar una de las notificaciones.'; }
      });
    });
    this.notifSeleccionadas.clear();
  }

  reagendarDesdeCancelacion(n: any): void {
    this.notifPanelAbierto = false;
    this.seccionActiva     = 'citas';
    this.citasTab          = 'solicitar';
    this.pasoAgendar       = 1;
    this.marcarNotifLeida(n);
  }

  // ══════════════════════════════════════
  // PROFESIONALES — con paginación
  // ══════════════════════════════════════

  cargarProfesionales(): void {
    this.http.get<any[]>(`${API}/profesionales`).subscribe({
      next: (data) => {
        this.profesionales = (data ?? []).map(p => ({
          ...p,
          iniciales: p.iniciales ?? this.calcularIniciales(p.nombre)
        }));
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  private calcularIniciales(nombre: string): string {
    const partes = nombre.split(' ');
    return partes.length >= 2
      ? partes[0][0] + partes[1][0]
      : nombre.substring(0, 2).toUpperCase();
  }

  cargarProximasCitas(): void {
    this.http.get<any[]>(`${API}/citas/estudiante/${this.estudianteId}`).subscribe({
      next: (data) => {
        this.proximasCitas = data ?? [];
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  cargarHistorial(): void {
    this.http.get<any[]>(`${API}/historial/estudiante/${this.estudianteId}`).subscribe({
      next: (data) => {
        this.historialCompleto = data ?? [];
        this.historialMostrado = this.historialCompleto;
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  citasTab: 'proximas' | 'solicitar' | 'historial' = 'proximas';

  navegarA(seccion: string, subTab?: string): void {
    this.seccionActiva     = seccion;
    if (seccion === 'citas') {
      this.citasTab = (subTab as any) || 'proximas';
    }
    this.mensajeExito      = '';
    this.mensajeError      = '';
    this.notifPanelAbierto = false;
    this.sidebarMovilAbierto = false;
  }

  cerrarSesion(): void {
    sessionStorage.clear();
    window.location.href = '/login';
  }

  profesionales: any[] = [];

  // Filtrado + paginación de profesionales
  get profesionalesFiltradosTotal(): any[] {
    return this.profesionales.filter(p =>
      coincideBusqueda(this.busqueda, p.nombre, p.especialidad)
      && (this.filtroArea === '' || p.especialidad === this.filtroArea)
    );
  }

  profesionalesFiltrados(): any[] {
    const todos = this.profesionalesFiltradosTotal;
    return todos.slice(this.pagProf * this.profPorPagina, (this.pagProf + 1) * this.profPorPagina);
  }

  get hayPaginaAnterior(): boolean { return this.pagProf > 0; }
  get hayPaginaSiguiente(): boolean {
    return (this.pagProf + 1) * this.profPorPagina < this.profesionalesFiltradosTotal.length;
  }

  paginaAnteriorProf(): void { if (this.hayPaginaAnterior) this.pagProf--; }
  paginaSiguienteProf(): void { if (this.hayPaginaSiguiente) this.pagProf++; }

  // Especialidades dinámicas desde backend
  get especialidadesDisponibles(): string[] {
    return Array.from(new Set(this.profesionales.map(p => p.especialidad).filter(Boolean)));
  }

  // ══════════════════════════════════════
  // CALENDARIO MENSUAL
  // ══════════════════════════════════════

  mesVisible    = new Date().getMonth();
  anioVisible   = new Date().getFullYear();
  diasMes: any[] = [];
  fechaSeleccionada: string | null = null;
  horasDisponibles: string[] = [];
  mensajeDisponibilidad: string | null = null;
  calendarioAbierto = false;

  private _cargandoDisponibilidad = false;
  private _ultimaFechaPedida: string | null = null;

  readonly NOMBRES_MES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
    'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

  get nombreMesVisible(): string {
    return `${this.NOMBRES_MES[this.mesVisible]} ${this.anioVisible}`;
  }

  private hoyStr(): string {
    const h = new Date();
    return `${h.getFullYear()}-${String(h.getMonth()+1).padStart(2,'0')}-${String(h.getDate()).padStart(2,'0')}`;
  }

  seleccionarProfesional(p: any, event?: Event): void {
    if (event) event.stopPropagation();
    this.profesionalSeleccionado = p;
    this.horaSeleccionada = ''; this.fechaSeleccionada = null;
    this.horasDisponibles = []; this.mensajeDisponibilidad = null;
    this.calendarioAbierto = false; this._ultimaFechaPedida = null;
    this.pasoAgendar = 2;
    const hoy = new Date();
    this.mesVisible  = hoy.getMonth();
    this.anioVisible = hoy.getFullYear();
    this.generarCalendario();
  }

  toggleCalendario(): void { this.calendarioAbierto = !this.calendarioAbierto; }

  generarCalendario(): void {
    const primerDia = new Date(this.anioVisible, this.mesVisible, 1);
    const ultimoDia = new Date(this.anioVisible, this.mesVisible + 1, 0);
    const hoyStr    = this.hoyStr();
    const offset    = (primerDia.getDay() + 6) % 7;
    const celdas: any[] = [];
    for (let i = 0; i < offset; i++) celdas.push(null);
    for (let dia = 1; dia <= ultimoDia.getDate(); dia++) {
      const fecha     = new Date(this.anioVisible, this.mesVisible, dia);
      const fechaStr  = `${this.anioVisible}-${String(this.mesVisible+1).padStart(2,'0')}-${String(dia).padStart(2,'0')}`;
      const diaSemana = fecha.getDay();
      const esFinde   = diaSemana === 0 || diaSemana === 6;
      const esPasado  = fechaStr < hoyStr;
      const diaCerradoInfo = this.diasCerrados.find(d => d.fecha === fechaStr);
      // Días que el profesional no atiende habitualmente (dias_disponibles,
      // 0=Lunes...4=Viernes — igual que app.reglas_horario en el backend).
      // null significa "profesional sin horario configurado todavía": no se
      // restringe nada para no bloquear de más algo que no se ha cargado.
      const diasDisp = this.profesionalSeleccionado?.dias_disponibles;
      const diaSemanaBackend = (diaSemana + 6) % 7; // JS: 0=Dom...6=Sáb → 0=Lun...6=Dom
      const noAtiendeEsteDia = !esFinde && Array.isArray(diasDisp) && !diasDisp.includes(diaSemanaBackend);
      celdas.push({
        num: dia, fecha: fechaStr, esFinde, esPasado, esHoy: fechaStr === hoyStr,
        esCerrado: !!diaCerradoInfo,
        motivoCerrado: diaCerradoInfo?.motivo || (noAtiendeEsteDia ? 'El profesional no atiende este día' : ''),
        deshabilitado: esFinde || esPasado || !!diaCerradoInfo || noAtiendeEsteDia
      });
    }
    this.diasMes = celdas;
  }

  diasCerrados: any[] = [];
  cargarDiasCerrados(): void {
    this.http.get<any[]>(`${API}/dias-cerrados`).subscribe({
      next: (data) => { this.diasCerrados = data ?? []; this.generarCalendario(); this.cdr.detectChanges(); },
      error: () => {}
    });
  }

  mesAnterior(): void {
    this.mesVisible--;
    if (this.mesVisible < 0) { this.mesVisible = 11; this.anioVisible--; }
    this.generarCalendario();
  }

  mesSiguiente(): void {
    this.mesVisible++;
    if (this.mesVisible > 11) { this.mesVisible = 0; this.anioVisible++; }
    this.generarCalendario();
  }

  seleccionarDia(dia: any): void {
    if (!dia || dia.deshabilitado) return;
    if (this.fechaSeleccionada === dia.fecha) { this.calendarioAbierto = false; return; }
    this.fechaSeleccionada = dia.fecha;
    this.horaSeleccionada  = '';
    this.calendarioAbierto = false;
    this.cargarDisponibilidad();
  }

  cargarDisponibilidad(): void {
    if (!this.profesionalSeleccionado || !this.fechaSeleccionada) return;
    if (this._ultimaFechaPedida === this.fechaSeleccionada && this._cargandoDisponibilidad) return;
    const profesionalId = this.profesionalSeleccionado.profesional_id ?? this.profesionalSeleccionado.id;
    if (!profesionalId) { this.mensajeDisponibilidad = 'No se pudo identificar al profesional.'; return; }
    this._ultimaFechaPedida      = this.fechaSeleccionada;
    this._cargandoDisponibilidad = true;
    this.cargando                = true;
    this.horasDisponibles        = [];
    this.mensajeDisponibilidad   = null;
    this.http.get<any>(`${API}/disponibilidad/${profesionalId}?fecha=${this.fechaSeleccionada}`).subscribe({
      next: (data) => {
        this.horasDisponibles      = data?.horas   ?? [];
        this.mensajeDisponibilidad = data?.mensaje ?? null;
        if (this.horasDisponibles.length > 0) this.mensajeDisponibilidad = null;
        this.cargando = false; this._cargandoDisponibilidad = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.mensajeDisponibilidad   = err?.error?.detail ?? 'No se pudo cargar la disponibilidad.';
        this.cargando = false; this._cargandoDisponibilidad = false;
        this.cdr.detectChanges();
      }
    });
  }

  seleccionarHora(hora: string): void { this.horaSeleccionada = hora; }
  getHoraDisplay(): string { return this.horaSeleccionada || ''; }

  getFechaDisplay(): string {
    if (!this.fechaSeleccionada) return '';
    const [anio, mes, dia] = this.fechaSeleccionada.split('-').map(Number);
    const fecha = new Date(anio, mes - 1, dia);
    const nombresDia = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
    return `${nombresDia[fecha.getDay()]} ${dia} de ${this.NOMBRES_MES[mes-1]}, ${anio}`;
  }

  enviandoCita = false;

  confirmarCita(): void {
    if (this.enviandoCita) return; // evita doble envío por doble clic
    this.mensajeError = '';
    const duplicada = this.proximasCitas.find(
      c => c.especialidad === this.profesionalSeleccionado?.especialidad && c.estado === 'pendiente'
    );
    if (duplicada) {
      this.mensajeError = 'Ya tienes una cita pendiente en esta especialidad.';
      return;
    }
    this.enviandoCita = true;
    const profesionalId = this.profesionalSeleccionado.profesional_id ?? this.profesionalSeleccionado.id;
    this.http.post<any>(`${API}/citas`, {
      estudiante_id: this.estudianteId, profesional_id: profesionalId,
      fecha: this.fechaSeleccionada || '', hora: this.getHoraDisplay(),
      observaciones: this.observaciones || null
    }).subscribe({
      next: (resp) => {
        this.proximasCitas.push({
          id: resp.id, iniciales: resp.iniciales, especialidad: resp.especialidad,
          profesional: resp.profesional, fecha: this.getFechaDisplay(),
          hora: resp.hora, urgente: false, aviso: resp.aviso, estado: resp.estado
        });
        this.resetAgendar();
        this.mensajeExito  = '✓ ¡Tu hora fue agendada correctamente!';
        this.seccionActiva = 'citas';
        this.enviandoCita = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.mensajeError = err?.error?.detail || 'No se pudo agendar la cita.';
        this.enviandoCita = false;
        // Si perdió la hora por una reserva simultánea de otra persona,
        // refrescamos la lista para que vea de inmediato que ya no está libre.
        if (err?.status === 409) {
          this.horaSeleccionada = '';
          this.cargarDisponibilidad();
        }
        this.cdr.detectChanges();
      }
    });
  }

  private resetAgendar(): void {
    this.pasoAgendar = 1; this.profesionalSeleccionado = null;
    this.horaSeleccionada = ''; this.fechaSeleccionada = null;
    this.horasDisponibles = []; this.observaciones = '';
    this.calendarioAbierto = false; this._ultimaFechaPedida = null;
    this.filtroArea = '';
  }

  // ══════════════════════════════════════
  // MIS CITAS
  // ══════════════════════════════════════

  proximasCitas: any[] = [];

  // NOTA (Fase 5B): puedeCancelar / citaPendienteVencida / avisoCancelacion /
  // diffHorasParaCancelar se relocalizaron a EstudianteCitasProximasComponent
  // (frontend/src/app/dashboard-estudiante/citas-proximas/). Son lógica
  // puramente visual, sin HTTP, exclusiva de la pestaña "Próximas" — el shell
  // sigue siendo dueño de proximasCitas y de todo lo que implica HTTP/modal.

  // ══════════════════════════════════════
  // MODAL: CANCELAR CITA (con opción de reagendar)
  // ══════════════════════════════════════
  modalCancelarAbierto = false;
  citaParaCancelar: { cita: any; index: number } | null = null;

  cancelarCita(index: number, cita: any): void {
    this.citaParaCancelar = { cita, index };
    this.modalCancelarAbierto = true;
  }

  cerrarModalCancelar(): void {
    this.modalCancelarAbierto = false;
    this.citaParaCancelar = null;
  }

  confirmarSoloCancelar(): void {
    if (!this.citaParaCancelar) return;
    const { cita, index } = this.citaParaCancelar;
    this.cerrarModalCancelar();
    this.http.delete(`${API}/citas/${cita.id}`).subscribe({
      next: () => {
        this.proximasCitas.splice(index, 1);
        this.cargarHistorial();
        this.cdr.detectChanges();
      },
      error: (err) => { alert(err?.error?.detail || 'No se pudo cancelar la cita.'); }
    });
  }

  confirmarCancelarYReagendar(): void {
    if (!this.citaParaCancelar) return;
    const { cita, index } = this.citaParaCancelar;
    this.cerrarModalCancelar();
    this.http.delete(`${API}/citas/${cita.id}`).subscribe({
      next: () => {
        this.proximasCitas.splice(index, 1);
        this.cargarHistorial();
        this.irAAgendarConProfesional(cita);
        this.cdr.detectChanges();
      },
      error: (err) => { alert(err?.error?.detail || 'No se pudo cancelar la cita para reagendar.'); }
    });
  }

  private irAAgendarConProfesional(cita: any): void {
    const prof = this.profesionales.find(p => p.nombre === cita.profesional);
    this.seccionActiva = 'citas';
    this.citasTab = 'solicitar';
    if (prof) { this.seleccionarProfesional(prof); }
    else { this.pasoAgendar = 1; }
  }

  reagendarCita(cita: any): void {
    // Si la cita todavía está pendiente (viene de "Próximas citas"), hay
    // que cancelarla primero: si no, el backend rechaza la nueva hora
    // porque ya existe una cita pendiente en esa misma especialidad.
    // Si ya está cancelada (viene del historial), no hace falta cancelar
    // de nuevo — se va directo al flujo de agendar.
    if (cita.estado === 'pendiente' && cita.id) {
      if (!confirm(`¿Deseas reagendar con ${cita.profesional}? Se cancelará esta hora y podrás elegir una nueva.`)) return;
      this.http.delete(`${API}/citas/${cita.id}`).subscribe({
        next: () => {
          this.cargarProximasCitas();
          this.cargarHistorial();
          this.irAAgendarConProfesional(cita);
        },
        error: (err) => { alert(err?.error?.detail || 'No se pudo cancelar la cita para reagendar.'); }
      });
    } else {
      this.irAAgendarConProfesional(cita);
    }
  }

  descargarPdf(citaId: number): void {
    this.http.get(`${API}/citas/${citaId}/pdf`, {
      responseType: 'blob'
    }).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const enlace = document.createElement('a');

        enlace.href = url;
        enlace.target = '_blank';
        enlace.rel = 'noopener';
        enlace.click();

        setTimeout(() => URL.revokeObjectURL(url), 60000);
      },
      error: () => {
        this.mensajeError = 'No se pudo descargar el documento.';
        setTimeout(() => this.mensajeError = '', 3000);
      }
    });
  }

  // ══════════════════════════════════════
  // HISTORIAL
  // ══════════════════════════════════════
  historialCompleto: any[] = [];
  historialMostrado: any[] = [];

  // Ícono representativo por especialidad — con fallback genérico para
  // cualquier especialidad nueva que se agregue desde el backend.
  private readonly iconosEspecialidad: Record<string, string> = {
    'nutrición': '🥗',
    'odontología': '🦷',
    'kinesiología': '🦴',
    'medicina general': '🩺',
    'oftalmología': '👁️',
    'rayos x': '🩻',
    'psicología': '🧠',
    'enfermería': '❤️',
  };
  iconoEspecialidad(especialidad: string): string {
    return this.iconosEspecialidad[(especialidad || '').toLowerCase()] || '🩺';
  }

  // -- Modal de detalle de atención (medicamento, observaciones, motivo) --
  detalleAtencionAbierto = false;
  atencionSeleccionada: any = null;

  verDetalleAtencion(h: any): void {
    this.atencionSeleccionada = h;
    this.detalleAtencionAbierto = true;
    this.cdr.detectChanges();
  }

  cerrarDetalleAtencion(): void {
    this.detalleAtencionAbierto = false;
    this.atencionSeleccionada = null;
    this.cdr.detectChanges();
  }


  get totalCitas()       { return this.historialCompleto.length; }
  get citasCompletadas() { return this.historialCompleto.filter(h => h.estado === 'completada').length; }
  get citasCanceladas()  { return this.historialCompleto.filter(h => h.estado === 'cancelada').length; }

  // ══════════════════════════════════════
  // CONFIGURACIÓN
  // ══════════════════════════════════════

  estudianteData: any  = null;
  celularOriginal      = '';
  celularEditable       = '';
  correoSecundarioOriginal = '';
  correoSecundarioEditable = '';
  perfilEnEdicion      = false;
  fotoPerfilUrl: string | null = null;
  fotoPerfilCambiada   = false;
  imagenParaRecortar: string | null = null;
  verFotoAmpliada = false;
  temaOscuro           = false;

faqs = [
  { pregunta: '¿Cómo cancelar una cita?', respuesta: 'Ve a "Mis Citas", busca la cita que deseas cancelar y presiona el botón "Cancelar". Puedes cancelar hasta 5 horas antes de la hora agendada.', abierta: false },
  { pregunta: '¿Cómo reprogramar una cita?', respuesta: 'En "Mis Citas", presiona el botón "Reagendar" junto a la cita. Esto te llevará al flujo de agendamiento con el mismo profesional para elegir una nueva fecha y hora.', abierta: false },
  { pregunta: '¿Qué pasa si llego tarde?', respuesta: 'Si llegas tarde, el profesional podría no poder atenderte y tu cita quedará marcada como inasistencia. Te recomendamos llegar con anticipación.', abierta: false },
  { pregunta: '¿Qué debo llevar a mi cita?', respuesta: 'Trae tu credencial de estudiante UTEM. Si tu atención lo requiere, también lleva exámenes o documentación médica previa relacionada con tu consulta.', abierta: false },
  { pregunta: '¿Puedo elegir otro profesional?', respuesta: 'Sí. En "Agendar Hora" puedes ver todos los profesionales disponibles por especialidad y elegir con cuál deseas atenderte.', abierta: false }
];

toggleFaq(faq: any): void {
  faq.abierta = !faq.abierta;
}

  // ══════════════════════════════════════
  // AYUDA (Mapa de SESAES + Preguntas Frecuentes)
  // ══════════════════════════════════════
  tabAyuda: 'faq' | 'mapa' | 'contacto' = 'faq';
  get perfilModificado(): boolean {
    return this.celularEditable !== this.celularOriginal
        || this.correoSecundarioEditable !== this.correoSecundarioOriginal
        || this.fotoPerfilCambiada;
  }

  get correoSecundarioValido(): boolean {
    if (!this.correoSecundarioEditable) return true; // opcional, vacío es válido
    return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(this.correoSecundarioEditable);
  }

  // ══════════════════════════════════════
  // CAMBIO DE CONTRASEÑA
  // ══════════════════════════════════════
  modalCambiarPasswordAbierto = false;
  passwordActual = '';
  passwordNueva = '';
  passwordConfirmacion = '';
  errorCambioPassword = '';
  guardandoCambioPassword = false;
  modalConfirmarCambioPasswordAbierto = false;
  mostrarPasswordActual = false;
  mostrarPasswordNueva = false;
  mostrarPasswordConfirmacion = false;

  get passwordChecklist(): PasswordChecklist {
    return evaluarPassword(this.passwordNueva);
  }

  get passwordMinimo8(): boolean {
    return this.passwordChecklist.minimo8;
  }

  get passwordTieneMayuscula(): boolean {
    return this.passwordChecklist.mayuscula;
  }

  get passwordTieneMinuscula(): boolean {
    return this.passwordChecklist.minuscula;
  }

  get passwordTieneNumero(): boolean {
    return this.passwordChecklist.numero;
  }

  get passwordTieneEspecial(): boolean {
    return this.passwordChecklist.especial;
  }

  get passwordSinEspacios(): boolean {
    return this.passwordChecklist.sinEspacios;
  }

  get passwordCumpleReglas(): boolean {
    return this.passwordChecklist.valida;
  }

  abrirModalCambiarPassword(): void {
    this.passwordActual = '';
    this.passwordNueva = '';
    this.passwordConfirmacion = '';
    this.errorCambioPassword = '';
    this.mostrarPasswordActual = false;
    this.mostrarPasswordNueva = false;
    this.mostrarPasswordConfirmacion = false;
    this.modalConfirmarCambioPasswordAbierto = false;
    this.modalCambiarPasswordAbierto = true;
    this.cdr.detectChanges();
  }

  cerrarModalCambiarPassword(): void {
    if (this.guardandoCambioPassword) return;
    this.modalCambiarPasswordAbierto = false;
    this.passwordActual = '';
    this.passwordNueva = '';
    this.passwordConfirmacion = '';
    this.errorCambioPassword = '';
    this.mostrarPasswordActual = false;
    this.mostrarPasswordNueva = false;
    this.mostrarPasswordConfirmacion = false;
    this.modalConfirmarCambioPasswordAbierto = false;
    this.cdr.detectChanges();
  }

  guardarCambioPassword(): void {
    if (this.guardandoCambioPassword) return;

    if (!this.passwordActual) {
      this.errorCambioPassword = 'Ingresa tu contraseña actual.';
      return;
    }
    if (!this.passwordCumpleReglas) {
      this.errorCambioPassword =
        'La nueva contraseña no cumple todos los requisitos de seguridad.';
      return;
    }
    if (this.passwordNueva === this.passwordActual) {
      this.errorCambioPassword =
        'La nueva contraseña debe ser diferente a la contraseña actual.';
      return;
    }
    if (this.passwordNueva !== this.passwordConfirmacion) {
      this.errorCambioPassword = 'Las contraseñas nuevas no coinciden.';
      return;
    }

    this.errorCambioPassword = '';
    this.modalConfirmarCambioPasswordAbierto = true;
    this.cdr.detectChanges();
  }

  cancelarConfirmacionCambioPassword(): void {
    if (this.guardandoCambioPassword) return;
    this.modalConfirmarCambioPasswordAbierto = false;
    this.cdr.detectChanges();
  }

  confirmarCambioPassword(): void {
    if (this.guardandoCambioPassword) return;

    this.modalConfirmarCambioPasswordAbierto = false;
    this.guardandoCambioPassword = true;

    this.http.patch(`${API}/estudiante/${this.estudianteId}/cambiar-password`, {
      contrasena_actual: this.passwordActual,
      contrasena_nueva: this.passwordNueva
    }).subscribe({
      next: () => {
        this.guardandoCambioPassword = false;
        this.cerrarModalCambiarPassword();
        this.mensajeExito = 'Contraseña actualizada correctamente.';
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.guardandoCambioPassword = false;
        this.errorCambioPassword =
          err?.error?.detail || 'No se pudo cambiar la contraseña.';
        this.cdr.detectChanges();
      }
    });
  }

  cargarDatosEstudiante(): void {
    const id = this.estudianteId;
    if (!id) { this.cerrarSesion(); return; }
    this.http.get<any>(`${API}/estudiante/${id}`).subscribe({
      next: (data) => {
        this.estudianteData  = data;
        if (data.id) sessionStorage.setItem('usuario_id', String(data.id));
        this.celularOriginal = this.extraerDigitosCelular(data.telefono);
        this.celularEditable = this.celularOriginal;
        this.correoSecundarioOriginal = data.correo_secundario || '';
        this.correoSecundarioEditable = this.correoSecundarioOriginal;
        this.fotoPerfilUrl   = data.foto_url || null;
        this.temaOscuro      = data.tema_oscuro || false;
        document.body.classList.toggle('tema-oscuro', this.temaOscuro);
        this.cargarProximasCitas();
        this.cargarHistorial();
        this.cdr.detectChanges();
      },
      error: () => {
        this.cargarProximasCitas();
        this.cargarHistorial();
      }
    });
  }

  private extraerDigitosCelular(telefono: string | null | undefined): string {
    return (telefono || '').replace(/^\+?56/, '').replace(/\D/g, '').slice(0, 9);
  }

  private formatearCelularCompleto(digitos: string): string {
    return digitos ? `+56 ${digitos}` : '';
  }

  habilitarEdicionPerfil(): void { this.perfilEnEdicion = true; }

  onCelularChange(valor: string): void {
    this.celularEditable = (valor || '').replace(/\D/g, '').slice(0, 9);
  }

  onFotoSeleccionada(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file  = input.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) { alert('Por favor selecciona un archivo de imagen válido.'); return; }
    const reader = new FileReader();
    reader.onload = () => {
      this.imagenParaRecortar = reader.result as string;
      this.cdr.detectChanges();
    };
    reader.readAsDataURL(file);
    input.value = '';
  }

  onFotoRecortada(dataUrl: string): void {
    this.fotoPerfilUrl      = dataUrl;
    this.fotoPerfilCambiada = true;
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

  /** Lo que se celebra ese día: feriado chileno + días internacionales ONU (informativo, no bloquea nada). */
  infoDelDia(fecha: string | undefined): string[] {
    if (!fecha) return [];
    const info: string[] = [];
    const feriado = obtenerFeriado(fecha);
    if (feriado) info.push(`🇨🇱 Feriado: ${feriado.nombre}`);
    for (const d of obtenerDiasInternacionales(fecha)) info.push(`🌍 ${d.nombre}`);
    return info;
  }


  toggleTema(oscuro: boolean): void {
    this.temaOscuro = oscuro;
    document.body.classList.toggle('tema-oscuro', oscuro);
    this.http.patch<any>(`${API}/estudiante/${this.estudianteId}`, { tema_oscuro: oscuro }).subscribe({ error: () => {} });
  }

  // Toggle desde el ícono sol/luna del topbar
  toggleTemaRapido(): void {
    this.toggleTema(!this.temaOscuro);
  }

  cancelarEdicionPerfil(): void {
    this.celularEditable    = this.celularOriginal;
    this.correoSecundarioEditable = this.correoSecundarioOriginal;
    this.perfilEnEdicion    = false;
    this.fotoPerfilUrl      = this.estudianteData?.foto_url || null;
    this.fotoPerfilCambiada = false;
  }

  guardarPerfil(): void {
    if (!this.perfilModificado || !this.correoSecundarioValido) return;
    const payload: any = {};
    if (this.celularEditable !== this.celularOriginal) payload.telefono = this.formatearCelularCompleto(this.celularEditable);
    if (this.correoSecundarioEditable !== this.correoSecundarioOriginal) payload.correo_secundario = this.correoSecundarioEditable || null;
    if (this.fotoPerfilCambiada) payload.foto_url = this.fotoPerfilUrl;
    this.http.patch<any>(`${API}/estudiante/${this.estudianteId}`, payload).subscribe({
      next: (data) => {
        this.estudianteData = data;
        this.celularOriginal = this.extraerDigitosCelular(data.telefono);
        this.celularEditable = this.celularOriginal;
        this.correoSecundarioOriginal = data.correo_secundario || '';
        this.correoSecundarioEditable = this.correoSecundarioOriginal;
        this.fotoPerfilCambiada = false; this.perfilEnEdicion = false;
        this.mensajeExito = '✓ Cambios guardados correctamente.';
        setTimeout(() => { this.mensajeExito = ''; this.cdr.detectChanges(); }, 3000);
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.mensajeError = err?.error?.detail || 'No se pudieron guardar los cambios.';
        setTimeout(() => { this.mensajeError = ''; this.cdr.detectChanges(); }, 3000);
        this.cdr.detectChanges();
      }
    });
  }

  abrirComoLlegar(): void {
    const direccion = (this.infoCentro.direccion || '').trim();
    if (!direccion) {
      this.mensajeError = 'La ubicación de SESAES no está configurada actualmente.';
      return;
    }
    const destino = encodeURIComponent(direccion);
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${destino}`, '_blank', 'noopener,noreferrer');
  }

  getMapaUrl(): SafeResourceUrl {
    const q = encodeURIComponent((this.infoCentro.direccion || '').trim());
    const url = `https://maps.google.com/maps?q=${q}&t=&z=16&ie=UTF8&iwloc=&output=embed`;
    return this.sanitizer.bypassSecurityTrustResourceUrl(url);
  }
}