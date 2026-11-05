import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-professional-ayuda',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './professional-ayuda.html',
  styleUrl: './professional-ayuda.css'
})
export class ProfessionalAyudaComponent {

  // Estado local: solo controla si el banner superior de bienvenida está visible.
  // No se persiste ni se comparte con ninguna otra sección.
  bannerCerrado = false;

  // La navegación entre secciones sigue siendo responsabilidad del shell
  // (dashboard-profesional.ts posee seccionActiva y navegarA()).
  // Este componente solo emite la intención de navegar.
  @Output() navegar = new EventEmitter<string>();

  irA(seccion: string): void {
    this.navegar.emit(seccion);
  }
}
