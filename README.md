# Sistema Web de Gestión de Turnos de Cuidadores y Actividades Médicas con WhatsApp y Correo Electrónico (Resend)

Sistema integral de gestión de turnos para centros de atención, clínicas y servicios domiciliarios con notificaciones automatizadas vía WhatsApp (Twilio), correo electrónico vía API HTTP (Resend) y control de acceso basado en roles (RBAC).

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
- **Correo Electrónico (`mail`)**: Campo opcional para habilitar el envío de notificaciones por email.
- **Rol eliminado por completo**: Se eliminó cualquier concepto de rol laboral en los cuidadores; todos son gestionados exclusivamente como cuidadores.

### 3. Notificaciones por Correo Electrónico vía API HTTP (Resend)
Para garantizar la compatibilidad total con **Render**, Railway u otros entornos en la nube (donde los puertos SMTP salientes 25, 465 y 587 son bloqueados por los proveedores causando errores *Network is unreachable*), el sistema utiliza la **API REST HTTP oficial de Resend** (a través del puerto HTTPS 443 estándar) y variables de entorno de producción:
- **Configuración en Producción / Render / `.env`**:
  - `RESEND_API_KEY`: Clave de API generada en [resend.com/api-keys](https://resend.com/api-keys) para autenticar el cliente de Resend (`resend.api_key`).
  - `SENDER_EMAIL`: Dirección de correo del remitente verificado (por defecto `notificaciones@medturnospro.tech`).
  - `RESEND_FROM`: Construcción del remitente con formato `Sistema MedTurnos <notificaciones@medturnospro.tech>`, garantizando que los correos se envíen desde el dominio verificado `@medturnospro.tech` y no desde la dirección de prueba de Resend (`onboarding@resend.dev`).
- **Respuesta Estructurada y Manejo de Excepciones**:
  - Todas las llamadas al servicio de envío capturan excepciones (`try/except`) y retornan respuestas JSON estructuradas con el estado explícito (`status: "success"` con su identificador `id`, o `status: "error"` con el detalle del fallo).
  - Endpoint de prueba disponible: `POST /api/admin/notificaciones/enviar-email-prueba`.
- **Prevención de Agrupación de Conversaciones (Anti-Threading)**:
  - Para evitar que proveedores como Gmail agrupen múltiples correos enviados el mismo día en un único hilo de conversación, el asunto (`subject`) incluye automáticamente una marca de tiempo dinámica con la hora exacta de emisión (ej. `MedTurnos Pro - Tu turno para hoy [14:35:10]`), garantizando que cada notificación se visualice como un correo independiente.
- **Envío Semanal ("Enviar Correo Semanal")**:
  - Botón ubicado en la parte inferior derecha del horario, junto al botón de WhatsApp.
  - Recorre los cuidadores con turnos asignados en la semana y envía un resumen estructurado con sus días y bloques asignados, y sus actividades médicas y medicamentos programados agrupados por fármaco y actividad.
- **Envío Diario ("Enviar Correo Diario")**:
  - Botón ubicado en la barra de navegación superior, junto al botón de Actualización Diaria de WhatsApp.
  - Informa al cuidador su turno o consolidado de turnos del día (fecha, bloque, horario inicio/fin), pauta de medicamentos agrupada por horario y detalle de actividades médicas programadas para la jornada.
- **Robustez y Tolerancia a Fallos**:
  - Solo envía a cuidadores con correo válido en `cuidadores.mail`.
  - Si un cuidador no tiene correo registrado o el formato es inválido, se registra como `OMITIDO`.
  - Captura excepciones por destinatario para evitar que el fallo de un correo interrumpa el envío masivo al resto de cuidadores.

### 4. Notificaciones por WhatsApp (Twilio)
- **Actualización Diaria**: Botón ubicado en la barra superior ("Actualización Diaria") que envía el turno del día y las actividades médicas.
- **Notificación Semanal**: Botón ubicado abajo a la derecha del cuadrante semanal ("Enviar a toda la semana") con mensaje consolidado de todos los turnos y actividades.

### 5. Asignación de Turnos con Horario Libre (00:00 a 23:59)
- Horario de inicio y fin libremente configurable de 00:00 a 23:59 hrs.
- Clasificación visual automática en los bloques estándar del cuadrante: `AM`, `PM1`, `PM2` y `Nocturno`.
- Posibilidad de asignar uno o múltiples cuidadores a un mismo turno.

### 6. Actividades Médicas y Procedimientos
- Registro de curaciones, visitas domiciliarias y procedimientos médicos con horario específico.
- Asignación opcional a Personal Médico registrado (médicos, enfermeros, kinesiólogos, etc.).
- Vinculación automática en las notificaciones diarias y semanales (WhatsApp y Email).

### 7. Gestión de Medicamentos y Pautas Horarias
- **Modelo de Tratamientos (`TratamientoMedicamento`)**: Registra la prescripción o indicación asociada a un profesional de la salud (`personal_medico`), indicando nombre del fármaco y fecha inicial.
- **Horarios y Días (`MedicamentoHorario`)**: Almacena cada toma individual (`dia` y `hora`) vinculada al tratamiento con eliminación en cascada (`ON DELETE CASCADE`).
- **Registro y Clonación Dinámica**: Permite registrar un tratamiento con múltiples horarios iniciales y replicarlos dinámicamente durante una cantidad de días (`duracion_dias`), fechas específicas o listas de horarios personalizados.
- **Consulta de Pauta por Profesional**: Endpoint para consultar tratamientos y horarios filtrados por fecha (`GET /api/medicamentos/{personal_medico_id}`).
- **Cruce Estricto por Horario de Turno en Notificaciones**: Los envíos (WhatsApp y Correo Electrónico) cruzan estrictamente el rango horario del turno asignado al cuidador (`hora_inicio` - `hora_fin`). Si una actividad médica o toma de medicamento ocurre fuera de su horario de trabajo (por ejemplo, turno de 10:00 a 14:00 y medicamento a las 16:00 o actividad a las 08:00), esa información no le llegará al cuidador, garantizando que cada profesional reciba exclusivamente las tareas y fármacos que debe gestionar durante su turno.

### 8. Generación y Descarga de Imagen Semanal (Afiche Estilo Canva)
- **Botón "Generar Imagen Semanal"**: Disponible en la barra de control de fecha superior y en la barra inferior al finalizar la asignación semanal de turnos.
- **Renderizado en Alta Resolución (1600 &times; 1056 px)**:
  - Encabezado elegante con tipografía serif y caligráfica (*CALENDARIO SEMANAL / Planificación de Personal*).
  - 7 columnas correspondientes a los días de la semana con paletas de color pastel diferenciadas, ramitas botánicas y medallón de fecha.
  - Bloques de turno distribuidos por tarjetas:
    - **AM**: Píldora de turno, icono de sol radiante, horario y nombres de cuidadores.
    - **PM**: Píldora de turno, icono de atardecer, soporte para 1 o múltiples turnos de tarde (PM1 y PM2) y nombres.
    - **N (Nocturno)**: Píldora en azul marino, icono de luna en medallón, horario y cuidadores.
  - **Post-It amarillo con cinta adhesiva (Washi Tape)**: Pre-llenado automáticamente con las actividades y visitas médicas registradas para la semana, con editor de notas personalizado antes de exportar.
  - **Emblema inferior y acuarela botánica**: Sello circular con silueta de cuidadores y follaje decorativo.
- **Opciones de Exportación**:
  - **Descargar PNG** en alta calidad.
  - **Descargar JPG** optimizado.
  - **Copiar Imagen al Portapapeles** para pegar directamente con `Ctrl+V` en WhatsApp Web o chat.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy ORM, Pydantic v2, Uvicorn, Passlib (Bcrypt), Python-JOSE (JWT), Resend Python SDK (API HTTP).
- **Base de Datos**: PostgreSQL en la nube (Supabase / Neon / Render) con fallback automático de respaldo a SQLite local (`turnos_medicos.db`).
- **Frontend**: HTML5, CSS3 con Tailwind CSS (CDN), FontAwesome Icons, JavaScript Vanilla (Fetch API).
- **Notificaciones**: Twilio WhatsApp API & Resend Email HTTP API.

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
- `POST /api/admin/cuidadores`: Registrar cuidador (nombre obligatorio, apellido opcional, WhatsApp `+569XXXXXXXX`, correo opcional, sin rol).
- `DELETE /api/admin/cuidadores/{id_cuidador}`: Desactivación de cuidador (exclusivo `super_user`).

### Cuadrante y Turnos
- `GET /api/public/cuadrante`: Matriz semanal por bloques y días.
- `POST /api/admin/asignaciones`: Asignar turno con rango horario (00:00 - 23:59) a cuidador(es).
- `DELETE /api/admin/asignaciones/{id_asignacion}`: Desasignar turno.

### Gestión de Medicamentos
- `POST /api/medicamentos/`: Registrar tratamiento farmacológico con día inicial, múltiples horarios y opciones de clonación dinámica (por duración de días, fechas adicionales o lista de horarios dinámicos).
- `GET /api/medicamentos/{personal_medico_id}`: Consultar pauta de medicamentos asignada por un profesional médico, con filtro opcional por fecha (`?fecha=YYYY-MM-DD`).
- `GET /api/medicamentos/`: Listado general de tratamientos con filtros opcionales de fecha y personal médico.
- `POST /api/medicamentos/{tratamiento_id}/horarios`: Replicar, clonar o incorporar nuevos días y horas a un tratamiento existente.
- `DELETE /api/medicamentos/{tratamiento_id}`: Eliminar un tratamiento y todos sus horarios asociados en cascada.
- `DELETE /api/medicamentos/horarios/{horario_id}`: Eliminar un horario de administración puntual.

### Notificaciones WhatsApp
- `POST /api/admin/notificaciones/enviar-dia`: Dispara actualización diaria por WhatsApp para la fecha indicada.
- `POST /api/admin/notificaciones/enviar-semana`: Dispara notificación semanal consolidada por WhatsApp a todos los cuidadores de la semana.

### Notificaciones por Correo Electrónico (Resend HTTP API)
- `POST /api/admin/notificaciones/enviar-email-dia`: Envía notificación diaria por email con turnos y actividades a cuidadores en turno.
- `POST /api/admin/notificaciones/enviar-email-semana`: Envía planificación semanal consolidada por email a todos los cuidadores de la semana.
- `POST /api/admin/notificaciones/enviar-email-prueba`: Envía un correo de prueba vía Resend API y retorna el estado (`status: success` / `status: error`).

---

## ⚙️ Cómo Ejecutar

1. Abre tu terminal en la carpeta del proyecto:
   ```powershell
   cd "C:\Users\admin\Desktop\Proyecto cuidado\repositorio cuidado"
   ```
2. Instala dependencias:
   ```powershell
   pip install -r requirements.txt
   ```
3. Ejecuta el servidor:
   ```powershell
   python run.py
   ```
4. Accede desde tu navegador:
   - **Plataforma Web**: [http://localhost:8000](http://localhost:8000)
   - **Documentación Swagger API**: [http://localhost:8000/docs](http://localhost:8000/docs)

#### 🔐 Seguridad y Configuración de Acceso:
Las credenciales de acceso inicial se configuran de manera segura mediante variables de entorno en el archivo `.env` (`SUPERUSER_USERNAME` y `SUPERUSER_PASSWORD`). Nunca compartas ni almacenes contraseñas en el repositorio público. Al ingresar por primera vez, el sistema exige obligatoriamente cambiar la contraseña predeterminada por una clave personalizada y segura.
