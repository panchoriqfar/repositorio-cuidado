# Sistema Web de Gestión de Turnos de Cuidadores y Actividades Médicas con WhatsApp

Sistema integral de gestión de turnos para centros de atención, clínicas y servicios domiciliarios con notificaciones automatizadas vía WhatsApp (Twilio) y control de acceso basado en roles (RBAC).

---

## 🚀 Características y Reglas del Sistema

### 1. Gestión de Usuarios y Cambio de Contraseñas
- **Creación exclusiva por `super_user`**: Únicamente el Superusuario tiene autorización para ver usuarios y crear nuevas cuentas (`admin` o `super_user`).
- **Primer ingreso obligatorio**: Al primer ingreso de un usuario nuevo, el sistema **obliga a cambiar su contraseña** inmediatamente. Tanto la interfaz como la API restringen todas las operaciones hasta que la nueva contraseña sea establecida (`must_change_password`).
- **Cambio voluntario de contraseña**: Todos los usuarios autenticados disponen del botón **"Cambiar Contraseña"** en la barra superior para actualizar su clave en cualquier momento ingresando su contraseña actual y la nueva.

### 2. Creación y Gestión de Cuidadores
- **Nombre**: Obligatorio.
- **Apellido**: Opcional.
- **WhatsApp**: Obligatorio. Utiliza el prefijo predeterminado **`+569`** y exige ingresar estrictamente los **8 dígitos numéricos restantes** (formato total `+569XXXXXXXX`).
- **Rol eliminado por completo**: Se eliminó cualquier concepto de rol laboral en los cuidadores; todos son gestionados exclusivamente como cuidadores.

### 3. Notificaciones WhatsApp (Twilio)
- **Actualización Diaria**: Botón ubicado en la barra de navegación superior ("Actualización Diaria") que envía el turno del día objetivo y el detalle de actividades médicas programadas para la jornada.
- **Notificación Semanal (Toda la Semana)**: Botón ubicado en la **parte final del horario, abajo a la derecha** del cuadrante semanal. Genera un mensaje consolidado para cada cuidador asignado en la semana completa (lunes a domingo), incluyendo sus horarios de cada día y las actividades médicas programadas en sus turnos.

### 4. Asignación de Turnos con Horario Libre (00:00 a 23:59)
- Horario de inicio y fin libremente configurable de 00:00 a 23:59 hrs.
- Clasificación visual automática en los bloques estándar del cuadrante: `AM`, `PM1`, `PM2` y `Nocturno`.
- Posibilidad de asignar uno o múltiples cuidadores a un mismo turno.

### 5. Actividades Médicas y Procedimientos
- Registro de curaciones, visitas domiciliarias y procedimientos médicos con horario específico.
- Asignación opcional a Personal Médico registrado (médicos, enfermeros, kinesiólogos, etc.).
- Vinculación automática en los mensajes de WhatsApp diarios y semanales de los cuidadores.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy ORM, Pydantic v2, Uvicorn, Passlib (Bcrypt), Python-JOSE (JWT).
- **Base de Datos**: PostgreSQL en la nube (Supabase / Neon / Render) con fallback automático de respaldo a SQLite local (`turnos_medicos.db`).
- **Frontend**: HTML5, CSS3 con Tailwind CSS (CDN), FontAwesome Icons, JavaScript Vanilla (Fetch API).
- **Notificaciones**: Twilio WhatsApp API.

---

## 📡 Endpoints Principales de la API

### Autenticación y Perfil
- `POST /api/auth/login`: Autenticación con credenciales JWT (Bearer token).
- `GET /api/auth/me`: Datos del usuario actual en sesión (incluye estado `must_change_password`).
- `POST /api/auth/cambiar-password`: Cambio de contraseña (obligatorio primer login o voluntario).

### Administración de Usuarios (Exclusivo `super_user`)
- `GET /api/admin/usuarios`: Listado de usuarios del sistema.
- `POST /api/admin/usuarios`: Registro de nuevo usuario (inicia con `must_change_password=True`).
- `PUT /api/admin/usuarios/{id_usuario}`: Modificación de usuario.
- `DELETE /api/admin/usuarios/{id_usuario}`: Eliminación de usuario.

### Cuidadores
- `GET /api/admin/cuidadores`: Listar cuidadores activos.
- `POST /api/admin/cuidadores`: Registrar cuidador (nombre obligatorio, apellido opcional, WhatsApp `+569XXXXXXXX`, sin rol).
- `DELETE /api/admin/cuidadores/{id_cuidador}`: Desactivación de cuidador (exclusivo `super_user`).

### Cuadrante y Turnos
- `GET /api/public/cuadrante`: Matriz semanal por bloques y días.
- `POST /api/admin/asignaciones`: Asignar turno con rango horario (00:00 - 23:59) a cuidador(es).
- `DELETE /api/admin/asignaciones/{id_asignacion}`: Desasignar turno.

### Notificaciones WhatsApp
- `POST /api/admin/notificaciones/enviar-dia`: Dispara actualización diaria para la fecha indicada.
- `POST /api/admin/notificaciones/enviar-semana`: Dispara notificación semanal consolidada a todos los cuidadores de la semana completa junto con sus actividades.

---

## ⚙️ Cómo Ejecutar

1. Abre tu terminal en la carpeta del proyecto:
   ```powershell
   cd "C:\Users\admin\Desktop\Proyecto cuidado\repositorio cuidado"
   ```
2. Ejecuta el servidor:
   ```powershell
   python run.py
   ```
3. Accede desde tu navegador:
   - **Plataforma Web**: [http://localhost:8000](http://localhost:8000)
   - **Documentación Swagger API**: [http://localhost:8000/docs](http://localhost:8000/docs)

#### 🔐 Credenciales del Superusuario por Defecto:
- **Usuario**: `admin`
- **Contraseña**: `admin1234`
- **Rol**: `super_user`
