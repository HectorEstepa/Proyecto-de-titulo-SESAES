import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LucideDynamicIcon, type LucideIcon } from '@lucide/angular';

/**
 * SESAES — EmptyState (Fase 2.3)
 *
 * Versión aprobada, sin cambios de contrato: `title` requerido,
 * `description` e `icon` opcionales. La acción (botón, link, etc.) no es
 * una prop — se proyecta vía `<ng-content>`, para no acoplar EmptyState a
 * un tipo de acción concreto ni a lógica de navegación/dominio. El ícono,
 * si se provee, es puramente decorativo (`aria-hidden="true"`).
 */
@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [CommonModule, LucideDynamicIcon],
  templateUrl: './empty-state.html',
  styleUrls: ['./empty-state.css'],
})
export class EmptyStateComponent {
  @Input({ required: true }) title!: string;
  @Input() description?: string;
  @Input() icon?: LucideIcon;
}
