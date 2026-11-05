import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../config';

const API = environment.apiUrl;

export interface CapacidadCatalogo {
  valor: string; nombre: string; descripcion: string; activa_en_sistema: boolean;
}

export interface EspecialidadCapacidades {
  clave: string; nombre: string; profesionales: number;
  incluidas: string[];      // las trae la especialidad de fábrica: no se editan
  capacidades: string[];    // incluidas + autorizaciones adicionales
}

interface FilaEditable extends EspecialidadCapacidades {
  seleccion: Set<string>;     // lo que está marcado ahora
  guardando: boolean;
  mensaje: string;
  error: string;
}

/**
 * Pestaña "Capacidades clínicas" de Configuración. Cada especialidad trae de
 * fábrica lo propio de su profesión (un médico receta sin pedir permiso): eso
 * se muestra como "incluida" y no se edita. Aquí se otorgan las AUTORIZACIONES
 * ADICIONALES y supervisadas (por ejemplo, enfermería). Requiere el permiso
 * configuracion.gestionar; el backend lo vuelve a exigir en cada llamada.
 */
@Component({
  selector: 'app-admin-capacidades-clinicas',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './admin-capacidades-clinicas.html',
  styleUrls: ['./admin-capacidades-clinicas.css']
})
export class AdminCapacidadesClinicasComponent implements OnInit {

  catalogo: CapacidadCatalogo[] = [];
  filas: FilaEditable[] = [];
  cargando = true;
  errorCarga = '';

  constructor(private http: HttpClient, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void { this.cargar(); }

  cargar(): void {
    this.cargando = true;
    this.errorCarga = '';
    this.http.get<{ catalogo: CapacidadCatalogo[]; especialidades: EspecialidadCapacidades[] }>(
      `${API}/admin/capacidades-clinicas`
    ).subscribe({
      next: (r) => {
        this.catalogo = r.catalogo;
        this.filas = r.especialidades.map(e => this.aFila(e));
        this.cargando = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.errorCarga = err?.status === 403
          ? 'No tienes permiso para administrar las capacidades clínicas.'
          : 'No pudimos cargar las capacidades. Inténtalo de nuevo.';
        this.cargando = false;
        this.cdr.detectChanges();
      }
    });
  }

  private aFila(e: EspecialidadCapacidades): FilaEditable {
    return { ...e, seleccion: new Set(e.capacidades), guardando: false, mensaje: '', error: '' };
  }

  marcada(f: FilaEditable, valor: string): boolean { return f.seleccion.has(valor); }

  deFabrica(f: FilaEditable, valor: string): boolean { return f.incluidas.includes(valor); }

  alternar(f: FilaEditable, valor: string): void {
    if (this.deFabrica(f, valor)) return;     // lo propio de la profesión no se retira
    if (f.seleccion.has(valor)) f.seleccion.delete(valor); else f.seleccion.add(valor);
    f.mensaje = '';
    f.error = '';
  }

  /** Hay cambios sin guardar respecto de lo que tiene el servidor. */
  modificada(f: FilaEditable): boolean {
    return f.seleccion.size !== f.capacidades.length
        || f.capacidades.some(c => !f.seleccion.has(c));
  }

  guardar(f: FilaEditable): void {
    if (f.guardando || !this.modificada(f)) return;
    f.guardando = true;
    f.mensaje = '';
    f.error = '';
    this.http.put<EspecialidadCapacidades>(
      `${API}/admin/capacidades-clinicas/${encodeURIComponent(f.clave)}`,
      { capacidades: [...f.seleccion] }
    ).subscribe({
      next: (r) => {
        f.capacidades = r.capacidades;
        f.seleccion = new Set(r.capacidades);
        f.guardando = false;
        f.mensaje = 'Cambios guardados.';
        this.cdr.detectChanges();
      },
      error: (err) => {
        f.guardando = false;
        f.error = typeof err?.error?.detail === 'string' ? err.error.detail : 'No se pudo guardar. Inténtalo de nuevo.';
        this.cdr.detectChanges();
      }
    });
  }
}
