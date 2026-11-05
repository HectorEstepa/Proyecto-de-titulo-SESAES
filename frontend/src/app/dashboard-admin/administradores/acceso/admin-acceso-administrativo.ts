import { ChangeDetectorRef, Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';

import { environment } from '../../../config';
import { ToastService } from '../../../shared/toast/toast.service';
import { isPermission, Permission } from '../../../shared/auth/permission.model';

const API = environment.apiUrl;

type PerfilAdministrativo =
  | 'administrador_general'
  | 'administrador_especialidad'
  | 'secretaria_general'
  | 'secretaria_especialidad';

type TipoAlcanceAdministrativo = 'institucional' | 'especialidades';

interface AdministradorAccesoTarget {
  id: number;
  nombre: string | null;
  correo: string;
  rol: 'admin' | 'superadmin';
}

interface PerfilAccesoCatalogo {
  perfil: PerfilAdministrativo;
  tipo_alcance: TipoAlcanceAdministrativo;
  permisos_permitidos: Permission[];
}

interface CatalogoAccesoAdministrativo {
  perfiles: PerfilAccesoCatalogo[];
}

interface AccesoAdministrativoGestion {
  usuario_id: number;
  configurado: boolean;
  perfil: PerfilAdministrativo | null;
  permisos: Permission[];
  alcance: {
    tipo: TipoAlcanceAdministrativo | null;
    especialidades: string[];
  };
}

interface AccesoAdministrativoForm {
  perfil: PerfilAdministrativo | '';
  permisos: Permission[];
  especialidades: string[];
  nuevaEspecialidad: string;
}

@Component({
  selector: 'app-admin-acceso-administrativo',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-acceso-administrativo.html',
  styleUrl: './admin-acceso-administrativo.css'
})
export class AdminAccesoAdministrativoComponent implements OnInit {
  @Input({ required: true }) admin!: AdministradorAccesoTarget;
  @Output() cerrar = new EventEmitter<void>();

  cargando = true;
  guardando = false;
  errorCarga: string | null = null;
  errorGuardado: string | null = null;
  configurado = false;

  catalogo: CatalogoAccesoAdministrativo | null = null;
  form: AccesoAdministrativoForm = this.formularioVacio();

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    if (!this.admin || this.admin.rol !== 'admin') {
      this.cargando = false;
      this.errorCarga = 'Solo las cuentas con rol Administrador pueden tener permisos y alcance delegados.';
      return;
    }

    this.cargarCatalogoYAcceso();
  }

  private formularioVacio(): AccesoAdministrativoForm {
    return {
      perfil: '',
      permisos: [],
      especialidades: [],
      nuevaEspecialidad: ''
    };
  }

  private cargarCatalogoYAcceso(): void {
    this.cargando = true;
    this.errorCarga = null;
    this.errorGuardado = null;

    this.http.get<unknown>(
      `${API}/usuarios/administradores/catalogo-acceso`
    ).subscribe({
      next: (raw) => {
        try {
          this.catalogo = this.normalizarCatalogo(raw);
        } catch {
          this.cargando = false;
          this.errorCarga = 'El backend devolvió un catálogo de permisos administrativos inválido.';
          this.cdr.detectChanges();
          return;
        }

        this.cargarAccesoActual();
      },
      error: (err: HttpErrorResponse) => {
        this.cargando = false;
        this.errorCarga = this.mensajeDeError(err, {
          403: 'No tienes permisos para consultar el catálogo de acceso administrativo.'
        });
        this.cdr.detectChanges();
      }
    });
  }

  private cargarAccesoActual(): void {
    this.http.get<unknown>(
      `${API}/usuarios/administradores/${this.admin.id}/acceso-administrativo`
    ).subscribe({
      next: (raw) => {
        try {
          const acceso = this.normalizarAcceso(raw);
          this.aplicarAcceso(acceso);
          this.cargando = false;
        } catch {
          this.cargando = false;
          this.errorCarga = 'El backend devolvió una configuración de acceso inválida.';
        }
        this.cdr.detectChanges();
      },
      error: (err: HttpErrorResponse) => {
        this.cargando = false;
        this.errorCarga = this.mensajeDeError(err, {
          403: 'No tienes permisos para consultar el acceso de esta cuenta.',
          409: 'Esta cuenta ya no tiene rol Administrador.'
        });
        this.cdr.detectChanges();
      }
    });
  }

  get perfilesDisponibles(): PerfilAccesoCatalogo[] {
    return this.catalogo?.perfiles ?? [];
  }

  get perfilSeleccionado(): PerfilAccesoCatalogo | null {
    if (!this.form.perfil || !this.catalogo) return null;
    return this.catalogo.perfiles.find(
      item => item.perfil === this.form.perfil
    ) ?? null;
  }

  get permisosDisponibles(): Permission[] {
    return this.perfilSeleccionado?.permisos_permitidos ?? [];
  }

  get requiereEspecialidades(): boolean {
    return this.perfilSeleccionado?.tipo_alcance === 'especialidades';
  }

  get formularioValido(): boolean {
    if (!this.perfilSeleccionado) return false;
    if (this.requiereEspecialidades && this.form.especialidades.length === 0) return false;
    return true;
  }

  cambiarPerfil(): void {
    this.errorGuardado = null;
    const perfil = this.perfilSeleccionado;

    if (!perfil) {
      this.form.permisos = [];
      this.form.especialidades = [];
      this.form.nuevaEspecialidad = '';
      return;
    }

    const permitidos = new Set(perfil.permisos_permitidos);
    this.form.permisos = this.form.permisos.filter(
      permiso => permitidos.has(permiso)
    );

    if (perfil.tipo_alcance === 'institucional') {
      this.form.especialidades = [];
      this.form.nuevaEspecialidad = '';
    }
  }

  permisoSeleccionado(permiso: Permission): boolean {
    return this.form.permisos.includes(permiso);
  }

  cambiarPermiso(permiso: Permission, seleccionado: boolean): void {
    if (!this.permisosDisponibles.includes(permiso)) return;
    this.errorGuardado = null;

    if (seleccionado) {
      if (!this.form.permisos.includes(permiso)) {
        this.form.permisos = [...this.form.permisos, permiso];
      }
      return;
    }

    this.form.permisos = this.form.permisos.filter(
      actual => actual !== permiso
    );
  }

  agregarEspecialidad(): void {
    if (!this.requiereEspecialidades) return;

    const limpia = this.form.nuevaEspecialidad.trim().replace(/\s+/g, ' ');
    if (!limpia) return;

    const clave = limpia.toLocaleLowerCase();
    const existe = this.form.especialidades.some(
      item => item.toLocaleLowerCase() === clave
    );

    if (!existe) {
      this.form.especialidades = [...this.form.especialidades, limpia];
    }

    this.form.nuevaEspecialidad = '';
    this.errorGuardado = null;
  }

  quitarEspecialidad(especialidad: string): void {
    this.form.especialidades = this.form.especialidades.filter(
      item => item !== especialidad
    );
    this.errorGuardado = null;
  }

  guardar(): void {
    if (!this.formularioValido || this.guardando || !this.perfilSeleccionado) return;

    this.guardando = true;
    this.errorGuardado = null;

    const perfil = this.perfilSeleccionado;
    const payload = {
      perfil: perfil.perfil,
      permisos: [...this.form.permisos],
      alcance: {
        tipo: perfil.tipo_alcance,
        especialidades: perfil.tipo_alcance === 'especialidades'
          ? [...this.form.especialidades]
          : []
      }
    };

    this.http.put<unknown>(
      `${API}/usuarios/administradores/${this.admin.id}/acceso-administrativo`,
      payload
    ).subscribe({
      next: (raw) => {
        try {
          const acceso = this.normalizarAcceso(raw);
          this.aplicarAcceso(acceso);
          this.guardando = false;
          this.toast.success('Permisos y alcance actualizados correctamente.');
          this.cerrar.emit();
        } catch {
          this.guardando = false;
          this.errorGuardado = 'El backend devolvió una configuración de acceso inválida.';
          this.cdr.detectChanges();
        }
      },
      error: (err: HttpErrorResponse) => {
        this.guardando = false;
        this.errorGuardado = this.mensajeDeError(err, {
          403: 'No tienes permisos para modificar el acceso de esta cuenta.',
          409: 'Esta cuenta ya no tiene rol Administrador.',
          422: 'La combinación de perfil, permisos y alcance no es válida.'
        });
        this.cdr.detectChanges();
      }
    });
  }

  solicitarCierre(): void {
    if (!this.guardando) this.cerrar.emit();
  }

  perfilVisual(perfil: PerfilAdministrativo): string {
    const etiquetas: Record<PerfilAdministrativo, string> = {
      administrador_general: 'Administrador general',
      administrador_especialidad: 'Administrador de especialidad',
      secretaria_general: 'Secretaría general',
      secretaria_especialidad: 'Secretaría de especialidad'
    };
    return etiquetas[perfil];
  }

  permisoVisual(permiso: Permission): string {
    const etiquetas: Partial<Record<Permission, string>> = {
      'usuarios.ver': 'Ver usuarios y estudiantes',
      'usuarios.gestionar': 'Gestionar usuarios',
      'profesionales.ver': 'Ver profesionales',
      'profesionales.gestionar': 'Gestionar profesionales',
      'agenda.ver': 'Ver agenda',
      'agenda.gestionar': 'Gestionar agenda',
      'reportes.ver': 'Ver reportes'
    };
    return etiquetas[permiso] ?? permiso;
  }

  private aplicarAcceso(acceso: AccesoAdministrativoGestion): void {
    this.configurado = acceso.configurado;
    this.form = {
      perfil: acceso.perfil ?? '',
      permisos: [...acceso.permisos],
      especialidades: [...acceso.alcance.especialidades],
      nuevaEspecialidad: ''
    };
    this.cambiarPerfil();
  }

  private normalizarCatalogo(raw: unknown): CatalogoAccesoAdministrativo {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      throw new Error('Catálogo inválido.');
    }

    const perfilesRaw = (raw as Record<string, unknown>)['perfiles'];
    if (!Array.isArray(perfilesRaw)) throw new Error('Catálogo inválido.');

    const perfiles: PerfilAccesoCatalogo[] = perfilesRaw.map(
      (item): PerfilAccesoCatalogo => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) {
        throw new Error('Perfil inválido.');
      }

      const data = item as Record<string, unknown>;
      const perfil = data['perfil'];
      const tipo = data['tipo_alcance'];
      const permisos = data['permisos_permitidos'];

      if (!this.esPerfil(perfil)) throw new Error('Perfil inválido.');
      if (tipo !== 'institucional' && tipo !== 'especialidades') {
        throw new Error('Alcance inválido.');
      }
      if (
        !Array.isArray(permisos) ||
        !permisos.every(isPermission) ||
        new Set(permisos).size !== permisos.length
      ) {
        throw new Error('Permisos inválidos.');
      }

      return {
        perfil,
        tipo_alcance: tipo,
        permisos_permitidos: [...permisos] as Permission[]
      };
      }
    );

    return { perfiles };
  }

  private normalizarAcceso(raw: unknown): AccesoAdministrativoGestion {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      throw new Error('Acceso inválido.');
    }

    const data = raw as Record<string, unknown>;
    const configurado = data['configurado'];
    const perfil = data['perfil'];
    const permisos = data['permisos'];
    const alcance = data['alcance'];

    if (data['usuario_id'] !== this.admin.id || typeof configurado !== 'boolean') {
      throw new Error('Acceso inválido.');
    }
    if (perfil !== null && !this.esPerfil(perfil)) {
      throw new Error('Perfil inválido.');
    }
    if (
      !Array.isArray(permisos) ||
      !permisos.every(isPermission) ||
      new Set(permisos).size !== permisos.length
    ) {
      throw new Error('Permisos inválidos.');
    }
    if (!alcance || typeof alcance !== 'object' || Array.isArray(alcance)) {
      throw new Error('Alcance inválido.');
    }

    const alcanceData = alcance as Record<string, unknown>;
    const tipo = alcanceData['tipo'];
    const especialidades = alcanceData['especialidades'];

    if (tipo !== null && tipo !== 'institucional' && tipo !== 'especialidades') {
      throw new Error('Alcance inválido.');
    }
    if (
      !Array.isArray(especialidades) ||
      !especialidades.every(
        value => typeof value === 'string' && value.trim().length > 0
      )
    ) {
      throw new Error('Especialidades inválidas.');
    }

    return {
      usuario_id: this.admin.id,
      configurado,
      perfil,
      permisos: [...permisos] as Permission[],
      alcance: {
        tipo,
        especialidades: [...especialidades] as string[]
      }
    };
  }

  private esPerfil(value: unknown): value is PerfilAdministrativo {
    return value === 'administrador_general' ||
      value === 'administrador_especialidad' ||
      value === 'secretaria_general' ||
      value === 'secretaria_especialidad';
  }

  private mensajeDeError(
    err: HttpErrorResponse,
    fallbackPorStatus: Record<number, string>
  ): string {
    const detalle = err?.error?.detail;
    if (typeof detalle === 'string' && detalle.trim()) return detalle;
    return fallbackPorStatus[err.status] ?? 'Ocurrió un error inesperado.';
  }
}
