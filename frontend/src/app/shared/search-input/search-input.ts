import { Component, Input, OnChanges, forwardRef, isDevMode } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { LucideDynamicIcon, LucideSearch, type LucideIcon } from '@lucide/angular';

let nextAutoId = 0;

/**
 * SESAES — SearchInput (Fase 2.3)
 *
 * ControlValueAccessor real, igual criterio que Input: expone
 * `[(ngModel)]="busqueda"` públicamente pero NO usa `[ngModel]` ni
 * `(ngModelChange)` internamente. Trabaja siempre con `string` (no hay
 * variante numérica). Sin clear button, debounce ni submit automático:
 * la auditoría de Fase 2.3 no encontró evidencia real de esos
 * comportamientos en el proyecto.
 *
 * El `<input>` nativo usa `type="text"` (no `type="search"`) a propósito:
 * varios navegadores dibujan un ícono nativo de "borrar" sobre
 * `type="search"` cuando hay contenido, lo que introduciría un clear
 * button de facto no auditado ni pedido por esta fase. La semántica de
 * "buscar" se expresa igual mediante `role="search"` en el contenedor.
 */
@Component({
  selector: 'app-search-input',
  standalone: true,
  imports: [CommonModule, LucideDynamicIcon],
  templateUrl: './search-input.html',
  styleUrls: ['./search-input.css'],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => SearchInputComponent),
      multi: true,
    },
  ],
})
export class SearchInputComponent implements ControlValueAccessor, OnChanges {
  @Input() label = '';
  @Input() placeholder = 'Buscar...';
  @Input() disabled = false;
  @Input() ariaLabel?: string;
  @Input() id?: string;

  private readonly generatedId = `app-search-input-${nextAutoId++}`;

  /** Puramente decorativo, ver plantilla: aria-hidden="true". */
  readonly lucideSearch: LucideIcon = LucideSearch;

  value = '';

  private onChange: (value: string) => void = () => {};
  private onTouchedFn: () => void = () => {};

  get inputId(): string {
    return this.id ?? this.generatedId;
  }

  get hasVisibleLabel(): boolean {
    return this.label.trim().length > 0;
  }

  get hasAccessibleAriaLabel(): boolean {
    return !!this.ariaLabel?.trim();
  }

  get resolvedAriaLabel(): string | null {
    if (this.hasVisibleLabel) {
      return null;
    }
    return this.hasAccessibleAriaLabel ? this.ariaLabel!.trim() : null;
  }

  onNativeInput(event: Event): void {
    this.value = (event.target as HTMLInputElement).value;
    this.onChange(this.value);
  }

  onBlur(): void {
    this.onTouchedFn();
  }

  writeValue(value: string): void {
    this.value = value == null ? '' : String(value);
  }

  registerOnChange(fn: (value: string) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouchedFn = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled = isDisabled;
  }

  ngOnChanges(): void {
    if (isDevMode() && !this.hasVisibleLabel && !this.hasAccessibleAriaLabel) {
      // eslint-disable-next-line no-console
      console.warn(
        '[app-search-input] SearchInput sin texto de "label" visible ni ' +
          '"ariaLabel": los lectores de pantalla no podrán anunciar su ' +
          'propósito. El "placeholder" no cuenta como nombre accesible. ' +
          'Define "label" o "ariaLabel".'
      );
    }
  }
}
