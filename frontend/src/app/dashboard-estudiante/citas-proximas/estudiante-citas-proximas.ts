import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { EstudianteTipoCitaBadgeComponent } from '../tipo-cita-badge/estudiante-tipo-cita-badge';

// ══════════════════════════════════════════════════════════════════
// EstudianteCitasProximasComponent — Student 5B (extracción presentacional)
//
// Este componente NO hace HTTP. Recibe las próximas citas ya cargadas
// por DashboardEstudianteComponent vía @Input y solo se encarga de
// renderizarlas, calcular sus estados visuales (vencida / cancelable /
// aviso de cancelación) y avisar al shell (vía @Output) cuando el
// estudiante quiere cancelar una cita o solicitar una nueva — esas
// acciones siguen resolviéndose en el shell porque implican HTTP,
// un modal compartido o navegación.
// ══════════════════════════════════════════════════════════════════
@Component({
  selector: 'app-estudiante-citas-proximas',
  standalone: true,
  imports: [CommonModule, EstudianteTipoCitaBadgeComponent],
  templateUrl: './estudiante-citas-proximas.html',
  styleUrl: './estudiante-citas-proximas.css'
})
export class EstudianteCitasProximasComponent {

  // -- Datos que el shell ya obtuvo del backend --
  @Input() citas: any[] = [];

  // -- Acciones que el shell debe resolver (HTTP, modal o navegación) --
  @Output() cancelar = new EventEmitter<{ index: number; cita: any }>();
  @Output() solicitarNueva = new EventEmitter<void>();

  // -- Lógica puramente visual, exclusiva de esta sección --

  private diffHorasParaCancelar(cita: any): number | null {
    if (!cita.fecha_raw || !cita.hora) return null;
    const horaMatch = cita.hora.match(/(\d{1,2}):(\d{2})/);
    if (!horaMatch) return null;
    const fechaHora = new Date(`${cita.fecha_raw}T${horaMatch[1].padStart(2,'0')}:${horaMatch[2]}:00`);
    return (fechaHora.getTime() - Date.now()) / (1000 * 60 * 60);
  }

  puedeCancelar(cita: any): boolean {
    const diff = this.diffHorasParaCancelar(cita);
    if (diff === null) return true;
    // Igual que el backend: la restricción de "mínimo 5 horas antes" solo
    // aplica si la cita todavía está por venir. Si ya pasó (diff negativo)
    // y sigue "pendiente" porque el profesional no la cerró, el estudiante
    // debe poder cancelarla o reagendar sin quedar atrapado.
    return diff < 0 || diff > 5;
  }

  // true si la cita ya pasó su fecha/hora pero el profesional todavía no
  // la marcó como completada/inasistencia/cancelada — para mostrar un
  // aviso claro en vez de dejarla ahí como si nada, dando a entender que
  // "no asistió" cuando en realidad solo falta que el profesional la cierre.
  citaPendienteVencida(cita: any): boolean {
    const diff = this.diffHorasParaCancelar(cita);
    return diff !== null && diff <= 0;
  }

  avisoCancelacion(cita: any): string {
    const diff = this.diffHorasParaCancelar(cita);
    if (diff === null || diff <= 0) return '';
    const horas = Math.floor(diff); const minutos = Math.round((diff - horas) * 60);
    if (horas === 0) return `Faltan ${minutos} min, no se puede cancelar`;
    if (minutos === 0) return `Faltan ${horas}h, no se puede cancelar`;
    return `Faltan ${horas}h ${minutos}min, no se puede cancelar`;
  }
}
