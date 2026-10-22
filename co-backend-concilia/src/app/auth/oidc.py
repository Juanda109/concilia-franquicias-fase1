import json
import logging
import re
import time
from typing import Any

import httpx
from jose import JWTError, jwt

from app.core.auth_config import auth_settings

logger = logging.getLogger(__name__)


class OidcInvalid(Exception):
    """El código o la identidad entregada por Nauthilus no es válida."""


class OidcUnavailable(Exception):
    """No se puede contactar o interpretar al proveedor OIDC."""


class OidcClient:
    def __init__(self) -> None:
        self._metadata: dict[str, Any] | None = None
        self._metadata_at = 0.0
        self._jwks: dict[str, Any] | None = None
        self._jwks_at = 0.0

    async def _get_json(self, url: str, headers: dict[str, str] | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Respuesta JSON no es un objeto")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise OidcUnavailable("Nauthilus no está disponible") from exc

    async def metadata(self) -> dict:
        if self._metadata and time.monotonic() - self._metadata_at < auth_settings.jwks_cache_ttl:
            return self._metadata
        data = await self._get_json(auth_settings.oidc_discovery_url)
        if not all(isinstance(data.get(key), str) for key in ("issuer", "jwks_uri", "token_endpoint")):
            raise OidcUnavailable("Discovery OIDC incompleto")
        if not all(data[key].startswith("https://") for key in ("issuer", "jwks_uri", "token_endpoint")):
            raise OidcUnavailable("Endpoints OIDC inseguros")
        if data["issuer"] != auth_settings.oidc_issuer:
            raise OidcUnavailable("El issuer publicado no coincide con el configurado")
        self._metadata = data
        self._metadata_at = time.monotonic()
        return data

    async def _get_jwks(self, refresh: bool = False) -> dict:
        if not refresh and self._jwks and time.monotonic() - self._jwks_at < auth_settings.jwks_cache_ttl:
            return self._jwks
        metadata = await self.metadata()
        keys = await self._get_json(metadata["jwks_uri"])
        if not isinstance(keys.get("keys"), list):
            raise OidcUnavailable("JWKS OIDC inválido")
        self._jwks = keys
        self._jwks_at = time.monotonic()
        return keys

    async def verify_id_token(self, token: str, access_token: str | None = None) -> dict:
        try:
            header = jwt.get_unverified_header(token)
        except JWTError:
            raise OidcInvalid("Token de identidad inválido") from None
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise OidcInvalid("Algoritmo o clave de token inválidos")
        metadata = await self.metadata()
        jwks = await self._get_jwks()
        key = next((item for item in jwks["keys"] if item.get("kid") == header["kid"]), None)
        if key is None:
            jwks = await self._get_jwks(refresh=True)
            key = next((item for item in jwks["keys"] if item.get("kid") == header["kid"]), None)
        if key is None or key.get("kty") != "RSA" or key.get("use", "sig") != "sig":
            raise OidcInvalid("Clave de firma no reconocida")
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=metadata["issuer"],
                audience=auth_settings.oidc_client_id,
                access_token=access_token,
            )
        except JWTError:
            raise OidcInvalid("Firma o claims de identidad inválidos") from None
        if not all(claims.get(name) for name in ("sub", "iss", "aud", "exp", "iat")):
            raise OidcInvalid("Claims de identidad incompletos")
        if isinstance(claims["aud"], list) and len(claims["aud"]) > 1:
            if claims.get("azp") != auth_settings.oidc_client_id:
                raise OidcInvalid("Cliente autorizado del token incorrecto")
        return claims

    @staticmethod
    def _roles_from(claims: dict) -> tuple[list[str], str | None]:
        roles: list[str] = []
        sources: list[str] = []
        for path in auth_settings.role_claim_paths:
            value: Any = claims
            resolved_path = path.replace("<client_id>", auth_settings.oidc_client_id)
            for part in resolved_path.split("."):
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(part)
            if isinstance(value, str):
                value = re.split(r"[\s,]+", value.strip())
            if isinstance(value, list):
                found = [role for role in value if isinstance(role, str)]
                if found:
                    roles.extend(found)
                    sources.append(resolved_path)
        return list(dict.fromkeys(roles)), ",".join(sources) if sources else None

    async def exchange(self, code: str, redirect_uri: str, code_verifier: str | None) -> dict:
        if redirect_uri != auth_settings.oidc_redirect_uri:
            raise OidcInvalid("URI de retorno no autorizada")
        metadata = await self.metadata()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            form["code_verifier"] = code_verifier
        secret = auth_settings.oidc_client_secret
        assert secret is not None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    metadata["token_endpoint"],
                    data=form,
                    auth=(auth_settings.oidc_client_id, secret.get_secret_value()),
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise OidcUnavailable("Nauthilus no está disponible") from exc
        if response.status_code in (400, 401, 403):
            raise OidcInvalid("Código de autorización inválido o vencido")
        if response.status_code != 200:
            raise OidcUnavailable("Nauthilus rechazó el intercambio")
        try:
            token_data = response.json()
        except ValueError:
            raise OidcUnavailable("Respuesta de Nauthilus inválida") from None
        if not isinstance(token_data, dict) or not isinstance(token_data.get("id_token"), str):
            raise OidcInvalid("Nauthilus no entregó un id_token")
        access_token = token_data.get("access_token")
        if access_token is not None and not isinstance(access_token, str):
            raise OidcInvalid("Nauthilus entregó un access_token inválido")
        claims = await self.verify_id_token(token_data["id_token"], access_token)
        roles, source = self._roles_from(claims)
        if not auth_settings.allowed_roles.intersection(roles) and access_token:
            userinfo_url = metadata.get("userinfo_endpoint")
            if isinstance(userinfo_url, str) and userinfo_url.startswith("https://"):
                userinfo = await self._get_json(
                    userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if userinfo.get("sub") != claims["sub"]:
                    raise OidcInvalid("UserInfo no coincide con la identidad")
                userinfo_roles, userinfo_source = self._roles_from(userinfo)
                roles = list(dict.fromkeys([*roles, *userinfo_roles]))
                if userinfo_source:
                    source = ",".join(filter(None, [source, f"userinfo.{userinfo_source}"]))
        if auth_settings.oidc_role_diagnostics:
            logger.info(
                "OIDC roles %s",
                json.dumps(
                    {
                        "sub": claims["sub"],
                        "roles": roles,
                        "source": source,
                        "claim_keys": sorted(claims.keys()) if not auth_settings.allowed_roles.intersection(roles) else None,
                    },
                    ensure_ascii=True,
                ),
            )
        application_roles = [role for role in roles if role in auth_settings.allowed_roles]
        if not application_roles:
            raise PermissionError("Usuario sin rol GIAM autorizado")
        return {
            "sub": claims["sub"],
            "email": claims.get("email") or claims.get("mail"),
            "name": claims.get("name") or claims.get("preferred_username"),
            "roles": application_roles,
        }


oidc_client = OidcClient()
