import { Component, ElementRef, EventEmitter, Input, Output, ViewChildren, QueryList } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface TabItem {
  id: string;
  label: string;
}

let nextAutoId = 0;

/**
 * SESAES — Tabs (Fase 2.4)
 *
 * Componente CONTROLADO, equivalente a los ~5 grupos reales de tabs ya
 * existentes en los 3 dashboards (todos controlan contenido local vía
 * variable + `*ngIf`, nunca rutas). No incluye `disabled`, íconos,
 * badges ni variantes por dashboard: la auditoría real no encontró
 * evidencia de ninguno de esos comportamientos.
 *
 * Nunca hace `this.activeTab = ...` internamente; toda intención de
 * cambio se comunica vía `activeTabChange` y el consumidor decide si
 * de verdad cambia `activeTab`.
 */
@Component({
  selector: 'app-tabs',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './tabs.html',
  styleUrls: ['./tabs.css'],
})
export class TabsComponent {
  @Input({ required: true }) tabs: TabItem[] = [];
  @Input({ required: true }) activeTab = '';

  @Output() readonly activeTabChange = new EventEmitter<string>();

  @ViewChildren('tabButton') private readonly tabButtons?: QueryList<ElementRef<HTMLButtonElement>>;

  private readonly instanceId = `app-tabs-${nextAutoId++}`;

  tabButtonId(tabId: string): string {
    return `${this.instanceId}-tab-${tabId}`;
  }

  panelId(tabId: string): string {
    return `${this.instanceId}-panel-${tabId}`;
  }

  isActive(tabId: string): boolean {
    return this.activeTab === tabId;
  }

  selectTab(tabId: string): void {
    if (tabId !== this.activeTab) {
      this.activeTabChange.emit(tabId);
    }
  }

  onKeydown(event: KeyboardEvent, currentIndex: number): void {
    let targetIndex: number | null = null;

    switch (event.key) {
      case 'ArrowRight':
        targetIndex = (currentIndex + 1) % this.tabs.length;
        break;
      case 'ArrowLeft':
        targetIndex = (currentIndex - 1 + this.tabs.length) % this.tabs.length;
        break;
      case 'Home':
        targetIndex = 0;
        break;
      case 'End':
        targetIndex = this.tabs.length - 1;
        break;
      default:
        return;
    }

    event.preventDefault();
    this.focusAndActivate(targetIndex);
  }

  /**
   * Enfoca SIEMPRE el botón destino (navegación por teclado real), pero
   * solo emite `activeTabChange` si el tab destino es distinto al activo
   * actual. Evita emisiones redundantes con Home/End repetido o cuando
   * solo hay un tab.
   */
  private focusAndActivate(targetIndex: number): void {
    const target = this.tabs[targetIndex];
    if (!target) {
      return;
    }

    const buttonEl = this.tabButtons?.toArray()[targetIndex]?.nativeElement;
    buttonEl?.focus();

    if (target.id !== this.activeTab) {
      this.activeTabChange.emit(target.id);
    }
  }
}
