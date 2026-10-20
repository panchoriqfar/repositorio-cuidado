# Sistema Web de Gestión de Turnos de Cuidadores y Actividades Médicas con WhatsApp

Sistema integral de gestión de turnos para centros de atención, clínicas y servicios domiciliarios con notificaciones automatizadas vía WhatsApp (Twilio) y control de acceso basado en roles (RBAC).

---

## 🚀 Nuevas Reglas y Características Implementadas

1. **Gestión de Usuarios y Roles (RBAC Exclusivo)**:
   - **`super_user` (Super Admin)**: Acceso total y exclusivo a la administración de cuentas. **Solo él puede ver la lista de usuarios, crear administradores, crear otros superusuarios y eliminar usuarios o cuidadores**.
   - **`admin`**: Permisos operativos para gestión de turnos de cuidadores, actividades médicas y WhatsApp. **Tiene estrictamente prohibido ver, crear, editar o eliminar usuarios y superusuarios, así como eliminar cuidadores**.

2. **Creación del Superusuario Inicial (Seed / Arranque)**:
   - Al arrancar la aplicación, se verifica automáticamente si existen usuarios. Si no, se crea el superusuario por defecto usando las variables de entorno `SUPERUSER_USERNAME` y `SUPERUSER_PASSWORD`, con su contraseña cifrada mediante `passlib` (bcrypt).

3. **Endpoints y Menú Protegidos de Creación de Perfiles**:
   - `GET /api/admin/usuarios`: Listar usuarios del sistema (exclusivo `super_user`, `admin` recibe 403 Forbidden).
   - `POST /api/admin/usuarios`: Registro de nuevos administradores y superusuarios (exclusivo `super_user`, `admin` recibe 403 Forbidden).
   - `PUT /api/admin/usuarios/{id_usuario}`: Modificación de cuentas (exclusivo `super_user`).
   - `DELETE /api/admin/usuarios/{id_usuario}`: Eliminación de cuentas (exclusivo `super_user`).

4. **Separación Estricta en Base de Datos**:
   - **`Cuidadores` (`cuidadores`)**: A quienes **exclusivamente** se les asignan turnos de cuidado.
   - **`Personal Médico` (`personal_medico`)**: Médicos, enfermeros/as, kinesiólogos, etc., a quienes **se les pueden o no asignar actividades médicas y visitas especiales del día** (asignación opcional).

5. **Asignación de Turnos con Horario Libre (00:00 a 23:59)**:
   - En el frontend, el usuario administrador selecciona libremente la **Hora de Inicio** y la **Hora de Fin** (desde las 00:00 hasta las 23:59) y los cuidadores asignados.

6. **Cuadrante Semanal Visual**:
   - Cuadrante interactivo organizado por bloques horarios (`AM`, `PM1`, `PM2`, `Nocturno`), con detalle de rangos exactos de horas asignadas.

7. **Notificaciones Personalizadas por WhatsApp (Twilio)**:
   - Envío masivo diario a los cuidadores en turno con sus horarios específicos y el listado de actividades médicas programadas.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy ORM, Pydantic v2, Uvicorn, Passlib (Bcrypt), Python-JOSE (JWT).
- **Base de Datos**: PostgreSQL en la nube (Supabase / Neon / Render) con fallback automático de respaldo a SQLite local (`turnos_medicos.db`).
- **Frontend**: HTML5, CSS3 con Tailwind CSS (CDN), FontAwesome Icons, JavaScript Vanilla (Fetch API).
- **Notificaciones**: Twilio WhatsApp API.

---

## ⚙️ Cómo Ejecutar

1. Abre tu terminal en la carpeta del proyecto:
   ```powershell
   cd "C:\Users\admin\Desktop\Proyecto cuidado\repositorio cuidado"
   ```
2. Ejecuta:
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
