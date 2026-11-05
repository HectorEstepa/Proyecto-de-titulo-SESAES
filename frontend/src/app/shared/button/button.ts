import {
  Component,
  HostBinding,
  Input,
  OnChanges,
  isDevMode,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { LucideDynamicIcon, type LucideIcon } from '@lucide/angular';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md';
export type ButtonType = 'button' | 'submit';

/**
 * SESAES — Button (Fase 2.2)
 *
 * Botón compartido para los tres dashboards. Renderiza un <button> nativo
 * real; toda la lógica de negocio (guardar, cancelar, navegar, etc.) sigue
 * viviendo en quien lo consume.
 *
 * Accesibilidad:
 * - El nombre accesible siempre sale del propio <button>: si hay texto
 *   visible (`label` no vacío/no solo-espacios), ese texto es el nombre
 *   accesible. Si no hay texto visible, se usa `[attr.aria-label]="ariaLabel"`.
 * - TODOS los íconos visuales (icon normal, icon en icon-only, spinner de
 *   loading) son puramente decorativos: `aria-hidden="true"` siempre, sin
 *   condicionarlo a si hay label visible o no.
 * - `loading` fija `aria-busy="true"`, `disabled` real (evita doble envío) y
 *   conserva el nombre accesible (label visible o ariaLabel), tanto si el
 *   botón tiene texto como si es icon-only.
 * - Si no hay label visible NI ariaLabel, se advierte solo en desarrollo
 *   (isDevMode) vía console.warn; no se lanza ninguna excepción en runtime.
 *
 * fullWidth se resuelve a nivel de :host (ver button.css) porque
 * <app-button> es un custom element que por defecto puede seguir
 * comportándose como elemento inline; no basta con width:100% en el
 * <button> interno.
 */
@Component({
  selector: 'app-button',
  standalone: true,
  imports: [CommonModule, LucideDynamicIcon],
  templateUrl: './button.html',
  styleUrls: ['./button.css'],
})
export class ButtonComponent implements OnChanges {
  @Input() label = '';
  @Input() variant: ButtonVariant = 'primary';
  @Input() size: ButtonSize = 'md';
  @Input() icon?: LucideIcon;
  @Input() disabled = false;
  @Input() loading = false;
  @Input() fullWidth = false;
  @Input() type: ButtonType = 'button';
  @Input() ariaLabel?: string;

  @HostBinding('class.app-button--full-width')
  get hostFullWidth(): boolean {
    return this.fullWidth;
  }

  /**
   * Considera texto accesible solo si `label` tiene contenido real más
   * allá de espacios en blanco (un string de solo espacios no cuenta como
   * nombre accesible).
   */
  get hasVisibleLabel(): boolean {
    return this.label.trim().length > 0;
  }

  /**
   * Igual que `hasVisibleLabel` pero para `ariaLabel`: un string de solo
   * espacios ("   ") no cuenta como nombre accesible válido.
   */
  get hasAccessibleAriaLabel(): boolean {
    return !!this.ariaLabel?.trim();
  }

  /**
   * Nombre accesible cuando NO hay texto visible: solo entonces se aplica
   * `ariaLabel` (recortado) como atributo `aria-label` del <button>. Cuando
   * hay texto visible, el propio texto ya es el nombre accesible y no debe
   * duplicarse con aria-label. Un `ariaLabel` de solo espacios se trata
   * como ausente.
   */
  get resolvedAriaLabel(): string | null {
    if (this.hasVisibleLabel) {
      return null;
    }
    return this.hasAccessibleAriaLabel ? this.ariaLabel!.trim() : null;
  }

  get isDisabled(): boolean {
    return this.disabled || this.loading;
  }

  ngOnChanges(): void {
    if (isDevMode() && !this.hasVisibleLabel && !this.hasAccessibleAriaLabel) {
      // eslint-disable-next-line no-console
      console.warn(
        '[app-button] Botón sin texto visible ni "ariaLabel": los lectores ' +
          'de pantalla no podrán anunciar su propósito. Define "label" o ' +
          '"ariaLabel".'
      );
    }
  }
}
