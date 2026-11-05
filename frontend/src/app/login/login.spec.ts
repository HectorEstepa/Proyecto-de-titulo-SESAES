import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { of } from 'rxjs';

import { LoginComponent } from './login';
import { AuthService, type LoginResponse } from '../auth.service';

describe('LoginComponent', () => {
  let component: LoginComponent;
  let fixture: ComponentFixture<LoginComponent>;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [provideRouter([]), provideHttpClient()],
    }).compileComponents();

    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    router = TestBed.inject(Router);

    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('redirige ADMIN a /dashboard/admin', () => {
    const spy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    (component as any).redirigir('admin');

    expect(spy).toHaveBeenCalledWith(['/dashboard/admin']);
  });

  it('redirige SUPERADMIN al mismo /dashboard/admin', () => {
    const spy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    (component as any).redirigir('superadmin');

    expect(spy).toHaveBeenCalledWith(['/dashboard/admin']);
  });

  it('rol desconocido vuelve a /login', () => {
    const spy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    (component as any).redirigir('rol-invalido');

    expect(spy).toHaveBeenCalledWith(['/login']);
  });

  it('login profesional guarda solo la sesión oficial y redirige', () => {
    const auth = TestBed.inject(AuthService);
    const respuesta: LoginResponse = {
      message: 'ok',
      access_token: 'token-prueba',
      token_type: 'bearer',
      rol: 'profesional',
      id: 15,
      nombre: 'Profesional',
      foto_url: null,
      debe_cambiar_password: false
    };

    vi.spyOn(auth, 'login').mockReturnValue(of(respuesta));
    const guardarSesion = vi.spyOn(auth, 'guardarSesion');
    const navegar = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    localStorage.setItem('prof_db_id', '99');

    component.correo = 'profesional@utem.cl';
    component.password = 'Password1!';
    component.onLogin();

    expect(guardarSesion).toHaveBeenCalledWith(respuesta);
    expect(localStorage.getItem('prof_db_id')).toBeNull();
    expect(navegar).toHaveBeenCalledTimes(1);
  });


});
