import { ChangeDetectorRef, Component, EventEmitter, Input, OnDestroy, OnInit, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../config';

const API = environment.apiUrl;

export const CAP_MEDICAMENTO_SUMINISTRADO = 'registrar_medicamento_suministrado';
export const CAP_RECETA = 'emitir_receta';
export const CAP_JUSTIFICATIVO = 'emitir_justificativo';

export interface PacienteAtencion { nombre: string; rut?: string; carrera?: string; }

export interface ItemReceta {
  medicamento: string; dosis: string; via: string; frecuencia: string; periodo: string;
  cantidad: string; marca: string; indicacion: string;
}

export interface DocumentoEmitido { id: number; tipo: string; nombre_tipo: string; folio: string; }

interface Borrador {
  observaciones: string; medicamento: string;
  recetaActiva: boolean; items: ItemReceta[];
  justActiva: boolean; just: FormJustificativo;
}

interface FormJustificativo {
  modalidad: 'Presencial' | 'Remota';
  tipo_atencion: 'Consulta' | 'Control' | 'Urgencia';
  motivo_consulta: string;
  reposo: boolean; reposo_desde: string; reposo_hasta: string;
  restricciones: string; control_sugerido: string; observaciones: string;
}

const MAX_ITEMS = 10;

function itemVacio(): ItemReceta {
  return { medicamento: '', dosis: '', via: 'Oral', frecuencia: '', periodo: '', cantidad: '', marca: '', indicacion: '' };
}

function justVacio(): FormJustificativo {
  return {
    modalidad: 'Presencial', tipo_atencion: 'Consulta', motivo_consulta: '',
    reposo: false, reposo_desde: '', reposo_hasta: '',
    restricciones: '', control_sugerido: '', observaciones: ''
  };
}

/**
 * Pantalla "Completar atención" (reemplaza al modal antiguo).
 *
 * Una sola página con secciones: el registro de la atención siempre está
 * abierto; la receta y el justificativo son tarjetas con interruptor que solo
 * aparecen si la especialidad del profesional tiene la capacidad clínica
 * correspondiente. Un resumen en vivo muestra qué se enviará al estudiante y
 * un paso de revisión final evita olvidos antes de guardar.
 *
 * El borrador se guarda en sessionStorage (se borra al cerrar la pestaña):
 * así no queda contenido clínico en un computador compartido.
 */
@Component({
  selector: 'app-completar-atencion',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './completar-atencion.html',
  styleUrls: ['./completar-atencion.css']
})
export class CompletarAtencionComponent implements OnInit, OnDestroy {

  @Input({ required: true }) cita: any;
  @Input({ required: true }) profId!: number;
  @Input() paciente: PacienteAtencion = { nombre: '—' };

  @Output() completada = new EventEmitter<DocumentoEmitido[]>();
  @Output() cancelar   = new EventEmitter<void>();

  readonly vias = ['Oral', 'Sublingual', 'Tópica', 'Oftálmica', 'Ótica', 'Nasal', 'Inhalatoria', 'Intramuscular', 'Intravenosa', 'Subcutánea', 'Rectal'];
  readonly maxItems = MAX_ITEMS;

  capacidades: Set<string> | null = null;   // null = cargando
  paso: 'editar' | 'revisar' = 'editar';
  enviando = false;
  error = '';
  borradorRecuperado = false;
  borradorGuardadoA = '';

  observaciones = '';
  medicamento = '';
  recetaActiva = false;
  items: ItemReceta[] = [itemVacio()];
  justActiva = false;
  just: FormJustificativo = justVacio();

  private timerBorrador: any;
  private finalizado = false;   // ya se completó: no volver a escribir el borrador
  private ultimoBorrador = '';

  constructor(private http: HttpClient, private cdr: ChangeDetectorRef) {}

  // ── ciclo de vida ────────────────────────────────────────────────────
  ngOnInit(): void {
    this.observaciones = this.cita?.observaciones_atencion || '';
    this.medicamento   = this.cita?.medicamento || '';
    this.recuperarBorrador();

    this.http.get<{ capacidades: string[] }>(`${API}/profesional/capacidades-clinicas`).subscribe({
      next: (r) => { this.capacidades = new Set(r?.capacidades ?? []); this.sanearSegunCapacidades(); this.cdr.detectChanges(); },
      // Fail-closed, igual que el backend: sin capacidades conocidas no se ofrecen documentos.
      error: () => { this.capacidades = new Set(); this.sanearSegunCapacidades(); this.cdr.detectChanges(); }
    });

    this.timerBorrador = setInterval(() => this.guardarBorrador(false), 4000);
  }

  ngOnDestroy(): void {
    clearInterval(this.timerBorrador);
    this.guardarBorrador(false);
  }

  // ── capacidades ──────────────────────────────────────────────────────
  get cargandoCapacidades(): boolean { return this.capacidades === null; }
  get puedeMedicamento(): boolean { return !!this.capacidades?.has(CAP_MEDICAMENTO_SUMINISTRADO); }
  get puedeReceta(): boolean      { return !!this.capacidades?.has(CAP_RECETA); }
  get puedeJustificativo(): boolean { return !!this.capacidades?.has(CAP_JUSTIFICATIVO); }
  get sinDocumentosHabilitados(): boolean {
    return this.capacidades !== null && !this.puedeReceta && !this.puedeJustificativo;
  }

  /** Un borrador recuperado no puede dejar activo algo que ya no está permitido. */
  private sanearSegunCapacidades(): void {
    if (!this.puedeReceta) this.recetaActiva = false;
    if (!this.puedeJustificativo) this.justActiva = false;
    if (!this.puedeMedicamento) this.medicamento = '';
  }

  // ── receta ───────────────────────────────────────────────────────────
  agregarMedicamento(): void {
    if (this.items.length < MAX_ITEMS) this.items.push(itemVacio());
  }

  quitarMedicamento(i: number): void {
    this.items.splice(i, 1);
    if (this.items.length === 0) this.items.push(itemVacio());
  }

  // ── validación y resumen ─────────────────────────────────────────────
  private lleno(v: string): boolean { return (v ?? '').trim().length > 0; }

  get itemsCompletos(): number {
    return this.items.filter(it => this.itemValido(it)).length;
  }

  itemValido(it: ItemReceta): boolean {
    return this.lleno(it.medicamento) && this.lleno(it.dosis) && this.lleno(it.via)
        && this.lleno(it.frecuencia) && this.lleno(it.periodo);
  }

  get diasReposo(): number | null {
    if (!this.just.reposo || !this.just.reposo_desde || !this.just.reposo_hasta) return null;
    const d = new Date(this.just.reposo_desde + 'T00:00:00');
    const h = new Date(this.just.reposo_hasta + 'T00:00:00');
    const dias = Math.round((h.getTime() - d.getTime()) / 86400000) + 1;
    return dias >= 1 ? dias : null;
  }

  /** Lo que impide guardar. Se muestra en el resumen y en la revisión final. */
  get problemas(): string[] {
    const p: string[] = [];
    if (this.recetaActiva && this.puedeReceta) {
      const parciales = this.items.filter(it => !this.itemValido(it) && (this.lleno(it.medicamento) || this.lleno(it.dosis) || this.lleno(it.frecuencia) || this.lleno(it.periodo)));
      if (this.itemsCompletos === 0) p.push('La receta está activada pero no tiene ningún medicamento completo (medicamento, dosis, vía, frecuencia y período).');
      else if (parciales.length) p.push('Hay medicamentos de la receta a medias: complétalos o quítalos.');
    }
    if (this.justActiva && this.puedeJustificativo && this.just.reposo) {
      if (!this.just.reposo_desde || !this.just.reposo_hasta) p.push('Indicaste reposo: falta la fecha desde o hasta.');
      else if (this.just.reposo_hasta < this.just.reposo_desde) p.push('En el reposo, la fecha "hasta" no puede ser anterior a "desde".');
    }
    return p;
  }

  get puedeRevisar(): boolean { return this.problemas.length === 0 && !this.enviando; }

  get hayDocumentos(): boolean {
    return (this.recetaActiva && this.puedeReceta) || (this.justActiva && this.puedeJustificativo);
  }

  // ── navegación entre pasos ───────────────────────────────────────────
  irARevisar(): void {
    if (!this.puedeRevisar) return;
    this.error = '';
    this.paso = 'revisar';
    this.guardarBorrador(false);
  }

  volverAEditar(): void { this.paso = 'editar'; this.error = ''; }

  cerrar(): void {
    this.guardarBorrador(false);   // lo escrito queda como borrador para retomarlo
    this.cancelar.emit();
  }

  // ── envío ────────────────────────────────────────────────────────────
  private o(v: string): string | null { const t = (v ?? '').trim(); return t ? t : null; }

  /** Cuerpo del PATCH /completar. Solo incluye lo que está activo y permitido. */
  construirPayload(): any {
    const body: any = {
      observaciones_atencion: this.o(this.observaciones),
      medicamento: this.puedeMedicamento ? this.o(this.medicamento) : null
    };

    if (this.recetaActiva && this.puedeReceta) {
      body.receta = {
        medicamentos: this.items.filter(it => this.itemValido(it)).map(it => ({
          medicamento: it.medicamento.trim(),
          dosis: it.dosis.trim(),
          via: it.via.trim(),
          frecuencia: it.frecuencia.trim(),
          periodo: it.periodo.trim(),
          cantidad: this.o(it.cantidad),
          marca: this.o(it.marca),
          indicacion: this.o(it.indicacion)
        }))
      };
    }

    if (this.justActiva && this.puedeJustificativo) {
      const j = this.just;
      body.justificativo = {
        modalidad: j.modalidad,
        tipo_atencion: j.tipo_atencion,
        motivo_consulta: this.o(j.motivo_consulta),
        reposo: j.reposo,
        reposo_desde: j.reposo ? j.reposo_desde : null,
        reposo_hasta: j.reposo ? j.reposo_hasta : null,
        restricciones: this.o(j.restricciones),
        control_sugerido: j.control_sugerido || null,
        observaciones: this.o(j.observaciones)
      };
    }
    return body;
  }

  guardarYCompletar(): void {
    if (this.enviando || this.problemas.length) return;
    this.enviando = true;
    this.error = '';

    this.http.patch<{ message: string; documentos?: DocumentoEmitido[] }>(
      `${API}/profesional/${this.profId}/citas/${this.cita.id}/completar`,
      this.construirPayload()
    ).subscribe({
      next: (r) => {
        this.enviando = false;
        this.finalizado = true;
        clearInterval(this.timerBorrador);
        this.descartarBorrador();
        this.completada.emit(r?.documentos ?? []);
      },
      error: (err) => {
        this.enviando = false;
        this.paso = 'editar';
        const detalle = err?.error?.detail;
        if (err?.status === 422) this.error = 'Revisa los datos ingresados: hay campos con un formato no válido o demasiado largos.';
        else this.error = typeof detalle === 'string' ? detalle : 'No se pudo completar la atención. No se guardó nada; inténtalo de nuevo.';
        this.cdr.detectChanges();
      }
    });
  }

  // ── borrador (sessionStorage) ────────────────────────────────────────
  private get claveBorrador(): string { return `sesaes_borrador_atencion_${this.cita?.id}`; }

  private recuperarBorrador(): void {
    try {
      const crudo = sessionStorage.getItem(this.claveBorrador);
      if (!crudo) return;
      const b = JSON.parse(crudo) as Borrador;
      this.observaciones = b.observaciones ?? this.observaciones;
      this.medicamento   = b.medicamento ?? this.medicamento;
      this.recetaActiva  = !!b.recetaActiva;
      this.items         = b.items?.length ? b.items : [itemVacio()];
      this.justActiva    = !!b.justActiva;
      this.just          = { ...justVacio(), ...(b.just ?? {}) };
      this.borradorRecuperado = true;
      this.ultimoBorrador = crudo;
    } catch { /* un borrador ilegible simplemente se ignora */ }
  }

  guardarBorrador(manual: boolean): void {
    if (this.finalizado) return;
    const b: Borrador = {
      observaciones: this.observaciones, medicamento: this.medicamento,
      recetaActiva: this.recetaActiva, items: this.items,
      justActiva: this.justActiva, just: this.just
    };
    const crudo = JSON.stringify(b);
    if (crudo === this.ultimoBorrador && !manual) return;
    try {
      sessionStorage.setItem(this.claveBorrador, crudo);
      this.ultimoBorrador = crudo;
      this.borradorGuardadoA = new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' });
      this.cdr.detectChanges();
    } catch { /* sin almacenamiento disponible: no es crítico */ }
  }

  descartarBorrador(): void {
    try { sessionStorage.removeItem(this.claveBorrador); } catch { /* nada que limpiar */ }
    this.ultimoBorrador = '';
  }

  empezarDeCero(): void {
    this.descartarBorrador();
    this.observaciones = this.cita?.observaciones_atencion || '';
    this.medicamento = this.cita?.medicamento || '';
    this.recetaActiva = false; this.items = [itemVacio()];
    this.justActiva = false; this.just = justVacio();
    this.borradorRecuperado = false;
    this.sanearSegunCapacidades();
  }

  fechaLegible(iso: string): string {
    if (!iso) return '—';
    const [a, m, d] = iso.split('-');
    return `${d}/${m}/${a}`;
  }
}
