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
import { coincideBusqueda } from '../../shared/text-normalization';
import { fechaCorta } from '../../shared/formato-fecha';
import type { DocumentoResumen } from '../../shared/documentos-cita/documentos-cita';
import { EstudianteTipoCitaBadgeComponent } from '../tipo-cita-badge/estudiante-tipo-cita-badge';

// ══════════════════════════════════════════════════════════════════
// EstudianteHistorialComponent — sección "Mis atenciones"
//
// Este componente NO hace HTTP. Recibe el historial ya cargado por
// DashboardEstudianteComponent vía @Input y se encarga de calcular
// los indicadores, filtrar localmente su tabla y avisar al shell
// (vía @Output) cuando el estudiante quiere reagendar, ver el detalle
// de una atención o descargar un PDF o un documento: esas acciones
// siguen resolviéndose en el shell porque son compartidas con Inicio
// y/o implican HTTP.
// ══════════════════════════════════════════════════════════════════
@Component({
  selector: 'app-estudiante-historial',
  standalone: true,
  imports: [CommonModule, FormsModule, EstudianteTipoCitaBadgeComponent],
  templateUrl: './estudiante-historial.html',
  styleUrl: './estudiante-historial.css'
})
export class EstudianteHistorialComponent implements OnChanges {

  // -- Datos que el shell ya obtuvo del backend --
  @Input() historial: any[] = [];
  @Input() especialidadesDisponibles: string[] = [];

  // -- Acciones que el shell debe resolver (HTTP, navegación o modal compartido) --
  @Output() reagendar = new EventEmitter<any>();
  @Output() verDetalle = new EventEmitter<any>();
  @Output() descargarPdf = new EventEmitter<number>();
  @Output() descargarDocumento = new EventEmitter<DocumentoResumen>();

  readonly fechaCorta = fechaCorta;

  // -- Filtros locales de esta sección (no se comparten con ninguna otra) --
  filtroBusqueda = '';
  filtroEspecialidad = '';
  filtroFecha = '';

  // Lista efectivamente mostrada en la tabla (todo el historial hasta que
  // se presiona "Filtrar").
  historialMostrado: any[] = [];
  filtrado = false;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['historial']) {
      // Si había un filtro aplicado, se vuelve a aplicar sobre los datos nuevos.
      if (this.filtrado) {
        this.filtrar();
      } else {
        this.historialMostrado = this.historial;
      }
    }
  }

  // ── Indicadores ──
  get totalAtenciones(): number { return this.historial.length; }
  get completadas(): number { return this.historial.filter(h => h.estado === 'completada').length; }
  get canceladas(): number { return this.historial.filter(h => h.estado === 'cancelada').length; }
  get documentosEmitidos(): number {
    return this.historial.reduce((total, h) => total + (h.documentos?.length ?? 0), 0);
  }

  filtrar(): void {
    this.filtrado = true;
    this.historialMostrado = this.historial.filter(h => {
      const matchTexto = !this.filtroBusqueda || coincideBusqueda(this.filtroBusqueda, h.profesional, h.especialidad);
      const matchEsp   = !this.filtroEspecialidad || h.especialidad === this.filtroEspecialidad;
      const matchFecha = !this.filtroFecha || h.fechaRaw === this.filtroFecha;
      return matchTexto && matchEsp && matchFecha;
    });
  }

  limpiarFiltros(): void {
    this.filtroBusqueda = '';
    this.filtroEspecialidad = '';
    this.filtroFecha = '';
    this.filtrado = false;
    this.historialMostrado = this.historial;
  }

  iconoDocumento(d: DocumentoResumen): string {
    return d.tipo === 'receta' ? 'prescriptions' : 'description';
  }

  trackPorDocumento = (_: number, d: DocumentoResumen): number => d.id;
}
