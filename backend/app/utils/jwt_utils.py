import uuid
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from jose import jwt, JWTError
from app.config import settings

def hash_password(password: str) -> str:
    """Hash password using bcrypt with cost factor 12."""
    salt = bcrypt.gensalt(12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify standard bcrypt password."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: str, email: str, role: str) -> str:
    """Generate access token with a 15-minute expiration time."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4())
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None

def create_refresh_token(user_id: str) -> str:
    """Generate a refresh token JWT with a 7-day expiration time."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": user_id,
        "type": "refresh",
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4())
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt
