import { Component, OnInit, ChangeDetectorRef, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { environment } from '../../config';
import { ToastService } from '../../shared/toast/toast.service';
import { AuthService } from '../../auth.service';
import { AdminAccesoAdministrativoComponent } from './acceso/admin-acceso-administrativo';

const API = environment.apiUrl;

type RolAdministrativo = 'admin' | 'superadmin';
type TipoConfirmacion = 'desactivar' | 'promover' | 'degradar';

interface AdministradorOut {
  id: number;
  nombre: string | null;
  correo: string;
  telefono: string | null;
  foto_url: string | null;
  rol: RolAdministrativo;
  activo: boolean;
}

interface NuevoAdministradorForm {
  correo: string;
  password: string;
  nombre: string;
  telefono: string;
  rol: RolAdministrativo;
}

/**
 * SA-4 — UI Administradores.
 *
 * Componente hijo dueño de su propio HTTP/loading (mismo patrón que
 * AdminCitasComponent, Fase 3.4B): Administradores no es dato
 * compartido con ninguna otra sección del shell, así que no hay
 * razón para que el shell (DashboardAdminComponent) posea este
 * estado ni dispare estos requests.
 *
 * Contrato backend real (SA-3, backend/app/routers/usuarios.py):
 *   GET   /usuarios/administradores
 *   POST  /usuarios/administradores
 *   PATCH /usuarios/administradores/{id}/estado   { activo: boolean }
 *   PATCH /usuarios/administradores/{id}/rol      { rol: 'admin'|'superadmin' }
 * No existe DELETE — no se implementa ninguna acción de baja acá.
 *
 * Reglas de diseño no negociables:
 * - El backend es la única fuente de verdad. Tras cualquier mutación
 *   exitosa se RECARGA la lista completa (cargarAdministradores()) en
 *   vez de mutar el array local de forma optimista — mismo patrón
 *   dominante que el resto de dashboard-admin.ts.
 * - Ante un error (403/409/422), el estado local NUNCA se altera de
 *   forma optimista: como no mutamos el array antes de la respuesta,
 *   un 409 simplemente no cambia nada localmente.
 * - Este componente NUNCA decide en el frontend cuál es "el último
 *   SUPERADMIN": esa regla vive exclusivamente en el backend
 *   (_contar_superadmin_activos en usuarios.py). Aquí solo se muestra
 *   el mensaje que el backend devuelve cuando responde 409.
 * - La contraseña del formulario de creación se limpia siempre que el
 *   modal se cierra (éxito o cancelación) y nunca se persiste en
 *   localStorage/sessionStorage: vive únicamente en memoria del
 *   componente mientras el modal está abierto.
 */
@Component({
  selector: 'app-admin-administradores',
  standalone: true,
  imports: [CommonModule, FormsModule, AdminAccesoAdministrativoComponent],
  templateUrl: './admin-administradores.html'
})
export class AdminAdministradoresComponent implements OnInit {

  @Output() sesionAdministrativaActualizada = new EventEmitter<void>();

  administradores: AdministradorOut[] = [];
  cargando = false;

  /** Error de listado (ej. 403 si el permiso se revoca a mitad de sesión). */
  errorListado: string | null = null;

  // ── Filtros (solo sobre lo ya cargado; no hay filtrado server-side) ──
  filtroTexto = '';
  filtroRol: '' | RolAdministrativo = '';
  filtroEstado: '' | 'activo' | 'inactivo' = '';

  // ── Modal de creación ──
  modalCrearAbierto = false;
  guardando = false;
  mensajeErrorModal: string | null = null;
  mostrarPassword = false;

  nuevoAdmin: NuevoAdministradorForm = this.formularioVacio();

  // ── Acción en curso por fila (evita doble click mientras responde el PATCH) ──
  procesandoId: number | null = null;

  // ── Modal de confirmación (desactivar / promover / degradar) ──
  // Requerido por contrato SA-4: ninguna de estas 3 acciones dispara el
  // PATCH directamente desde el template; primero abren este modal, y el
  // PATCH solo ocurre si el usuario confirma explícitamente.
  modalConfirmAbierto = false;
  tipoConfirmacion: TipoConfirmacion | null = null;
  adminEnConfirmacion: AdministradorOut | null = null;

  // SA-12B: target ADMIN cuyo perfil/permisos/alcance se está editando.
  adminAccesoSeleccionado: AdministradorOut | null = null;

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
    private toast: ToastService,
    private auth: AuthService
  ) {}

  ngOnInit(): void {
    this.cargarAdministradores();
  }

  private formularioVacio(): NuevoAdministradorForm {
    return { correo: '', password: '', nombre: '', telefono: '', rol: 'admin' };
  }

  // ══════════════════════════════════════
  // LISTADO
  // ══════════════════════════════════════

  cargarAdministradores(): void {
    this.cargando = true;
    this.errorListado = null;
    this.http.get<AdministradorOut[]>(`${API}/usuarios/administradores`).subscribe({
      next: (data) => {
        this.administradores = data ?? [];
        this.cargando = false;
        this.cdr.detectChanges();
      },
      error: (err: HttpErrorResponse) => {
        this.cargando = false;
        if (err.status === 403) {
          this.errorListado = 'No tienes permisos para ver esta sección.';
        } else {
          this.errorListado = 'No se pudo cargar el listado de administradores.';
        }
        this.cdr.detectChanges();
      }
    });
  }

  get administradoresFiltrados(): AdministradorOut[] {
    const texto = this.filtroTexto.trim().toLowerCase();
    return this.administradores.filter(a => {
      if (this.filtroRol && a.rol !== this.filtroRol) return false;
      if (this.filtroEstado === 'activo' && !a.activo) return false;
      if (this.filtroEstado === 'inactivo' && a.activo) return false;
      if (texto) {
        const enCorreo = a.correo?.toLowerCase().includes(texto);
        const enNombre = a.nombre?.toLowerCase().includes(texto);
        if (!enCorreo && !enNombre) return false;
      }
      return true;
    });
  }

  limpiarFiltros(): void {
    this.filtroTexto = '';
    this.filtroRol = '';
    this.filtroEstado = '';
  }

  // ── Resumen (sobre el total real, no sobre lo filtrado) ──
  get totalAdministradores(): number {
    return this.administradores.length;
  }
  get totalActivos(): number {
    return this.administradores.filter(a => a.activo).length;
  }
  get totalSuperadmins(): number {
    return this.administradores.filter(a => a.rol === 'superadmin').length;
  }
  get totalInactivos(): number {
    return this.administradores.filter(a => !a.activo).length;
  }

  // ══════════════════════════════════════
  // CREAR ADMINISTRADOR
  // ══════════════════════════════════════

  abrirModalCrear(): void {
    this.nuevoAdmin = this.formularioVacio();
    this.mensajeErrorModal = null;
    this.mostrarPassword = false;
    this.modalCrearAbierto = true;
  }

  cerrarModalCrear(): void {
    this.modalCrearAbierto = false;
    this.mensajeErrorModal = null;
    // La contraseña nunca sobrevive al cierre del modal, ni por éxito
    // ni por cancelación.
    this.nuevoAdmin = this.formularioVacio();
  }

  get correoCreacionValido(): boolean {
    return /^[^@\s]+@utem\.cl$/i.test(this.nuevoAdmin.correo.trim());
  }

  get creacionValida(): boolean {
    return this.correoCreacionValido && !!this.nuevoAdmin.password && !!this.nuevoAdmin.rol;
  }

  crearAdministrador(): void {
    if (!this.creacionValida || this.guardando) return;

    this.guardando = true;
    this.mensajeErrorModal = null;

    const payload: any = {
      correo: this.nuevoAdmin.correo.trim().toLowerCase(),
      password: this.nuevoAdmin.password,
      rol: this.nuevoAdmin.rol
    };
    if (this.nuevoAdmin.nombre.trim())   payload.nombre = this.nuevoAdmin.nombre.trim();
    if (this.nuevoAdmin.telefono.trim()) payload.telefono = this.nuevoAdmin.telefono.trim();

    this.http.post<AdministradorOut>(`${API}/usuarios/administradores`, payload).subscribe({
      next: () => {
        this.guardando = false;
        // Recarga completa (no merge local optimista) — el backend es la
        // única fuente de verdad del listado.
        this.cargarAdministradores();
        this.toast.success('Cuenta administrativa creada correctamente.');
        this.cerrarModalCrear();
      },
      error: (err: HttpErrorResponse) => {
        this.guardando = false;
        this.mensajeErrorModal = this.mensajeDeError(err, {
          409: 'Ya existe un usuario con ese correo.',
          422: 'La contraseña no cumple la política de seguridad requerida.',
          403: 'No tienes permisos para crear cuentas administrativas.'
        });
        // La contraseña se limpia siempre, incluso ante error: nunca se
        // reintenta reenviándola desde un estado "recordado".
        this.nuevoAdmin.password = '';
        this.cdr.detectChanges();
      }
    });
  }

  // ══════════════════════════════════════
  // PERMISOS Y ALCANCE (SA-12B)
  // ══════════════════════════════════════

  abrirAccesoAdministrativo(admin: AdministradorOut): void {
    if (admin.rol !== 'admin' || this.procesandoId !== null) return;
    this.adminAccesoSeleccionado = admin;
  }

  cerrarAccesoAdministrativo(): void {
    this.adminAccesoSeleccionado = null;
  }

  // ══════════════════════════════════════
  // CONFIRMACIÓN (desactivar / promover / degradar)
  // ══════════════════════════════════════
  //
  // Reactivar una cuenta sigue siendo directo (cambiarEstado(a, true) se
  // llama tal cual desde el template). Las 3 acciones sensibles pasan
  // primero por este modal; cancelar no dispara ningún request.

  pedirConfirmacionDesactivar(admin: AdministradorOut): void {
    if (this.procesandoId !== null) return;
    this.tipoConfirmacion = 'desactivar';
    this.adminEnConfirmacion = admin;
    this.modalConfirmAbierto = true;
  }

  pedirConfirmacionRol(admin: AdministradorOut, nuevoRol: RolAdministrativo): void {
    if (this.procesandoId !== null) return;
    if (nuevoRol === admin.rol) return;
    this.tipoConfirmacion = nuevoRol === 'superadmin' ? 'promover' : 'degradar';
    this.adminEnConfirmacion = admin;
    this.modalConfirmAbierto = true;
  }

  cancelarConfirmacion(): void {
    this.modalConfirmAbierto = false;
    this.tipoConfirmacion = null;
    this.adminEnConfirmacion = null;
  }

  confirmarAccionPendiente(): void {
    if (!this.adminEnConfirmacion || !this.tipoConfirmacion) return;
    const admin = this.adminEnConfirmacion;
    const tipo = this.tipoConfirmacion;

    // El modal se cierra antes de disparar el PATCH; procesandoId sigue
    // siendo la única guarda contra doble-click mientras responde.
    this.modalConfirmAbierto = false;
    this.tipoConfirmacion = null;
    this.adminEnConfirmacion = null;

    if (tipo === 'desactivar') {
      this.cambiarEstado(admin, false);
    } else if (tipo === 'promover') {
      this.cambiarRol(admin, 'superadmin');
    } else {
      this.cambiarRol(admin, 'admin');
    }
  }

  get tituloConfirmacion(): string {
    switch (this.tipoConfirmacion) {
      case 'desactivar': return 'Desactivar cuenta';
      case 'promover': return 'Promover a Superadministrador';
      case 'degradar': return 'Degradar a Administrador';
      default: return '';
    }
  }

  get mensajeConfirmacion(): string {
    switch (this.tipoConfirmacion) {
      case 'desactivar':
        return 'Esta cuenta dejará de poder acceder al sistema.';
      case 'promover':
        return 'Esta cuenta obtendrá privilegios de gobernanza administrativa. Su configuración ADMIN de permisos y alcance se eliminará al promoverla.';
      case 'degradar':
        return 'Esta cuenta volverá al rol Administrador sin permisos ni alcance configurados. Deberás asignarlos explícitamente después de degradarla.';
      default:
        return '';
    }
  }

  // ══════════════════════════════════════
  // CAMBIAR ESTADO (activar / desactivar)
  // ══════════════════════════════════════

  cambiarEstado(admin: AdministradorOut, nuevoActivo: boolean): void {
    if (this.procesandoId !== null) return;
    this.procesandoId = admin.id;

    this.http.patch<AdministradorOut>(
      `${API}/usuarios/administradores/${admin.id}/estado`,
      { activo: nuevoActivo }
    ).subscribe({
      next: () => {
        this.procesandoId = null;
        this.cargarAdministradores();
        this.toast.success(nuevoActivo ? 'Cuenta activada correctamente.' : 'Cuenta desactivada correctamente.');
      },
      error: (err: HttpErrorResponse) => {
        this.procesandoId = null;
        const mensaje = this.mensajeDeError(err, {
          409: 'No es posible desactivar al último SUPERADMIN activo.',
          422: 'Datos inválidos.',
          403: 'No tienes permisos para cambiar el estado de esta cuenta.'
        });
        this.toast.error(mensaje);
        this.cdr.detectChanges();
      }
    });
  }

  // ══════════════════════════════════════
  // CAMBIAR ROL (admin ↔ superadmin)
  // ══════════════════════════════════════

  cambiarRol(admin: AdministradorOut, nuevoRol: RolAdministrativo): void {
    if (this.procesandoId !== null) return;
    if (nuevoRol === admin.rol) return;
    this.procesandoId = admin.id;

    this.http.patch<AdministradorOut>(
      `${API}/usuarios/administradores/${admin.id}/rol`,
      { rol: nuevoRol }
    ).subscribe({
    next: (actualizado) => {
      this.procesandoId = null;

      const esSesionActual = admin.id === this.auth.getUsuarioId();

      if (esSesionActual) {
        this.auth.actualizarRolSesion(actualizado.rol);
        this.sesionAdministrativaActualizada.emit();
      }

      // Si la propia cuenta perdio roles.gestionar, evitamos un GET
      // que el backend rechazaria correctamente con 403.
      if (this.auth.hasPermission('roles.gestionar')) {
        this.cargarAdministradores();
      }

      this.toast.success('Rol actualizado correctamente.');
    },
      error: (err: HttpErrorResponse) => {
        this.procesandoId = null;
        const mensaje = this.mensajeDeError(err, {
          409: 'No es posible degradar al último SUPERADMIN activo.',
          422: 'Datos inválidos.',
          403: 'No tienes permisos para cambiar el rol de esta cuenta.'
        });
        this.toast.error(mensaje);
        this.cdr.detectChanges();
      }
    });
  }

  // ══════════════════════════════════════
  // HELPERS
  // ══════════════════════════════════════

  /**
   * Prioriza siempre el detail real que envía el backend (fuente de
   * verdad); el mapa de fallback solo cubre el caso en que el backend
   * no traiga detail utilizable.
   */
  private mensajeDeError(err: HttpErrorResponse, fallbackPorStatus: Record<number, string>): string {
    const detalle = err?.error?.detail;
    if (typeof detalle === 'string' && detalle.trim()) return detalle;
    return fallbackPorStatus[err.status] ?? 'Ocurrió un error inesperado.';
  }

  rolVisual(rol: RolAdministrativo): string {
    return rol === 'superadmin' ? 'Superadministrador' : 'Administrador';
  }

  iniciales(admin: AdministradorOut): string {
    const nombre = admin.nombre;
    if (!nombre) return admin.correo.slice(0, 2).toUpperCase();
    const palabras = nombre.trim().split(/\s+/).filter(Boolean);
    if (palabras.length === 0) return admin.correo.slice(0, 2).toUpperCase();
    const primera = palabras[0][0] ?? '';
    const segunda = palabras.length > 1 ? (palabras[1][0] ?? '') : (palabras[0][1] ?? '');
    return (primera + segunda).toUpperCase() || 'AD';
  }
}
