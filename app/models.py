from sqlalchemy import Column, Integer, String, Boolean, Date, Time, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Usuario(Base):
    """
    Tabla de Usuarios del Sistema con soporte de Roles (RBAC):
    - 'super_user': Acceso total, gestión de usuarios, orquestación y eliminación de cuidadores.
    - 'admin': Mismos permisos operativos excepto eliminación de cuidadores y asignación de rol super_user.
    """
    __tablename__ = "usuarios"

    id_usuario = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(20), default="admin", nullable=False) # 'super_user', 'admin'


class Cuidador(Base):
    """
    Tabla de Cuidadores: A quienes EXCLUSIVAMENTE se les asignan los turnos de cuidado.
    """
    __tablename__ = "cuidadores"

    id_cuidador = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    telefono_whatsapp = Column(String(25), nullable=False)  # Formato E.164 ej: +56912345678
    rol_trabajo = Column(String(100), default="Cuidador", nullable=False) # ej: Cuidador Diurno, Cuidador Nocturno, TENS
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
    apellido = Column(String(100), nullable=False)
    telefono_whatsapp = Column(String(25), nullable=False)  # Formato E.164
    especialidad = Column(String(100), nullable=False)      # ej: 'Médico General', 'Enfermera Jefe', 'Kinesiólogo'
    activo = Column(Boolean, default=True, nullable=False)

    # Relaciones: Se le pueden asociar o no actividades médicas
    actividades = relationship("ActividadMedica", back_populates="medico_asignado")


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
