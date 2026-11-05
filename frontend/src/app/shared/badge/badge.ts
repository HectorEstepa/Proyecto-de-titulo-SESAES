import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LucideDynamicIcon, type LucideIcon } from '@lucide/angular';
import type { BadgeTone, BadgeSize } from '../status/status-presentation.model';

/**
 * SESAES — Badge (Fase 2.1)
 *
 * Componente visual genérico para mostrar una etiqueta corta con un tono
 * semántico (success/info/warning/danger/lavender/neutral) y un ícono
 * opcional. No conoce estados de negocio: recibe `label`, `tone` e `icon`
 * ya resueltos por quien lo use (por ejemplo, StatusBadge).
 *
 * - Usa exclusivamente tokens.css (--tone-*, --space-*, --radius-*,
 *   --font-*). Cero valores hex nuevos.
 * - Ancho natural (inline-flex); nunca `width: 100%` por defecto.
 * - Sin `text-overflow: ellipsis` ni recorte de texto: labels largos como
 *   "Fuera de horario" se muestran completos, con `white-space: nowrap`.
 * - El ícono es decorativo cuando hay texto visible (`aria-hidden="true"`),
 *   ya que el label ya comunica la información a lectores de pantalla.
 */
@Component({
  selector: 'app-badge',
  standalone: true,
  imports: [CommonModule, LucideDynamicIcon],
  templateUrl: './badge.html',
  styleUrls: ['./badge.css'],
})
export class BadgeComponent {
  @Input() label = '';
  @Input() tone: BadgeTone = 'neutral';
  @Input() size: BadgeSize = 'md';
  @Input() icon?: LucideIcon;
}
