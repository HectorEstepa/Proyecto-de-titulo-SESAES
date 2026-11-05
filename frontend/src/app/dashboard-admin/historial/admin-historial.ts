import {
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

const PALETA_AVATAR = [
  '#0F8A7E', '#7A4FD1', '#B93A76', '#2F7F4F', '#B0590F', '#2F6BBF',
];

@Component({
  selector: 'app-admin-historial',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-historial.html'
})
export class AdminHistorialComponent implements OnChanges {

  @Input() historialAdmin: any[] = [];
  @Input() especialidades: string[] = [];
  @Input() estadisticasEstudiante: any = null;

  @Input() histFiltroEstudiante = '';
  @Output() histFiltroEstudianteChange = new EventEmitter<string>();

  @Input() histFiltroDesde = '';
  @Output() histFiltroDesdeChange = new EventEmitter<string>();

  @Input() histFiltroHasta = '';
  @Output() histFiltroHastaChange = new EventEmitter<string>();

  @Input() histFiltroEspecialidad = '';
  @Output() histFiltroEspecialidadChange = new EventEmitter<string>();

  @Input() histFiltroEstado = '';
  @Output() histFiltroEstadoChange = new EventEmitter<string>();

  @Input() histFiltroCarrera = '';
  @Output() histFiltroCarreraChange = new EventEmitter<string>();

  @Input() cgrAnio: number | string = new Date().getFullYear();
  @Output() cgrAnioChange = new EventEmitter<number | string>();

  @Input() cgrAniosDisponibles: number[] = [];

  @Input() cgrFechaFin = '';
  @Output() cgrFechaFinChange = new EventEmitter<string>();

  @Input() puedeExportarCgr = false;
  @Input() puedeDescargarPdf = true;

  @Output() aplicarFiltros = new EventEmitter<void>();
  @Output() limpiarFiltros = new EventEmitter<void>();

  @Output() exportarHistorialPdf = new EventEmitter<void>();
  @Output() exportarHistorialExcel = new EventEmitter<void>();

  @Output() exportarCgr = new EventEmitter<void>();
  @Output() exportarAlumnos = new EventEmitter<void>();

  @Output() verDetalle = new EventEmitter<any>();
  @Output() descargarPdf = new EventEmitter<number>();

  pagHist = 1;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['historialAdmin']) {
      this.pagHist = 1;
    }
  }

  get historialPaginado(): any[] {
    return this.historialAdmin.slice(
      (this.pagHist - 1) * 8,
      this.pagHist * 8
    );
  }

  getPaginasHist(): number[] {
    const total = Math.ceil(this.historialAdmin.length / 8);
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  minVal(a: number, b: number): number {
    return Math.min(a, b);
  }

  /**
   * Primer nombre + primer apellido (no las dos primeras palabras
   * a secas, no el último apellido; ver AdminEstudiantesComponent
   * .inicialesDe / citas/admin-citas.utils.ts::inicialesDe para la
   * misma regla).
   */
  inicialesEstudiante(nombre: unknown): string {
    const partes = String(nombre ?? '').trim().split(/\s+/).filter(Boolean);
    if (partes.length === 0) return '?';
    if (partes.length === 1) return partes[0][0].toUpperCase();
    const idxApellido = Math.ceil(partes.length / 2);
    return (partes[0][0] + partes[idxApellido][0]).toUpperCase();
  }

  /** Color determinístico del avatar (misma fórmula que admin-citas.utils.ts). */
  colorAvatar(id: number | null | undefined): string {
    if (id === null || id === undefined) return PALETA_AVATAR[0];
    const texto = String(id);
    let suma = 0;
    for (let i = 0; i < texto.length; i++) suma += texto.charCodeAt(i);
    return PALETA_AVATAR[suma % PALETA_AVATAR.length];
  }
}
