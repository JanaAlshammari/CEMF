import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

_password_hash = PasswordHash.recommended()  # Argon2id


def hash_password(plain: str) -> str:
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _password_hash.verify(plain, hashed)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """The token carries identity only. Roles are re-read from the DB on every
    request, so a demotion or deactivation takes effect immediately."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {"sub": subject, "type": "access", "iat": now, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on bad signature / expiry / malformed token."""
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def sign_value(value: str) -> str:
    """HMAC signature, used later for ticket QR codes and certificate verification."""
    return hmac.new(
        settings.ticket_signing_key.encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def verify_signature(value: str, signature: str) -> bool:
    return hmac.compare_digest(sign_value(value), signature)
