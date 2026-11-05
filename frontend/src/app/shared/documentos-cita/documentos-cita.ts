import { ChangeDetectorRef, Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../config';
import { guardarBlob, mensajeErrorDescarga } from '../descarga-archivo';

const API = environment.apiUrl;

export interface DocumentoResumen {
  id: number;
  tipo: string;
  nombre_tipo: string;
  folio: string;
  estado: 'vigente' | 'anulado' | string;
}

/**
 * Documentos clínicos emitidos en una atención (receta y justificativo).
 *
 * Lo usan el estudiante (solo descarga) y el profesional (descarga y anulación
 * con motivo). El PDF se pide con HttpClient —no con un enlace— porque el
 * endpoint exige sesión y el interceptor adjunta el Bearer.
 */
@Component({
  selector: 'app-documentos-cita',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './documentos-cita.html',
  styleUrls: ['./documentos-cita.css']
})
export class DocumentosCitaComponent {

  @Input() documentos: DocumentoResumen[] = [];
  /** El profesional emisor puede anular; el estudiante solo descarga. */
  @Input() modoProfesional = false;
  /** Se emite tras anular, para que el padre recargue sus datos. */
  @Output() cambio = new EventEmitter<void>();

  descargando: number | null = null;
  anulando: DocumentoResumen | null = null;
  motivo = '';
  enviando = false;
  error = '';

  constructor(private http: HttpClient, private cdr: ChangeDetectorRef) {}

  descargar(d: DocumentoResumen): void {
    if (this.descargando !== null) return;
    this.error = '';
    this.descargando = d.id;
    this.http.get(`${API}/documentos/${d.id}/pdf`, { responseType: 'blob' }).subscribe({
      next: (blob) => {
        guardarBlob(blob, `${d.folio}.pdf`);
        this.descargando = null;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.error = mensajeErrorDescarga(err?.status);
        this.descargando = null;
        this.cdr.detectChanges();
      }
    });
  }

  pedirAnulacion(d: DocumentoResumen): void {
    this.anulando = d;
    this.motivo = '';
    this.error = '';
  }

  cancelarAnulacion(): void { this.anulando = null; this.motivo = ''; }

  get motivoValido(): boolean { return this.motivo.trim().length >= 3; }

  confirmarAnulacion(): void {
    const d = this.anulando;
    if (!d || !this.motivoValido || this.enviando) return;
    this.enviando = true;
    this.error = '';
    this.http.post(`${API}/documentos/${d.id}/anular`, { motivo: this.motivo.trim() }).subscribe({
      next: () => {
        d.estado = 'anulado';
        this.enviando = false;
        this.anulando = null;
        this.cambio.emit();
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.error = typeof err?.error?.detail === 'string' ? err.error.detail : 'No se pudo anular el documento. Inténtalo de nuevo.';
        this.enviando = false;
        this.cdr.detectChanges();
      }
    });
  }
}
