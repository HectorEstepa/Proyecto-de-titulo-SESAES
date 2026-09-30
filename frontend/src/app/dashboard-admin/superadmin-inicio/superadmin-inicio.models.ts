/**
 * Inicio institucional de SUPERADMIN — contratos de datos.
 *
 * Reflejan EXACTAMENTE las respuestas del backend:
 *   GET /admin/inicio/resumen          (backend/app/routers/admin_inicio.py)
 *   GET /admin/inicio/gestion          (idem)
 *   GET /admin/graficos/especialidad   (reutilizado)
 *   GET /usuarios/administradores      (reutilizado)
 *   GET /admin/auditoria?limit=        (reutilizado; `limit` y `actor_nombre` aditivos)
 */

/** Estado independiente de cada bloque de la pantalla. */
export type EstadoBloque =
  | 'cargando'
  | 'listo'
  | 'vacio'
  | 'error'
  | 'sin_permiso';

export interface Bloque<T> {
  estado: EstadoBloque;
  datos: T | null;
}

export function bloqueCargando<T>(): Bloque<T> {
  return { estado: 'cargando', datos: null };
}

// ── /admin/inicio/resumen ──────────────────────────────────────
export interface KpiIncidencias {
  total: number;
  dias: number;
}

export interface ResumenKpis {
  estudiantes_registrados: number;
  profesionales_activos: number;
  citas_mes: number;
  especialidades: number;
  solicitudes_pendientes: number;
  /** null: el actor no tiene AUDITORIA_VER; el dato no se calculó. */
  incidencias: KpiIncidencias | null;
}

export interface CitasMesPunto {
  /** YYYY-MM */
  mes: string;
  cantidad: number;
}

export interface CitasPorMes {
  desde: string;
  hasta: string;
  meses: CitasMesPunto[];
}

export interface ProfesionalSolicitado {
  profesional_id: number;
  nombre: string;
  tratamiento: string | null;
  especialidad: string | null;
  cantidad: number;
}

export interface ProfesionalesMasSolicitados {
  desde: string;
  hasta: string;
  dias: number;
  items: ProfesionalSolicitado[];
}

export interface ResumenInicio {
  generado_en: string;
  kpis: ResumenKpis;
  citas_por_mes: CitasPorMes;
  profesionales_mas_solicitados: ProfesionalesMasSolicitados;
}

// ── /admin/inicio/gestion ──────────────────────────────────────
export interface UsuarioReciente {
  id: number;
  nombre: string | null;
  rol: string;
  /** null en cuentas históricas: la UI muestra "—". */
  fecha_creacion: string | null;
}

export interface SolicitudPendiente {
  id: number;
  profesional_id: number;
  profesional_nombre: string | null;
  especialidad: string | null;
  tipo: string;
  hora_inicio: string | null;
  hora_fin: string | null;
  estado: string;
  fecha_solicitud: string | null;
}

export interface GestionInicio {
  ultimos_usuarios: UsuarioReciente[];
  solicitudes_pendientes: {
    total: number;
    items: SolicitudPendiente[];
  };
}

// ── Endpoints reutilizados ─────────────────────────────────────
export interface EspecialidadCitas {
  especialidad: string;
  cantidad: number;
  porcentaje: number;
}

export interface AdministradorResumen {
  id: number;
  nombre: string | null;
  correo: string;
  rol: 'admin' | 'superadmin';
  activo: boolean;
}

export interface EventoAuditoria {
  id: number;
  usuario_id: number | null;
  actor_rol: string | null;
  actor_nombre: string | null;
  accion: string;
  resultado: string;
  detalle: string | null;
  entidad: string | null;
  entidad_id: number | null;
  fecha: string | null;
}

// ── Navegación desde el Inicio ─────────────────────────────────
/**
 * Destinos REALES a los que el Inicio puede derivar. No son rutas del
 * router (solo existe /dashboard/admin): son secciones internas del shell,
 * las mismas que abre el sidebar mediante navegarA(seccion).
 *
 *  · 'auditoria' = sección "configuracion" + pestaña "seguridad" (ahí vive
 *    la tabla de auditoría).
 */
export type DestinoInicioInstitucional =
  | 'reportes'
  | 'historial'
  | 'horario'
  | 'administradores'
  | 'auditoria';

export interface AccionInicio {
  clave: string;
  destino: DestinoInicioInstitucional;
  etiqueta: string;
}
