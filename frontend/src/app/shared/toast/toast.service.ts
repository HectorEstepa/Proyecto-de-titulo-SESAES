import { Injectable, signal } from '@angular/core';

export type ToastTipo = 'exito' | 'error' | 'info';

export interface ToastItem {
  id: number;
  tipo: ToastTipo;
  mensaje: string;
}

/**
 * Servicio global de notificaciones tipo "toast". Reemplaza el patrón
 * repetido de `mensajeExito`/`mensajeError` + setTimeout que existía por
 * separado en cada uno de los 3 dashboards, con una sola pieza de UI
 * consistente montada una vez en el componente raíz (app.html).
 */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private contador = 0;
  toasts = signal<ToastItem[]>([]);

  private mostrar(tipo: ToastTipo, mensaje: string, duracionMs: number): void {
    if (!mensaje) return;
    const id = ++this.contador;
    this.toasts.update(lista => [...lista, { id, tipo, mensaje }]);
    setTimeout(() => this.cerrar(id), duracionMs);
  }

  success(mensaje: string, duracionMs = 4000): void { this.mostrar('exito', mensaje, duracionMs); }
  error(mensaje: string, duracionMs = 5000): void { this.mostrar('error', mensaje, duracionMs); }
  info(mensaje: string, duracionMs = 4000): void { this.mostrar('info', mensaje, duracionMs); }

  cerrar(id: number): void {
    this.toasts.update(lista => lista.filter(t => t.id !== id));
  }
}
