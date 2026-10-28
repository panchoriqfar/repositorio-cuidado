from sqlalchemy import Column, Integer, String, Boolean, Date, Time, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Usuario(Base):
    """
    Tabla de Usuarios del Sistema con soporte de Roles (RBAC):
    - 'super_user': Acceso total, gestión de usuarios, orquestación y eliminación de cuidadores.
    - 'admin': Mismos permisos operativos excepto eliminación de cuidadores y gestión de usuarios.
    - must_change_password: Si es True, el usuario debe cambiar su contraseña obligatoriamente en el primer login.
    """
    __tablename__ = "usuarios"

    id_usuario = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(20), default="admin", nullable=False) # 'super_user', 'admin'
    must_change_password = Column(Boolean, default=False, nullable=False)  # Cambio obligatorio primer login


class Cuidador(Base):
    """
    Tabla de Cuidadores: A quienes EXCLUSIVAMENTE se les asignan los turnos de cuidado.
    - nombre: obligatorio
    - apellido: opcional
    - telefono_whatsapp: obligatorio, formato +569XXXXXXXX (8 números)
    - rol_trabajo: eliminado por completo de la lógica (mantenido opcional nullable para compatibilidad con esquemas anteriores)
    """
    __tablename__ = "cuidadores"

    id_cuidador = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=True, default="")
    telefono_whatsapp = Column(String(25), nullable=False)  # Formato +569XXXXXXXX
    mail = Column(String(150), nullable=True, default=None)  # Correo electrónico para notificaciones
    rol_trabajo = Column(String(100), default="", nullable=False)  # Campo interno por compatibilidad con esquema previo
    activo = Column(Boolean, default=True, nullable=False)

    # Relaciones: Solo los cuidadores tienen asignaciones de turnos
    asignaciones = relationship("AsignacionTurno", back_populates="cuidador", cascade="all, delete-orphan")


class PersonalMedico(Base):
    """
    Tabla de Personal Médico: A quienes se les pueden asignar o no actividades médicas y visitas del día.
    """
    __tablename__ = "personal_medico"

    id_medico = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=True, default="")
    telefono_whatsapp = Column(String(25), nullable=True, default="")  # Opcional / interno
    especialidad = Column(String(100), nullable=False)      # ej: 'Médico General', 'Enfermera Jefe', 'Kinesiólogo'
    activo = Column(Boolean, default=True, nullable=False)

    # Relaciones: Se le pueden asociar o no actividades médicas y tratamientos de medicamentos
    actividades = relationship("ActividadMedica", back_populates="medico_asignado")
    tratamientos = relationship("TratamientoMedicamento", back_populates="personal_medico", cascade="all, delete-orphan")


class BloqueTurno(Base):
    """
    Bloques horarios para organización visual del cuadrante semanal:
    AM, PM1, PM2, N (Nocturno)
    """
    __tablename__ = "bloques_turnos"

    id_bloque = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo_bloque = Column(String(10), unique=True, nullable=False) # 'AM', 'PM1', 'PM2', 'N'
    nombre_bloque = Column(String(100), nullable=False)            # 'AM', 'PM1', 'PM2', 'Nocturno'
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    # Relaciones
    asignaciones = relationship("AsignacionTurno", back_populates="bloque")


class AsignacionTurno(Base):
    """
    Asignación de turnos: Exclusiva para Cuidadores, con horario libre de 00:00 a 23:59
    y vinculación al bloque horario correspondiente en el cuadrante.
    """
    __tablename__ = "asignaciones_turnos"

    id_asignacion = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fecha = Column(Date, nullable=False, index=True)
    id_cuidador = Column(Integer, ForeignKey("cuidadores.id_cuidador"), nullable=False)
    
    # Horario específico configurado (00:00 a 23:59)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    # Bloque asociado para renderizar en el cuadrante del front (AM, PM1, PM2, N)
    id_bloque = Column(Integer, ForeignKey("bloques_turnos.id_bloque"), nullable=False)

    estado_notificacion = Column(String(20), default="PENDIENTE", nullable=False) # 'PENDIENTE', 'ENVIADO', 'ERROR'
    fecha_envio_whatsapp = Column(DateTime, nullable=True)
    reunion_familiar = Column(Boolean, default=False, nullable=False)

    # Relaciones
    cuidador = relationship("Cuidador", back_populates="asignaciones")
    bloque = relationship("BloqueTurno", back_populates="asignaciones")


class ActividadMedica(Base):
    """
    Actividades y Visitas Médicas: Curaciones, visitas domiciliarias, etc.
    El personal médico es opcional (puede o no estar asignado).
    """
    __tablename__ = "actividades_medicas"

    id_actividad = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fecha = Column(Date, nullable=False, index=True)
    hora = Column(Time, nullable=False)
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    id_medico = Column(Integer, ForeignKey("personal_medico.id_medico"), nullable=True)

    # Relaciones
    medico_asignado = relationship("PersonalMedico", back_populates="actividades")


class TratamientoMedicamento(Base):
    """
    Tabla de Tratamientos de Medicamentos:
    Registra el tratamiento indicado por o asignado a un personal médico,
    con su día inicial y horarios de toma.
    """
    __tablename__ = "tratamiento_medicamentos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    personal_medico_id = Column(Integer, ForeignKey("personal_medico.id_medico", ondelete="SET NULL"), nullable=True, index=True)
    nombre_medicamento = Column(String(200), nullable=False)
    dia_inicial = Column(Date, nullable=False, index=True)

    # Relaciones
    personal_medico = relationship("PersonalMedico", back_populates="tratamientos")
    horarios = relationship(
        "MedicamentoHorario",
        back_populates="tratamiento",
        cascade="all, delete-orphan",
        order_by="MedicamentoHorario.dia, MedicamentoHorario.hora"
    )


class MedicamentoHorario(Base):
    """
    Tabla de Horarios de Medicamentos:
    Días y horas específicas programadas para la administración del medicamento.
    Eliminación en cascada vinculada al tratamiento.
    """
    __tablename__ = "medicamento_horarios"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    medicamento_id = Column(Integer, ForeignKey("tratamiento_medicamentos.id", ondelete="CASCADE"), nullable=False, index=True)
    dia = Column(Date, nullable=False, index=True)
    hora = Column(Time, nullable=False)

    # Relaciones
    tratamiento = relationship("TratamientoMedicamento", back_populates="horarios")

