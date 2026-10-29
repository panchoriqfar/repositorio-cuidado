from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, time, datetime

# --- Esquemas de Usuario y Autenticación (RBAC) ---
class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    rol: str

class TokenData(BaseModel):
    username: Optional[str] = None
    rol: Optional[str] = None

class UsuarioCreate(BaseModel):
    username: str
    password: str
    rol: str = Field(default="admin", description="Rol del usuario: 'super_user' o 'admin'")

class UsuarioUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    rol: Optional[str] = None

class CambiarPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str

class UsuarioResponse(BaseModel):
    id_usuario: int
    username: str
    rol: str
    must_change_password: bool = False

    class Config:
        from_attributes = True


# --- Esquema para envío WhatsApp semanal ---
class NotificacionSemanalRequest(BaseModel):
    fecha_base: Optional[date] = None  # Si None, usa la semana actual


# --- Esquemas de Cuidadores (Exclusivos para Turnos) ---
class CuidadorBase(BaseModel):
    nombre: str = Field(..., min_length=1, description="Nombre del cuidador/a (obligatorio)")
    apellido: Optional[str] = Field(default="", description="Apellido (opcional)")
    telefono_whatsapp: str = Field(..., pattern=r"^\+569\d{8}$", description="Formato +569XXXXXXXX (obligatorio, exactamente 8 dígitos tras +569)")
    mail: Optional[str] = Field(default=None, description="Correo electrónico del cuidador/a (opcional)")
    activo: bool = True

class CuidadorCreate(CuidadorBase):
    pass

class CuidadorUpdate(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    telefono_whatsapp: Optional[str] = Field(default=None, pattern=r"^\+569\d{8}$")
    mail: Optional[str] = None
    activo: Optional[bool] = None

class CuidadorResponse(BaseModel):
    id_cuidador: int
    nombre: str
    apellido: Optional[str] = ""
    telefono_whatsapp: str
    mail: Optional[str] = None
    rol_trabajo: Optional[str] = None
    activo: bool

    class Config:
        from_attributes = True


# --- Esquemas de Personal Médico (Actividades y Visitas Opcionales) ---
class PersonalMedicoBase(BaseModel):
    nombre: str
    apellido: Optional[str] = ""
    especialidad: str = Field(..., description="Ej: Médico General, Enfermera Universitaria, Kinesiólogo")
    telefono_whatsapp: Optional[str] = ""
    mail: Optional[str] = None
    activo: bool = True

class PersonalMedicoCreate(PersonalMedicoBase):
    pass

class PersonalMedicoUpdate(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
    mail: Optional[str] = None
    especialidad: Optional[str] = None
    activo: Optional[bool] = None

class PersonalMedicoResponse(PersonalMedicoBase):
    id_medico: int

    class Config:
        from_attributes = True


# --- Esquemas de BloqueTurno (AM, PM1, PM2, Nocturno) ---
class BloqueTurnoBase(BaseModel):
    codigo_bloque: str
    nombre_bloque: str
    hora_inicio: time
    hora_fin: time

class BloqueTurnoResponse(BloqueTurnoBase):
    id_bloque: int

    class Config:
        from_attributes = True


# --- Esquemas de Asignación de Turno (Soporta múltiples cuidadores por turno) ---
class AsignacionTurnoCreate(BaseModel):
    fecha: date
    id_cuidador: Optional[int] = None
    cuidadores_ids: Optional[List[int]] = None # Lista de cuidadores (1 o más)
    hora_inicio: time
    hora_fin: time
    id_bloque: Optional[int] = None
    reunion_familiar: Optional[bool] = False

class AsignacionTurnoResponse(BaseModel):
    id_asignacion: int
    fecha: date
    id_cuidador: int
    hora_inicio: time
    hora_fin: time
    id_bloque: int
    estado_notificacion: str
    fecha_envio_whatsapp: Optional[datetime] = None
    reunion_familiar: Optional[bool] = False
    cuidador: Optional[CuidadorResponse] = None
    bloque: Optional[BloqueTurnoResponse] = None

    class Config:
        from_attributes = True


# --- Esquemas de Actividad Médica (Personal Médico opcional) ---
class ActividadMedicaBase(BaseModel):
    fecha: date
    hora: time
    titulo: str
    descripcion: Optional[str] = None
    id_medico: Optional[int] = None

class ActividadMedicaCreate(ActividadMedicaBase):
    pass

class ActividadMedicaUpdate(BaseModel):
    fecha: Optional[date] = None
    hora: Optional[time] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    id_medico: Optional[int] = None

class ActividadMedicaResponse(ActividadMedicaBase):
    id_actividad: int
    medico_asignado: Optional[PersonalMedicoResponse] = None

    class Config:
        from_attributes = True


# --- Esquemas de WhatsApp ---
class NotificacionDiaRequest(BaseModel):
    fecha: Optional[date] = None

class DetalleEnvio(BaseModel):
    id_asignacion: int
    personal: str
    telefono: str
    bloque: str
    horario: str
    mensaje: str
    estado: str
    detalle_error: Optional[str] = None

class NotificacionDiaResponse(BaseModel):
    fecha: date
    total_asignaciones: int
    enviados: int
    errores: int
    detalles: List[DetalleEnvio]


# --- Esquemas de Correo Electrónico (Gmail SMTP) ---
class NotificacionEmailDiaRequest(BaseModel):
    fecha: Optional[date] = None

class NotificacionEmailSemanalRequest(BaseModel):
    fecha_base: Optional[date] = None

class NotificacionEmailMedicamentosRequest(BaseModel):
    tipo: str = "semana"  # 'dia' o 'semana'
    fecha: Optional[date] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    destinatario_tipo: str = "todos"  # 'cuidador', 'manual', 'todos'
    id_cuidador: Optional[int] = None
    destinatario_email: Optional[str] = None

class NotificacionEmailActividadesRequest(BaseModel):
    tipo: str = "semana"  # 'dia' o 'semana'
    fecha: Optional[date] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    destinatario_tipo: str = "todos"  # 'cuidador', 'manual', 'todos'
    id_cuidador: Optional[int] = None
    destinatario_email: Optional[str] = None

class DetalleEnvioEmail(BaseModel):
    id_cuidador: int
    cuidador: str
    mail: Optional[str] = None
    estado: str  # 'ENVIADO', 'OMITIDO', 'ERROR'
    detalle: Optional[str] = None

class NotificacionEmailResponse(BaseModel):
    tipo: str  # 'diario' o 'semanal'
    periodo: str
    total_cuidadores: int
    enviados: int
    omitidos: int
    errores: int
    detalles: List[DetalleEnvioEmail]


class EnvioEmailPruebaRequest(BaseModel):
    destinatario: str
    asunto: Optional[str] = "MedTurnos Pro - Correo de Prueba"
    mensaje: Optional[str] = "Este es un correo de prueba de MedTurnos Pro desde producción."
    html: Optional[str] = None


# --- Esquemas de Gestión de Medicamentos ---
class MedicamentoHorarioBase(BaseModel):
    dia: date
    hora: time

class MedicamentoHorarioCreate(BaseModel):
    dia: Optional[date] = None  # Si es None, hereda dia_inicial
    hora: time

class MedicamentoHorarioResponse(BaseModel):
    id: int
    medicamento_id: int
    dia: date
    hora: time

    class Config:
        from_attributes = True

class TratamientoMedicamentoBase(BaseModel):
    personal_medico_id: Optional[int] = Field(default=None, description="ID del profesional de personal médico (opcional)")
    nombre_medicamento: str = Field(..., min_length=1, description="Nombre y presentación del medicamento")
    dia_inicial: date = Field(..., description="Fecha inicial del tratamiento")

class TratamientoMedicamentoCreate(TratamientoMedicamentoBase):
    horarios_iniciales: Optional[List[time]] = Field(
        default=[],
        description="Lista de horas para el día inicial (ej: ['08:00:00', '14:00:00', '20:00:00'])"
    )
    # Clonación o replicación dinámica:
    duracion_dias: Optional[int] = Field(
        default=None,
        description="Cantidad de días consecutivos para clonar los horarios iniciales a partir del día inicial"
    )
    dias_a_clonar: Optional[int] = Field(
        default=None,
        description="Alias de duracion_dias para replicación dinámica de horarios"
    )
    fechas_adicionales: Optional[List[date]] = Field(
        default=[],
        description="Lista explícita de fechas adicionales donde replicar los horarios iniciales"
    )
    horarios: Optional[List[MedicamentoHorarioCreate]] = Field(
        default=[],
        description="Lista de horarios adicionales con día y hora personalizados"
    )
    horarios_dinamicos: Optional[List[MedicamentoHorarioCreate]] = Field(
        default=[],
        description="Alias de horarios para registrar nuevos días y horas dinámicamente"
    )

class ClonarHorariosRequest(BaseModel):
    """Esquema para agregar o clonar nuevos días y horas a un tratamiento existente."""
    dias_a_clonar: Optional[int] = Field(default=None, description="Número de días a extender")
    fechas: Optional[List[date]] = Field(default=[], description="Fechas específicas adicionales")
    horas: Optional[List[time]] = Field(default=[], description="Horas a programar (si vacío, clona horarios del día inicial)")
    horarios_dinamicos: Optional[List[MedicamentoHorarioCreate]] = Field(default=[], description="Lista dinámica de día y hora")

class TratamientoMedicamentoResponse(TratamientoMedicamentoBase):
    id: int
    personal_medico: Optional[PersonalMedicoResponse] = None
    horarios: List[MedicamentoHorarioResponse] = []

    class Config:
        from_attributes = True

