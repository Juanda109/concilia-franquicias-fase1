import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.auth_config import auth_settings
from app.repositories.database import connection

COOKIE_NAME = "session_token"
SESSION_ISSUER = "co-concilia"
SESSION_AUDIENCE = "co-concilia-session"


def create_session(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        **user,
        "iss": SESSION_ISSUER,
        "aud": SESSION_AUDIENCE,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=auth_settings.session_ttl_seconds)).timestamp()),
    }
    key = auth_settings.session_sign_key
    assert key is not None
    return jwt.encode(payload, key.get_secret_value(), algorithm="HS256")


def _decode(token: str) -> dict:
    """Decodifica y valida firma/claims basicos, sin chequear revocacion -
    uso interno compartido por read_session (que si la chequea) y
    revoke_session (que necesita leer jti/exp de un token que esta a punto
    de invalidar, sea o no que ya este revocado)."""
    data = jwt.decode(
        token,
        auth_settings.session_sign_key.get_secret_value(),
        algorithms=["HS256"],
        issuer=SESSION_ISSUER,
        audience=SESSION_AUDIENCE,
    )
    if (
        not all(data.get(key) for key in ("sub", "iat", "exp", "iss", "aud", "jti"))
        or not isinstance(data.get("roles"), list)
    ):
        raise JWTError("Sesión incompleta")
    return data


def read_session(token: str | None) -> dict:
    if not token or not auth_settings.session_sign_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sin sesión activa")
    try:
        data = _decode(token)
        if not auth_settings.allowed_roles.intersection(
            role for role in data["roles"] if isinstance(role, str)
        ):
            raise JWTError("Sin rol autorizado")
        with connection() as c:
            revocada = c.execute(
                "SELECT 1 FROM CON_SESION_REVOCADA WHERE JTI=%s", (data["jti"],)
            ).fetchone()
        if revocada:
            raise JWTError("Sesión cerrada")
        return {key: data.get(key) for key in ("sub", "email", "name", "roles")}
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión expirada o inválida") from None


def revoke_session(token: str | None) -> str | None:
    """Logout real: registra el jti del token actual como revocado, para que
    read_session lo rechace aunque su EXP original todavia no haya pasado.
    Silencioso ante cualquier token ausente/invalido - un logout nunca debe
    fallar porque la cookie ya estaba vencida o corrupta.
    Devuelve el id_token original (si lo trae la sesión) para que el router
    pueda armar el RP-Initiated Logout contra Nauthilus - sin eso, cerrar
    sesión solo aquí no cierra la sesión SSO del IdP."""
    if not token or not auth_settings.session_sign_key:
        return None
    try:
        data = _decode(token)
    except JWTError:
        return None
    exp = datetime.fromtimestamp(data["exp"], tz=timezone.utc)
    with connection() as c:
        c.execute(
            "INSERT INTO CON_SESION_REVOCADA (JTI, EXPIRA_EN) VALUES (%s, %s) "
            "ON CONFLICT (JTI) DO NOTHING",
            (data["jti"], exp),
        )
        # Limpieza oportunista: una fila revocada ya no hace falta despues de
        # su propio EXP (el JWT se rechazaria por vencido de todas formas).
        c.execute("DELETE FROM CON_SESION_REVOCADA WHERE EXPIRA_EN < CURRENT_TIMESTAMP")
    return data.get("id_token")
