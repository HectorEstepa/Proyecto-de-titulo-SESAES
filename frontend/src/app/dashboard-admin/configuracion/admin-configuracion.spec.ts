import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AdminConfiguracionComponent } from './admin-configuracion';

describe('AdminConfiguracionComponent', () => {
  let component: AdminConfiguracionComponent;
  let fixture: ComponentFixture<AdminConfiguracionComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminConfiguracionComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(AdminConfiguracionComponent);
    component = fixture.componentInstance;
  });

  it('debe crearse', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('debe cambiar y emitir la pestaña activa', () => {
    const spy = vi.spyOn(component.configTabActivaChange, 'emit');

    component.cambiarTab('seguridad');

    expect(component.configTabActiva).toBe('seguridad');
    expect(spy).toHaveBeenCalledWith('seguridad');
  });

  it('debe mostrar la información general del centro', () => {
    fixture.componentRef.setInput('configCentro', {
      nombre_centro: 'SESAES UTEM',
      telefono: '+56 2 1234 5678',
      direccion: 'Ñuñoa',
      correo_contacto: 'sesaes@utem.cl',
      horario_atencion: '08:00–18:00'
    });

    fixture.componentRef.setInput('configTabActiva', 'general');
        fixture.componentRef.setInput('puedeConfigGeneral', true);
fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(
      'Información del Centro SESAES'
    );
  });

  it('debe emitir las acciones de edición del centro', () => {
    const editarSpy = vi.spyOn(component.habilitarEdicionCentro, 'emit');
    const cancelarSpy = vi.spyOn(component.cancelarEdicionCentro, 'emit');
    const guardarSpy = vi.spyOn(component.guardarInfoCentro, 'emit');

    component.habilitarEdicionCentro.emit();
    component.cancelarEdicionCentro.emit();
    component.guardarInfoCentro.emit();

    expect(editarSpy).toHaveBeenCalledTimes(1);
    expect(cancelarSpy).toHaveBeenCalledTimes(1);
    expect(guardarSpy).toHaveBeenCalledTimes(1);
  });

  it('debe mostrar las reglas de citas y emitir guardado', () => {
    const guardarSpy = vi.spyOn(
      component.guardarConfiguracionCitas,
      'emit'
    );

    fixture.componentRef.setInput('configTabActiva', 'citas');
    fixture.componentRef.setInput('configCitas', {
      duracion_turno_min: 20,
      cupos_por_turno: 4,
      agendamiento_por_pacientes: true,
      cancelacion_instantanea: false,
      sobreturnos_habilitados: true
    });

        fixture.componentRef.setInput('puedeConfigCitas', true);
fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Reglas de citas');

    component.guardarConfiguracionCitas.emit();
    expect(guardarSpy).toHaveBeenCalledTimes(1);
  });

  it('debe mostrar los días cerrados y emitir sus acciones', () => {
    const verSpy = vi.spyOn(component.verCitasDiaCerrado, 'emit');
    const reabrirSpy = vi.spyOn(component.reabrirDiaCerrado, 'emit');
    const crearSpy = vi.spyOn(component.crearDiaCerrado, 'emit');

    const dia = {
      id: 7,
      fecha: '2026-09-18',
      motivo: 'Centro cerrado'
    };

    fixture.componentRef.setInput('configTabActiva', 'horarios');
    fixture.componentRef.setInput('diasCerrados', [dia]);
        fixture.componentRef.setInput('puedeConfigHorarios', true);
fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('2026-09-18');
    expect(fixture.nativeElement.textContent).toContain('Centro cerrado');

    component.verCitasDiaCerrado.emit(dia);
    component.reabrirDiaCerrado.emit(dia);
    component.crearDiaCerrado.emit();

    expect(verSpy).toHaveBeenCalledWith(dia);
    expect(reabrirSpy).toHaveBeenCalledWith(dia);
    expect(crearSpy).toHaveBeenCalledTimes(1);
  });

  it('muestra una sola tabla por pestaña (Estudiantes por defecto, luego Profesionales y Administradores)', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuariosEstudiantes', [
      { id: 1, nombre: 'José Pérez', rut: '11.111.111-1', carrera: 'Kinesiología', activo: true }
    ]);
    fixture.componentRef.setInput('usuariosEstudiantesTotal', 1);
    fixture.componentRef.setInput('usuariosProfesionales', [
      { id: 2, nombre: 'Dra. Bárbara García', rut: '22.222.222-2', especialidad: 'Otorrinolaringología', estado: 'activo' }
    ]);
    fixture.componentRef.setInput('usuariosAdministradores', [
      { id: 3, nombre: 'Admin SESAES', rut: '33.333.333-3', correo: 'admin@sesaes.cl', rol: 'admin', activo: true }
    ]);
    fixture.componentRef.setInput('puedeVerAdministradoresUsuarios', true);
    fixture.detectChanges();

    let texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('José Pérez');
    expect(texto).toContain('11.111.111-1');
    expect(texto).not.toContain('Dra. Bárbara García');
    expect(texto).not.toContain('Admin SESAES');

    fixture.componentRef.setInput('usuariosSubTab', 'profesionales');
    fixture.detectChanges();
    texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Dra. Bárbara García');
    expect(texto).toContain('22.222.222-2');
    expect(texto).not.toContain('José Pérez');

    fixture.componentRef.setInput('usuariosSubTab', 'administradores');
    fixture.detectChanges();
    texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Admin SESAES');
    expect(texto).toContain('33.333.333-3');
  });

  it('el filtro Estado de estudiantes trata un estudiante sin campo activo como Activo (igual que la tabla)', () => {
    fixture.componentRef.setInput('usuariosEstudiantes', [
      { id: 1, nombre: 'Sin campo' },
      { id: 2, nombre: 'Explícito activo', activo: true },
      { id: 3, nombre: 'Inactivo', activo: false }
    ]);
    fixture.componentRef.setInput('usuariosFiltroEstado', 'activo');
    expect(component.estudiantesFiltrados.map(e => e.id)).toEqual([1, 2]);
    fixture.componentRef.setInput('usuariosFiltroEstado', 'inactivo');
    expect(component.estudiantesFiltrados.map(e => e.id)).toEqual([3]);
  });

  it('oculta la sub-pestaña y la sección de Administradores sin el permiso roles.gestionar', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('puedeVerAdministradoresUsuarios', false);
    fixture.componentRef.setInput('usuariosSubTab', 'administradores');
    fixture.componentRef.setInput('usuariosAdministradores', [{ id: 9, nombre: 'Fantasma', correo: 'x@sesaes.cl', rol: 'admin', activo: true }]);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).not.toContain('Fantasma');
  });

  it('el filtro local de búsqueda narrowea profesionales y administradores sin tocar el estado del padre', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuariosProfesionales', [
      { id: 1, nombre: 'Dra. Bárbara García', rut: '1-1', estado: 'activo' },
      { id: 2, nombre: 'Klgo. Andrés Soto', rut: '2-2', estado: 'activo' }
    ]);
    fixture.componentRef.setInput('usuariosBusqueda', 'garcía');
    fixture.detectChanges();

    expect(component.profesionalesFiltrados.length).toBe(1);
    expect(component.profesionalesFiltrados[0].nombre).toContain('García');
  });

  it('seleccionar una fila emite seleccionarUsuarioPerfil con el usuario y el tipo correctos', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuariosSubTab', 'profesionales');
    const prof = { id: 5, nombre: 'Dra. Bárbara García', especialidad: 'Kinesiología' };
    fixture.componentRef.setInput('usuariosProfesionales', [prof]);
    fixture.detectChanges();

    let emitido: any = null;
    component.seleccionarUsuarioPerfil.subscribe((e: any) => (emitido = e));

    const fila: HTMLElement = fixture.nativeElement.querySelector('.usuarios-tabla-wrap table tbody tr');
    fila.click();

    expect(emitido).toEqual({ usuario: prof, tipo: 'profesional' });
  });

  it('el panel de perfil muestra "Horarios y jornada" solo para profesionales y nunca inventa un registro de marcaje', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Dra. Bárbara García' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.componentRef.setInput('perfilTabActiva', 'horarios');
    fixture.componentRef.setInput('puedeVerHorariosPerfil', true);
    fixture.componentRef.setInput('perfilHorarios', []);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('No hay solicitudes de horario aprobadas');
    expect(texto).not.toMatch(/\d{2}:\d{2}\s*[-–]\s*\d{2}:\d{2}.*Hoy/); // nada parecido a un marcaje real inventado
  });

  it('avatar del perfil: usa la foto real cuando existe (foto_url), sin mostrar iniciales', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Dra. Bárbara García', foto_url: 'https://cdn.sesaes.cl/fotos/1.jpg', iniciales: 'BG' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.detectChanges();

    const img: HTMLImageElement = fixture.nativeElement.querySelector('.perfil-avatar-foto');
    expect(img).toBeTruthy();
    expect(img.src).toContain('fotos/1.jpg');
    expect(fixture.nativeElement.querySelector('.perfil-avatar')).toBeFalsy();
  });

  it('avatar del perfil: sin foto_url, muestra las iniciales REALES del profesional (campo iniciales, no recalculadas) sobre su color asignado', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Nombre Distinto', iniciales: 'ZZ', color_identificador: '#123456' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.perfil-avatar-foto')).toBeFalsy();
    const avatar: HTMLElement = fixture.nativeElement.querySelector('.perfil-avatar');
    expect(avatar.textContent?.trim()).toBe('ZZ'); // campo real, no "ND" calculado del nombre
    expect(avatar.style.color).toBe('rgb(18, 52, 86)'); // #123456 → color propio del profesional
  });

  it('avatar del perfil: sin color propio, usa el fallback por especialidad (mismo criterio que Profesionales)', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'X', iniciales: 'XX', especialidad: 'Kinesiología', color_identificador: null });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.detectChanges();

    expect(component.colorAvatarPerfil()).toBe('#D9A441');
  });

  it('avatar del perfil para estudiante/administrador: iniciales calculadas del nombre, sin aplicar el color de profesional', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'José Pérez' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'estudiante');
    fixture.detectChanges();

    const avatar: HTMLElement = fixture.nativeElement.querySelector('.perfil-avatar');
    expect(avatar.textContent?.trim()).toBe('JP');
    expect(avatar.style.background).toBe('');
  });

  it('"Permisos y ausencias": sin ninguno de los dos permisos, no se muestra nada (ni gestión ni panel básico)', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Dra. Bárbara García' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.componentRef.setInput('perfilTabActiva', 'permisos');
    fixture.componentRef.setInput('puedeGestionarAusenciasProfesional', false);
    fixture.componentRef.setInput('puedeVerAusenciasBasicoProfesional', false);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('No tienes permiso para ver esta información');
    expect(texto).not.toContain('Retorno estimado');
    expect(texto).not.toContain('Licencias médicas');
  });

  it('"Permisos y ausencias" — gestión completa (profesionales.gestionar): 4 categorías, visual, sin datos inventados', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Dra. Bárbara García' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.componentRef.setInput('perfilTabActiva', 'permisos');
    fixture.componentRef.setInput('puedeGestionarAusenciasProfesional', true);
    fixture.componentRef.setInput('puedeVerAusenciasBasicoProfesional', false);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Licencias médicas');
    expect(texto).toContain('Permisos administrativos');
    expect(texto).toContain('Faltas');
    expect(texto).toContain('Vacaciones');
    expect(texto).toContain('Sin datos todavía');
    const botones: HTMLButtonElement[] = Array.from(fixture.nativeElement.querySelectorAll('.perfil-ausencia-card .btn-ver-perfil'));
    expect(botones.length).toBeGreaterThan(0);
    expect(botones.every(b => b.disabled)).toBe(true);
  });

  it('"Permisos y ausencias" — panel básico (solo profesionales.ver): estado y retorno estimado, SIN documentos ni suplente', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Dra. Bárbara García' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.componentRef.setInput('perfilTabActiva', 'permisos');
    fixture.componentRef.setInput('puedeGestionarAusenciasProfesional', false);
    fixture.componentRef.setInput('puedeVerAusenciasBasicoProfesional', true);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Retorno estimado');
    expect(texto).not.toContain('Licencias médicas');
    expect(texto).not.toContain('Ver historial');
    expect(texto).not.toContain('suplente');
  });

  it('cuando tiene ambos permisos, prevalece la gestión completa (no el panel reducido)', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Dra. Bárbara García' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.componentRef.setInput('perfilTabActiva', 'permisos');
    fixture.componentRef.setInput('puedeGestionarAusenciasProfesional', true);
    fixture.componentRef.setInput('puedeVerAusenciasBasicoProfesional', true);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Licencias médicas');
    expect(texto).not.toContain('Retorno estimado');
  });

  it('debe mostrar auditoría y emitir filtrado/exportaciones', () => {
    const cargarSpy = vi.spyOn(component.cargarAuditoria, 'emit');
    const excelSpy = vi.spyOn(component.exportarAuditoriaExcel, 'emit');
    const pdfSpy = vi.spyOn(component.exportarAuditoriaPdf, 'emit');

    fixture.componentRef.setInput('configTabActiva', 'seguridad');
    fixture.componentRef.setInput('auditoria', [
      {
        fecha: '2026-08-31T10:00:00',
        accion: 'ACTUALIZAR',
        detalle: 'Cambio de configuración',
        entidad: 'configuracion',
        entidad_id: 1
      }
    ]);

        fixture.componentRef.setInput('puedeVerAuditoria', true);
fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(
      'Cambio de configuración'
    );

    component.cargarAuditoria.emit();
    component.exportarAuditoriaExcel.emit();
    component.exportarAuditoriaPdf.emit();

    expect(cargarSpy).toHaveBeenCalledTimes(1);
    expect(excelSpy).toHaveBeenCalledTimes(1);
    expect(pdfSpy).toHaveBeenCalledTimes(1);
  });

  // ── SA-5: auditoría append-only — regresión de UI destructiva ──────
  it('no debe existir botón "Eliminar seleccionados" en auditoría', () => {
    fixture.componentRef.setInput('configTabActiva', 'seguridad');
    fixture.componentRef.setInput('auditoria', [
      {
        fecha: '2026-08-31T10:00:00',
        accion: 'ACTUALIZAR',
        detalle: 'Cambio de configuración',
        entidad: 'configuracion',
        entidad_id: 1
      }
    ]);
    fixture.componentRef.setInput('puedeVerAuditoria', true);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain(
      'Eliminar seleccionados'
    );
    expect(
      fixture.nativeElement.querySelector('.btn-eliminar-todo-auditoria')
    ).toBeNull();
  });

  it('no debe existir ningún checkbox de selección en la tabla de auditoría', () => {
    fixture.componentRef.setInput('configTabActiva', 'seguridad');
    fixture.componentRef.setInput('auditoria', [
      {
        fecha: '2026-08-31T10:00:00',
        accion: 'ACTUALIZAR',
        detalle: 'Cambio de configuración',
        entidad: 'configuracion',
        entidad_id: 1
      }
    ]);
    fixture.componentRef.setInput('puedeVerAuditoria', true);
    fixture.detectChanges();

    const tabla = fixture.nativeElement.querySelector('.admin-tabla');
    expect(tabla).not.toBeNull();
    expect(tabla.querySelectorAll('input[type="checkbox"]').length).toBe(0);

    const filasEncabezado = tabla.querySelectorAll('thead th');
    expect(filasEncabezado.length).toBe(4);
  });

  it('no debe exponer inputs/outputs de selección o borrado de auditoría', () => {
    expect((component as any).hayAuditoriaSeleccionada).toBeUndefined();
    expect((component as any).auditoriaSeleccionada).toBeUndefined();
    expect((component as any).todaAuditoriaSeleccionada).toBeUndefined();
    expect((component as any).puedeGestionarAuditoria).toBeUndefined();
    expect((component as any).eliminarAuditoriaSeleccionada).toBeUndefined();
    expect((component as any).toggleSeleccionarTodaAuditoria).toBeUndefined();
  });

  it('debe mantener los filtros de auditoría enlazables con el shell', () => {
    const desdeSpy = vi.spyOn(component.auditFiltroDesdeChange, 'emit');
    const hastaSpy = vi.spyOn(component.auditFiltroHastaChange, 'emit');

    component.auditFiltroDesdeChange.emit('2026-08-01');
    component.auditFiltroHastaChange.emit('2026-08-31');

    expect(desdeSpy).toHaveBeenCalledWith('2026-08-01');
    expect(hastaSpy).toHaveBeenCalledWith('2026-08-31');
  });

  // ── Tabla de Usuarios y roles (rediseño según la referencia visual) ──

  it('tabla: cada fila muestra avatar con iniciales (nombre + apellido, sin Dr./Dra.) cuando no hay foto', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuariosSubTab', 'profesionales');
    fixture.componentRef.setInput('usuariosProfesionales', [
      { id: 1, nombre: 'Dra. Valentina Rojas', rut: '9.876.543-3', especialidad: 'Odontología', estado: 'activo' }
    ]);
    fixture.detectChanges();

    const avatar: HTMLElement = fixture.nativeElement.querySelector('.usuarios-tabla-wrap .usuario-avatar');
    expect(avatar.textContent?.trim()).toBe('VR');
  });

  it('tabla: con foto_url usa la imagen real y no muestra iniciales', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuariosSubTab', 'profesionales');
    fixture.componentRef.setInput('usuariosProfesionales', [
      { id: 1, nombre: 'Dra. Valentina Rojas', foto_url: 'https://cdn.sesaes.cl/fotos/1.jpg', estado: 'activo' }
    ]);
    fixture.detectChanges();

    const img: HTMLImageElement = fixture.nativeElement.querySelector('.usuarios-tabla-wrap .usuario-avatar-foto');
    expect(img.src).toContain('fotos/1.jpg');
    expect(fixture.nativeElement.querySelector('.usuarios-tabla-wrap .usuario-avatar')).toBeFalsy();
  });

  it('tabla: el color del avatar de estudiante es determinístico por id (sin requests por fila)', () => {
    expect(component.colorAvatarUsuario({ id: 4 }, 'estudiante')).toBe(component.colorAvatarUsuario({ id: 4 }, 'estudiante'));
    expect(component.colorAvatarUsuario({ id: 1 }, 'estudiante')).not.toBe(component.colorAvatarUsuario({ id: 2 }, 'estudiante'));
  });

  it('tabla: el color del avatar de profesional usa su color asignado y, si no tiene, el fallback por especialidad', () => {
    expect(component.colorAvatarUsuario({ color_identificador: '#123456', especialidad: 'Kinesiología' }, 'profesional')).toBe('#123456');
    expect(component.colorAvatarUsuario({ color_identificador: null, especialidad: 'Kinesiología' }, 'profesional')).toBe('#D9A441');
  });

  it('tabla: la fila del usuario abierto en el panel queda marcada como seleccionada', () => {
    const prof = { id: 7, nombre: 'Dra. Valentina Rojas', estado: 'activo' };
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuariosSubTab', 'profesionales');
    fixture.componentRef.setInput('usuariosProfesionales', [prof, { id: 8, nombre: 'Otro Prof', estado: 'activo' }]);
    fixture.componentRef.setInput('usuarioSeleccionado', prof);
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.detectChanges();

    const filas = fixture.nativeElement.querySelectorAll('.usuarios-tabla-wrap tbody tr');
    expect(filas[0].classList.contains('fila-seleccionada')).toBe(true);
    expect(filas[1].classList.contains('fila-seleccionada')).toBe(false);
  });

  it('tabla: el botón de acciones (⋮) abre el perfil sin disparar el clic de la fila dos veces', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuariosSubTab', 'profesionales');
    const prof = { id: 5, nombre: 'Dra. Bárbara García', especialidad: 'Kinesiología' };
    fixture.componentRef.setInput('usuariosProfesionales', [prof]);
    fixture.detectChanges();

    const emitidos: any[] = [];
    component.seleccionarUsuarioPerfil.subscribe((e: any) => emitidos.push(e));
    (fixture.nativeElement.querySelector('.btn-acciones-fila') as HTMLElement).click();

    expect(emitidos).toEqual([{ usuario: prof, tipo: 'profesional' }]);
  });

  it('pie de estudiantes: "Mostrando a - b de N" sale de la paginación real, no de un valor fijo', () => {
    fixture.componentRef.setInput('usuariosEstudiantes', [{ id: 9 }, { id: 10 }, { id: 11 }]);
    fixture.componentRef.setInput('usuariosEstudiantesTotal', 19);
    fixture.componentRef.setInput('usuariosEstudiantesPorPagina', 8);
    fixture.componentRef.setInput('usuariosEstudiantesPagina', 3);
    expect(component.rangoEstudiantes).toEqual({ desde: 17, hasta: 19 });

    fixture.componentRef.setInput('usuariosEstudiantes', []);
    expect(component.rangoEstudiantes).toEqual({ desde: 0, hasta: 0 });
  });

  it('pie de profesionales: informa cuántos se muestran respecto del total real', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuariosSubTab', 'profesionales');
    fixture.componentRef.setInput('usuariosProfesionales', [
      { id: 1, nombre: 'Dra. Bárbara García', rut: '1-1', estado: 'activo' },
      { id: 2, nombre: 'Klgo. Andrés Soto', rut: '2-2', estado: 'activo' }
    ]);
    fixture.componentRef.setInput('usuariosBusqueda', 'garcía');
    fixture.detectChanges();

    expect((fixture.nativeElement.textContent as string)).toContain('Mostrando 1 de 2 profesionales');
  });

  it('panel de perfil: muestra especialidad y rol en el resumen superior, y el RUT bajo el nombre', () => {
    fixture.componentRef.setInput('configTabActiva', 'usuarios');
    fixture.componentRef.setInput('puedeConfigUsuarios', true);
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Dra. Valentina Rojas', rut: '9.876.543-3', especialidad: 'Odontología' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'profesional');
    fixture.detectChanges();

    const resumen = fixture.nativeElement.querySelector('.perfil-resumen').textContent as string;
    expect(resumen).toContain('Odontología');
    expect(resumen).toContain('Profesional');
    expect(fixture.nativeElement.querySelector('.perfil-identidad-rut').textContent).toContain('9.876.543-3');
  });

  it('panel de perfil: etiqueta el rol de superadmin como Superadministrador', () => {
    fixture.componentRef.setInput('usuarioSeleccionado', { id: 1, nombre: 'Veronica Mendez', rol: 'superadmin' });
    fixture.componentRef.setInput('usuarioSeleccionadoTipo', 'administrador');
    expect(component.etiquetaRolSeleccionado).toBe('Superadministrador');
  });

  it('inicialesNombre ignora el prefijo Dr./Dra. y mantiene el cálculo para nombres sin prefijo', () => {
    expect(component.inicialesNombre('Dra. Valentina Rojas')).toBe('VR');
    expect(component.inicialesNombre('Dr. Carlos Muñoz')).toBe('CM');
    expect(component.inicialesNombre('José Pérez')).toBe('JP');
  });

});
