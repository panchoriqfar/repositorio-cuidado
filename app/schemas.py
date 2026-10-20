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
    nombre: str = Field(..., description="Nombre del cuidador/a (obligatorio)")
    apellido: Optional[str] = Field(default="", description="Apellido (opcional)")
    telefono_whatsapp: str = Field(..., description="Formato E.164, ej: +56912345678 (obligatorio)")
    activo: bool = True

class CuidadorCreate(CuidadorBase):
    pass

class CuidadorUpdate(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
    activo: Optional[bool] = None

class CuidadorResponse(BaseModel):
    id_cuidador: int
    nombre: str
    apellido: Optional[str] = ""
    telefono_whatsapp: str
    rol_trabajo: Optional[str] = ""
    activo: bool

    class Config:
        from_attributes = True


# --- Esquemas de Personal Médico (Actividades y Visitas Opcionales) ---
class PersonalMedicoBase(BaseModel):
    nombre: str
    apellido: str
    telefono_whatsapp: str = Field(..., description="Formato E.164, ej: +56912345678")
    especialidad: str = Field(..., description="Ej: Médico General, Enfermera Universitaria, Kinesiólogo")
    activo: bool = True

class PersonalMedicoCreate(PersonalMedicoBase):
    pass

class PersonalMedicoUpdate(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
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

class AsignacionTurnoResponse(BaseModel):
    id_asignacion: int
    fecha: date
    id_cuidador: int
    hora_inicio: time
    hora_fin: time
    id_bloque: int
    estado_notificacion: str
    fecha_envio_whatsapp: Optional[datetime] = None
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
