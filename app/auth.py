import os
from datetime import datetime, timedelta
from typing import Optional
import bcrypt

# Garantizar compatibilidad passlib con bcrypt >= 4 y Python 3.12
if not hasattr(bcrypt, '__about__'):
    class About:
        __version__ = getattr(bcrypt, '__version__', '5.0.0')
    bcrypt.__about__ = About()

_orig_hashpw = bcrypt.hashpw
def _safe_hashpw(password, salt):
    if isinstance(password, str):
        password = password.encode('utf-8')
    return _orig_hashpw(password[:72], salt)
bcrypt.hashpw = _safe_hashpw

from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import get_db
from app.models import Usuario

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "clave_super_secreta_jwt_para_sistema_medico_2026_segura")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

# Contexto passlib con algoritmo bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash usando passlib (bcrypt)."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        try:
            plain_bytes = plain_password.encode('utf-8')[:72]
            hash_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(plain_bytes, hash_bytes)
        except Exception:
            return False


def get_password_hash(password: str) -> str:
    """Genera hash Bcrypt seguro utilizando passlib."""
    try:
        return pwd_context.hash(password)
    except Exception:
        pwd_bytes = password.encode('utf-8')[:72]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Usuario:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionaron credenciales de autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(Usuario).filter(Usuario.username == username).first()
    if user is None:
        raise credentials_exception
    return user


class RoleChecker:
    """
    Dependencia reutilizable para control de acceso basado en roles (RBAC).
    Valida roles permitidos y verifica obligatoriedad de cambio de contraseña.
    """
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = [r.lower().strip() for r in allowed_roles]

    def __call__(self, current_user: Usuario = Depends(get_current_user)) -> Usuario:
        if getattr(current_user, "must_change_password", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debe cambiar su contraseña obligatoriamente en el primer inicio de sesión antes de continuar.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        rol_normalizado = (current_user.rol or "").lower().strip()
        roles_permitidos_normalizados = set(self.allowed_roles)
        if "super_user" in roles_permitidos_normalizados:
            roles_permitidos_normalizados.update(["super_admin", "superadmin"])

        if rol_normalizado not in roles_permitidos_normalizados and (current_user.rol or "").upper() not in [r.upper() for r in self.allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso restringido: Se requieren permisos de {', '.join(self.allowed_roles)}",
                headers={"WWW-Authenticate": "Bearer"}
            )
        return current_user


require_super_user = RoleChecker(["super_user"])
require_admin_or_super_user = RoleChecker(["admin", "super_user"])
get_current_admin = require_admin_or_super_user
