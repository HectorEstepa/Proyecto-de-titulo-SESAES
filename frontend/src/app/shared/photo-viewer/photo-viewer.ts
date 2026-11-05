import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Lightbox simple para ver la foto de perfil en grande al hacer click en ella.
 * Uso:
 *   <app-photo-viewer *ngIf="verFotoAmpliada" [imagenSrc]="fotoPerfilUrl" (cerrar)="verFotoAmpliada = false"></app-photo-viewer>
 */
@Component({
  selector: 'app-photo-viewer',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="viewer-overlay" (click)="cerrar.emit()">
      <button class="viewer-cerrar" (click)="cerrar.emit()" title="Cerrar">✕</button>
      <img [src]="imagenSrc" alt="Foto de perfil ampliada" (click)="$event.stopPropagation()" />
    </div>
  `,
  styles: [`
    .viewer-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,0.75);
      display: flex; align-items: center; justify-content: center;
      z-index: 600; padding: 24px; cursor: zoom-out;
    }
    .viewer-overlay img {
      max-width: min(90vw, 480px);
      max-height: 80vh;
      border-radius: 16px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.4);
      cursor: default;
    }
    .viewer-cerrar {
      position: absolute; top: 20px; right: 24px;
      width: 38px; height: 38px; border-radius: 50%;
      border: none; background: rgba(255,255,255,0.15); color: white;
      font-size: 16px; cursor: pointer; display: flex; align-items: center; justify-content: center;
    }
    .viewer-cerrar:hover { background: rgba(255,255,255,0.25); }
  `]
})
export class PhotoViewerComponent {
  @Input() imagenSrc: string | null = null;
  @Output() cerrar = new EventEmitter<void>();
}
