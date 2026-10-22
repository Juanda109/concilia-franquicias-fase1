from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth.oidc import OidcInvalid, OidcUnavailable, oidc_client
from app.auth.session import COOKIE_NAME, create_session, read_session
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
    return {"authenticated": True, "user": user}


@router.get("/me")
async def me(session_token: str | None = Cookie(default=None)):
    return {"authenticated": True, **read_session(session_token)}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=auth_settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"authenticated": False}
