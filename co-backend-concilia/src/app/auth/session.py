from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.auth_config import auth_settings

COOKIE_NAME = "session_token"
SESSION_ISSUER = "co-concilia"
SESSION_AUDIENCE = "co-concilia-session"


def create_session(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        **user,
        "iss": SESSION_ISSUER,
        "aud": SESSION_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=auth_settings.session_ttl_seconds)).timestamp()),
    }
    key = auth_settings.session_sign_key
    assert key is not None
    return jwt.encode(payload, key.get_secret_value(), algorithm="HS256")


def read_session(token: str | None) -> dict:
    if not token or not auth_settings.session_sign_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sin sesión activa")
    try:
        data = jwt.decode(
            token,
            auth_settings.session_sign_key.get_secret_value(),
            algorithms=["HS256"],
            issuer=SESSION_ISSUER,
            audience=SESSION_AUDIENCE,
        )
        if (
            not all(data.get(key) for key in ("sub", "iat", "exp", "iss", "aud"))
            or not isinstance(data.get("roles"), list)
        ):
            raise JWTError("Sesión incompleta")
        if not auth_settings.allowed_roles.intersection(
            role for role in data["roles"] if isinstance(role, str)
        ):
            raise JWTError("Sin rol autorizado")
        return {key: data.get(key) for key in ("sub", "email", "name", "roles")}
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión expirada o inválida") from None
