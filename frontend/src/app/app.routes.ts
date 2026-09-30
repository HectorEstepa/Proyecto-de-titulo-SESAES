import { Routes } from '@angular/router';
import { LoginComponent } from './login/login';
import { authGuard } from './auth.guard';
import { rolGuard } from './rol.guard';
import { leaveDashboardGuard } from './leave-dashboard.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },

  {
    path: 'dashboard/estudiante',
    canActivate: [authGuard, rolGuard],
    canDeactivate: [leaveDashboardGuard],
    data: { roles: ['estudiante'] },
    loadComponent: () =>
      import('./dashboard-estudiante/dashboard-estudiante')
        .then(m => m.DashboardEstudianteComponent)
  },
  {
    path: 'dashboard/profesional',
    canActivate: [authGuard, rolGuard],
    canDeactivate: [leaveDashboardGuard],
    data: { roles: ['profesional'] },
    loadComponent: () =>
      import('./dashboard-profesional/dashboard-profesional')
        .then(m => m.DashboardProfesionalComponent)
  },
  {
    path: 'dashboard/admin',
    canActivate: [authGuard, rolGuard],
    canDeactivate: [leaveDashboardGuard],
    data: { roles: ['admin', 'superadmin'] },
    loadComponent: () =>
      import('./dashboard-admin/dashboard-admin')
        .then(m => m.DashboardAdminComponent)
  },

  { path: '**', redirectTo: 'login' }
];
