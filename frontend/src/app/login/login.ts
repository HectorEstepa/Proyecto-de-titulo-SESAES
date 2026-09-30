import { Component, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../auth.service';
import { Router } from '@angular/router';
import { rutaDashboardPorRol } from '../shared/auth/role.model';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.html',
  styleUrls: ['./login.css']
})
export class LoginComponent {

  correo = '';
  password = '';
  error = '';
  cargando = false;
  cargandoLento = false;
  private timeoutLento: any;
  recordarme = false;
  mostrarPassword = false;
  errorCorreo = false;

  constructor(private auth: AuthService, private router: Router, private cdr: ChangeDetectorRef) {}

  togglePassword(): void { this.mostrarPassword = !this.mostrarPassword; }

  validarCorreo(): void {
    this.errorCorreo = this.correo.length > 0 && !this.correo.endsWith('@utem.cl');
  }

  onLogin(): void {
    if (this.cargando || !this.correo || !this.password) return;   // evita doble envío con Enter

    this.validarCorreo();
    if (this.errorCorreo) return;

    this.error         = '';
    this.cargando       = true;
    this.cargandoLento  = false;

    // Si la respuesta tarda (ej. el backend en Render estaba "dormido"),
    // avisamos para que no parezca que la app quedó pegada.
    this.timeoutLento = setTimeout(() => {
      this.cargandoLento = true;
      this.cdr.detectChanges();
    }, 4000);

    this.auth.login(this.correo, this.password).subscribe({
      next: (res) => {
        this.auth.guardarSesion(res);
        this.finalizarCarga();
        this.redirigir(res.rol);
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Correo o contraseña incorrectos.';
        this.finalizarCarga();
        this.cdr.detectChanges();
      }
    });
  }

  private finalizarCarga(): void {
    clearTimeout(this.timeoutLento);
    this.cargando      = false;
    this.cargandoLento = false;
    this.cdr.detectChanges();
  }

  private redirigir(rol: string): void {
    const ruta = rutaDashboardPorRol(rol);
    this.router.navigate([ruta ?? '/login']);
  }
}
