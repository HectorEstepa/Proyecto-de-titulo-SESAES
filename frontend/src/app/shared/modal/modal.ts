import {
  AfterViewInit,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
  isDevMode,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { LucideDynamicIcon, LucideX, type LucideIcon } from '@lucide/angular';

export type ModalSize = 'sm' | 'md';
export type ModalCloseReason = 'backdrop' | 'escape' | 'close-button';

let nextAutoId = 0;

/**
 * Contador global de "body scroll lock" compartido por TODAS las
 * instancias de Modal (varios modales pueden coexistir, p.ej. un modal
 * que abre otro modal encima). Vive a nivel de módulo a propósito: no es
 * un servicio inyectable porque no hay nada que configurar ni testear en
 * aislamiento más allá de este contador, y evita agregar un provider
 * nuevo al árbol de DI para algo que es, en esencia, un mutex de un solo
 * recurso compartido (document.body.style.overflow).
 */
let scrollLockCount = 0;
let previousBodyOverflow: string | null = null;

function acquireBodyScrollLock(): void {
  if (scrollLockCount === 0) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  scrollLockCount += 1;
}

/** Idempotente: nunca deja el contador en negativo. */
function releaseBodyScrollLock(): void {
  if (scrollLockCount === 0) {
    return;
  }
  scrollLockCount = Math.max(0, scrollLockCount - 1);
  if (scrollLockCount === 0) {
    document.body.style.overflow = previousBodyOverflow ?? '';
    previousBodyOverflow = null;
  }
}

/**
 * SESAES — Modal (Fase 2.4)
 *
 * Envoltorio delgado sobre `<dialog>` nativo (`showModal()` / `close()`).
 * No implementa focus trap manual (el navegador ya lo resuelve al usar
 * `showModal()`) ni overlay/backdrop manual: el backdrop es el
 * `::backdrop` del propio `<dialog>`, y el click-fuera se detecta
 * comparando el elemento sobre el que ocurrió el `pointerdown` con el
 * elemento sobre el que ocurre el `click`, ambos contra `dialogEl` mismo
 * (el `<dialog>` ocupa exactamente el área de su contenido; un click en
 * el backdrop nativo llega con `event.target === dialogEl`).
 *
 * Modal es CONTROLADO: nunca hace `this.open = false` internamente. Toda
 * intención de cierre se comunica vía `closeRequested`; quien lo consume
 * decide si de verdad cierra (y por tanto cambia `open` a `false`).
 */
@Component({
  selector: 'app-modal',
  standalone: true,
  imports: [CommonModule, LucideDynamicIcon],
  templateUrl: './modal.html',
  styleUrls: ['./modal.css'],
})
export class ModalComponent implements OnChanges, AfterViewInit, OnDestroy {
  @Input() open = false;
  @Input() title?: string;
  @Input() ariaLabel?: string;
  @Input() size: ModalSize = 'md';
  @Input() closeOnBackdrop = true;
  @Input() closeOnEscape = true;
  @Input() showCloseButton = true;

  @Output() readonly closeRequested = new EventEmitter<ModalCloseReason>();

  @ViewChild('dialogEl') private readonly dialogRef?: ElementRef<HTMLDialogElement>;

  readonly lucideX: LucideIcon = LucideX;

  private readonly generatedId = `app-modal-${nextAutoId++}`;

  /** Target del `pointerdown` más reciente, usado para distinguir click real de backdrop vs. drag iniciado dentro del contenido. */
  private pointerDownTarget: EventTarget | null = null;

  /** Marca si ESTA instancia sostiene actualmente un lock adquirido (para no liberar de más en ngOnDestroy / onNativeClose). */
  private heldScrollLock = false;

  get titleId(): string {
    return `${this.generatedId}-title`;
  }

  /** Solo cuenta como título visible si `title` tiene contenido real más allá de espacios en blanco. */
  get hasVisibleTitle(): boolean {
    return !!this.title?.trim();
  }

  get hasAccessibleAriaLabel(): boolean {
    return !!this.ariaLabel?.trim();
  }

  get resolvedAriaLabel(): string | null {
    if (this.hasVisibleTitle) {
      return null;
    }
    return this.hasAccessibleAriaLabel ? this.ariaLabel!.trim() : null;
  }

  get resolvedAriaLabelledBy(): string | null {
    return this.hasVisibleTitle ? this.titleId : null;
  }

  ngOnChanges(changes: SimpleChanges): void {
    if ('open' in changes) {
      this.syncNativeDialog();
    }

    if (this.open && isDevMode() && !this.hasVisibleTitle && !this.hasAccessibleAriaLabel) {
      // eslint-disable-next-line no-console
      console.warn(
        '[app-modal] Modal abierto sin "title" visible ni "ariaLabel": los ' +
          'lectores de pantalla no podrán anunciar su propósito. Define ' +
          '"title" o "ariaLabel".'
      );
    }
  }

  /**
   * `ngOnChanges` puede dispararse antes de que la vista (y por tanto
   * `dialogRef`) exista — p.ej. cuando el consumidor pasa `open = true`
   * desde el primer render. Este hook cubre ese caso re-sincronizando
   * una vez que el `<dialog>` nativo ya está disponible.
   */
  ngAfterViewInit(): void {
    this.syncNativeDialog();
  }

  ngOnDestroy(): void {
    const dialogEl = this.dialogRef?.nativeElement;

    if (dialogEl?.open) {
      dialogEl.close();
    }

    this.releaseScrollLockIfHeld();
  }

  /**
   * Sincroniza el estado nativo del `<dialog>` con el `@Input open`
   * controlado. Se apoya en `dialogEl.open` (estado real del navegador)
   * en vez de duplicar un booleano propio.
   */
  private syncNativeDialog(): void {
    const dialogEl = this.dialogRef?.nativeElement;
    if (!dialogEl) {
      return;
    }

    if (this.open && !dialogEl.open) {
      dialogEl.showModal();
      acquireBodyScrollLock();
      this.heldScrollLock = true;
    }

    if (!this.open && dialogEl.open) {
      dialogEl.close();
      this.releaseScrollLockIfHeld();
    }
  }

  private releaseScrollLockIfHeld(): void {
    if (this.heldScrollLock) {
      releaseBodyScrollLock();
      this.heldScrollLock = false;
    }
  }

  /**
   * Handler del evento nativo `close` del `<dialog>`. Puede llegar
   * TARDE (después de que `open` ya haya vuelto a `true` por una
   * reapertura rápida). Por eso nunca libera el lock ciegamente: si el
   * estado controlado actual es `open = true`, reconcilia en vez de
   * asumir que este evento corresponde al cierre más reciente.
   */
  onNativeClose(): void {
    if (this.open) {
      this.syncNativeDialog();
      return;
    }

    this.releaseScrollLockIfHeld();
  }

  /**
   * Evento `cancel` (se dispara con la tecla Escape). Siempre se previene
   * el cierre nativo automático para mantener el modal CONTROLADO; el
   * cierre real solo ocurre si el consumidor responde a
   * `closeRequested` cambiando `open` a `false`.
   */
  onNativeCancel(event: Event): void {
    event.preventDefault();

    if (this.closeOnEscape) {
      this.closeRequested.emit('escape');
    }
  }

  onBackdropPointerDown(event: PointerEvent): void {
    this.pointerDownTarget = event.target;
  }

  /**
   * Solo se considera "click en backdrop real" cuando TANTO el
   * `pointerdown` como el `click` cayeron directamente sobre `dialogEl`
   * (el área fuera de la caja de contenido). Un drag que empieza dentro
   * del contenido y termina fuera no cumple ambas condiciones y por
   * tanto no cierra.
   */
  onBackdropClick(event: MouseEvent): void {
    const dialogEl = this.dialogRef?.nativeElement;
    if (!dialogEl) {
      return;
    }

    const isRealBackdropClick =
      this.pointerDownTarget === dialogEl && event.target === dialogEl;

    this.pointerDownTarget = null;

    if (isRealBackdropClick && this.closeOnBackdrop) {
      this.closeRequested.emit('backdrop');
    }
  }

  onCloseButtonClick(): void {
    this.closeRequested.emit('close-button');
  }
}
