import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        import sqlite3
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    except Exception:
        pass

logger = logging.getLogger("database")
logging.basicConfig(level=logging.INFO)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(BASE_DIR, "turnos_medicos.db")
DEFAULT_SQLITE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH.replace(os.sep, '/')}"

raw_db_url = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)
if raw_db_url.startswith("sqlite:///./") or raw_db_url == "sqlite:///turnos_medicos.db":
    rel = raw_db_url.replace("sqlite:///./", "").replace("sqlite:///", "")
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, rel).replace(os.sep, '/')}"
else:
    DATABASE_URL = raw_db_url

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
        DATABASE_URL = DEFAULT_SQLITE_URL
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
