import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PhotoCropperComponent } from '../../shared/photo-cropper/photo-cropper';
import { PhotoViewerComponent } from '../../shared/photo-viewer/photo-viewer';

/**
 * SA-1.2 — "Mi Perfil" desacoplado de ConfiguracionCentro.
 *
 * Fuente de verdad de identidad: el Usuario autenticado (GET
 * /usuarios/me), recibido por @Input `usuario` desde el shell
 * (DashboardAdminComponent). Este componente ya NO lee ni escribe
 * configCentro.nombre_admin / configCentro.foto_admin_url /
 * configCentro.correo_contacto — esos campos quedan reservados a
 * información institucional (ver ConfiguracionCentro).
 *
 * Campos editables: nombre, foto_url, telefono (más el cambio de
 * contraseña, que sigue su propio flujo por
 * PATCH /configuracion-centro/cambiar-password, sin mover de
 * namespace en esta fase). Correo y rol son de solo lectura: el correo
 * es identidad de login (no editable en SA-1.2) y el rol no es
 * autoservicio.
 *
 * Este componente no ejecuta HTTP propio: solo emite `guardarPerfil`
 * con la intención. El shell decide qué PATCH(es) disparar
 * (PATCH /usuarios/me y, si corresponde, cambiar-password) y, tras
 * éxito, actualiza la sesión de AuthService para que el topbar
 * (SA-1.1) refleje el cambio sin exigir logout/login.
 */
@Component({
  selector: 'app-admin-perfil',
  standalone: true,
  imports: [CommonModule, FormsModule, PhotoCropperComponent, PhotoViewerComponent],
  templateUrl: './admin-perfil.html'
})
export class AdminPerfilComponent implements OnChanges {

  // ── Identidad real del Usuario autenticado (fuente: GET /usuarios/me) ──
  @Input() usuario: any = {};

  // SA-1.2 v2: mientras el GET inicial no responde, no se debe permitir
  // editar/guardar un objeto vacío como si fueran datos reales del
  // usuario. El shell pone `perfilCargado = true` recién cuando
  // `usuario` contiene la respuesta real de GET /usuarios/me.
  @Input() perfilCargado = false;
  @Input() cargandoPerfil = false;

  // ── Intención emitida al shell (el shell ejecuta el/los PATCH reales) ──
  @Output() guardarPerfil = new EventEmitter<{
    nombre: string;
    telefono: string;
    foto_url?: string;
    contrasena_actual: string;
    contrasena_nueva: string;
    contrasena_conf: string;
  }>();

  // ══════════════════════════════════════
  // FORMULARIO DE PERFIL (estado exclusivo/local)
  // ══════════════════════════════════════
  configPerfil: any = { nombre: '', telefono: '', contrasena_actual: '', contrasena_nueva: '', contrasena_conf: '' };
  mostrarContrasenaActual = false;
  mostrarContrasenaaNueva  = false;
  mostrarContrasenaConf   = false;

  // Edición de Mi Perfil: campos bloqueados hasta presionar "Editar"
  adminPerfilEnEdicion = false;
  fotoCambiada = false;

  // Foto en edición local: a diferencia del monolito legacy, NO muta el
  // @Input `usuario` directamente. Se muestra con fallback a
  // usuario.foto_url mientras no se ha recortado una foto nueva, y el
  // cambio se confirma recién al guardar (PATCH /usuarios/me).
  fotoPreview: string | null = null;

  /**
   * Sincroniza el formulario local cuando el shell recarga/reasigna
   * `usuario` (tras un GET /usuarios/me exitoso).
   */
  ngOnChanges(changes: SimpleChanges): void {
    if (changes['usuario']) {
      this.configPerfil.nombre   = this.usuario?.nombre ?? '';
      this.configPerfil.telefono = this.usuario?.telefono ?? '';
    }
  }

  get fotoActual(): string | null {
    return this.fotoPreview ?? this.usuario?.foto_url ?? null;
  }

  // Rol visual: admin -> Administrador, superadmin -> Superadministrador.
  // Nunca muestra el string técnico "superadmin" tal cual.
  get rolVisual(): string {
    return this.usuario?.rol === 'superadmin' ? 'Superadministrador' : 'Administrador';
  }
  get inicialesUsuario(): string {
    const nombre = this.usuario?.nombre;
    if (!nombre) return 'AD';

    const palabras = String(nombre).trim().split(/\s+/).filter(Boolean);
    if (palabras.length === 0) return 'AD';

    const primera = palabras[0][0] ?? '';
    const segunda = palabras.length > 1
      ? (palabras[1][0] ?? '')
      : (palabras[0][1] ?? '');

    const iniciales = (primera + segunda).toUpperCase();
    return iniciales || 'AD';
  }

  habilitarEdicionPerfilAdmin(): void {
    if (!this.perfilCargado) return; // no editar sobre datos aún no confirmados como reales
    this.adminPerfilEnEdicion = true;
  }

  cancelarEdicionPerfilAdmin(): void {
    this.adminPerfilEnEdicion = false;
    this.configPerfil.nombre      = this.usuario?.nombre ?? '';
    this.configPerfil.telefono    = this.usuario?.telefono ?? '';
    this.configPerfil.contrasena_actual = '';
    this.configPerfil.contrasena_nueva  = '';
    this.configPerfil.contrasena_conf   = '';
    this.fotoPreview  = null;
    this.fotoCambiada = false;
  }

  get perfilAdminModificado(): boolean {
    return this.configPerfil.nombre   !== (this.usuario?.nombre ?? '')
        || this.configPerfil.telefono !== (this.usuario?.telefono ?? '')
        || !!this.configPerfil.contrasena_actual
        || !!this.configPerfil.contrasena_nueva
        || !!this.configPerfil.contrasena_conf
        || this.fotoCambiada;
  }

  /** Emite la intención al shell; el shell ejecuta el/los PATCH reales. */
  guardarPerfilAdmin(): void {
    if (!this.perfilCargado) return;
    if (!this.perfilAdminModificado) return;
    this.guardarPerfil.emit({
      nombre: this.configPerfil.nombre,
      telefono: this.configPerfil.telefono,
      ...(this.fotoCambiada && this.fotoPreview ? { foto_url: this.fotoPreview } : {}),
      contrasena_actual: this.configPerfil.contrasena_actual,
      contrasena_nueva: this.configPerfil.contrasena_nueva,
      contrasena_conf: this.configPerfil.contrasena_conf
    });
  }

  /**
   * Público: el shell lo invoca (vía @ViewChild) tras un guardado
   * exitoso para restablecer el estado de edición.
   */
  finalizarEdicion(limpiarPassword: boolean): void {
    this.adminPerfilEnEdicion = false;
    this.fotoCambiada = false;
    this.fotoPreview  = null;
    if (limpiarPassword) {
      this.configPerfil.contrasena_actual = '';
      this.configPerfil.contrasena_nueva  = '';
      this.configPerfil.contrasena_conf   = '';
    }
  }

  // ══════════════════════════════════════
  // FOTO (selección, recorte, visor ampliado)
  // ══════════════════════════════════════
  imagenParaRecortar: string | null = null;
  verFotoAmpliada = false;

  onFotoSeleccionada(event: any): void {
    if (!this.adminPerfilEnEdicion) return;
    const file = event.target.files?.[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = (e: any) => {
      this.imagenParaRecortar = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  /**
   * Guarda la foto recortada en estado local (`fotoPreview`) sin mutar
   * `usuario`. El cambio se confirma recién al presionar
   * "Guardar cambios", vía PATCH /usuarios/me.
   */
  onFotoRecortada(dataUrl: string): void {
    this.fotoPreview  = dataUrl;
    this.fotoCambiada = true;
    this.imagenParaRecortar = null;
  }

  // Mi Perfil es autoservicio del usuario autenticado: no hay Permission
  // administrativo asociado (documentado únicamente; sin permissionGuard).
}
