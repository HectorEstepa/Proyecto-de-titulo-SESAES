import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ToastService } from './toast.service';

@Component({
  selector: 'app-toast',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './toast.html',
  styleUrls: ['./toast.css']
})
export class ToastComponent {
  constructor(public toastService: ToastService) {}

  icono(tipo: string): string {
    return tipo === 'exito' ? '✓' : tipo === 'error' ? '!' : 'ℹ';
  }
}
