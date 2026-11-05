import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Marca de una cita que no es normal: "Sobrecupo" (la agenda el administrador o la secretaría;
 * el estudiante no puede pedirla) o "Urgente". Una cita normal no muestra nada.
 * Los colores son los que el administrador usa en su Agenda para esos mismos tipos.
 */
@Component({
  selector: 'app-tipo-cita-badge',
  standalone: true,
  imports: [CommonModule],
  template: `<span *ngIf="etiqueta" class="tipo-cita" [ngClass]="tipo" [attr.title]="descripcion">{{ etiqueta }}</span>`,
  styles: [`
    .tipo-cita {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 2px 10px;
      font-size: 11px;
      font-weight: 600;
      white-space: nowrap;
      border-radius: 20px;
    }
    .tipo-cita::before {
      content: '';
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: currentColor;
    }
    .tipo-cita.sobrecupo { color: var(--est-sobrecupo); background: var(--est-sobrecupo-tint); }
    .tipo-cita.urgente { color: var(--est-urgente); background: var(--est-urgente-tint); }
  `]
})
export class EstudianteTipoCitaBadgeComponent {
  @Input() tipo: string | null | undefined;

  get etiqueta(): string {
    return this.tipo === 'sobrecupo' ? 'Sobrecupo' : this.tipo === 'urgente' ? 'Urgente' : '';
  }

  get descripcion(): string {
    return this.tipo === 'sobrecupo' ? 'Cita agendada como sobrecupo' : this.tipo === 'urgente' ? 'Atención de urgencia' : '';
  }
}
