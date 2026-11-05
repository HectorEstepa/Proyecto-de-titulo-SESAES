import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

// Paleta de colores para el avatar genérico (sin foto), elegida
// determinísticamente a partir del nombre o ID (nunca de una lista fija
// asociada a nombres), para que se mantenga estable con 1.000+ estudiantes
// sin requests adicionales. Mismos 6 tonos y mismo algoritmo (suma de
// charCodes) que citas/admin-citas.css (.av-0..av-5) y
// admin-citas.utils.ts::indiceColorAvatar, para que el mismo estudiante
// se vea con el mismo color en todas las vistas administrativas.
const PALETA_AVATAR = [
  '#0F8A7E', '#7A4FD1', '#B93A76', '#2F7F4F', '#B0590F', '#2F6BBF',
];

@Component({
  selector: 'app-admin-estudiantes',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-estudiantes.html'
})
export class AdminEstudiantesComponent {
  @Input() estudiantesAdmin: any[] = [];
  @Input() estudiantesTotal = 0;
  @Input() estudiantesPagina = 1;
  @Input() estudiantesPorPagina = 20;
  @Input() estudiantesCargando = false;

  @Input() estudiantesFiltroQ = '';
  @Output() estudiantesFiltroQChange = new EventEmitter<string>();

  @Input() estudiantesFiltroCarrera = '';
  @Output() estudiantesFiltroCarreraChange = new EventEmitter<string>();

  @Input() modalPerfilEstudianteAbierto = false;
  @Input() perfilEstudianteCargando = false;
  @Input() fichaEstudianteSeleccionado: any = null;

  // Historial paginado/filtrable dentro de la ficha del estudiante.
  @Input() histEstudianteQ = '';
  @Output() histEstudianteQChange = new EventEmitter<string>();
  @Output() buscarHistorialEstudiante = new EventEmitter<void>();
  @Output() cambiarPaginaHistorialEstudiante = new EventEmitter<number>();

  // Detalle de una cita puntual del historial (sin datos clínicos).
  @Input() modalDetalleCitaEstudianteAbierto = false;
  @Input() citaDetalleEstudiante: any = null;
  @Output() verDetalleCita = new EventEmitter<any>();
  @Output() cerrarDetalleCita = new EventEmitter<void>();

  // Solo se puede cancelar una cita pendiente, y solo con el permiso
  // agenda.gestionar (lo decide el shell; este componente solo oculta
  // el botón si no corresponde).
  @Input() puedeGestionarAgenda = false;
  @Output() cancelarCitaDesdeFicha = new EventEmitter<any>();

  @Output() buscar = new EventEmitter<void>();
  @Output() limpiar = new EventEmitter<void>();
  @Output() cambiarPagina = new EventEmitter<number>();
  @Output() verPerfil = new EventEmitter<any>();
  @Output() cerrarPerfil = new EventEmitter<void>();

  getPaginasEstudiantes(): number[] {
    const total = Math.ceil(this.estudiantesTotal / this.estudiantesPorPagina);
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  minVal(a: number, b: number): number {
    return Math.min(a, b);
  }

  /**
   * Primer nombre + primer apellido (no las dos primeras palabras
   * a secas, no el último apellido). Con nombres compuestos, el
   * primer apellido cae en el punto medio de los tokens
   * redondeando hacia arriba (si el total es impar, la palabra
   * extra queda del lado de los nombres — caso más común de un
   * segundo nombre). Misma regla que
   * citas/admin-citas.utils.ts::inicialesDe:
   *   "María Fernanda García López" -> "MG"
   *   "Juan Carlos Pérez" -> "JP"
   *   "Juan" -> "J"
   *   "" -> "?"
   */
  inicialesDe(nombre: string | null | undefined): string {
    const partes = (nombre ?? '').trim().split(/\s+/).filter(Boolean);
    if (partes.length === 0) return '?';
    if (partes.length === 1) return partes[0][0].toUpperCase();
    const idxApellido = Math.ceil(partes.length / 2);
    return (partes[0][0] + partes[idxApellido][0]).toUpperCase();
  }

  /**
   * Color determinístico del avatar genérico, estable por ID (misma
   * fórmula que citas/admin-citas.utils.ts::indiceColorAvatar).
   */
  colorAvatar(id: number | null | undefined): string {
    if (id === null || id === undefined) return PALETA_AVATAR[0];
    const texto = String(id);
    let suma = 0;
    for (let i = 0; i < texto.length; i++) suma += texto.charCodeAt(i);
    return PALETA_AVATAR[suma % PALETA_AVATAR.length];
  }

  getPaginasHistorial(): number[] {
    const ficha = this.fichaEstudianteSeleccionado;
    if (!ficha) return [];
    const total = Math.ceil((ficha.historial_total || 0) / (ficha.historial_por_pagina || 5));
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  puedeCancelarCita(cita: any): boolean {
    return this.puedeGestionarAgenda && cita?.estado === 'pendiente';
  }
}