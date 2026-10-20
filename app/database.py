import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("database")
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./turnos_medicos.db")

def format_database_url(url: str) -> str:
    """Normaliza la URL de conexión para PostgreSQL/Supabase/Neon/Render."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url

DATABASE_URL = format_database_url(DATABASE_URL)

def _build_engine(url: str):
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        connect_args["connect_timeout"] = 5
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)

try:
    engine = _build_engine(DATABASE_URL)
    with engine.connect() as conn:
        pass
    logger.info("Base de datos conectada exitosamente.")
except Exception as exc:
    if not DATABASE_URL.startswith("sqlite"):
        logger.warning(
            f"No fue posible conectar con la base de datos principal. "
            f"Se activa respaldo local SQLite (turnos_medicos.db). Detalle: {exc}"
        )
        DATABASE_URL = "sqlite:///./turnos_medicos.db"
        engine = _build_engine(DATABASE_URL)
    else:
        raise exc

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
