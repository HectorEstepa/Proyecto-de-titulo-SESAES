import { ChangeDetectorRef, Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../config';

const API = environment.apiUrl;

/**
 * Cuestionario de antecedentes previo a la atención: es OPCIONAL y lo decide
 * el profesional. Puede enviarlo o no a ESTE estudiante, o fijar un ajuste
 * general para todos sus pacientes (la decisión puntual gana sobre el ajuste).
 */
@Component({
  selector: 'app-cuestionario-opcional',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './cuestionario-opcional.html',
  styleUrls: ['./cuestionario-opcional.css']
})
export class CuestionarioOpcionalComponent implements OnInit {

  @Input({ required: true }) profId!: number;
  @Input({ required: true }) estudianteId!: number;
  /** Estado real que informa el backend: ¿este estudiante lo recibirá? */
  @Input() solicitado = false;
  /** El estudiante ya tiene ficha de antecedentes: no hay nada que enviar. */
  @Input() yaExiste = false;
  /** Se emite tras cambiar algo, para que el padre recargue la ficha. */
  @Output() cambio = new EventEmitter<void>();

  porDefecto = false;
  cargandoAjuste = true;
  guardando = false;
  error = '';

  constructor(private http: HttpClient, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.http.get<{ enviar_por_defecto: boolean }>(`${API}/historial-clinico/config-cuestionario/${this.profId}`).subscribe({
      next: (r) => { this.porDefecto = !!r.enviar_por_defecto; this.cargandoAjuste = false; this.cdr.detectChanges(); },
      error: () => { this.cargandoAjuste = false; this.cdr.detectChanges(); }
    });
  }

  private ejecutar(peticion: any, alExito?: () => void): void {
    if (this.guardando) return;
    this.guardando = true;
    this.error = '';
    peticion.subscribe({
      next: () => {
        this.guardando = false;
        alExito?.();
        this.cambio.emit();
        this.cdr.detectChanges();
      },
      error: (err: any) => {
        this.guardando = false;
        this.error = typeof err?.error?.detail === 'string' ? err.error.detail : 'No se pudo guardar el cambio. Inténtalo de nuevo.';
        this.cdr.detectChanges();
      }
    });
  }

  private get ruta(): string { return `${API}/historial-clinico/${this.profId}/${this.estudianteId}/cuestionario`; }

  enviar(): void { this.ejecutar(this.http.put(this.ruta, { solicitar: true })); }
  noEnviar(): void { this.ejecutar(this.http.put(this.ruta, { solicitar: false })); }
  usarAjusteGeneral(): void { this.ejecutar(this.http.delete(this.ruta)); }

  cambiarAjusteGeneral(valor: boolean): void {
    this.ejecutar(
      this.http.put(`${API}/historial-clinico/config-cuestionario/${this.profId}`, { enviar_por_defecto: valor }),
      () => { this.porDefecto = valor; }
    );
  }
}
