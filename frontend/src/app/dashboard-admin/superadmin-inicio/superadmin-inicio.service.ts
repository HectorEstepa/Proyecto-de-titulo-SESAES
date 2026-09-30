import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../config';
import {
  AdministradorResumen,
  EspecialidadCitas,
  EventoAuditoria,
  GestionInicio,
  ResumenInicio
} from './superadmin-inicio.models';

const API = environment.apiUrl;

/** Cantidad de eventos que se piden a auditoría para el Inicio. */
export const LIMITE_AUDITORIA_INICIO = 10;

/**
 * Acceso HTTP del Inicio de SUPERADMIN. Solo transporta: la autorización
 * real vive en el backend (fail-closed); el frontend únicamente decide
 * qué bloques intentar según los permisos efectivos.
 */
@Injectable({ providedIn: 'root' })
export class SuperadminInicioService {
  private readonly http = inject(HttpClient);

  getResumen(): Observable<ResumenInicio> {
    return this.http.get<ResumenInicio>(`${API}/admin/inicio/resumen`);
  }

  getGestion(): Observable<GestionInicio> {
    return this.http.get<GestionInicio>(`${API}/admin/inicio/gestion`);
  }

  /** Reutiliza el gráfico existente, acotado a un mes/año. */
  getCitasPorEspecialidad(mes: number, anio: number): Observable<EspecialidadCitas[]> {
    const params = new HttpParams().set('mes', mes).set('anio', anio);
    return this.http.get<EspecialidadCitas[]>(
      `${API}/admin/graficos/especialidad`,
      { params }
    );
  }

  getAdministradores(): Observable<AdministradorResumen[]> {
    return this.http.get<AdministradorResumen[]>(`${API}/usuarios/administradores`);
  }

  getAuditoriaReciente(limit = LIMITE_AUDITORIA_INICIO): Observable<EventoAuditoria[]> {
    const params = new HttpParams().set('limit', limit);
    return this.http.get<EventoAuditoria[]>(`${API}/admin/auditoria`, { params });
  }
}
