import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export type CardPadding = 'sm' | 'md' | 'lg';
export type CardVariant = 'default' | 'elevated';

/**
 * SESAES — Card (Fase 2.2)
 *
 * Contenedor visual pasivo y genérico, equivalente a los patrones reales
 * `.card` / `.card-prof` ya usados en los tres dashboards. Solo resuelve
 * padding, elevación (sombra), color de superficie y dark mode.
 *
 * No es un botón ni simula uno: las cards clickeables reales del sistema
 * ya son elementos <button> nativos por su cuenta (ver por ejemplo
 * `.ayuda-tema-card-prof` y `.atencion-card-prof`), así que Card no
 * necesita (ni debe tener) una variante `interactive`. Composiciones
 * futuras (KPI, stat cards por rol, etc.) se resuelven envolviendo este
 * componente, no extendiendo su API.
 */
@Component({
  selector: 'app-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './card.html',
  styleUrls: ['./card.css'],
})
export class CardComponent {
  @Input() padding: CardPadding = 'md';
  @Input() variant: CardVariant = 'default';
}
