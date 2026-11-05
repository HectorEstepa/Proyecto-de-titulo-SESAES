import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BadgeComponent } from '../badge/badge';
import type { BadgeSize, StatusPresentation } from '../status/status-presentation.model';

/**
 * SESAES — StatusBadge (Fase 2.1)
 *
 * Envoltorio delgado sobre <app-badge> que recibe una `StatusPresentation`
 * ya resuelta por un mapper de dominio (cita-status.map.ts,
 * solicitud-horario-status.map.ts, disponibilidad-profesional-status.map.ts,
 * agenda-slot-status.map.ts, ficha-clinica-status.map.ts) y la traduce a
 * las props de Badge. No duplica la implementación visual: toda la
 * presentación (colores, tipografía, espaciado) vive en Badge.
 */
@Component({
  selector: 'app-status-badge',
  standalone: true,
  imports: [CommonModule, BadgeComponent],
  templateUrl: './status-badge.html',
})
export class StatusBadgeComponent {
  @Input({ required: true }) presentation!: StatusPresentation;
  @Input() size: BadgeSize = 'md';
}
