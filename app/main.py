import os
from datetime import date, time, datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import engine, Base, get_db
from app.models import (
    Usuario, Cuidador, PersonalMedico, BloqueTurno,
    AsignacionTurno, ActividadMedica, TratamientoMedicamento, MedicamentoHorario
)
from app import schemas, auth, whatsapp, email_service
from sqlalchemy.orm import joinedload

load_dotenv()

# Crear tablas en la base de datos (PostgreSQL/Supabase o SQLite de respaldo)
Base.metadata.create_all(bind=engine)

def migrar_esquema_bd(target_engine):
    """Garantiza la existencia de columnas nuevas como must_change_password, cuidadores.mail y asignaciones_turnos.reunion_familiar."""
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(target_engine)
        tablas = inspector.get_table_names()
        if "usuarios" in tablas:
            columnas = [c["name"] for c in inspector.get_columns("usuarios")]
            if "must_change_password" not in columnas:
                with target_engine.begin() as conn:
                    conn.execute(text("ALTER TABLE usuarios ADD COLUMN must_change_password BOOLEAN DEFAULT 0 NOT NULL"))
        if "cuidadores" in tablas:
            cuid_cols = [c["name"] for c in inspector.get_columns("cuidadores")]
            if "mail" not in cuid_cols:
                with target_engine.begin() as conn:
                    conn.execute(text("ALTER TABLE cuidadores ADD COLUMN mail VARCHAR(150)"))
        if "asignaciones_turnos" in tablas:
            asig_cols = [c["name"] for c in inspector.get_columns("asignaciones_turnos")]
            if "reunion_familiar" not in asig_cols:
                with target_engine.begin() as conn:
                    conn.execute(text("ALTER TABLE asignaciones_turnos ADD COLUMN reunion_familiar BOOLEAN DEFAULT 0 NOT NULL"))
    except Exception as exc:
        print(f"Aviso migración de esquema: {exc}")

migrar_esquema_bd(engine)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
is_production = ENVIRONMENT in ["production", "prod"]

docs_url = None if is_production else "/docs"
redoc_url = None if is_production else "/redoc"
openapi_url = None if is_production else "/openapi.json"

app = FastAPI(
    title="Sistema de Gestión de Turnos de Cuidadores y Actividades Médicas",
    description="API con Control de Acceso Basado en Roles (RBAC: super_user y admin), Gestión de Turnos y Actividades Médicas",
    version="2.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url
)

# Configuración estricta de CORS (evita comodín indiscriminado en producción con credentials)
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
if allowed_origins_env:
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
elif is_production:
    allowed_origins = [
        "https://medturnospro.cl",
        "https://app.medturnospro.cl"
    ]
else:
    allowed_origins = [
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8000"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Manejador global de excepciones para prevenir filtraciones de trazas internas o de base de datos
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import logging
    logging.exception(f"Error no controlado en la ruta {request.url.path}: {exc}")
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None)
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Ha ocurrido un error interno en el servidor. Por favor, contacte al administrador."}
    )

# Configuración de carpetas estáticas y templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)
if not os.path.exists(TEMPLATES_DIR):
    os.makedirs(TEMPLATES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def calcular_bloque_por_horario(hora_inicio: time, db: Session) -> BloqueTurno:
    """
    Clasifica automáticamente el horario en los bloques visuales estándar:
    - AM: 06:00 a 14:29
    - PM1: 14:30 a 17:59
    - PM2: 18:00 a 20:59
    - Nocturno (N): 21:00 a 05:59
    """
    bloques = {b.codigo_bloque: b for b in db.query(BloqueTurno).all()}
    minutos = hora_inicio.hour * 60 + hora_inicio.minute

    if 360 <= minutos < 870:
        return bloques.get("AM") or list(bloques.values())[0]
    elif 870 <= minutos < 1080:
        return bloques.get("PM1") or list(bloques.values())[0]
    elif 1080 <= minutos < 1260:
        return bloques.get("PM2") or list(bloques.values())[0]
    else:
        return bloques.get("N") or list(bloques.values())[0]


# --- EVENTO DE INICIALIZACIÓN (SEED / ARRANQUE) ---
@app.on_event("startup")
def startup_seed_data():
    db = next(get_db())
    try:
        # 1. Superusuario Inicial (Seed / Script de arranque con passlib)
        superuser_user = os.getenv("SUPERUSER_USERNAME") or os.getenv("ADMIN_DEFAULT_USERNAME") or "admin"
        superuser_pass = os.getenv("SUPERUSER_PASSWORD") or os.getenv("ADMIN_DEFAULT_PASSWORD") or "admin1234"

        # Verificar si existe algún superusuario o usuario
        usuarios_count = db.query(Usuario).count()
        if usuarios_count == 0:
            super_user = Usuario(
                username=superuser_user,
                password_hash=auth.get_password_hash(superuser_pass),
                rol="super_user"
            )
            db.add(super_user)
            db.commit()
        else:
            # Migración suave: normalizar usuarios antiguos 'ADMIN' a 'super_user'
            admins_viejos = db.query(Usuario).filter(Usuario.rol == "ADMIN").all()
            for u in admins_viejos:
                u.rol = "super_user"
            if admins_viejos:
                db.commit()

        # Garantizar que la cuenta superuser_user tenga rol super_user
        super_record = db.query(Usuario).filter(Usuario.username == superuser_user).first()
        if super_record and super_record.rol != "super_user":
            super_record.rol = "super_user"
            db.commit()

        # 2. Bloques visuales para el cuadrante del front: AM, PM1, PM2, Nocturno
        bloques_default = [
            {"codigo_bloque": "AM", "nombre_bloque": "AM", "hora_inicio": time(10, 0), "hora_fin": time(14, 30)},
            {"codigo_bloque": "PM1", "nombre_bloque": "PM1", "hora_inicio": time(14, 30), "hora_fin": time(18, 0)},
            {"codigo_bloque": "PM2", "nombre_bloque": "PM2", "hora_inicio": time(18, 0), "hora_fin": time(21, 0)},
            {"codigo_bloque": "N", "nombre_bloque": "Nocturno", "hora_inicio": time(21, 0), "hora_fin": time(10, 0)},
        ]

        for b_data in bloques_default:
            existe = db.query(BloqueTurno).filter(BloqueTurno.codigo_bloque == b_data["codigo_bloque"]).first()
            if not existe:
                db.add(BloqueTurno(**b_data))
            else:
                existe.nombre_bloque = b_data["nombre_bloque"]
        db.commit()
    finally:
        db.close()


# --- VISTA PÚBLICA ---
@app.get("/", response_class=HTMLResponse)
def vista_publica(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# --- AUTENTICACIÓN JWT ---
@app.post("/api/auth/login", response_model=schemas.Token)
def login(creds: schemas.LoginRequest, db: Session = Depends(get_db)):
    username_clean = creds.username.strip()
    user = db.query(Usuario).filter(Usuario.username == username_clean).first()
    if not user or not auth.verify_password(creds.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Asegurar rol normalizado
    rol_limpio = (user.rol or "admin").lower().strip()
    superuser_user = os.getenv("SUPERUSER_USERNAME") or os.getenv("ADMIN_DEFAULT_USERNAME") or "admin"
    if user.username == superuser_user:
        rol_limpio = "super_user"
        if user.rol != "super_user":
            user.rol = "super_user"
            db.commit()

    access_token = auth.create_access_token(
        data={"sub": user.username, "rol": rol_limpio}
    )
    return schemas.Token(
        access_token=access_token,
        token_type="bearer",
        username=user.username,
        rol=rol_limpio
    )

@app.get("/api/auth/me", response_model=schemas.UsuarioResponse)
def get_mi_perfil(current_user: Usuario = Depends(auth.get_current_user)):
    return current_user


# --- CAMBIO DE CONTRASEÑA (Disponible para cualquier usuario autenticado) ---
@app.post("/api/auth/cambiar-password")
def cambiar_password(
    datos: schemas.CambiarPasswordRequest,
    current_user: Usuario = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Permite a cualquier usuario autenticado cambiar su propia contraseña.
    Si must_change_password=True, es obligatorio antes de realizar acciones en el sistema.
    """
    if not auth.verify_password(datos.password_actual, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta"
        )
    nueva = datos.password_nueva.strip()
    if len(nueva) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe tener al menos 4 caracteres"
        )
    if auth.verify_password(nueva, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe ser diferente a la contraseña actual"
        )
    current_user.password_hash = auth.get_password_hash(nueva)
    current_user.must_change_password = False
    db.commit()
    return {"message": "Contraseña actualizada exitosamente"}


# --- GESTIÓN DE USUARIOS Y ROLES (RBAC EXCLUSIVO SUPER_USER) ---
@app.get("/api/admin/usuarios", response_model=List[schemas.UsuarioResponse])
def listar_usuarios(
    current_user: Usuario = Depends(auth.require_super_user),
    db: Session = Depends(get_db)
):
    """Permite listar los usuarios del sistema. Disponible EXCLUSIVAMENTE para super_user."""
    return db.query(Usuario).order_by(Usuario.id_usuario.asc()).all()

@app.post("/api/admin/usuarios", response_model=schemas.UsuarioResponse)
def crear_usuario(
    datos: schemas.UsuarioCreate,
    current_user: Usuario = Depends(auth.require_super_user),
    db: Session = Depends(get_db)
):
    """
    Crea un nuevo usuario en el sistema.
    RESTRICCIÓN ESTRICTA: Solo el super_user puede crear usuarios (admin o super_user).
    Los administradores estándar tienen prohibido el acceso a este endpoint.
    """
    rol_solicitado = (datos.rol or "admin").lower().strip()
    if rol_solicitado not in ["super_user", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rol inválido. Los roles permitidos son: 'super_user' o 'admin'"
        )

    username_limpio = datos.username.strip()
    if not username_limpio:
        raise HTTPException(status_code=400, detail="El nombre de usuario es obligatorio")

    if not datos.password or len(datos.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 4 caracteres")

    existe = db.query(Usuario).filter(Usuario.username == username_limpio).first()
    if existe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El nombre de usuario '{username_limpio}' ya se encuentra registrado"
        )

    nuevo_usuario = Usuario(
        username=username_limpio,
        password_hash=auth.get_password_hash(datos.password.strip()),
        rol=rol_solicitado,
        must_change_password=True  # El usuario DEBE cambiar su contraseña en el primer login
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return nuevo_usuario

@app.put("/api/admin/usuarios/{id_usuario}", response_model=schemas.UsuarioResponse)
def actualizar_usuario(
    id_usuario: int,
    datos: schemas.UsuarioUpdate,
    current_user: Usuario = Depends(auth.require_super_user),
    db: Session = Depends(get_db)
):
    """Actualiza datos de un usuario. Exclusivo para super_user."""
    target_user = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if datos.rol:
        nuevo_rol = datos.rol.lower().strip()
        if nuevo_rol not in ["super_user", "admin"]:
            raise HTTPException(status_code=400, detail="Rol inválido ('super_user' o 'admin')")
        target_user.rol = nuevo_rol

    if datos.username:
        username_limpio = datos.username.strip()
        if username_limpio:
            existe_otro = db.query(Usuario).filter(Usuario.username == username_limpio, Usuario.id_usuario != id_usuario).first()
            if existe_otro:
                raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso")
            target_user.username = username_limpio

    if datos.password and datos.password.strip():
        target_user.password_hash = auth.get_password_hash(datos.password.strip())

    db.commit()
    db.refresh(target_user)
    return target_user

@app.delete("/api/admin/usuarios/{id_usuario}")
def eliminar_usuario(
    id_usuario: int,
    current_user: Usuario = Depends(auth.require_super_user),
    db: Session = Depends(get_db)
):
    """Solo un super_user puede eliminar usuarios."""
    if current_user.id_usuario == id_usuario:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta en sesión")

    target_user = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    username_eliminado = target_user.username
    db.delete(target_user)
    db.commit()
    return {"message": f"Usuario '{username_eliminado}' eliminado exitosamente"}


# --- GESTIÓN DE CUIDADORES (A QUIENES SE ASIGNAN LOS TURNOS) ---
@app.get("/api/admin/cuidadores", response_model=List[schemas.CuidadorResponse])
def listar_cuidadores(
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    return db.query(Cuidador).order_by(Cuidador.nombre.asc()).all()

@app.post("/api/admin/cuidadores", response_model=schemas.CuidadorResponse)
def crear_cuidador(
    datos: schemas.CuidadorCreate,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    import re
    nombre_limpio = datos.nombre.strip()
    if not nombre_limpio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre del cuidador/a es obligatorio"
        )

    # Validar formato WhatsApp: debe ser +569 seguido de exactamente 8 dígitos
    patron_wa = re.compile(r"^\+569\d{8}$")
    if not patron_wa.match(datos.telefono_whatsapp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El número de WhatsApp debe tener el formato +569XXXXXXXX (exactamente 8 dígitos después de +569)"
        )
    mail_limpio = datos.mail.strip() if datos.mail and datos.mail.strip() else None
    nuevo = Cuidador(
        nombre=nombre_limpio,
        apellido=(datos.apellido or "").strip(),
        telefono_whatsapp=datos.telefono_whatsapp.strip(),
        mail=mail_limpio,
        rol_trabajo="",
        activo=True
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@app.put("/api/admin/cuidadores/{id_cuidador}", response_model=schemas.CuidadorResponse)
def actualizar_cuidador(
    id_cuidador: int,
    datos: schemas.CuidadorUpdate,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    cuid = db.query(Cuidador).filter(Cuidador.id_cuidador == id_cuidador).first()
    if not cuid:
        raise HTTPException(status_code=404, detail="Cuidador no encontrado")
    for key, val in datos.model_dump(exclude_unset=True).items():
        setattr(cuid, key, val)
    db.commit()
    db.refresh(cuid)
    return cuid

@app.delete("/api/admin/cuidadores/{id_cuidador}")
def eliminar_cuidador(
    id_cuidador: int,
    current_user: Usuario = Depends(auth.require_super_user),
    db: Session = Depends(get_db)
):
    """
    Eliminación de cuidador:
    RESTRICCIÓN RBAC ESTRICTA: Solo el rol 'super_user' tiene permitido eliminar o desactivar cuidadores.
    Los usuarios con rol 'admin' tienen prohibida esta acción.
    """
    cuid = db.query(Cuidador).filter(Cuidador.id_cuidador == id_cuidador).first()
    if not cuid:
        raise HTTPException(status_code=404, detail="Cuidador no encontrado")
    cuid.activo = False
    db.commit()
    return {"message": "Cuidador desactivado exitosamente por super_user"}


# --- GESTIÓN DE PERSONAL MÉDICO (ACTIVIDADES Y VISITAS) ---
@app.get("/api/admin/medicos", response_model=List[schemas.PersonalMedicoResponse])
def listar_medicos(
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    return db.query(PersonalMedico).order_by(PersonalMedico.nombre.asc()).all()

@app.post("/api/admin/medicos", response_model=schemas.PersonalMedicoResponse)
def crear_medico(
    datos: schemas.PersonalMedicoCreate,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    nombre_limpio = datos.nombre.strip()
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    especialidad_limpia = datos.especialidad.strip()
    if not especialidad_limpia:
        raise HTTPException(status_code=400, detail="La especialidad es obligatoria")

    nuevo = PersonalMedico(
        nombre=nombre_limpio,
        apellido=(datos.apellido or "").strip(),
        especialidad=especialidad_limpia,
        telefono_whatsapp=(datos.telefono_whatsapp or "").strip(),
        activo=True
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@app.put("/api/admin/medicos/{id_medico}", response_model=schemas.PersonalMedicoResponse)
def actualizar_medico(
    id_medico: int,
    datos: schemas.PersonalMedicoUpdate,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    med = db.query(PersonalMedico).filter(PersonalMedico.id_medico == id_medico).first()
    if not med:
        raise HTTPException(status_code=404, detail="Personal médico no encontrado")
    for key, val in datos.model_dump(exclude_unset=True).items():
        setattr(med, key, val)
    db.commit()
    db.refresh(med)
    return med

@app.delete("/api/admin/medicos/{id_medico}")
def eliminar_medico(
    id_medico: int,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    med = db.query(PersonalMedico).filter(PersonalMedico.id_medico == id_medico).first()
    if not med:
        raise HTTPException(status_code=404, detail="Personal médico no encontrado")
    med.activo = False
    db.commit()
    return {"message": "Personal médico desactivado exitosamente"}


# --- BLOQUES HORARIOS ---
@app.get("/api/admin/bloques", response_model=List[schemas.BloqueTurnoResponse])
def listar_bloques(
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    return db.query(BloqueTurno).order_by(BloqueTurno.id_bloque.asc()).all()


# --- CUADRANTE SEMANAL (VISTA PÚBLICA) ---
@app.get("/api/public/cuadrante")
def obtener_cuadrante_semanal(
    fecha_base: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    if not fecha_base:
        fecha_base = date.today()

    inicio_semana = fecha_base - timedelta(days=fecha_base.weekday())
    fin_semana = inicio_semana + timedelta(days=6)

    nombres_dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dias = []
    for i in range(7):
        current_date = inicio_semana + timedelta(days=i)
        dias.append({
            "nombre": nombres_dias[i],
            "fecha": current_date.isoformat(),
            "es_hoy": (current_date == date.today())
        })

    bloques = db.query(BloqueTurno).order_by(BloqueTurno.id_bloque.asc()).all()

    asignaciones = (
        db.query(AsignacionTurno)
        .join(Cuidador)
        .join(BloqueTurno)
        .filter(AsignacionTurno.fecha >= inicio_semana, AsignacionTurno.fecha <= fin_semana)
        .all()
    )

    matriz = {}
    for asig in asignaciones:
        f_str = asig.fecha.isoformat()
        b_id = asig.id_bloque
        if b_id not in matriz:
            matriz[b_id] = {}
        if f_str not in matriz[b_id]:
            matriz[b_id][f_str] = []

        hora_ini_str = asig.hora_inicio.strftime("%H:%M")
        hora_fin_str = asig.hora_fin.strftime("%H:%M")

        matriz[b_id][f_str].append({
            "id_asignacion": asig.id_asignacion,
            "id_cuidador": asig.id_cuidador,
            "cuidador_nombre": f"{asig.cuidador.nombre} {asig.cuidador.apellido or ''}".strip(),
            "cuidador_telefono": asig.cuidador.telefono_whatsapp,
            "hora_inicio": hora_ini_str,
            "hora_fin": hora_fin_str,
            "horario_texto": f"{hora_ini_str} - {hora_fin_str}",
            "estado_notificacion": asig.estado_notificacion,
            "fecha_envio_whatsapp": asig.fecha_envio_whatsapp.isoformat() if asig.fecha_envio_whatsapp else None,
            "reunion_familiar": bool(getattr(asig, "reunion_familiar", False))
        })

    return {
        "inicio_semana": inicio_semana.isoformat(),
        "fin_semana": fin_semana.isoformat(),
        "dias": dias,
        "bloques": [
            {
                "id_bloque": b.id_bloque,
                "codigo_bloque": b.codigo_bloque,
                "nombre_bloque": b.nombre_bloque,
                "hora_inicio": b.hora_inicio.strftime("%H:%M"),
                "hora_fin": b.hora_fin.strftime("%H:%M")
            }
            for b in bloques
        ],
        "matriz": matriz
    }


# --- ASIGNACIONES DE TURNO ---
@app.post("/api/admin/asignaciones", response_model=schemas.AsignacionTurnoResponse)
def crear_o_actualizar_asignacion(
    datos: schemas.AsignacionTurnoCreate,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    cuidadores_ids = []
    if datos.cuidadores_ids and len(datos.cuidadores_ids) > 0:
        cuidadores_ids = [cid for cid in datos.cuidadores_ids if cid]
    elif datos.id_cuidador:
        cuidadores_ids = [datos.id_cuidador]

    if not cuidadores_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe seleccionar al menos un/a cuidador/a"
        )

    cuidadores = db.query(Cuidador).filter(Cuidador.id_cuidador.in_(cuidadores_ids), Cuidador.activo == True).all()
    cuidadores_map = {c.id_cuidador: c for c in cuidadores}
    for cid in cuidadores_ids:
        if cid not in cuidadores_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El cuidador con ID {cid} no es válido o está inactivo"
            )

    if datos.id_bloque:
        bloque = db.query(BloqueTurno).filter(BloqueTurno.id_bloque == datos.id_bloque).first()
        if not bloque:
            bloque = calcular_bloque_por_horario(datos.hora_inicio, db)
    else:
        bloque = calcular_bloque_por_horario(datos.hora_inicio, db)

    asignaciones_guardadas = []
    for cid in cuidadores_ids:
        existente = (
            db.query(AsignacionTurno)
            .filter(
                AsignacionTurno.fecha == datos.fecha,
                AsignacionTurno.id_bloque == bloque.id_bloque,
                AsignacionTurno.id_cuidador == cid
            )
            .first()
        )

        if existente:
            existente.hora_inicio = datos.hora_inicio
            existente.hora_fin = datos.hora_fin
            existente.id_bloque = bloque.id_bloque
            existente.reunion_familiar = bool(datos.reunion_familiar)
            existente.estado_notificacion = "PENDIENTE"
            existente.fecha_envio_whatsapp = None
            asignaciones_guardadas.append(existente)
        else:
            nueva = AsignacionTurno(
                fecha=datos.fecha,
                id_cuidador=cid,
                hora_inicio=datos.hora_inicio,
                hora_fin=datos.hora_fin,
                id_bloque=bloque.id_bloque,
                reunion_familiar=bool(datos.reunion_familiar),
                estado_notificacion="PENDIENTE"
            )
            db.add(nueva)
            asignaciones_guardadas.append(nueva)

    db.commit()
    for asig in asignaciones_guardadas:
        db.refresh(asig)

    return asignaciones_guardadas[0]

@app.delete("/api/admin/asignaciones/{id_asignacion}")
def eliminar_asignacion(
    id_asignacion: int,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    asig = db.query(AsignacionTurno).filter(AsignacionTurno.id_asignacion == id_asignacion).first()
    if not asig:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    db.delete(asig)
    db.commit()
    return {"message": "Turno desasignado exitosamente"}


# --- ACTIVIDADES MÉDICAS ---
@app.get("/api/public/actividades-semana", response_model=List[schemas.ActividadMedicaResponse])
def obtener_actividades_semana(
    fecha_base: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    if not fecha_base:
        fecha_base = date.today()
    inicio_semana = fecha_base - timedelta(days=fecha_base.weekday())
    fin_semana = inicio_semana + timedelta(days=6)

    actividades = (
        db.query(ActividadMedica)
        .filter(ActividadMedica.fecha >= inicio_semana, ActividadMedica.fecha <= fin_semana)
        .order_by(ActividadMedica.fecha.asc(), ActividadMedica.hora.asc())
        .all()
    )
    return actividades

@app.post("/api/admin/actividades", response_model=schemas.ActividadMedicaResponse)
def crear_actividad(
    datos: schemas.ActividadMedicaCreate,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    if datos.id_medico:
        medico = db.query(PersonalMedico).filter(PersonalMedico.id_medico == datos.id_medico).first()
        if not medico:
            raise HTTPException(status_code=400, detail="El personal médico seleccionado no existe")

    nueva = ActividadMedica(**datos.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@app.put("/api/admin/actividades/{id_actividad}", response_model=schemas.ActividadMedicaResponse)
def actualizar_actividad(
    id_actividad: int,
    datos: schemas.ActividadMedicaUpdate,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    act = db.query(ActividadMedica).filter(ActividadMedica.id_actividad == id_actividad).first()
    if not act:
        raise HTTPException(status_code=404, detail="Actividad médica no encontrada")
    for key, val in datos.model_dump(exclude_unset=True).items():
        setattr(act, key, val)
    db.commit()
    db.refresh(act)
    return act

@app.delete("/api/admin/actividades/{id_actividad}")
def eliminar_actividad(
    id_actividad: int,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    act = db.query(ActividadMedica).filter(ActividadMedica.id_actividad == id_actividad).first()
    if not act:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    db.delete(act)
    db.commit()
    return {"message": "Actividad eliminada exitosamente"}


# --- NOTIFICACIONES WHATSAPP DEL DÍA ---
@app.post("/api/admin/notificaciones/enviar-dia", response_model=schemas.NotificacionDiaResponse)
def enviar_notificaciones_del_dia(
    payload: schemas.NotificacionDiaRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    target_date = payload.fecha or date.today()
    resultado = whatsapp.enviar_notificaciones_del_dia(target_date, db)
    return resultado


# --- NOTIFICACIONES WHATSAPP SEMANA COMPLETA ---
@app.post("/api/admin/notificaciones/enviar-semana")
def enviar_notificaciones_semana(
    payload: schemas.NotificacionSemanalRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """
    Envía mensaje consolidado de WhatsApp a TODOS los cuidadores de la semana
    con sus turnos asignados y actividades médicas correspondientes.
    """
    fecha_base = payload.fecha_base or date.today()
    resultado = whatsapp.enviar_notificaciones_semana_completa(fecha_base, db)
    return resultado


# --- NOTIFICACIONES POR CORREO ELECTRÓNICO (GMAIL SMTP) ---
@app.post("/api/admin/notificaciones/enviar-email-dia", response_model=schemas.NotificacionEmailResponse)
def enviar_email_del_dia(
    payload: schemas.NotificacionEmailDiaRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """
    Envía notificación por correo a los cuidadores asignados al turno del día,
    detallando sus horarios y actividades médicas.
    """
    target_date = payload.fecha or date.today()
    return email_service.enviar_correos_del_dia(target_date, db)


@app.post("/api/admin/notificaciones/enviar-email-semana", response_model=schemas.NotificacionEmailResponse)
def enviar_email_semana_completa(
    payload: schemas.NotificacionEmailSemanalRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """
    Envía planificación semanal consolidada por correo a todos los cuidadores
    con turnos asignados en la semana, incluyendo sus actividades médicas.
    """
    fecha_base = payload.fecha_base or date.today()
    return email_service.enviar_correos_semana_completa(fecha_base, db)


@app.post("/api/admin/notificaciones/enviar-email-medicamentos", response_model=schemas.NotificacionEmailResponse)
def enviar_email_medicamentos(
    payload: schemas.NotificacionEmailMedicamentosRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """
    Envía por correo electrónico la pauta exclusiva de medicamentos y sus horarios
    (sin turnos ni actividades médicas), con el formato agrupado consolidado.
    """
    tipo = payload.tipo or "semana"
    if tipo == "dia":
        f_ini = payload.fecha or date.today()
        f_fin = f_ini
    else:
        if payload.fecha_inicio and payload.fecha_fin:
            f_ini = payload.fecha_inicio
            f_fin = payload.fecha_fin
        else:
            base = payload.fecha or date.today()
            f_ini = base - timedelta(days=base.weekday())
            f_fin = f_ini + timedelta(days=6)

    return email_service.enviar_correos_solo_medicamentos_periodo(
        db=db,
        fecha_inicio=f_ini,
        fecha_fin=f_fin,
        destinatario_tipo=payload.destinatario_tipo or "todos",
        id_cuidador=payload.id_cuidador,
        email_manual=payload.destinatario_email
    )


@app.post("/api/admin/notificaciones/enviar-email-actividades", response_model=schemas.NotificacionEmailResponse)
def enviar_email_actividades(
    payload: schemas.NotificacionEmailActividadesRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """
    Envía por correo electrónico la lista exclusiva de actividades y visitas médicas
    (sin turnos ni medicamentos).
    """
    tipo = payload.tipo or "semana"
    if tipo == "dia":
        f_ini = payload.fecha or date.today()
        f_fin = f_ini
    else:
        if payload.fecha_inicio and payload.fecha_fin:
            f_ini = payload.fecha_inicio
            f_fin = payload.fecha_fin
        else:
            base = payload.fecha or date.today()
            f_ini = base - timedelta(days=base.weekday())
            f_fin = f_ini + timedelta(days=6)

    return email_service.enviar_correos_solo_actividades_periodo(
        db=db,
        fecha_inicio=f_ini,
        fecha_fin=f_fin,
        destinatario_tipo=payload.destinatario_tipo or "todos",
        id_cuidador=payload.id_cuidador,
        email_manual=payload.destinatario_email
    )


@app.post("/api/admin/notificaciones/enviar-email-horario", response_model=schemas.NotificacionEmailResponse)
def enviar_email_horario(
    payload: schemas.NotificacionEmailHorarioRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """
    Envía por correo electrónico la planificación de horarios y turnos
    (con actividades y pauta de medicamentos asignada a cada cuidador).
    Permite seleccionar entre semana completa o día específico, y enviar a todos
    los cuidadores con turnos o a uno en particular.
    """
    tipo = payload.tipo or "semana"
    if tipo == "dia":
        f_ini = payload.fecha or date.today()
        f_fin = f_ini
    else:
        if payload.fecha_inicio and payload.fecha_fin:
            f_ini = payload.fecha_inicio
            f_fin = payload.fecha_fin
        else:
            base = payload.fecha or date.today()
            f_ini = base - timedelta(days=base.weekday())
            f_fin = f_ini + timedelta(days=6)

    return email_service.enviar_correos_horario_periodo(
        db=db,
        fecha_base=f_ini,
        tipo=tipo,
        destinatario_tipo=payload.destinatario_tipo or "todos",
        id_cuidador=payload.id_cuidador,
        email_manual=payload.destinatario_email,
        fecha_inicio=f_ini,
        fecha_fin=f_fin
    )


@app.post("/api/admin/notificaciones/enviar-email-prueba")
def enviar_email_prueba(
    payload: schemas.EnvioEmailPruebaRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user)
):
    """
    Envía un correo de prueba vía Resend API utilizando las variables de entorno de producción.
    Retorna respuesta JSON estructurada con status: success / status: error.
    """
    resultado = email_service.enviar_email_via_resend(
        destinatario=payload.destinatario,
        asunto=payload.asunto or "MedTurnos Pro - Correo de Prueba",
        texto=payload.mensaje or "Este es un correo de prueba de MedTurnos Pro desde producción.",
        html=payload.html or f"<p>{payload.mensaje or 'Este es un correo de prueba de MedTurnos Pro desde producción.'}</p>"
    )
    return resultado


# ==============================================================================
# --- GESTIÓN DE MEDICAMENTOS ---
# ==============================================================================

@app.post(
    "/api/medicamentos/",
    response_model=schemas.TratamientoMedicamentoResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Medicamentos"]
)
def registrar_tratamiento_medicamento(
    payload: schemas.TratamientoMedicamentoCreate,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """
    Registra un tratamiento de medicamento con su día inicial, múltiples horarios iniciales
    y la opción de clonar/agregar nuevos días y horas de forma dinámica.
    """
    # 1. Verificar existencia del profesional de personal médico si fue proporcionado
    if payload.personal_medico_id is not None:
        medico = db.query(PersonalMedico).filter(PersonalMedico.id_medico == payload.personal_medico_id).first()
        if not medico:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Personal médico con id {payload.personal_medico_id} no encontrado."
            )

    # 2. Instanciar tratamiento
    nuevo_tratamiento = TratamientoMedicamento(
        personal_medico_id=payload.personal_medico_id,
        nombre_medicamento=payload.nombre_medicamento.strip(),
        dia_inicial=payload.dia_inicial
    )
    db.add(nuevo_tratamiento)
    db.flush()

    # 3. Recopilar y clonar/agregar horarios dinámicamente sin duplicados
    horarios_unicos = set()
    lista_horarios: List[MedicamentoHorario] = []

    # 3.1 Horarios iniciales en el día inicial
    horas_base = list(payload.horarios_iniciales or [])
    for hora in horas_base:
        clave = (payload.dia_inicial, hora)
        if clave not in horarios_unicos:
            horarios_unicos.add(clave)
            lista_horarios.append(
                MedicamentoHorario(medicamento_id=nuevo_tratamiento.id, dia=payload.dia_inicial, hora=hora)
            )

    # 3.2 Clonar dinámicamente según cantidad de días (duracion_dias o dias_a_clonar)
    total_dias = payload.duracion_dias or payload.dias_a_clonar
    if total_dias and total_dias > 1 and horas_base:
        for offset in range(1, total_dias):
            dia_clonado = payload.dia_inicial + timedelta(days=offset)
            for hora in horas_base:
                clave = (dia_clonado, hora)
                if clave not in horarios_unicos:
                    horarios_unicos.add(clave)
                    lista_horarios.append(
                        MedicamentoHorario(medicamento_id=nuevo_tratamiento.id, dia=dia_clonado, hora=hora)
                    )

    # 3.3 Clonar a fechas adicionales específicas si fueron proporcionadas
    if payload.fechas_adicionales and horas_base:
        for fecha_adic in payload.fechas_adicionales:
            for hora in horas_base:
                clave = (fecha_adic, hora)
                if clave not in horarios_unicos:
                    horarios_unicos.add(clave)
                    lista_horarios.append(
                        MedicamentoHorario(medicamento_id=nuevo_tratamiento.id, dia=fecha_adic, hora=hora)
                    )

    # 3.4 Horarios dinámicos o personalizados explícitos (horarios / horarios_dinamicos)
    dinamicos = (payload.horarios or []) + (payload.horarios_dinamicos or [])
    for item in dinamicos:
        dia_final = item.dia or payload.dia_inicial
        clave = (dia_final, item.hora)
        if clave not in horarios_unicos:
            horarios_unicos.add(clave)
            lista_horarios.append(
                MedicamentoHorario(medicamento_id=nuevo_tratamiento.id, dia=dia_final, hora=item.hora)
            )

    if lista_horarios:
        db.add_all(lista_horarios)

    db.commit()
    db.refresh(nuevo_tratamiento)
    return nuevo_tratamiento


@app.get(
    "/api/medicamentos/{personal_medico_id}",
    response_model=List[schemas.TratamientoMedicamentoResponse],
    tags=["Medicamentos"]
)
def consultar_pauta_medicamentos(
    personal_medico_id: int,
    fecha: Optional[date] = Query(None, description="Filtrar por fecha específica (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Endpoint para consultar la pauta de medicamentos asignada a un cuidador/médico filtrada por fecha.
    """
    # 1. Validar existencia del personal médico
    medico = db.query(PersonalMedico).filter(PersonalMedico.id_medico == personal_medico_id).first()
    if not medico:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Personal médico con id {personal_medico_id} no encontrado."
        )

    # 2. Consultar tratamientos vinculados
    tratamientos: List[TratamientoMedicamento] = (
        db.query(TratamientoMedicamento)
        .options(
            joinedload(TratamientoMedicamento.personal_medico),
            joinedload(TratamientoMedicamento.horarios)
        )
        .filter(TratamientoMedicamento.personal_medico_id == personal_medico_id)
        .order_by(TratamientoMedicamento.dia_inicial.desc(), TratamientoMedicamento.id.desc())
        .all()
    )

    # 3. Si se especifica filtro por fecha, seleccionar los horarios del día solicitado (incluyendo tomas arrastradas)
    if fecha is not None:
        resultado_filtrado = []
        for t in tratamientos:
            horarios_dia = [h for h in t.horarios if h.dia == fecha]
            if not horarios_dia and fecha >= t.dia_inicial:
                horas_base = [h.hora for h in t.horarios if h.dia == t.dia_inicial]
                if not horas_base and t.horarios:
                    horas_base = sorted({h.hora for h in t.horarios})
                horarios_dia = [
                    schemas.MedicamentoHorarioResponse(
                        id=0,
                        medicamento_id=t.id,
                        dia=fecha,
                        hora=hb
                    )
                    for hb in horas_base
                ]
            if horarios_dia:
                resultado_filtrado.append(
                    schemas.TratamientoMedicamentoResponse(
                        id=t.id,
                        personal_medico_id=t.personal_medico_id,
                        nombre_medicamento=t.nombre_medicamento,
                        dia_inicial=t.dia_inicial,
                        personal_medico=t.personal_medico,
                        horarios=horarios_dia
                    )
                )
        return resultado_filtrado

    return tratamientos


@app.get(
    "/api/medicamentos/",
    response_model=List[schemas.TratamientoMedicamentoResponse],
    tags=["Medicamentos"]
)
def listar_todos_tratamientos(
    fecha: Optional[date] = Query(None, description="Filtrar por fecha"),
    personal_medico_id: Optional[int] = Query(None, description="Filtrar por personal médico"),
    db: Session = Depends(get_db)
):
    """Listar tratamientos generales con filtros opcionales de fecha y personal médico."""
    query = (
        db.query(TratamientoMedicamento)
        .options(
            joinedload(TratamientoMedicamento.personal_medico),
            joinedload(TratamientoMedicamento.horarios)
        )
    )
    if personal_medico_id:
        query = query.filter(TratamientoMedicamento.personal_medico_id == personal_medico_id)

    tratamientos = query.order_by(TratamientoMedicamento.dia_inicial.desc()).all()

    if fecha is not None:
        resultado = []
        for t in tratamientos:
            horarios_dia = [h for h in t.horarios if h.dia == fecha]
            if not horarios_dia and fecha >= t.dia_inicial:
                horas_base = [h.hora for h in t.horarios if h.dia == t.dia_inicial]
                if not horas_base and t.horarios:
                    horas_base = sorted({h.hora for h in t.horarios})
                horarios_dia = [
                    schemas.MedicamentoHorarioResponse(
                        id=0,
                        medicamento_id=t.id,
                        dia=fecha,
                        hora=hb
                    )
                    for hb in horas_base
                ]
            if horarios_dia:
                resultado.append(
                    schemas.TratamientoMedicamentoResponse(
                        id=t.id,
                        personal_medico_id=t.personal_medico_id,
                        nombre_medicamento=t.nombre_medicamento,
                        dia_inicial=t.dia_inicial,
                        personal_medico=t.personal_medico,
                        horarios=horarios_dia
                    )
                )
        return resultado

    return tratamientos


@app.post(
    "/api/medicamentos/{tratamiento_id}/horarios",
    response_model=schemas.TratamientoMedicamentoResponse,
    tags=["Medicamentos"]
)
def clonar_o_agregar_horarios(
    tratamiento_id: int,
    payload: schemas.ClonarHorariosRequest,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """Clonar o agregar nuevos días y horas a un tratamiento existente."""
    tratamiento = (
        db.query(TratamientoMedicamento)
        .options(joinedload(TratamientoMedicamento.horarios))
        .filter(TratamientoMedicamento.id == tratamiento_id)
        .first()
    )
    if not tratamiento:
        raise HTTPException(status_code=404, detail="Tratamiento no encontrado.")

    existentes = {(h.dia, h.hora) for h in tratamiento.horarios}
    nuevos: List[MedicamentoHorario] = []

    # Determinar horas base a replicar
    horas_base = list(payload.horas) if payload.horas else [h.hora for h in tratamiento.horarios if h.dia == tratamiento.dia_inicial]
    if not horas_base and tratamiento.horarios:
        horas_base = [tratamiento.horarios[0].hora]

    # Clonar por cantidad de días a partir de la fecha más reciente registrada
    if payload.dias_a_clonar and payload.dias_a_clonar > 0 and horas_base:
        fecha_max = max((h.dia for h in tratamiento.horarios), default=tratamiento.dia_inicial)
        for i in range(1, payload.dias_a_clonar + 1):
            dia_destino = fecha_max + timedelta(days=i)
            for hora in horas_base:
                if (dia_destino, hora) not in existentes:
                    existentes.add((dia_destino, hora))
                    nuevos.append(MedicamentoHorario(medicamento_id=tratamiento_id, dia=dia_destino, hora=hora))

    # Clonar a fechas específicas
    if payload.fechas and horas_base:
        for f in payload.fechas:
            for hora in horas_base:
                if (f, hora) not in existentes:
                    existentes.add((f, hora))
                    nuevos.append(MedicamentoHorario(medicamento_id=tratamiento_id, dia=f, hora=hora))

    # Agregar dinámicos
    for item in (payload.horarios_dinamicos or []):
        dia_final = item.dia or tratamiento.dia_inicial
        if (dia_final, item.hora) not in existentes:
            existentes.add((dia_final, item.hora))
            nuevos.append(MedicamentoHorario(medicamento_id=tratamiento_id, dia=dia_final, hora=item.hora))

    if nuevos:
        db.add_all(nuevos)
        db.commit()
        db.refresh(tratamiento)

    return tratamiento


@app.delete(
    "/api/medicamentos/{tratamiento_id}",
    tags=["Medicamentos"]
)
def eliminar_tratamiento_medicamento(
    tratamiento_id: int,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """Eliminar tratamiento de medicamento y todos sus horarios asociados en cascada."""
    tratamiento = (
        db.query(TratamientoMedicamento)
        .options(joinedload(TratamientoMedicamento.horarios))
        .filter(TratamientoMedicamento.id == tratamiento_id)
        .first()
    )
    if not tratamiento:
        raise HTTPException(status_code=404, detail="Tratamiento no encontrado.")
    db.delete(tratamiento)
    db.commit()
    return {"message": "Tratamiento de medicamento y horarios eliminados exitosamente"}


@app.delete(
    "/api/medicamentos/horarios/{horario_id}",
    tags=["Medicamentos"]
)
def eliminar_horario_medicamento(
    horario_id: int,
    current_user: Usuario = Depends(auth.require_admin_or_super_user),
    db: Session = Depends(get_db)
):
    """Eliminar un horario puntual de toma de medicamento."""
    horario = db.query(MedicamentoHorario).filter(MedicamentoHorario.id == horario_id).first()
    if not horario:
        raise HTTPException(status_code=404, detail="Horario de medicamento no encontrado.")
    db.delete(horario)
    db.commit()
    return {"message": "Horario eliminado exitosamente"}

