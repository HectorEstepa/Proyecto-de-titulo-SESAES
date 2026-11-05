import { ChangeDetectorRef, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { environment } from '../config';

type EstadoValidacion = 'vigente' | 'anulado' | 'modificado' | 'no_encontrado';

interface ResultadoValidacion {
  valido: boolean;
  estado: EstadoValidacion;
  tipo?: string;
  emitido_por?: string;
  fecha_emision?: string;
  estudiante?: string;
}

/**
 * Pantalla PÚBLICA (sin sesión) para comprobar la autenticidad de una receta o
 * un justificativo. Se abre desde el botón del login o escaneando el QR del
 * PDF (que trae ?codigo=...). Solo muestra los datos que el backend entrega:
 * tipo, profesional, fecha y nombre enmascarado del estudiante.
 */
@Component({
  selector: 'app-validar-documento',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './validar-documento.html',
  styleUrls: ['./validar-documento.css']
})
export class ValidarDocumentoComponent implements OnInit, OnDestroy {

  codigo = '';
  cargando = false;
  resultado: ResultadoValidacion | null = null;
  errorRed = '';

  // Escáner de QR (solo donde el navegador tiene BarcodeDetector)
  escaneando = false;
  errorCamara = '';
  @ViewChild('video') videoRef?: ElementRef<HTMLVideoElement>;
  private stream: MediaStream | null = null;
  private timerEscaneo: any;

  constructor(
    private http: HttpClient,
    private route: ActivatedRoute,
    private router: Router,
    private cdr: ChangeDetectorRef
  ) {}

  get escanerDisponible(): boolean {
    return typeof (window as any).BarcodeDetector !== 'undefined'
      && !!navigator.mediaDevices?.getUserMedia;
  }

  ngOnInit(): void {
    const desdeUrl = this.route.snapshot.queryParamMap.get('codigo');
    if (desdeUrl) {
      this.codigo = desdeUrl.toUpperCase();
      this.validar();
    }
  }

  ngOnDestroy(): void { this.detenerEscaner(); }

  onCodigoChange(valor: string): void {
    this.codigo = (valor || '').toUpperCase();
    this.resultado = null;
    this.errorRed = '';
  }

  validar(): void {
    const codigo = this.codigo.trim();
    if (!codigo || this.cargando) return;

    this.cargando = true;
    this.resultado = null;
    this.errorRed = '';

    this.http.get<ResultadoValidacion>(
      `${environment.apiUrl}/documentos/validar/${encodeURIComponent(codigo)}`
    ).subscribe({
      next: (res) => {
        this.resultado = res;
        this.cargando = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.errorRed = err?.status === 429
          ? 'Hiciste demasiadas consultas seguidas. Espera un minuto e inténtalo de nuevo.'
          : 'No pudimos validar el documento. Revisa tu conexión e inténtalo de nuevo.';
        this.cargando = false;
        this.cdr.detectChanges();
      }
    });
  }

  // ── Escáner QR ──────────────────────────────────────────────────────
  async iniciarEscaner(): Promise<void> {
    this.errorCamara = '';
    if (!this.escanerDisponible) {
      this.errorCamara = 'Tu navegador no permite escanear desde aquí. Usa la cámara de tu teléfono: el QR abre esta página con el código ya cargado.';
      return;
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    } catch {
      this.errorCamara = 'No pudimos acceder a la cámara. Revisa los permisos o ingresa el código a mano.';
      this.cdr.detectChanges();
      return;
    }
    this.escaneando = true;
    this.cdr.detectChanges();

    const video = this.videoRef?.nativeElement;
    if (!video) { this.detenerEscaner(); return; }
    video.srcObject = this.stream;
    await video.play().catch(() => {});

    const detector = new (window as any).BarcodeDetector({ formats: ['qr_code'] });
    this.timerEscaneo = setInterval(async () => {
      try {
        const codigos = await detector.detect(video);
        if (codigos.length) {
          const leido = this.extraerCodigo(codigos[0].rawValue);
          if (leido) {
            this.detenerEscaner();
            this.codigo = leido;
            this.validar();
          }
        }
      } catch { /* un frame fallido no es un error: se reintenta */ }
    }, 400);
  }

  detenerEscaner(): void {
    clearInterval(this.timerEscaneo);
    this.stream?.getTracks().forEach(t => t.stop());
    this.stream = null;
    this.escaneando = false;
    this.cdr.detectChanges();
  }

  /** El QR trae una URL con ?codigo=...; también se acepta el código suelto. */
  private extraerCodigo(valor: string): string {
    try {
      const url = new URL(valor);
      return (url.searchParams.get('codigo') || '').toUpperCase();
    } catch {
      return (valor || '').trim().toUpperCase();
    }
  }

  get titulo(): string {
    switch (this.resultado?.estado) {
      case 'vigente':       return 'Documento válido';
      case 'anulado':       return 'Documento anulado';
      case 'modificado':    return 'Documento no válido';
      case 'no_encontrado': return 'Código no encontrado';
      default:              return '';
    }
  }

  get mensaje(): string {
    switch (this.resultado?.estado) {
      case 'anulado':       return 'El profesional anuló este documento. No tiene validez.';
      case 'modificado':    return 'El contenido no coincide con el que se emitió originalmente. No lo aceptes.';
      case 'no_encontrado': return 'Revisa que el código esté bien escrito. Si el error persiste, el documento no fue emitido por SESAES.';
      default:              return '';
    }
  }

  fechaLegible(iso?: string): string {
    if (!iso) return '—';
    const [a, m, d] = iso.split('-').map(Number);
    const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
    return `${String(d).padStart(2, '0')} de ${meses[m - 1]} de ${a}`;
  }
}
