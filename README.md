# Sistema Web de Gestión de Turnos de Cuidadores y Actividades Médicas con WhatsApp

Sistema integral de gestión de turnos para centros de atención, clínicas y servicios domiciliarios con notificaciones automatizadas vía WhatsApp (Twilio).

---
##holi
## 🚀 Nuevas Reglas y Características Implementadas

1. **Separación Estricta en Base de Datos**:
   - **`Cuidadores` (`cuidadores`)**: A quienes **exclusivamente** se les asignan turnos de cuidado.
   - **`Personal Médico` (`personal_medico`)**: Médicos, enfermeros/as, kinesiólogos, etc., a quienes **se les pueden o no asignar actividades médicas y visitas especiales del día** (asignación opcional).

2. **Asignación de Turnos con Horario Libre (00:00 a 23:59)**:
   - En el frontend, el administrador ya no está atado a un bloque rígido: selecciona libremente la **Hora de Inicio** y la **Hora de Fin** (desde las 00:00 hasta las 23:59).
   - Se selecciona exclusivamente a un miembro de la lista de **Cuidadores**.

3. **Cuadrante Semanal Visual**:
   - En el calendario del frontend se mantienen las filas por bloques requeridos:
     - **`AM`**
     - **`PM1`**
     - **`PM2`**
     - **`Nocturno`**
   - Cada casilla asignada muestra el nombre del cuidador/a y el **rango horario exacto asignado** (ej: `10:00 - 14:30`), junto con el estado de notificación de WhatsApp.

4. **Actividades y Visitas Médicas Especiales**:
   - Tarjetas para visitas domiciliarias, curaciones y procedimientos.
   - Posibilidad de asignar un profesional del **Personal Médico** o dejarlo sin médico asignado específico.

5. **Notificaciones Personalizadas por WhatsApp (Twilio)**:
   - Envío masivo de turnos diarios a los cuidadores con sus horarios exactos y el listado de actividades médicas programadas para la jornada.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy ORM, Pydantic v2, Uvicorn, Bcrypt nativo, Python-JOSE (JWT).
- **Base de Datos**: PostgreSQL en la nube (Supabase / Neon) y SQLite local con SQLAlchemy.
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

#### 🔐 Credenciales de Administrador:
- **Usuario**: `admin`
- **Contraseña**: `admin1234`
