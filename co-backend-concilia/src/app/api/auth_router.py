from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth.oidc import OidcInvalid, OidcUnavailable, oidc_client
from app.auth.session import COOKIE_NAME, create_session, read_session, revoke_session
from app.core.auth_config import auth_settings

router = APIRouter(prefix="/api/v0", tags=["Auth"])


class ExchangeRequest(BaseModel):
    code: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1)
    code_verifier: str | None = None


@router.post("/auth/oidc/exchange")
async def oidc_exchange(payload: ExchangeRequest, response: Response):
    if not auth_settings.auth_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        user = await oidc_client.exchange(
            payload.code, payload.redirect_uri, payload.code_verifier
        )
    except OidcInvalid as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from None
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from None
    except OidcUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session(user),
        httponly=True,
        secure=auth_settings.cookie_secure,
        samesite="lax",
        max_age=auth_settings.session_ttl_seconds,
        path="/",
    )
    # El id_token solo viaja dentro de la cookie (para el logout RP-Initiated)
    # - nunca se expone en el body de la respuesta.
    public_user = {k: v for k, v in user.items() if k != "id_token"}
    return {"authenticated": True, "user": public_user}


@router.get("/me")
async def me(session_token: str | None = Cookie(default=None)):
    return {"authenticated": True, **read_session(session_token)}


@router.post("/auth/logout")
async def logout(response: Response, session_token: str | None = Cookie(default=None)):
    id_token = revoke_session(session_token)
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=auth_settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    # Cerrar solo la cookie local no cierra la sesión SSO en Nauthilus: si el
    # IdP sigue con sesión activa, un siguiente login la retoma en silencio.
    # Con el id_token original armamos el RP-Initiated Logout para que
    # también termine la sesión del lado del IdP.
    end_session_url = None
    if id_token:
        try:
            metadata = await oidc_client.metadata()
        except OidcUnavailable:
            metadata = None
        end_session_endpoint = metadata.get("end_session_endpoint") if metadata else None
        if isinstance(end_session_endpoint, str):
            params = {
                "id_token_hint": id_token,
                "post_logout_redirect_uri": auth_settings.oidc_redirect_uri,
                "client_id": auth_settings.oidc_client_id,
            }
            end_session_url = f"{end_session_endpoint}?{urlencode(params)}"
    return {"authenticated": False, "endSessionUrl": end_session_url}
