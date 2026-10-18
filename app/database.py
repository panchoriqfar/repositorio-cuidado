import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("database")
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./turnos_medicos.db")

# Compatibilidad con URLs de Neon / Supabase / Heroku / Render
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

def _obtener_engine(url: str):
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)

try:
    engine = _obtener_engine(DATABASE_URL)
    # Probar conexión temprana
    with engine.connect() as conn:
        pass
    logger.info("Conectado exitosamente a la base de datos principal.")
except Exception as e:
    logger.warning(f"No fue posible conectar con DATABASE_URL ({DATABASE_URL}). Se activa respaldo SQLite local. Motivo: {e}")
    DATABASE_URL = "sqlite:///./turnos_medicos.db"
    engine = _obtener_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
