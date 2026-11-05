import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ProfessionalAyudaComponent } from './professional-ayuda';

describe('ProfessionalAyudaComponent', () => {
  let component: ProfessionalAyudaComponent;
  let fixture: ComponentFixture<ProfessionalAyudaComponent>;

  beforeEach(async () => {
    // Deliberadamente NO se provee HttpClient, Router ni ninguna dependencia
    // de sesión/auth: el componente real de Ayuda no las necesita. Si en el
    // futuro alguien le agrega una llamada HTTP sin actualizar este test,
    // TestBed fallará al crear el componente por falta de un provider.
    await TestBed.configureTestingModule({
      imports: [ProfessionalAyudaComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ProfessionalAyudaComponent);
    component = fixture.componentInstance;
  });

  it('1. crea el componente', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('2. renderiza el contenido principal de Ayuda', () => {
    fixture.detectChanges();
    const texto = (fixture.nativeElement as HTMLElement).textContent || '';
    expect(texto).toContain('Ayuda');
    expect(texto).toContain('Soporte, guías y respuestas para el uso de SESAES');
  });

  it('3. renderiza las subsecciones reales existentes (temas, guías y sidebar)', () => {
    fixture.detectChanges();
    const texto = (fixture.nativeElement as HTMLElement).textContent || '';

    // Explora por temas
    expect(texto).toContain('Explora por temas');
    expect(texto).toContain('Gestión de cuenta');
    expect(texto).toContain('Agenda y citas');
    expect(texto).toContain('Historial clínico');
    expect(texto).toContain('Solicitudes');
    expect(texto).toContain('Configuración');
    expect(texto).toContain('Preguntas frecuentes');

    // Guías y recursos
    expect(texto).toContain('Guías y recursos');
    expect(texto).toContain('Manual de uso para profesionales');
    expect(texto).toContain('Novedades del sistema');
    expect(texto).toContain('Política de privacidad');

    // Sidebar
    expect(texto).toContain('¿Necesitas ayuda personalizada?');
    expect(texto).toContain('Enlaces útiles');
  });

  it('4. no realiza llamadas HTTP (no inyecta HttpClient)', () => {
    // No hay HttpTestingController porque no se provee HttpClient en este
    // test: si el componente intentara inyectarlo, compileComponents/
    // createComponent ya habría fallado. Este test documenta esa garantía.
    expect(() => fixture.detectChanges()).not.toThrow();
  });

  it('banner: se muestra por defecto y puede cerrarse (estado local, sin persistencia)', () => {
    fixture.detectChanges();
    let banner = fixture.nativeElement.querySelector('.ayuda-banner-prof');
    expect(banner).toBeTruthy();
    expect(component.bannerCerrado).toBe(false);

    const cerrarBtn: HTMLButtonElement = fixture.nativeElement.querySelector('.ayuda-banner-cerrar-prof');
    cerrarBtn.click();
    fixture.detectChanges();

    expect(component.bannerCerrado).toBe(true);
    banner = fixture.nativeElement.querySelector('.ayuda-banner-prof');
    expect(banner).toBeFalsy();
  });

  it('temas: al hacer clic en una tarjeta de tema emite navegar con la sección correspondiente', () => {
    fixture.detectChanges();
    const emitidos: string[] = [];
    component.navegar.subscribe((seccion: string) => emitidos.push(seccion));

    const botones: NodeListOf<HTMLElement> = fixture.nativeElement.querySelectorAll('.ayuda-tema-card-prof');
    // Botón "Gestión de cuenta" -> perfil
    botones[0].click();
    // Botón "Agenda y citas" -> horario
    botones[1].click();
    // Botón "Historial clínico" -> historial-clinico
    botones[2].click();
    // Botón "Solicitudes" -> solicitudes
    botones[3].click();

    expect(emitidos).toEqual(['perfil', 'horario', 'historial-clinico', 'solicitudes']);
  });
});
