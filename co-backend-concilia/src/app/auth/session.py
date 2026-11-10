import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core.auth_config import auth_settings
from app.repositories.database import connection

COOKIE_NAME = "session_token"


def _hash(token: str) -> str:
    """La cookie lleva el token en claro, pero en base solo se guarda su
    hash - un dump de CON_SESION_ACTIVA no alcanza para suplantar sesiones."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user: dict) -> str:
    """Login real: upsert por USUARIO_SUB en CON_SESION_ACTIVA - una sola
    sesión activa por usuario, así que loguearse en un segundo equipo
    invalida la sesión anterior de ese mismo usuario. Devuelve el token
    opaco (no un JWT) que va en la cookie; todo lo demás se resuelve
    consultando la tabla en cada request."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=auth_settings.session_ttl_seconds)
    with connection() as c:
        c.execute(
            "DELETE FROM CON_SESION_ACTIVA WHERE FECHA_EXPIRA < CURRENT_TIMESTAMP"
        )
        c.execute(
            """
            INSERT INTO CON_SESION_ACTIVA
                (ID_SESION, USUARIO_SUB, EMAIL, NOMBRE, ROLES, ID_TOKEN,
                 FECHA_CREACION, FECHA_EXPIRA)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (USUARIO_SUB) DO UPDATE SET
                ID_SESION = EXCLUDED.ID_SESION,
                EMAIL = EXCLUDED.EMAIL,
                NOMBRE = EXCLUDED.NOMBRE,
                ROLES = EXCLUDED.ROLES,
                ID_TOKEN = EXCLUDED.ID_TOKEN,
                FECHA_CREACION = EXCLUDED.FECHA_CREACION,
                FECHA_EXPIRA = EXCLUDED.FECHA_EXPIRA
            """,
            (_hash(token), user["sub"], user.get("email"), user.get("name"),
             user["roles"], user.get("id_token"), now, exp),
        )
    return token


def read_session(token: str | None) -> dict:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sin sesión activa")
    with connection() as c:
        row = c.execute(
            "SELECT USUARIO_SUB, EMAIL, NOMBRE, ROLES FROM CON_SESION_ACTIVA "
            "WHERE ID_SESION=%s AND FECHA_EXPIRA > CURRENT_TIMESTAMP",
            (_hash(token),),
        ).fetchone()
    if not row:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sesión expirada o inválida"
        )
    sub, email, nombre, roles = row
    if not auth_settings.allowed_roles.intersection(roles or []):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sesión expirada o inválida"
        )
    return {"sub": sub, "email": email, "name": nombre, "roles": roles}


def revoke_session(token: str | None) -> str | None:
    """Logout real: borra la fila de CON_SESION_ACTIVA (no queda ningún
    rastro que permita reusar la cookie, aunque alguien la conserve).
    Devuelve el id_token original del IdP (si la sesión lo tenía) para que
    el router arme el RP-Initiated Logout contra Nauthilus."""
    if not token:
        return None
    with connection() as c:
        row = c.execute(
            "DELETE FROM CON_SESION_ACTIVA WHERE ID_SESION=%s "
            "RETURNING ID_TOKEN",
            (_hash(token),),
        ).fetchone()
    return row[0] if row else None
