# -*- coding: utf-8 -*-
"""Database connection utilities.

This module loads the ``DATABASE_URL`` from the environment (or falls back to a
local SQLite file) and creates a SQLAlchemy ``engine`` and ``SessionLocal``
factory. It also performs a quick health‑check at import time so connection
problems surface early during application start‑up.
"""

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load environment variables from a .env file located at the project root.
# ---------------------------------------------------------------------------
load_dotenv()

<<<<<<< HEAD
logger = logging.getLogger("database")
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./turnos_medicos.db")
=======
# ---------------------------------------------------------------------------
# DATABASE_URL handling
# ---------------------------------------------------------------------------
# Default to an absolute SQLite file path so the DB lives next to the repository
# regardless of the current working directory.
DEFAULT_SQLITE_PATH = os.path.abspath("turnos_medicos.db")
DEFAULT_SQLITE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"
>>>>>>> d914467b39bc388d08b8f44967ce83031b29b715

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL).strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not defined and no default could be resolved.")

# Compatibility shim for legacy Heroku‑style URLs (e.g. ``postgres://``).
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

<<<<<<< HEAD
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
=======
# ---------------------------------------------------------------------------
# Engine creation with driver‑specific connection arguments
# ---------------------------------------------------------------------------
connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    # SQLite needs ``check_same_thread=False`` when used with FastAPI's async
    # request handling.
    connect_args["check_same_thread"] = False

try:
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )
except Exception as exc:
    raise RuntimeError(f"Failed to initialise SQLAlchemy engine: {exc}") from exc
>>>>>>> d914467b39bc388d08b8f44967ce83031b29b715

# Quick health‑check – raises if the DB is unreachable or credentials are bad.
try:
    with engine.connect() as conn:
        conn.execute("SELECT 1")
except Exception as exc:
    raise RuntimeError(f"Database connection test failed: {exc}") from exc

# Session factory used by FastAPI dependencies.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for declarative models.
Base = declarative_base()

def get_db():
    """FastAPI dependency that yields a DB session and guarantees cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
