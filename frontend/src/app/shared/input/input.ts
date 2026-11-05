import {
  Component,
  Input,
  OnChanges,
  forwardRef,
  isDevMode,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { LucideDynamicIcon, LucideEye, LucideEyeOff, type LucideIcon } from '@lucide/angular';

export type InputType = 'text' | 'email' | 'password' | 'tel' | 'number' | 'date';

/**
 * Valor que maneja el CVA de Input.
 *
 * - Para `type !== 'number'` el valor es siempre `string` (o `null` si el
 *   consumidor externo escribe `null`/`undefined` vía `writeValue`).
 * - Para `type === 'number'` el valor es `number | null`. `null` representa
 *   el campo vacío: igual que el `<input type="number">` nativo usado con
 *   Angular Forms (NumberValueAccessor), un campo vacío NUNCA se convierte
 *   silenciosamente en `0`.
 */
type InputValue = string | number | null;

let nextAutoId = 0;

/**
 * SESAES — Input (Fase 2.3)
 *
 * ControlValueAccessor real: expone `[(ngModel)]="valor"` públicamente
 * (compatible con los ~95 usos existentes en el proyecto) pero NO usa
 * `[ngModel]`/`(ngModelChange)` dentro de su propia plantilla. Internamente
 * trabaja directo contra el `<input>` nativo con `[value]` + `(input)`, y
 * llama `onChange` una sola vez por cada entrada del usuario.
 *
 * Accesibilidad: mismo contrato que Button (Fase 2.2) — nombre accesible
 * vía `<label for>` cuando hay texto visible, o `ariaLabel` cuando no lo
 * hay; `placeholder` nunca cuenta como nombre accesible; sin ninguno de
 * los dos, se advierte solo en desarrollo (isDevMode) sin lanzar
 * excepciones en runtime.
 */
@Component({
  selector: 'app-input',
  standalone: true,
  imports: [CommonModule, LucideDynamicIcon],
  templateUrl: './input.html',
  styleUrls: ['./input.css'],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => InputComponent),
      multi: true,
    },
  ],
})
export class InputComponent implements ControlValueAccessor, OnChanges {
  @Input() label = '';
  @Input() type: InputType = 'text';
  @Input() placeholder = '';
  @Input() disabled = false;
  @Input() readonly = false;
  @Input() required = false;
  @Input() helperText?: string;
  @Input() errorText?: string;
  @Input() autocomplete?: string;
  @Input() ariaLabel?: string;
  @Input() showPasswordToggle = false;
  @Input() id?: string;

  private readonly generatedId = `app-input-${nextAutoId++}`;

  /** Icono decorativo del toggle de contraseña (siempre aria-hidden). */
  readonly lucideEye: LucideIcon = LucideEye;
  readonly lucideEyeOff: LucideIcon = LucideEyeOff;

  /** Valor interno. Ver {@link InputValue}. */
  value: InputValue = null;

  /** Solo aplica cuando `type === 'password' && showPasswordToggle`. */
  passwordVisible = false;

  private onChange: (value: InputValue) => void = () => {};
  private onTouchedFn: () => void = () => {};

  get inputId(): string {
    return this.id ?? this.generatedId;
  }

  /**
   * Solo cuenta como label visible si `label` tiene contenido real más
   * allá de espacios en blanco.
   */
  get hasVisibleLabel(): boolean {
    return this.label.trim().length > 0;
  }

  /**
   * Igual que `hasVisibleLabel` pero para `ariaLabel`: un string de solo
   * espacios ("   ") se considera AUSENTE, no un nombre accesible válido.
   */
  get hasAccessibleAriaLabel(): boolean {
    return !!this.ariaLabel?.trim();
  }

  /**
   * Nombre accesible cuando NO hay label visible. `placeholder` nunca
   * sustituye a esto: no aparece en este getter en absoluto.
   */
  get resolvedAriaLabel(): string | null {
    if (this.hasVisibleLabel) {
      return null;
    }
    return this.hasAccessibleAriaLabel ? this.ariaLabel!.trim() : null;
  }

  get hasError(): boolean {
    return !!this.errorText?.trim();
  }

  get hasHelper(): boolean {
    return !this.hasError && !!this.helperText?.trim();
  }

  get errorId(): string {
    return `${this.inputId}-error`;
  }

  get helperId(): string {
    return `${this.inputId}-helper`;
  }

  /**
   * `aria-describedby`: el error tiene prioridad sobre el helper cuando
   * ambos existen, igual que en la versión anterior aprobada.
   */
  get describedBy(): string | null {
    if (this.hasError) {
      return this.errorId;
    }
    return this.hasHelper ? this.helperId : null;
  }

  get isPasswordToggleVisible(): boolean {
    return this.type === 'password' && this.showPasswordToggle;
  }

  /** Tipo real aplicado al `<input>` nativo (alterna con el toggle). */
  get nativeType(): string {
    if (this.isPasswordToggleVisible && this.passwordVisible) {
      return 'text';
    }
    return this.type;
  }

  get passwordToggleAriaLabel(): string {
    return this.passwordVisible ? 'Ocultar contraseña' : 'Mostrar contraseña';
  }

  /** Valor mostrado en el `<input>` nativo: `null` se muestra como `''`. */
  get displayValue(): string | number {
    return this.value ?? '';
  }

  /**
   * Handler nativo (sin ngModel interno). Llama `onChange` exactamente una
   * vez por entrada del usuario.
   *
   * Para `type === 'number'` replica el comportamiento real del
   * `NumberValueAccessor` de Angular: valor vacío → `null` (NUNCA `0`),
   * valor no vacío → `parseFloat(raw)`. Para el resto de tipos el valor
   * sigue siendo `string`, igual que el `DefaultValueAccessor`.
   */
  onNativeInput(event: Event): void {
    const raw = (event.target as HTMLInputElement).value;

    if (this.type === 'number') {
      this.value = raw === '' ? null : parseFloat(raw);
    } else {
      this.value = raw;
    }

    this.onChange(this.value);
  }

  onBlur(): void {
    this.onTouchedFn();
  }

  togglePasswordVisibility(): void {
    this.passwordVisible = !this.passwordVisible;
  }

  writeValue(value: InputValue): void {
    if (this.type === 'number') {
      this.value = value === undefined ? null : (value as number | null);
    } else {
      this.value = value == null ? '' : String(value);
    }
  }

  registerOnChange(fn: (value: InputValue) => void): void {
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
        '[app-input] Input sin texto de "label" visible ni "ariaLabel": ' +
          'los lectores de pantalla no podrán anunciar su propósito. ' +
          'El "placeholder" no cuenta como nombre accesible. Define ' +
          '"label" o "ariaLabel".'
      );
    }
  }
}
