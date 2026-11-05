import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { obtenerFeriado } from '../../shared/feriados-chile';
import { obtenerDiasInternacionales } from '../../shared/dias-internacionales';

export interface CeldaCalendario {
  num: number;
  /** YYYY-MM-DD */
  fecha: string;
  esHoy: boolean;
  feriado: string | null;
  tieneDiasInternacionales: boolean;
}

export const NOMBRES_MES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
];

export const DIAS_SEMANA = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];

const aIso = (anio: number, mes0: number, dia: number): string =>
  `${anio}-${String(mes0 + 1).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;

/**
 * Calendario institucional del Inicio de SUPERADMIN. Solo informativo:
 * feriados de Chile y días internacionales (helpers compartidos ya
 * existentes). NO lee ni duplica la lógica de Agenda (disponibilidad,
 * sobrecupo, bloqueos, jornada, urgencias).
 */
@Component({
  selector: 'app-superadmin-inicio-calendario',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './superadmin-inicio-calendario.html',
  styleUrl: './superadmin-inicio-calendario.css'
})
export class SuperadminInicioCalendarioComponent {
  readonly diasSemana = DIAS_SEMANA;

  anioVisible: number;
  mesVisible: number; // 0-11
  celdas: (CeldaCalendario | null)[] = [];
  diaSeleccionado: string | null = null;

  constructor() {
    const hoy = new Date();
    this.anioVisible = hoy.getFullYear();
    this.mesVisible = hoy.getMonth();
    this.generar();
  }

  get tituloMes(): string {
    return `${NOMBRES_MES[this.mesVisible]} ${this.anioVisible}`;
  }

  generar(): void {
    const primerDia = new Date(this.anioVisible, this.mesVisible, 1);
    const diasEnMes = new Date(this.anioVisible, this.mesVisible + 1, 0).getDate();
    const desfase = (primerDia.getDay() + 6) % 7; // semana parte en lunes

    const hoy = new Date();
    const hoyIso = aIso(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());

    const celdas: (CeldaCalendario | null)[] = Array(desfase).fill(null);

    for (let dia = 1; dia <= diasEnMes; dia++) {
      const fecha = aIso(this.anioVisible, this.mesVisible, dia);
      celdas.push({
        num: dia,
        fecha,
        esHoy: fecha === hoyIso,
        feriado: obtenerFeriado(fecha)?.nombre ?? null,
        tieneDiasInternacionales: obtenerDiasInternacionales(fecha).length > 0
      });
    }

    this.celdas = celdas;
  }

  mesAnterior(): void {
    this.mesVisible--;
    if (this.mesVisible < 0) {
      this.mesVisible = 11;
      this.anioVisible--;
    }
    this.diaSeleccionado = null;
    this.generar();
  }

  mesSiguiente(): void {
    this.mesVisible++;
    if (this.mesVisible > 11) {
      this.mesVisible = 0;
      this.anioVisible++;
    }
    this.diaSeleccionado = null;
    this.generar();
  }

  seleccionar(celda: CeldaCalendario | null): void {
    if (!celda) return;
    this.diaSeleccionado = this.diaSeleccionado === celda.fecha ? null : celda.fecha;
  }

  /** Detalle informativo del día seleccionado. */
  get infoDiaSeleccionado(): string[] {
    if (!this.diaSeleccionado) return [];

    const info: string[] = [];
    const feriado = obtenerFeriado(this.diaSeleccionado);
    if (feriado) info.push(`Feriado: ${feriado.nombre}`);

    for (const dia of obtenerDiasInternacionales(this.diaSeleccionado)) {
      info.push(dia.nombre);
    }
    return info;
  }

  get tituloDiaSeleccionado(): string {
    if (!this.diaSeleccionado) return '';
    const [, mes, dia] = this.diaSeleccionado.split('-').map(Number);
    return `${dia} de ${NOMBRES_MES[mes - 1].toLowerCase()}`;
  }
}
