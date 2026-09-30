import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, map, tap, throwError } from 'rxjs';
import { environment } from './config';
import { normalizarRol } from './shared/auth/role.model';
import {
  isPermission,
  ROLE_DEFAULT_PERMISSIONS,
  Permission
} from './shared/auth/permission.model';
export interface LoginResponse {
  message: string;
  access_token: string;
  token_type: string;
  rol: 'estudiante' | 'profesional' | 'admin' | 'superadmin';
  id: number;
  nombre: string;
  foto_url: string | null;
  debe_cambiar_password: boolean;
}
export type PerfilAccesoAdministrativo =
  | 'administrador_general'
  | 'administrador_especialidad'
  | 'secretaria_general'
  | 'secretaria_especialidad';

export type TipoAlcanceAdministrativo =
  | 'institucional'
  | 'especialidades';

export interface ContextoAccesoAdministrativo {
  rol: 'admin' | 'superadmin';
  perfil: PerfilAccesoAdministrativo | null;
  permisos: Permission[];
  alcance: {
    tipo: TipoAlcanceAdministrativo;
    especialidades: string[];
  };
}

@Injectable({ providedIn: 'root' })
export class AuthService {

  private apiUrl = environment.apiUrl;

  // SA-10: snapshot solo en memoria.
  // null = no cargado/error => fail-closed.
  private contextoAccesoAdministrativo:
    ContextoAccesoAdministrativo | null = null;

  constructor(private http: HttpClient) {}

  login(correo: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/login`, {
      correo,
      password
    });
  }

  // Se usa sessionStorage (no localStorage) a propósito: sessionStorage es
  // aislado por pestaña, lo que permite tener sesiones distintas abiertas
  // en pestañas distintas del mismo navegador (ej. estudiante en una,
  // profesional en otra) sin que una pise los datos de la otra.
  guardarSesion(data: LoginResponse): void {
    this.contextoAccesoAdministrativo = null;

    // CLEAN SP-INT-3A: elimina identidad legacy que versiones antiguas
    // persistían globalmente entre pestañas. Las preferencias visuales
    // (p. ej. prof_tema_oscuro) permanecen intactas.
    localStorage.removeItem('prof_db_id');
    localStorage.removeItem('correo');

    sessionStorage.setItem('access_token', data.access_token);
    sessionStorage.setItem('rol', data.rol);
    sessionStorage.setItem('id', String(data.id));
    sessionStorage.setItem('usuario_id', String(data.id));
    sessionStorage.setItem('nombre', data.nombre ?? '');
    sessionStorage.setItem('foto_url', data.foto_url ?? '');
    sessionStorage.setItem('debe_cambiar_password', String(!!data.debe_cambiar_password));
  }

  getToken(): string | null {
    return sessionStorage.getItem('access_token');
  }

  getRol(): string | null {
    return sessionStorage.getItem('rol');
  }

  /**
   * Nombre real del Usuario autenticado (guardado por guardarSesion()).
   * Fail-safe: sin sesión o valor vacío -> null. Nunca usa un fallback
   * fijo ni una fuente distinta a la sesión (p. ej. ConfiguracionCentro).
   */
  getNombre(): string | null {
    const nombre = sessionStorage.getItem('nombre');
    return nombre && nombre.trim() ? nombre : null;
  }

  /**
   * URL de la foto de perfil del Usuario autenticado (guardado por
   * guardarSesion()). Fail-safe: sin sesión o valor vacío -> null.
   */
  getFotoUrl(): string | null {
    const fotoUrl = sessionStorage.getItem('foto_url');
    return fotoUrl && fotoUrl.trim() ? fotoUrl : null;
  }

  /**
   * Usuario.id de la sesión activa.
   *
   * Nunca usa un fallback fijo ni localStorage. Si la sesión no contiene
   * una identidad numérica positiva, falla cerrado devolviendo null.
   */
  getUsuarioId(): number | null {
    const raw = sessionStorage.getItem('usuario_id');
    if (!raw) return null;

    const id = Number(raw);
    return Number.isInteger(id) && id > 0 ? id : null;
  }

  /**
   * SA-1.2: actualiza nombre/foto de la sesión activa tras un guardado
   * exitoso de Mi Perfil (PATCH /usuarios/me), sin exigir logout/login.
   *
   * Función acotada a propósito: solo toca `nombre` y `foto_url` en
   * sessionStorage (nunca localStorage), y solo los campos presentes en
   * `datos` — no reemplaza ni borra el resto de la sesión (token, rol,
   * id). correo y rol no se editan desde Mi Perfil en esta fase, así
   * que esta función no los toca.
   */
  actualizarIdentidadSesion(datos: { nombre?: string; foto_url?: string | null }): void {
    if (datos.nombre !== undefined) {
      sessionStorage.setItem('nombre', datos.nombre ?? '');
    }
    if (datos.foto_url !== undefined) {
      sessionStorage.setItem('foto_url', datos.foto_url ?? '');
    }
  }

  /**
   * SA-6.2 - Sincroniza el rol administrativo de la sesion activa
   * despues de que el backend confirma un cambio de rol sobre la
   * propia cuenta.
   *
   * No modifica token, id, nombre ni foto. El backend sigue siendo
   * la autoridad real de permisos; esto mantiene coherente la UX
   * de la sesion ya abierta.
   */
  actualizarRolSesion(rol: 'admin' | 'superadmin'): void {
    this.contextoAccesoAdministrativo = null;
    sessionStorage.setItem('rol', rol);
  }

  logout(): void {
    this.contextoAccesoAdministrativo = null;
    sessionStorage.clear();

    // Limpieza de claves legacy sin borrar preferencias visuales locales.
    localStorage.removeItem('prof_db_id');
    localStorage.removeItem('correo');
  }

  isLoggedIn(): boolean {
    const token = this.getToken();
    if (!token || !this.getRol()) return false;
    return !this.tokenExpirado(token);
  }

  /**
   * Resuelve si el usuario de la sesión activa tiene `permission`, según
   * los DEFAULT permissions de su rol (ver permission.model.ts).
   *
   * IMPORTANTE: esto es solo UX (mostrar/ocultar acciones). El backend
   * sigue siendo la única autoridad real de seguridad — cualquier
   * endpoint protegido valida el permiso de nuevo server-side.
   *
   * Fail-closed: sin sesión, rol desconocido, o permiso no listado para
   * ese rol → false.
   */
  cargarAccesoAdministrativo(): Observable<ContextoAccesoAdministrativo> {
    // Una recarga invalida primero cualquier snapshot anterior.
    this.contextoAccesoAdministrativo = null;

    return this.http.get<unknown>(
      `${this.apiUrl}/usuarios/me/acceso-administrativo`
    ).pipe(
      map(raw => this.normalizarContextoAccesoAdministrativo(raw)),
      tap(contexto => {
        this.contextoAccesoAdministrativo = contexto;

        // El backend resolvio el rol ACTUAL desde BD.
        sessionStorage.setItem('rol', contexto.rol);
      }),
      catchError(error => {
        this.contextoAccesoAdministrativo = null;
        return throwError(() => error);
      })
    );
  }

  getContextoAccesoAdministrativo(): ContextoAccesoAdministrativo | null {
    const contexto = this.contextoAccesoAdministrativo;

    if (!contexto) return null;

    return {
      rol: contexto.rol,
      perfil: contexto.perfil,
      permisos: [...contexto.permisos],
      alcance: {
        tipo: contexto.alcance.tipo,
        especialidades: [...contexto.alcance.especialidades]
      }
    };
  }

  hasPermission(permission: Permission): boolean {
    const rol = normalizarRol(this.getRol());

    if (!rol) return false;

    if (rol === 'admin' || rol === 'superadmin') {
      const contexto = this.contextoAccesoAdministrativo;

      if (
        !contexto ||
        contexto.rol !== rol
      ) {
        return false;
      }

      return contexto.permisos.includes(permission);
    }

    return ROLE_DEFAULT_PERMISSIONS[rol].includes(permission);
  }

  private normalizarContextoAccesoAdministrativo(
    raw: unknown
  ): ContextoAccesoAdministrativo {
    if (
      !raw ||
      typeof raw !== 'object' ||
      Array.isArray(raw)
    ) {
      throw new Error('Contexto administrativo invalido.');
    }

    const data = raw as Record<string, unknown>;

    if (
      data['rol'] !== 'admin' &&
      data['rol'] !== 'superadmin'
    ) {
      throw new Error('Rol administrativo invalido.');
    }

    const perfiles = [
      'administrador_general',
      'administrador_especialidad',
      'secretaria_general',
      'secretaria_especialidad'
    ] as const;

    const perfil = data['perfil'];

    if (
      perfil !== null &&
      (
        typeof perfil !== 'string' ||
        !(perfiles as readonly string[]).includes(perfil)
      )
    ) {
      throw new Error('Perfil administrativo invalido.');
    }

    if (
      data['rol'] === 'admin' &&
      perfil === null
    ) {
      throw new Error('ADMIN sin perfil administrativo.');
    }

    if (
      data['rol'] === 'superadmin' &&
      perfil !== null
    ) {
      throw new Error(
        'SUPERADMIN no debe declarar perfil ADMIN.'
      );
    }

    const permisos = data['permisos'];

    if (
      !Array.isArray(permisos) ||
      !permisos.every(isPermission) ||
      new Set(permisos).size !== permisos.length
    ) {
      throw new Error(
        'Lista de permisos administrativos invalida.'
      );
    }

    const alcance = data['alcance'];

    if (
      !alcance ||
      typeof alcance !== 'object' ||
      Array.isArray(alcance)
    ) {
      throw new Error('Alcance administrativo invalido.');
    }

    const alcanceData =
      alcance as Record<string, unknown>;

    const tipo = alcanceData['tipo'];

    if (
      tipo !== 'institucional' &&
      tipo !== 'especialidades'
    ) {
      throw new Error(
        'Tipo de alcance administrativo invalido.'
      );
    }

    const especialidades =
      alcanceData['especialidades'];

    if (
      !Array.isArray(especialidades) ||
      !especialidades.every(
        value =>
          typeof value === 'string' &&
          value.trim().length > 0
      )
    ) {
      throw new Error(
        'Especialidades administrativas invalidas.'
      );
    }

    if (
      tipo === 'institucional' &&
      especialidades.length !== 0
    ) {
      throw new Error(
        'Alcance institucional no debe declarar especialidades.'
      );
    }

    if (
      tipo === 'especialidades' &&
      especialidades.length === 0
    ) {
      throw new Error(
        'Alcance por especialidades requiere al menos una.'
      );
    }

    return {
      rol: data['rol'],
      perfil:
        perfil as PerfilAccesoAdministrativo | null,
      permisos: [...permisos] as Permission[],
      alcance: {
        tipo,
        especialidades:
          [...especialidades] as string[]
      }
    };
  }

  /**
   * Decodifica (sin verificar firma, eso lo hace el backend) el payload
   * del JWT para leer su 'exp' y así poder cerrar sesión en el cliente
   * apenas expire, sin esperar a que un request falle con 401.
   */
  private tokenExpirado(token: string): boolean {
    try {
      const payloadBase64 = token.split('.')[1];
      const payload = JSON.parse(atob(payloadBase64.replace(/-/g, '+').replace(/_/g, '/')));
      if (!payload.exp) return false;
      return Date.now() >= payload.exp * 1000;
    } catch {
      return true; // token con formato inválido -> tratarlo como expirado
    }
  }
}