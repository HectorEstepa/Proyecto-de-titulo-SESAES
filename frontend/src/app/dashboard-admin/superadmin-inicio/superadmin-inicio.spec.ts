import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { AuthService } from '../../auth.service';
import {
  ACCIONES_INICIO,
  ETIQUETA_INCIDENCIAS,
  FILAS_ACTIVIDAD,
  FILAS_ADMINISTRADORES,
  FILAS_AUDITORIA_TABLA,
  PERMISOS_BLOQUE,
  SuperadminInicioComponent
} from './superadmin-inicio';
import {
  AdministradorResumen,
  DestinoInicioInstitucional,
  EventoAuditoria,
  GestionInicio,
  ResumenInicio
} from './superadmin-inicio.models';

// ── Fixtures ────────────────────────────────────────────────────
const TODOS_LOS_PERMISOS = [
  'roles.gestionar', 'auditoria.ver', 'reportes.ver', 'usuarios.ver', 'agenda.gestionar'
];

const URL = {
  resumen: '/admin/inicio/resumen',
  gestion: '/admin/inicio/gestion',
  especialidad: '/admin/graficos/especialidad',
  administradores: '/usuarios/administradores',
  auditoria: '/admin/auditoria'
};

function mesesDesde(valores: number[]) {
  return valores.map((cantidad, i) => {
    const total = 2025 * 12 + 9 + i; // parte en 2025-10
    const anio = Math.floor(total / 12);
    const mes = (total % 12) + 1;
    return { mes: `${anio}-${String(mes).padStart(2, '0')}`, cantidad };
  });
}

function resumen(over: Partial<ResumenInicio> = {}): ResumenInicio {
  return {
    generado_en: '2026-09-19T12:00:00',
    kpis: {
      estudiantes_registrados: 1234,
      profesionales_activos: 14,
      citas_mes: 37,
      especialidades: 6,
      solicitudes_pendientes: 3,
      incidencias: { total: 2, dias: 30 }
    },
    citas_por_mes: {
      desde: '2025-10',
      hasta: '2026-09',
      meses: mesesDesde([0, 4, 8, 12, 9, 15, 20, 18, 22, 30, 25, 37])
    },
    profesionales_mas_solicitados: {
      desde: '2026-06-22',
      hasta: '2026-09-19',
      dias: 90,
      items: [
        { profesional_id: 1, nombre: 'Ana Pérez', tratamiento: 'Dra.', especialidad: 'Psicología', cantidad: 20 },
        { profesional_id: 2, nombre: 'Beto Soto', tratamiento: null, especialidad: 'Nutrición', cantidad: 10 }
      ]
    },
    ...over
  };
}

function gestion(over: Partial<GestionInicio> = {}): GestionInicio {
  return {
    ultimos_usuarios: [
      { id: 12, nombre: 'Carla Rojas', rol: 'estudiante', fecha_creacion: '2026-09-18T09:30:00' },
      { id: 11, nombre: 'Dr. Luis Mena', rol: 'profesional', fecha_creacion: null },
      { id: 10, nombre: null, rol: 'admin', fecha_creacion: null }
    ],
    solicitudes_pendientes: {
      total: 8,
      items: [
        {
          id: 5, profesional_id: 2, profesional_nombre: 'Beto Soto', especialidad: 'Nutrición',
          tipo: 'colacion', hora_inicio: '13:00', hora_fin: '14:00', estado: 'pendiente',
          fecha_solicitud: '2026-09-17T10:00:00'
        },
        {
          id: 4, profesional_id: 1, profesional_nombre: 'Ana Pérez', especialidad: 'Psicología',
          tipo: 'jornada', hora_inicio: '09:00', hora_fin: '17:00', estado: 'pendiente',
          fecha_solicitud: '2026-09-16T10:00:00'
        }
      ]
    },
    ...over
  };
}

function admin(over: Partial<AdministradorResumen> = {}): AdministradorResumen {
  return { id: 1, nombre: 'Admin Uno', correo: 'admin1@sesaes.cl', rol: 'admin', activo: true, ...over };
}

function evento(over: Partial<EventoAuditoria> = {}): EventoAuditoria {
  return {
    id: 1,
    usuario_id: 7,
    actor_rol: 'admin',
    actor_nombre: 'Marta Vera',
    accion: 'Profesional completó cita',
    resultado: 'exito',
    detalle: 'Cita 15 completada',
    entidad: 'cita',
    entidad_id: 15,
    fecha: '2026-09-19T11:55:00',
    ...over
  };
}

/** Timestamp naive en HORA LOCAL (como los que entrega el backend): independiente de la zona del runner. */
function haceMinutosLocal(min: number): string {
  const d = new Date(Date.now() - min * 60000);
  const dos = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`
    + `T${dos(d.getHours())}:${dos(d.getMinutes())}:${dos(d.getSeconds())}`;
}

// ── Suite ───────────────────────────────────────────────────────
describe('SuperadminInicioComponent', () => {
  let fixture: ComponentFixture<SuperadminInicioComponent>;
  let component: SuperadminInicioComponent;
  let http: HttpTestingController;
  let el: HTMLElement;

  async function montar(
    permisos: string[] = TODOS_LOS_PERMISOS,
    rol: 'admin' | 'superadmin' = 'superadmin',
    puedeIrA?: (destino: DestinoInicioInstitucional) => boolean
  ) {
    sessionStorage.clear();
    localStorage.clear();
    sessionStorage.setItem('rol', rol);
    sessionStorage.setItem('usuario_id', '99');

    await TestBed.configureTestingModule({
      imports: [SuperadminInicioComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();

    http = TestBed.inject(HttpTestingController);

    // El componente solo se monta tras el contexto efectivo del shell.
    TestBed.inject(AuthService).cargarAccesoAdministrativo().subscribe();
    http.expectOne(r => r.url.includes('/usuarios/me/acceso-administrativo')).flush({
      rol,
      perfil: rol === 'admin' ? 'administrador_general' : null,
      permisos,
      alcance: { tipo: 'institucional', especialidades: [] }
    });

    fixture = TestBed.createComponent(SuperadminInicioComponent);
    component = fixture.componentInstance;
    el = fixture.nativeElement;
    if (puedeIrA) fixture.componentRef.setInput('puedeIrA', puedeIrA);
    fixture.detectChanges(); // ngOnInit → peticiones
  }

  const pedido = (fragmento: string) =>
    http.expectOne(r => r.url.includes(fragmento) && r.method === 'GET');

  function responderTodo(over: {
    resumen?: ResumenInicio; gestion?: GestionInicio; especialidad?: unknown[];
    admins?: AdministradorResumen[]; auditoria?: EventoAuditoria[];
  } = {}) {
    pedido(URL.resumen).flush(over.resumen ?? resumen());
    pedido(URL.gestion).flush(over.gestion ?? gestion());
    pedido(URL.especialidad).flush(over.especialidad ?? [
      { especialidad: 'Psicología', cantidad: 30, porcentaje: 60 },
      { especialidad: 'Nutrición', cantidad: 20, porcentaje: 40 }
    ]);
    pedido(URL.administradores).flush(over.admins ?? [
      admin({ id: 1, nombre: 'Zoe Admin' }),
      admin({ id: 2, nombre: 'Sofía Super', correo: 'sofia@sesaes.cl', rol: 'superadmin' }),
      admin({ id: 3, nombre: 'Inactivo', activo: false })
    ]);
    pedido(URL.auditoria).flush(over.auditoria ?? [evento()]);
    fixture.detectChanges();
  }

  const q = (sel: string) => el.querySelector<HTMLElement>(sel);
  const qa = (sel: string) => Array.from(el.querySelectorAll<HTMLElement>(sel));
  const texto = (sel: string) => (q(sel)?.textContent ?? '').replace(/\s+/g, ' ').trim();

  afterEach(() => {
    http.verify();
    sessionStorage.clear();
    localStorage.clear();
    TestBed.resetTestingModule();
  });

  // ══════════════════════════════════════
  // Acceso
  // ══════════════════════════════════════
  describe('acceso (RBAC fail-closed)', () => {
    it('SUPERADMIN con permisos efectivos pide los 5 bloques, cada uno con su endpoint', async () => {
      await montar();

      // Exactamente una petición por bloque (expectOne falla si hay 0 o 2+).
      const reqEspecialidad = pedido(URL.especialidad);
      expect(reqEspecialidad.request.params.get('mes')).toBeTruthy();
      expect(reqEspecialidad.request.params.get('anio')).toBeTruthy();
      expect(pedido(URL.auditoria).request.params.get('limit')).toBe('10');
      pedido(URL.resumen);
      pedido(URL.gestion);
      pedido(URL.administradores);
      // afterEach → http.verify(): no queda ninguna otra petición pendiente.
    });

    it('la combinación de permisos por bloque usa solo permisos ya existentes', () => {
      expect(PERMISOS_BLOQUE.resumen).toEqual(['roles.gestionar', 'reportes.ver']);
      expect(PERMISOS_BLOQUE.gestion).toEqual(['roles.gestionar', 'usuarios.ver', 'agenda.gestionar']);
      expect(PERMISOS_BLOQUE.administradores).toEqual(['roles.gestionar']);
      expect(PERMISOS_BLOQUE.auditoria).toEqual(['auditoria.ver']);
      expect(PERMISOS_BLOQUE.especialidades).toEqual(['reportes.ver']);
    });

    it('ADMIN sin permisos reservados: no hace las peticiones institucionales y lo indica', async () => {
      // Perfil operativo típico de ADMIN: sin roles.gestionar ni auditoria.ver.
      await montar(['reportes.ver', 'usuarios.ver', 'agenda.gestionar'], 'admin');

      // Solo el gráfico por especialidad (reportes.ver) es alcanzable.
      pedido(URL.especialidad).flush([{ especialidad: 'Psicología', cantidad: 3, porcentaje: 100 }]);
      http.expectNone(r => r.url.includes(URL.resumen));
      http.expectNone(r => r.url.includes(URL.gestion));
      http.expectNone(r => r.url.includes(URL.administradores));
      http.expectNone(r => r.url.includes(URL.auditoria));
      fixture.detectChanges();

      expect(component.resumen.estado).toBe('sin_permiso');
      expect(component.gestion.estado).toBe('sin_permiso');
      expect(component.administradores.estado).toBe('sin_permiso');
      expect(component.auditoria.estado).toBe('sin_permiso');
      expect(qa('[data-estado="sin_permiso"]').length).toBeGreaterThanOrEqual(6);
      expect(el.textContent).toContain('No tienes permiso para ver este bloque.');
    });

    it('sin contexto ni permisos no se emite ninguna petición', async () => {
      await montar([], 'superadmin');

      [URL.resumen, URL.gestion, URL.especialidad, URL.administradores, URL.auditoria]
        .forEach(u => http.expectNone(r => r.url.includes(u)));
      expect(qa('[data-estado="sin_permiso"]').length).toBeGreaterThan(0);
    });

    it('un 403 del backend se presenta como sin permiso, sin botón de reintento', async () => {
      await montar();
      pedido(URL.auditoria).flush({ detail: 'Forbidden' }, { status: 403, statusText: 'Forbidden' });
      [URL.resumen, URL.gestion, URL.especialidad, URL.administradores]
        .forEach(u => pedido(u).flush(u === URL.resumen ? resumen() : u === URL.gestion ? gestion() : []));
      fixture.detectChanges();

      expect(component.auditoria.estado).toBe('sin_permiso');
      const tarjeta = q('[data-testid="card-auditoria"]')!;
      expect(tarjeta.querySelector('.sa-reintentar')).toBeNull();
    });
  });

  // ══════════════════════════════════════
  // Loading
  // ══════════════════════════════════════
  describe('loading', () => {
    it('mientras carga muestra esqueletos y NO valores en cero', async () => {
      await montar();

      expect(component.resumen.estado).toBe('cargando');
      expect(qa('.sa-kpi.sa-esqueleto')).toHaveLength(6);
      expect(qa('[data-testid="kpi-valor"]')).toHaveLength(0);
      expect(q('.sa-kpis')?.getAttribute('aria-busy')).toBe('true');
      expect(qa('[data-estado="cargando"]').length).toBeGreaterThan(0);

      responderTodo();
    });

    it('al terminar la carga desaparecen los esqueletos', async () => {
      await montar();
      responderTodo();

      expect(qa('.sa-esqueleto')).toHaveLength(0);
      expect(qa('[data-estado="cargando"]')).toHaveLength(0);
      expect(q('.sa-kpis')?.getAttribute('aria-busy')).toBe('false');
    });
  });

  // ══════════════════════════════════════
  // KPIs
  // ══════════════════════════════════════
  describe('KPIs', () => {
    it('muestra los 6 KPIs con los valores reales del backend', async () => {
      await montar();
      responderTodo();

      const kpi = (clave: string) => texto(`[data-kpi="${clave}"]`);
      expect(qa('.sa-kpi[data-kpi]')).toHaveLength(6);
      expect(kpi('estudiantes')).toContain('1234');
      expect(kpi('estudiantes')).toContain('Estudiantes registrados');
      expect(kpi('profesionales')).toContain('14');
      expect(kpi('profesionales')).toContain('Profesionales activos');
      expect(kpi('citas')).toContain('37');
      expect(kpi('citas')).toContain('Citas este mes');
      expect(kpi('especialidades')).toContain('6');
      expect(kpi('especialidades')).toContain('Especialidades');
      expect(kpi('solicitudes')).toContain('3');
      expect(kpi('solicitudes')).toContain('Solicitudes pendientes');
    });

    it('etiqueta las incidencias como eventos de error/denegación, no como módulo formal', async () => {
      await montar();
      responderTodo();

      expect(ETIQUETA_INCIDENCIAS).toBe('Incidencias (eventos de error/denegación)');
      const card = texto('[data-kpi="incidencias"]');
      expect(card).toContain('Incidencias (eventos de error/denegación)');
      expect(card).toContain('2');
      expect(card).toContain('Últimos 30 días');
    });

    it('incidencias no disponibles (null) muestran "—" y no un 0 engañoso', async () => {
      await montar();
      const r = resumen();
      r.kpis.incidencias = null;
      responderTodo({ resumen: r });

      const card = q('[data-kpi="incidencias"]')!;
      expect(card.classList.contains('no-disponible')).toBe(true);
      expect(card.querySelector('[data-testid="kpi-valor"]')?.textContent?.trim()).toBe('—');
      expect(card.textContent).toContain('No disponible para tu acceso');
    });

    it('un valor legítimamente 0 tras cargar SÍ se muestra como 0', async () => {
      await montar();
      const r = resumen();
      r.kpis.solicitudes_pendientes = 0;
      responderTodo({ resumen: r });

      expect(q('[data-kpi="solicitudes"] [data-testid="kpi-valor"]')?.textContent?.trim()).toBe('0');
    });
  });

  // ══════════════════════════════════════
  // Gráficos
  // ══════════════════════════════════════
  describe('gráficos', () => {
    it('citas por mes: dibuja 12 puntos con tooltip accesible', async () => {
      await montar();
      responderTodo();

      const svg = q('[data-testid="card-citas-mes"] svg.sa-linea')!;
      expect(svg).toBeTruthy();
      expect(qa('[data-testid="card-citas-mes"] circle.sa-punto')).toHaveLength(12);
      expect(svg.getAttribute('aria-label')).toContain('200 citas');
      expect(texto('[data-testid="card-citas-mes"]')).toContain('Últimos 12 meses');
      expect(qa('[data-testid="card-citas-mes"] title')[11].textContent).toBe('septiembre 2026: 37 citas');
    });

    it('citas por mes sin ninguna cita: estado vacío en vez de una línea en cero', async () => {
      await montar();
      const r = resumen();
      r.citas_por_mes.meses = mesesDesde(new Array(12).fill(0));
      responderTodo({ resumen: r });

      expect(q('[data-testid="card-citas-mes"] svg')).toBeNull();
      expect(texto('[data-testid="card-citas-mes"]')).toContain('Aún no hay citas registradas en los últimos 12 meses.');
      // El resto de los bloques del resumen no se ven afectados.
      expect(qa('[data-testid="kpi-valor"]')).toHaveLength(6);
    });

    it('citas por especialidad: donut con un segmento por especialidad y leyenda con %', async () => {
      await montar();
      responderTodo();

      const card = q('[data-testid="card-especialidad"]')!;
      expect(card.querySelectorAll('svg.sa-donut circle[stroke-dasharray]')).toHaveLength(2);
      expect(card.querySelector('.sa-donut-total')?.textContent).toBe('50');
      const leyenda = texto('[data-testid="card-especialidad"] .sa-leyenda');
      expect(leyenda).toContain('Psicología');
      expect(leyenda).toContain('30 · 60%');
      expect(leyenda).toContain('20 · 40%');
    });

    it('citas por especialidad sin datos (lista vacía o solo ceros): estado vacío', async () => {
      await montar();
      responderTodo({ especialidad: [{ especialidad: 'Psicología', cantidad: 0, porcentaje: 0 }] });

      expect(component.especialidades.estado).toBe('vacio');
      expect(q('[data-testid="card-especialidad"] svg')).toBeNull();
      expect(texto('[data-testid="card-especialidad"]'))
        .toContain('No hay citas este mes para agrupar por especialidad.');
    });

    it('profesionales más solicitados: barras proporcionales, tratamiento y período explícito', async () => {
      await montar();
      responderTodo();

      const filas = qa('[data-testid="top-profesional"]');
      expect(filas).toHaveLength(2);
      expect(filas[0].textContent).toContain('Dra. Ana Pérez');
      expect(filas[0].textContent).toContain('Psicología');
      expect(filas[1].textContent).toContain('Beto Soto');

      const ancho = (i: number) =>
        parseFloat((filas[i].querySelector('.sa-barra-relleno') as HTMLElement).style.width);
      expect(ancho(0)).toBe(100);
      expect(ancho(1)).toBe(50);

      const periodo = texto('[data-testid="top-periodo"]');
      expect(periodo).toContain('Últimos 90 días');
      expect(periodo).toContain('22 jun');
      expect(periodo).toContain('19 sep 2026');
      expect(periodo).toContain('pendientes y completadas');
    });

    it('profesionales más solicitados sin datos: estado vacío', async () => {
      await montar();
      const r = resumen();
      r.profesionales_mas_solicitados.items = [];
      responderTodo({ resumen: r });

      expect(qa('[data-testid="top-profesional"]')).toHaveLength(0);
      expect(texto('[data-testid="card-top-profesionales"]')).toContain('No hay citas en los últimos 90 días.');
    });
  });

  // ══════════════════════════════════════
  // Gestión
  // ══════════════════════════════════════
  describe('últimos usuarios registrados', () => {
    it('muestra nombre, tipo y fecha; "—" cuando la cuenta es histórica (sin fecha)', async () => {
      await montar();
      responderTodo();

      const filas = qa('[data-testid="ultimo-usuario"]');
      expect(filas).toHaveLength(3);

      expect(filas[0].textContent).toContain('Carla Rojas');
      expect(filas[0].textContent).toContain('Estudiante');
      expect(filas[0].querySelector('[data-testid="usuario-fecha"]')?.textContent?.trim()).toBe('18 sep 2026');

      expect(filas[1].textContent).toContain('Profesional');
      expect(filas[1].querySelector('[data-testid="usuario-fecha"]')?.textContent?.trim()).toBe('—');

      // Nombre nulo → rótulo neutro, nunca un nombre inventado.
      expect(filas[2].textContent).toContain('Sin nombre');
      expect(filas[2].textContent).toContain('Administrador');
    });

    it('sin usuarios: estado vacío', async () => {
      await montar();
      responderTodo({ gestion: gestion({ ultimos_usuarios: [] }) });

      expect(texto('[data-testid="card-ultimos-usuarios"]')).toContain('Aún no hay usuarios registrados.');
    });
  });

  describe('solicitudes de horario pendientes', () => {
    it('lista profesional, especialidad, tipo, estado y fecha; indica el total cuando hay más', async () => {
      await montar();
      responderTodo();

      const filas = qa('[data-testid="solicitud-pendiente"]');
      expect(filas).toHaveLength(2);
      expect(filas[0].textContent).toContain('Beto Soto');
      expect(filas[0].textContent).toContain('Nutrición');
      expect(filas[0].textContent).toContain('Colación');
      expect(filas[0].textContent).toContain('Pendiente');
      expect(filas[0].textContent).toContain('17 sep 2026');
      expect(filas[1].textContent).toContain('Jornada');
      expect(texto('[data-testid="solicitudes-total"]')).toBe('Mostrando 2 de 8 solicitudes.');
      expect(texto('[data-testid="card-solicitudes"]')).toContain('Solicitudes de horario pendientes');
    });

    it('sin solicitudes: estado vacío y sin leyenda de total', async () => {
      await montar();
      responderTodo({
        gestion: gestion({ solicitudes_pendientes: { total: 0, items: [] } })
      });

      expect(texto('[data-testid="card-solicitudes"]')).toContain('No hay solicitudes de horario pendientes.');
      expect(q('[data-testid="solicitudes-total"]')).toBeNull();
    });
  });

  describe('administradores activos', () => {
    it('solo lista cuentas activas, con superadmin primero, y no promete "último acceso"', async () => {
      await montar();
      responderTodo();

      const filas = qa('[data-testid="administrador-activo"]');
      expect(filas).toHaveLength(2);
      expect(filas[0].textContent).toContain('Sofía Super');
      expect(filas[0].textContent).toContain('Superadmin');
      expect(filas[1].textContent).toContain('Zoe Admin');
      expect(el.textContent).not.toContain('Inactivo');

      const tarjeta = texto('[data-testid="card-administradores"]');
      expect(tarjeta).toContain('El último acceso aún no se registra');
    });

    it(`limita a ${FILAS_ADMINISTRADORES} filas e informa cuántas más hay`, async () => {
      await montar();
      const muchos = Array.from({ length: 8 }, (_, i) =>
        admin({ id: i + 1, nombre: `Admin ${i}`, correo: `a${i}@sesaes.cl` }));
      responderTodo({ admins: muchos });

      expect(qa('[data-testid="administrador-activo"]')).toHaveLength(FILAS_ADMINISTRADORES);
      expect(texto('[data-testid="admins-ocultos"]')).toBe('y 3 más.');
    });

    it('usa el correo cuando la cuenta no tiene nombre', async () => {
      await montar();
      responderTodo({ admins: [admin({ nombre: null, correo: 'sin.nombre@sesaes.cl' })] });

      expect(qa('[data-testid="administrador-activo"] .sa-item-titulo')[0].textContent)
        .toContain('sin.nombre@sesaes.cl');
    });

    it('sin administradores activos: estado vacío', async () => {
      await montar();
      responderTodo({ admins: [admin({ activo: false })] });

      expect(component.administradores.estado).toBe('vacio');
      expect(texto('[data-testid="card-administradores"]')).toContain('No hay administradores activos.');
    });
  });

  // ══════════════════════════════════════
  // Auditoría y actividad reciente
  // ══════════════════════════════════════
  describe('últimas acciones y actividad reciente', () => {
    it('la tabla muestra usuario, acción, módulo, detalle, fecha/hora y resultado', async () => {
      await montar();
      responderTodo({
        auditoria: [
          evento({ id: 3 }),
          evento({ id: 2, actor_nombre: null, actor_rol: 'superadmin', accion: 'Cerró el centro',
                   entidad: 'dia_cerrado', resultado: 'denegado', detalle: null }),
          evento({ id: 1, accion: 'Cambió estado', entidad: 'profesional', resultado: 'error', detalle: 'x'.repeat(200) })
        ]
      });

      const cabeceras = qa('[data-testid="card-auditoria"] th').map(t => t.textContent?.trim());
      expect(cabeceras).toEqual(['Usuario', 'Acción', 'Módulo', 'Detalles', 'Fecha y hora', 'Resultado']);

      const filas = qa('[data-testid="evento-auditoria"]');
      expect(filas).toHaveLength(3);
      expect(filas[0].textContent).toContain('Marta Vera');
      expect(filas[0].textContent).toContain('Profesional completó cita');
      expect(filas[0].textContent).toContain('Citas');
      expect(filas[0].textContent).toContain('Cita 15 completada');
      expect(filas[0].textContent).toContain('19 sep 2026, 11:55');
      expect(filas[0].querySelector('.sa-badge')?.textContent?.trim()).toBe('Éxito');

      // Sin nombre de actor → rol legible; sin detalle → "—"; denegado → badge de advertencia.
      expect(filas[1].textContent).toContain('Superadmin');
      expect(filas[1].textContent).toContain('Agenda');
      expect(filas[1].querySelector('.col-detalle')?.textContent?.trim()).toBe('—');
      expect(filas[1].querySelector('.sa-badge')?.classList.contains('warn')).toBe(true);

      // Detalle largo truncado (el texto completo queda en el tooltip).
      const detalle = filas[2].querySelector('.col-detalle') as HTMLElement;
      expect(detalle.textContent?.trim().length).toBeLessThanOrEqual(80);
      expect(detalle.title).toBe('x'.repeat(200));
      expect(filas[2].querySelector('.sa-badge')?.classList.contains('err')).toBe(true);
    });

    it('la tabla y la actividad reciente comparten UNA sola petición y respetan sus topes', async () => {
      await montar();
      const muchos = Array.from({ length: 10 }, (_, i) =>
        evento({ id: i + 1, accion: `Acción ${i + 1}` }));
      responderTodo({ auditoria: muchos });

      expect(qa('[data-testid="evento-auditoria"]')).toHaveLength(FILAS_AUDITORIA_TABLA);
      expect(qa('[data-testid="actividad-item"]')).toHaveLength(FILAS_ACTIVIDAD);
      expect(http.match(r => r.url.includes(URL.auditoria))).toHaveLength(0);
    });

    it('la actividad reciente resume actor y tiempo relativo', async () => {
      await montar();
      responderTodo({ auditoria: [evento({ fecha: haceMinutosLocal(5) })] });

      const item = texto('[data-testid="actividad-item"]');
      expect(item).toContain('Profesional completó cita');
      expect(item).toContain('Marta Vera');
      expect(item).toMatch(/Hace (5|6|4) min/);
    });

    it('sin eventos: estado vacío en la tabla y en la actividad', async () => {
      await montar();
      responderTodo({ auditoria: [] });

      expect(component.auditoria.estado).toBe('vacio');
      expect(texto('[data-testid="card-auditoria"]')).toContain('Aún no hay acciones registradas en la auditoría.');
      expect(texto('[data-testid="card-actividad"]')).toContain('Sin actividad reciente.');
    });
  });

  // ══════════════════════════════════════
  // Errores por bloque
  // ══════════════════════════════════════
  describe('manejo de errores', () => {
    it('un bloque que falla no tumba a los demás y muestra error visible con reintento', async () => {
      await montar();
      pedido(URL.resumen).flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
      pedido(URL.gestion).flush(gestion());
      pedido(URL.especialidad).flush([{ especialidad: 'Psicología', cantidad: 5, porcentaje: 100 }]);
      pedido(URL.administradores).flush([admin()]);
      pedido(URL.auditoria).flush([evento()]);
      fixture.detectChanges();

      // El resumen (KPIs + serie + top) falla de forma visible…
      expect(component.resumen.estado).toBe('error');
      expect(qa('[data-testid="kpi-valor"]')).toHaveLength(0);
      expect(texto('.sa-kpis-fallo')).toContain('No se pudo cargar esta información.');
      expect(texto('[data-testid="card-citas-mes"]')).toContain('No se pudo cargar esta información.');
      expect(texto('[data-testid="card-top-profesionales"]')).toContain('No se pudo cargar esta información.');

      // …y NO se disfraza de éxito con ceros.
      expect(el.querySelector('[data-kpi]')).toBeNull();

      // Los demás bloques siguen funcionando.
      expect(qa('[data-testid="ultimo-usuario"]')).toHaveLength(3);
      expect(qa('[data-testid="evento-auditoria"]')).toHaveLength(1);
      expect(qa('[data-testid="administrador-activo"]')).toHaveLength(1);
      expect(q('[data-testid="card-especialidad"] svg.sa-donut')).toBeTruthy();
    });

    it('reintentar recarga SOLO el bloque fallido y se recupera', async () => {
      await montar();
      pedido(URL.resumen).flush('err', { status: 500, statusText: 'Server Error' });
      pedido(URL.gestion).flush(gestion());
      pedido(URL.especialidad).flush([]);
      pedido(URL.administradores).flush([admin()]);
      pedido(URL.auditoria).flush([evento()]);
      fixture.detectChanges();

      const boton = q('.sa-kpis-fallo .sa-reintentar') as HTMLButtonElement;
      expect(boton).toBeTruthy();
      boton.click();
      fixture.detectChanges();

      // Vuelve a "cargando" y solo se emite la petición del resumen.
      expect(component.resumen.estado).toBe('cargando');
      expect(qa('.sa-kpi.sa-esqueleto')).toHaveLength(6);
      pedido(URL.resumen).flush(resumen());
      fixture.detectChanges();

      expect(component.resumen.estado).toBe('listo');
      expect(qa('[data-kpi]')).toHaveLength(6);
      // El resto no se volvió a pedir (verify() lo comprueba en afterEach).
    });

    it('cada bloque puede fallar de forma independiente (auditoría y administradores)', async () => {
      await montar();
      pedido(URL.resumen).flush(resumen());
      pedido(URL.gestion).flush(gestion());
      pedido(URL.especialidad).flush([]);
      pedido(URL.administradores).flush('x', { status: 500, statusText: 'Server Error' });
      pedido(URL.auditoria).flush('x', { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      expect(component.administradores.estado).toBe('error');
      expect(component.auditoria.estado).toBe('error');
      expect(qa('[data-testid="card-auditoria"] .sa-reintentar')).toHaveLength(1);
      expect(qa('[data-testid="card-actividad"] .sa-reintentar')).toHaveLength(1);
      expect(qa('[data-kpi]')).toHaveLength(6);
    });

    it('un error de red (status 0) también es un error visible', async () => {
      await montar();
      pedido(URL.resumen).error(new ProgressEvent('error'));
      pedido(URL.gestion).flush(gestion());
      pedido(URL.especialidad).flush([]);
      pedido(URL.administradores).flush([]);
      pedido(URL.auditoria).flush([]);
      fixture.detectChanges();

      expect(component.resumen.estado).toBe('error');
    });
  });

  // ══════════════════════════════════════
  // Acciones de navegación hacia el detalle
  // ══════════════════════════════════════
  describe('acciones de navegación (Inicio = resumen + acceso rápido)', () => {
    const TODAS = () => true;
    const accion = (clave: string) => q(`[data-accion="${clave}"]`) as HTMLButtonElement | null;

    it('los destinos son secciones reales del shell, sin rutas ni endpoints nuevos', () => {
      expect(ACCIONES_INICIO.citasMes.destino).toBe('historial');
      expect(ACCIONES_INICIO.especialidad.destino).toBe('reportes');
      expect(ACCIONES_INICIO.solicitudes.destino).toBe('horario');
      expect(ACCIONES_INICIO.administradores.destino).toBe('administradores');
      expect(ACCIONES_INICIO.auditoria.destino).toBe('auditoria');
      expect(ACCIONES_INICIO.actividad.destino).toBe('auditoria');
    });

    it('muestra cada acción con su etiqueta en el bloque correspondiente', async () => {
      await montar(TODOS_LOS_PERMISOS, 'superadmin', TODAS);
      responderTodo();

      const enTarjeta = (card: string, clave: string) =>
        q(`[data-testid="${card}"] [data-accion="${clave}"]`);

      expect(enTarjeta('card-citas-mes', 'citasMes')?.textContent).toContain('Ver historial');
      expect(enTarjeta('card-especialidad', 'especialidad')?.textContent).toContain('Ver reporte');
      expect(enTarjeta('card-solicitudes', 'solicitudes')?.textContent).toContain('Ver solicitudes');
      expect(enTarjeta('card-administradores', 'administradores')?.textContent).toContain('Ver administradores');
      expect(enTarjeta('card-auditoria', 'auditoria')?.textContent).toContain('Ver auditoría');
      expect(enTarjeta('card-actividad', 'actividad')?.textContent).toContain('Ver auditoría');
    });

    it('al pulsar cada acción emite el destino real correspondiente', async () => {
      await montar(TODOS_LOS_PERMISOS, 'superadmin', TODAS);
      responderTodo();

      const emitidos: DestinoInicioInstitucional[] = [];
      component.navegar.subscribe(d => emitidos.push(d));

      for (const clave of ['citasMes', 'especialidad', 'solicitudes', 'administradores', 'auditoria', 'actividad']) {
        accion(clave)!.click();
      }

      expect(emitidos).toEqual(['historial', 'reportes', 'horario', 'administradores', 'auditoria', 'auditoria']);
    });

    it('fail-closed: sin decisión del shell no se muestra ninguna acción', async () => {
      await montar(); // puedeIrA por defecto: () => false
      responderTodo();

      expect(qa('.sa-accion')).toHaveLength(0);
    });

    it('solo se muestran las acciones cuyo destino está permitido', async () => {
      await montar(TODOS_LOS_PERMISOS, 'superadmin', d => d === 'reportes' || d === 'auditoria');
      responderTodo();

      expect(qa('.sa-accion').map(b => b.getAttribute('data-accion')).sort())
        .toEqual(['actividad', 'auditoria', 'especialidad']);
    });

    it('ir() no emite si el destino no está permitido', async () => {
      await montar(TODOS_LOS_PERMISOS, 'superadmin', d => d === 'reportes');
      responderTodo();

      const emitidos: string[] = [];
      component.navegar.subscribe(d => emitidos.push(d));

      component.ir('administradores');
      component.ir('reportes');

      expect(emitidos).toEqual(['reportes']);
    });

    it('las acciones están disponibles aunque el bloque haya fallado (para llegar al módulo)', async () => {
      await montar(TODOS_LOS_PERMISOS, 'superadmin', TODAS);
      pedido(URL.resumen).flush('x', { status: 500, statusText: 'Server Error' });
      pedido(URL.gestion).flush(gestion());
      pedido(URL.especialidad).flush([]);
      pedido(URL.administradores).flush([admin()]);
      pedido(URL.auditoria).flush([evento()]);
      fixture.detectChanges();

      expect(accion('citasMes')).toBeTruthy();
      expect(accion('especialidad')).toBeTruthy();
    });

    it('bloques SIN destino equivalente no muestran acción (no se simula navegación)', async () => {
      await montar(TODOS_LOS_PERMISOS, 'superadmin', TODAS);
      responderTodo();

      // Profesionales más solicitados: no existe un reporte de ranking.
      expect(qa('[data-testid="card-top-profesionales"] .sa-accion')).toHaveLength(0);
      // Últimos usuarios: no existe un listado unificado de usuarios.
      expect(qa('[data-testid="card-ultimos-usuarios"] .sa-accion')).toHaveLength(0);
    });

    it('el Inicio no duplica las tablas completas ni los filtros de Reportes', async () => {
      await montar(TODOS_LOS_PERMISOS, 'superadmin', TODAS);
      responderTodo();

      expect(qa('input, select, textarea')).toHaveLength(0);       // sin filtros
      expect(qa('[data-testid="evento-auditoria"]').length).toBeLessThanOrEqual(FILAS_AUDITORIA_TABLA);
      expect(el.textContent).not.toMatch(/Exportar|Excel|Aplicar filtros/);
    });
  });

  // ══════════════════════════════════════
  // Definiciones explícitas de los KPI
  // ══════════════════════════════════════
  describe('definición de cada KPI', () => {
    it('cada KPI expone su definición como tooltip', async () => {
      await montar();
      responderTodo();

      for (const clave of ['estudiantes', 'profesionales', 'citas', 'especialidades', 'solicitudes', 'incidencias']) {
        const titulo = q(`[data-kpi="${clave}"]`)?.getAttribute('title') ?? '';
        expect(titulo.length, clave).toBeGreaterThan(20);
      }
    });

    it('Especialidades explicita que no hay catálogo y qué normaliza (sin unificar tildes)', async () => {
      await montar();
      responderTodo();

      const def = q('[data-kpi="especialidades"]')!.getAttribute('title')!;
      expect(def).toContain('No existe un catálogo');
      expect(def).toContain('mayúsculas y espacios sobrantes');
      expect(def).toContain('no unifica variantes con y sin tilde');
    });

    it('Incidencias aclara que no es un módulo formal', async () => {
      await montar();
      responderTodo();

      const def = q('[data-kpi="incidencias"]')!.getAttribute('title')!;
      expect(def).toContain('denegado o error');
      expect(def).toContain('No es un módulo formal de incidencias');
    });
  });

  // ══════════════════════════════════════
  // Composición
  // ══════════════════════════════════════
  describe('composición', () => {
    it('renderiza todos los bloques de la referencia', async () => {
      await montar();
      responderTodo();

      for (const id of [
        'card-citas-mes', 'card-especialidad', 'card-top-profesionales',
        'card-ultimos-usuarios', 'card-solicitudes', 'card-administradores',
        'card-auditoria', 'card-calendario', 'card-actividad', 'card-institucional'
      ]) {
        expect(q(`[data-testid="${id}"]`), id).toBeTruthy();
      }
      expect(qa('[data-kpi]')).toHaveLength(6);
    });

    it('incluye el calendario institucional y la tarjeta SESAES sin datos ficticios', async () => {
      await montar();
      responderTodo();

      expect(q('[data-testid="card-calendario"] app-superadmin-inicio-calendario')).toBeTruthy();
      const inst = texto('[data-testid="card-institucional"]');
      expect(inst).toContain('SESAES');
      expect(inst).toContain('Salud Estudiantil');
      expect(q('[data-testid="card-institucional"] img')?.getAttribute('alt')).toBeTruthy();
    });

    it('usa Material Symbols Outlined y ninguna otra librería de iconos', async () => {
      await montar();
      responderTodo();

      expect(qa('.material-symbols-outlined').length).toBeGreaterThan(10);
      expect(el.querySelector('i.fa, i[class*="fa-"], .bi, lucide-icon, [class*="lucide"]')).toBeNull();
    });

    it('no contiene datos de ejemplo: sin respuestas del backend no se inventa contenido', async () => {
      await montar();

      expect(component.kpis).toEqual([]);
      expect(component.eventosTabla).toEqual([]);
      expect(component.adminsActivos).toEqual([]);
      expect(qa('[data-testid="evento-auditoria"]')).toHaveLength(0);
      expect(qa('[data-testid="ultimo-usuario"]')).toHaveLength(0);

      responderTodo();
    });
  });
});
