import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminCapacidadesClinicasComponent } from './capacidades-clinicas/admin-capacidades-clinicas';

export type ConfigTab =
  | 'general'
  | 'citas'
  | 'horarios'
  | 'usuarios'
  | 'capacidades'
  | 'seguridad';

@Component({
  selector: 'app-admin-configuracion',
  standalone: true,
  imports: [CommonModule, FormsModule, AdminCapacidadesClinicasComponent],
  templateUrl: './admin-configuracion.html'
})
export class AdminConfiguracionComponent {
  @Input() configTabActiva: ConfigTab = 'general';
  @Output() configTabActivaChange = new EventEmitter<ConfigTab>();

  @Input() configCentro: any = {};
  @Input() centroEnEdicion = false;
  @Input() centroModificado = false;
  @Input() guardandoConfig = false;

  @Input() configCitas: any = {};
  @Input() guardandoConfigCitas = false;

  @Input() diasCerrados: any[] = [];
  @Input() nuevoDiaCerrado: { fecha: string; motivo: string } = {
    fecha: '',
    motivo: ''
  };
  @Input() creandoDiaCerrado = false;
  @Input() hoyISO = '';

  @Input() usuariosDelSistema: any[] = [];

  // ── Usuarios y roles (tabla unificada + perfil) ──
  @Input() usuariosSubTab: 'estudiantes' | 'profesionales' | 'administradores' = 'estudiantes';
  @Output() usuariosSubTabChange = new EventEmitter<'estudiantes' | 'profesionales' | 'administradores'>();

  @Input() usuariosBusqueda = '';
  @Output() usuariosBusquedaChange = new EventEmitter<string>();
  @Input() usuariosFiltroRol = '';
  @Output() usuariosFiltroRolChange = new EventEmitter<string>();
  @Input() usuariosFiltroEstado = '';
  @Output() usuariosFiltroEstadoChange = new EventEmitter<string>();
  @Output() buscarUsuarios = new EventEmitter<void>();

  @Input() usuariosEstudiantes: any[] = [];
  @Input() usuariosEstudiantesTotal = 0;
  @Input() usuariosEstudiantesPagina = 1;
  @Input() usuariosEstudiantesPorPagina = 8;
  @Input() usuariosEstudiantesCargando = false;
  @Input() totalPaginasUsuariosEstudiantes = 1;
  @Output() cambiarPaginaUsuariosEstudiantes = new EventEmitter<number>();

  @Input() usuariosProfesionales: any[] = [];
  @Input() usuariosAdministradores: any[] = [];
  @Input() puedeVerAdministradoresUsuarios = false;

  @Input() usuarioSeleccionado: any = null;
  @Input() usuarioSeleccionadoTipo: 'estudiante' | 'profesional' | 'administrador' | null = null;
  @Output() seleccionarUsuarioPerfil = new EventEmitter<{ usuario: any; tipo: 'estudiante' | 'profesional' | 'administrador' }>();
  @Output() cerrarPerfilUsuario = new EventEmitter<void>();

  @Input() perfilTabActiva: 'general' | 'horarios' | 'permisos' = 'general';
  @Output() perfilTabActivaChange = new EventEmitter<'general' | 'horarios' | 'permisos'>();
  @Input() perfilHorarios: any[] = [];
  @Input() perfilHorariosCargando = false;
  @Input() puedeVerHorariosPerfil = false;

  // Licencias/permisos/faltas/vacaciones (visual por ahora — se conecta a
  // datos reales cuando exista el flujo de solicitudes desde Dashboard
  // Profesional). Dos niveles de acceso, sin permisos nuevos:
  //   - profesionales.gestionar → gestión completa (hoy solo SUPERADMIN
  //     por defecto; un ADMIN la recibe solo si SUPERADMIN se la asigna).
  //   - profesionales.ver → panel reducido de solo lectura: estado +
  //     fecha estimada de retorno. NUNCA documentos ni nombre del suplente.
  @Input() puedeGestionarAusenciasProfesional = false;
  @Input() puedeVerAusenciasBasicoProfesional = false;

  @Input() auditoria: any[] = [];
  @Input() auditFiltroDesde = '';
  @Output() auditFiltroDesdeChange = new EventEmitter<string>();

  @Input() auditFiltroHasta = '';
  @Output() auditFiltroHastaChange = new EventEmitter<string>();

  @Input() cargandoAuditoria = false;

  @Input() puedeConfigGeneral = false;
  @Input() puedeConfigCitas = false;
  @Input() puedeConfigHorarios = false;
  @Input() puedeConfigUsuarios = false;
  @Input() puedeConfigCapacidades = false;
  @Input() puedeVerAuditoria = false;

  @Output() habilitarEdicionCentro = new EventEmitter<void>();
  @Output() cancelarEdicionCentro = new EventEmitter<void>();
  @Output() guardarInfoCentro = new EventEmitter<void>();

  @Output() guardarConfiguracionCitas = new EventEmitter<void>();

  @Output() crearDiaCerrado = new EventEmitter<void>();
  @Output() verCitasDiaCerrado = new EventEmitter<any>();
  @Output() reabrirDiaCerrado = new EventEmitter<any>();

  @Output() cargarAuditoria = new EventEmitter<void>();
  @Output() exportarAuditoriaExcel = new EventEmitter<void>();
  @Output() exportarAuditoriaPdf = new EventEmitter<void>();

  cambiarTab(tab: ConfigTab): void {
    this.configTabActiva = tab;
    this.configTabActivaChange.emit(tab);
  }

  cambiarUsuariosSubTab(tab: 'estudiantes' | 'profesionales' | 'administradores'): void {
    this.usuariosSubTab = tab;
    this.usuariosSubTabChange.emit(tab);
    // El filtro de rol solo existe dentro de Administradores: se limpia al cambiar de pestaña.
    if (this.usuariosFiltroRol) {
      this.usuariosFiltroRol = '';
      this.usuariosFiltroRolChange.emit('');
    }
  }

  // ── Filtro LOCAL de Rol/Estado/texto para Profesionales y
  // Administradores (listas ya cargadas completas, acotadas). Estudiantes
  // usa búsqueda real en backend (buscarUsuarios.emit()) por volumen. ──
  private coincideBusqueda(valor: string | null | undefined): boolean {
    if (!this.usuariosBusqueda.trim()) return true;
    return (valor ?? '').toLowerCase().includes(this.usuariosBusqueda.trim().toLowerCase());
  }

  get estudiantesFiltrados(): any[] {
    if (!this.usuariosFiltroEstado) return this.usuariosEstudiantes;
    const quiereActivo = this.usuariosFiltroEstado === 'activo';
    // La tabla trata `activo` ausente como Activo (solo `false` es Inactivo); el filtro debe hacer lo mismo.
    return this.usuariosEstudiantes.filter(e => (e.activo !== false) === quiereActivo);
  }

  get profesionalesFiltrados(): any[] {
    return this.usuariosProfesionales.filter(p =>
      (!this.usuariosFiltroEstado || String(p.estado || 'activo').toLowerCase() === this.usuariosFiltroEstado) &&
      (this.coincideBusqueda(p.nombre) || this.coincideBusqueda(p.rut))
    );
  }

  get administradoresFiltrados(): any[] {
    return this.usuariosAdministradores.filter(a =>
      (!this.usuariosFiltroEstado || (this.usuariosFiltroEstado === 'activo') === (a.activo !== false)) &&
      (!this.usuariosFiltroRol || a.rol === this.usuariosFiltroRol) &&
      (this.coincideBusqueda(a.nombre) || this.coincideBusqueda(a.rut) || this.coincideBusqueda(a.correo))
    );
  }


  // Estructura visual (sin datos reales todavía — ver nota en el panel):
  // se conectará cuando el profesional pueda solicitar estos ítems desde
  // su propio dashboard y el admin pueda aceptar/rechazar/modificar.
  readonly categoriasAusencia = [
    { tipo: 'licencia_medica', etiqueta: 'Licencias médicas', icono: 'medical_services' },
    { tipo: 'permiso_administrativo', etiqueta: 'Permisos administrativos', icono: 'badge' },
    { tipo: 'falta', etiqueta: 'Faltas', icono: 'event_busy' },
    { tipo: 'vacaciones', etiqueta: 'Vacaciones', icono: 'beach_access' }
  ];

  /** Nombre + apellido, sin prefijo profesional (Dr./Dra.): "Dra. Valentina Rojas" → VR. */
  inicialesNombre(nombre: unknown): string {
    const partes = String(nombre ?? '').replace(/^\s*dra?\.?\s+/i, '').trim().split(/\s+/).filter(Boolean);
    if (partes.length >= 2) return `${partes[0][0]}${partes[1][0]}`.toUpperCase();
    return (partes[0] ?? '?').substring(0, 2).toUpperCase();
  }

  // ── Avatar del panel de Perfil: mismo criterio que el resto de SESAES
  // (ver admin-profesionales.ts::colorDeProfesional) — foto real si existe;
  // si no, iniciales reales del profesional (prof.iniciales, no recalculadas)
  // sobre el color que el profesional tiene asignado, con el mismo
  // fallback por especialidad y neutro. Nunca se usa un color fijo nuevo. ──
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
  private readonly colorFallbackNeutro = '#5C706D';

  colorAvatarPerfil(): string {
    const u = this.usuarioSeleccionado;
    if (this.usuarioSeleccionadoTipo !== 'profesional' || !u) return this.colorFallbackNeutro;
    return u.color_identificador || this.colorFallbackPorEspecialidad[u.especialidad] || this.colorFallbackNeutro;
  }

  inicialesAvatarPerfil(): string {
    const u = this.usuarioSeleccionado;
    // Profesional: usa el campo real `iniciales` del backend (mismo que el
    // resto del proyecto), no un cálculo propio. Estudiante/administrador
    // no tienen ese campo: se calculan del nombre, como ya se hacía.
    if (this.usuarioSeleccionadoTipo === 'profesional' && u?.iniciales) return u.iniciales;
    return this.inicialesNombre(u?.nombre);
  }

  // ── Avatares de la tabla (mismo criterio que el panel de Perfil) ──
  // Profesional: iniciales reales (`iniciales`) y su color asignado, con el
  // mismo fallback por especialidad. Estudiante: color determinístico por id
  // (sin 1 request por fila). Administrador: color base del módulo.
  private readonly paletaEstudiantes = ['#5E857D', '#4F8EF7', '#8B5CF6', '#D9A441', '#D96C8A', '#7FB8A6', '#E07A5F', '#60A5FA'];

  colorAvatarUsuario(u: any, tipo: 'estudiante' | 'profesional' | 'administrador'): string {
    if (tipo === 'profesional') {
      return u?.color_identificador || this.colorFallbackPorEspecialidad[u?.especialidad] || this.colorFallbackNeutro;
    }
    if (tipo === 'estudiante') {
      const id = Number(u?.id ?? 0);
      return this.paletaEstudiantes[Math.abs(id) % this.paletaEstudiantes.length];
    }
    return '#5E857D';
  }

  inicialesAvatarUsuario(u: any, tipo: 'estudiante' | 'profesional' | 'administrador'): string {
    if (tipo === 'profesional' && u?.iniciales) return u.iniciales;
    return this.inicialesNombre(u?.nombre);
  }

  /** Marca la fila del usuario abierto en el panel de Perfil. */
  esSeleccionado(u: any, tipo: 'estudiante' | 'profesional' | 'administrador'): boolean {
    return !!this.usuarioSeleccionado && this.usuarioSeleccionadoTipo === tipo && this.usuarioSeleccionado.id === u?.id;
  }

  /** Texto "Mostrando a - b de N" del pie de estudiantes (paginación real del backend). */
  get rangoEstudiantes(): { desde: number; hasta: number } {
    const total = this.usuariosEstudiantesTotal;
    if (!total || !this.usuariosEstudiantes.length) return { desde: 0, hasta: 0 };
    const desde = (this.usuariosEstudiantesPagina - 1) * this.usuariosEstudiantesPorPagina + 1;
    return { desde, hasta: Math.min(desde + this.usuariosEstudiantes.length - 1, total) };
  }

  get etiquetaRolSeleccionado(): string {
    const u = this.usuarioSeleccionado;
    switch (this.usuarioSeleccionadoTipo) {
      case 'profesional': return 'Profesional';
      case 'administrador': return u?.rol === 'superadmin' ? 'Superadministrador' : 'Administrador';
      case 'estudiante': return 'Estudiante';
      default: return '—';
    }
  }
}
