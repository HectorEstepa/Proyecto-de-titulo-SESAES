import { Component, ElementRef, EventEmitter, Input, Output, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

/**
 * Modal reutilizable para recortar una foto de perfil antes de subirla.
 * Se usa igual en los 3 dashboards (admin, profesional, estudiante).
 *
 * Uso:
 *   <app-photo-cropper *ngIf="imagenParaRecortar"
 *     [imagenSrc]="imagenParaRecortar"
 *     (recortada)="onFotoRecortada($event)"
 *     (cancelado)="imagenParaRecortar = null">
 *   </app-photo-cropper>
 */
@Component({
  selector: 'app-photo-cropper',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="cropper-overlay" (click)="onCancelar()">
      <div class="cropper-modal" (click)="$event.stopPropagation()">
        <h3 class="cropper-titulo">Ajusta tu foto de perfil</h3>
        <p class="cropper-desc">Arrastra para mover, usa el control para acercar o alejar.</p>

        <div class="cropper-viewport"
             #viewport
             (mousedown)="onPointerDown($event)"
             (mousemove)="onPointerMove($event)"
             (mouseup)="onPointerUp()"
             (mouseleave)="onPointerUp()"
             (touchstart)="onPointerDown($event)"
             (touchmove)="onPointerMove($event)"
             (touchend)="onPointerUp()">
          <img #imagenRef
               [src]="imagenSrc"
               (load)="onImagenCargada()"
               [style.transform]="'translate(' + offsetX + 'px, ' + offsetY + 'px) scale(' + zoom + ')'"
               [style.width.px]="anchoBase"
               [style.height.px]="altoBase"
               draggable="false"
               alt="Foto a recortar" />
          <div class="cropper-mascara"></div>
        </div>

        <div class="cropper-zoom-row">
          <span class="cropper-zoom-icono">−</span>
          <input type="range" min="1" max="3" step="0.01" [(ngModel)]="zoom" (ngModelChange)="onZoomChange()" />
          <span class="cropper-zoom-icono">+</span>
        </div>

        <div class="cropper-acciones">
          <button type="button" class="cropper-btn-cancelar" (click)="onCancelar()">Cancelar</button>
          <button type="button" class="cropper-btn-confirmar" (click)="onConfirmar()">Usar esta foto</button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .cropper-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,0.55);
      display: flex; align-items: center; justify-content: center;
      z-index: 500; padding: 16px;
    }
    .cropper-modal {
      background: #fff; border-radius: 16px; padding: 24px;
      width: 340px; max-width: 100%;
      box-shadow: 0 20px 60px rgba(0,0,0,0.25);
    }
    .cropper-titulo { margin: 0 0 4px; font-size: 16px; color: #1e293b; }
    .cropper-desc { margin: 0 0 16px; font-size: 12px; color: #64748b; }
    .cropper-viewport {
      position: relative; width: 240px; height: 240px; margin: 0 auto 16px;
      overflow: hidden; border-radius: 50%; background: #f1f5f9;
      cursor: grab; touch-action: none; user-select: none;
    }
    .cropper-viewport:active { cursor: grabbing; }
    .cropper-viewport img { position: absolute; top: 0; left: 0; transform-origin: 0 0; pointer-events: none; }
    .cropper-mascara {
      position: absolute; inset: 0; border-radius: 50%;
      box-shadow: 0 0 0 2000px rgba(0,0,0,0.35) inset;
      pointer-events: none;
    }
    .cropper-zoom-row { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
    .cropper-zoom-row input[type="range"] { flex: 1; accent-color: #0d9488; }
    .cropper-zoom-icono { font-size: 16px; color: #94a3b8; width: 14px; text-align: center; }
    .cropper-acciones { display: flex; gap: 10px; }
    .cropper-btn-cancelar {
      flex: 1; padding: 10px; border: 1.5px solid #e2e8f0; border-radius: 8px;
      background: white; color: #64748b; font-size: 13px; cursor: pointer;
    }
    .cropper-btn-confirmar {
      flex: 1; padding: 10px; border: none; border-radius: 8px;
      background: #0d9488; color: white; font-size: 13px; font-weight: 600; cursor: pointer;
    }
    .cropper-btn-confirmar:hover { background: #0f766e; }

    body.tema-oscuro .cropper-modal,
    .dashboard.tema-oscuro .cropper-modal,
    .dashboard-prof.tema-oscuro .cropper-modal {
      background: #242f42;
    }
    body.tema-oscuro .cropper-titulo,
    .dashboard.tema-oscuro .cropper-titulo,
    .dashboard-prof.tema-oscuro .cropper-titulo { color: #e6edf3; }
    body.tema-oscuro .cropper-btn-cancelar,
    .dashboard.tema-oscuro .cropper-btn-cancelar,
    .dashboard-prof.tema-oscuro .cropper-btn-cancelar {
      background: #2d3b52; border-color: #3a4a63; color: #8b96a8;
    }
  `]
})
export class PhotoCropperComponent {
  @Input() imagenSrc: string | null = null;
  @Input() tamanoSalida = 400; // px del cuadrado final exportado
  @Output() recortada = new EventEmitter<string>();
  @Output() cancelado = new EventEmitter<void>();

  @ViewChild('viewport') viewportRef!: ElementRef<HTMLDivElement>;
  @ViewChild('imagenRef') imagenElRef!: ElementRef<HTMLImageElement>;

  readonly contenedorTam = 240;

  zoom = 1;
  offsetX = 0;
  offsetY = 0;
  anchoBase = 0;
  altoBase = 0;

  private arrastrando = false;
  private inicioX = 0;
  private inicioY = 0;
  private offsetInicioX = 0;
  private offsetInicioY = 0;

  onImagenCargada(): void {
    const img = this.imagenElRef.nativeElement;
    const naturalW = img.naturalWidth  || 1;
    const naturalH = img.naturalHeight || 1;
    // Escala base: la imagen cubre completamente el círculo, sin dejar bordes vacíos
    const escalaBase = Math.max(this.contenedorTam / naturalW, this.contenedorTam / naturalH);
    this.anchoBase = naturalW * escalaBase;
    this.altoBase  = naturalH * escalaBase;
    this.zoom = 1;
    this.offsetX = 0;
    this.offsetY = 0;
  }

  private coordsEvento(ev: MouseEvent | TouchEvent): { x: number; y: number } {
    if (ev instanceof TouchEvent) {
      const t = ev.touches[0] || ev.changedTouches[0];
      return { x: t.clientX, y: t.clientY };
    }
    return { x: ev.clientX, y: ev.clientY };
  }

  onPointerDown(ev: MouseEvent | TouchEvent): void {
    ev.preventDefault();
    this.arrastrando = true;
    const { x, y } = this.coordsEvento(ev);
    this.inicioX = x; this.inicioY = y;
    this.offsetInicioX = this.offsetX; this.offsetInicioY = this.offsetY;
  }

  onPointerMove(ev: MouseEvent | TouchEvent): void {
    if (!this.arrastrando) return;
    ev.preventDefault();
    const { x, y } = this.coordsEvento(ev);
    this.offsetX = this.offsetInicioX + (x - this.inicioX);
    this.offsetY = this.offsetInicioY + (y - this.inicioY);
    this.clampOffsets();
  }

  onPointerUp(): void {
    this.arrastrando = false;
  }

  onZoomChange(): void {
    this.clampOffsets();
  }

  private clampOffsets(): void {
    const dispW = this.anchoBase * this.zoom;
    const dispH = this.altoBase  * this.zoom;
    const maxX = Math.max(0, (dispW - this.contenedorTam) / 2);
    const maxY = Math.max(0, (dispH - this.contenedorTam) / 2);
    this.offsetX = Math.min(maxX, Math.max(-maxX, this.offsetX));
    this.offsetY = Math.min(maxY, Math.max(-maxY, this.offsetY));
  }

  onCancelar(): void {
    this.cancelado.emit();
  }

  onConfirmar(): void {
    const img = this.imagenElRef.nativeElement;
    const dispW = this.anchoBase * this.zoom;
    const dispH = this.altoBase  * this.zoom;
    const escalaFactor = dispW / (img.naturalWidth || 1);

    const imgLeft = this.contenedorTam / 2 - dispW / 2 + this.offsetX;
    const imgTop  = this.contenedorTam / 2 - dispH / 2 + this.offsetY;

    const srcX = -imgLeft / escalaFactor;
    const srcY = -imgTop  / escalaFactor;
    const srcSize = this.contenedorTam / escalaFactor;

    const canvas = document.createElement('canvas');
    canvas.width = this.tamanoSalida;
    canvas.height = this.tamanoSalida;
    const ctx = canvas.getContext('2d');
    if (!ctx) { this.cancelado.emit(); return; }

    ctx.drawImage(img, srcX, srcY, srcSize, srcSize, 0, 0, this.tamanoSalida, this.tamanoSalida);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
    this.recortada.emit(dataUrl);
  }
}
