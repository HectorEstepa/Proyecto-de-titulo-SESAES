<div align="center">

# SESAES
### Sistema de Agendamiento Estudiantil de Salud

**Proyecto de Título · UTEM**

![Angular](https://img.shields.io/badge/Angular-DD0031?style=flat&logo=angular&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)
![Status](https://img.shields.io/badge/status-en%20desarrollo-yellow)

Plataforma web para la gestión de atenciones y agenda del servicio de salud estudiantil.

</div>

---

## Descripción

SESAES centraliza la gestión de estudiantes, profesionales de salud, agenda, citas y administración del servicio. La aplicación utiliza una arquitectura con frontend Angular y backend FastAPI, con autorización aplicada en backend mediante roles, permisos y alcance.

## Estado actual

| Área | Estado |
|---|---|
| Autenticación y sesión | ✅ Operativo |
| Dashboard Estudiante | ✅ Integrado en `main` |
| Dashboard Profesional | ✅ Integrado en `main` |
| ADMIN / SUPERADMIN | 🚧 En evolución |
| Permisos y alcance de ADMIN | ✅ Implementado |
| Agenda clínica semanal V2 | 🚧 En desarrollo |
| Citas | ✅ Base operativa |
| Auditoría / gobernanza | 🚧 En evolución |
| Documentos clínicos avanzados | ⏳ Pendiente por fases |
| Responsive | 🚧 En progreso |

> El proyecto está en desarrollo activo. No todos los módulos se consideran cerrados aunque ya tengan una base funcional.

## Arquitectura

```text
Angular (frontend)
    │
    ▼
FastAPI (backend)
    │
    ▼
PostgreSQL
```

Desarrollo local:

```text
Frontend → http://localhost:4200
Backend  → http://127.0.0.1:8080
```

## Roles

| Rol | Responsabilidad general |
|---|---|
| `ESTUDIANTE` | Gestiona sus citas y consulta información propia permitida |
| `PROFESIONAL` | Gestiona agenda y atenciones dentro de su ámbito |
| `ADMIN` | Operación administrativa según permisos y alcance asignados |
| `SUPERADMIN` | Gobernanza institucional, roles, permisos y configuración administrativa |

### Principios de autorización

- El backend es la autoridad de seguridad.
- El frontend solo oculta o muestra acciones como ayuda de experiencia de usuario.
- Los accesos ADMIN son **fail-closed**: sin configuración válida no se conceden permisos.
- Los permisos administrativos pueden limitarse por especialidad.
- `SUPERADMIN` no recibe acceso clínico universal por su rol.
- Las operaciones sensibles deben conservar trazabilidad y auditoría.

## Permisos administrativos

La administración utiliza permisos efectivos y alcance, por ejemplo:

```text
usuarios.ver
usuarios.gestionar
profesionales.ver
profesionales.gestionar
agenda.ver
agenda.gestionar
reportes.ver
roles.gestionar
auditoria.ver
configuracion.gestionar
```

Un ADMIN puede tener alcance institucional o restringido a especialidades, según la configuración asignada por SUPERADMIN.

## Estructura del repositorio

```text
Proyecto-de-titulo-SESAES/
├── backend/      # API FastAPI, modelos, RBAC, servicios y tests
├── frontend/     # Aplicación Angular
├── .gitignore
├── README.md
└── vercel.json
```

> No se deben guardar en el repositorio cachés, entornos virtuales, `node_modules`, builds, archivos `.env`, respaldos temporales ni documentación obsoleta.

## Diseño

Reglas actuales de interfaz:

- Tipografía: **Inter**
- Iconografía: **Google Material Symbols Outlined**
- Cada dashboard mantiene sus estilos de forma independiente.
- Los estados clínicos conservan significado semántico.
- Los nuevos componentes deben ser responsive cuando corresponda.
- No introducir nuevas librerías de iconos sin una decisión explícita de arquitectura.

## Desarrollo local

### Backend

```powershell
cd backend
python -m venv venv
.env\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configura las variables de entorno en `backend/.env`.

Ejecutar:

```powershell
python -m uvicorn app.main:app --reload --port 8080
```

### Frontend

```powershell
cd frontend
npm ci
npx ng serve
```

La aplicación queda disponible normalmente en:

```text
http://localhost:4200
```

## Pruebas

### Backend

```powershell
cd backend
python -m pytest -q
```

### Frontend

```powershell
cd frontend
npx ng test --watch=false
npx ng build
```

Antes de integrar una rama a `main`, los cambios deben quedar sin errores de tests/build relacionados con su alcance.

## Flujo Git del equipo

`main` es la base oficial del proyecto.

### Antes de comenzar una tarea

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c feature/nombre-de-la-tarea
```

### Guardar y publicar avances

```powershell
git add .
git commit -m "feat(modulo): descripcion del cambio"
git push -u origin feature/nombre-de-la-tarea
```

### Integración

1. Abrir un **Pull Request** desde la rama de trabajo hacia `main`.
2. No hacer push directo a `main`.
3. El Pull Request debe revisarse antes de integrarse.
4. Si `main` avanzó mientras se trabajaba, actualizar la rama antes del merge.
5. No resolver conflictos reemplazando carpetas completas sin revisar los cambios.

### Autoría de commits

Cada integrante debe revisar una vez:

```powershell
git config user.name
git config user.email
```

El correo usado en los commits debe estar asociado a su cuenta de GitHub para que la autoría se atribuya correctamente.

## Convenciones de ramas

Ejemplos:

```text
feature/student-...
feature/professional-...
feature/admin-...
feature/superadmin-...
fix/...
test/...
```

Evitar reutilizar ramas antiguas para tareas nuevas.

## Variables y datos sensibles

- No versionar `.env`.
- No subir contraseñas, tokens ni credenciales.
- No utilizar contraseñas genéricas de producción.
- Evitar pruebas destructivas contra bases compartidas.
- Los cambios de esquema de base de datos deben coordinarse antes de integrarse.

## Equipo

- **Sandra García** — desarrollo e integración.
- **Héctor Estepa** — desarrollo en áreas de Estudiante y Profesional.

---

SESAES se desarrolla de manera incremental: cada módulo debe conservar seguridad, trazabilidad y compatibilidad con la arquitectura vigente antes de integrarse a `main`.
