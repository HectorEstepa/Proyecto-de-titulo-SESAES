import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideLucideConfig, provideLucideIcons } from '@lucide/angular';
import { routes } from './app.routes';
import { authInterceptor } from './auth.interceptor';
import { ICON_MAP } from './shared/icons/icon-map';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    // Configuración global SESAES para @lucide/angular (Fase 1)
    provideLucideConfig({
      strokeWidth: 1.75,
      size: 20,
      color: 'currentColor',
    }),
    provideLucideIcons(...Object.values(ICON_MAP)),
  ]
};