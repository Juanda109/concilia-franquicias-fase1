from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "okd"
    auth_enabled: bool = True
    oidc_client_id: str = "1c29829d-3ddd-4110-8d7f-2eb8466645fd"
    oidc_client_secret: SecretStr | None = None
    oidc_discovery_url: str = (
        "https://preidp.work.global.platform.bbva.com/oidc/.well-known/openid-configuration"
    )
    oidc_issuer: str = "https://preidp.work.global.platform.bbva.com/oidc/"
    oidc_redirect_uri: str = (
        "https://co-ccrcs-frontend-concilia-ccrcs-genai-dev.apps.work.ocp.co.igrupobbva/"
    )
    oidc_allowed_roles: str = (
        "conciliacion_adquirencias_Administrador_Plataforma,"
        "conciliacion_adquirencias_Analista"
    )
    oidc_role_claim_paths: str = (
        "realm_access.roles,resource_access.<client_id>.roles,roles,groups"
    )
    oidc_role_diagnostics: bool = False
    frontend_origin: str = (
        "https://co-ccrcs-frontend-concilia-ccrcs-genai-dev.apps.work.ocp.co.igrupobbva"
    )
    session_sign_key: SecretStr | None = None
    session_ttl_seconds: int = 8 * 60 * 60
    cookie_secure: bool = True
    jwks_cache_ttl: int = 480

    @model_validator(mode="after")
    def check_auth_config(self) -> "AuthSettings":
        if not self.auth_enabled:
            if self.app_env != "local":
                raise ValueError("AUTH_ENABLED=false solo se permite con APP_ENV=local")
            return self
        if not self.oidc_client_secret or not self.oidc_client_secret.get_secret_value():
            raise ValueError("OIDC_CLIENT_SECRET es obligatorio")
        if not self.session_sign_key or len(self.session_sign_key.get_secret_value().encode()) < 32:
            raise ValueError("SESSION_SIGN_KEY debe tener al menos 32 bytes")
        if not self.allowed_roles:
            raise ValueError("OIDC_ALLOWED_ROLES no puede estar vacío")
        if not self.role_claim_paths:
            raise ValueError("OIDC_ROLE_CLAIM_PATHS no puede estar vacío")
        if self.session_ttl_seconds <= 0 or self.jwks_cache_ttl <= 0:
            raise ValueError("Los tiempos de sesión y caché deben ser positivos")
        if not self.oidc_discovery_url.startswith("https://"):
            raise ValueError("OIDC_DISCOVERY_URL debe usar HTTPS")
        if not self.oidc_issuer.startswith("https://"):
            raise ValueError("OIDC_ISSUER debe usar HTTPS")
        if not self.oidc_redirect_uri.startswith("https://"):
            raise ValueError("OIDC_REDIRECT_URI debe usar HTTPS")
        if not self.cookie_secure:
            raise ValueError("COOKIE_SECURE debe estar activo fuera del entorno local")
        return self

    @property
    def allowed_roles(self) -> set[str]:
        return {value.strip() for value in self.oidc_allowed_roles.split(",") if value.strip()}

    @property
    def role_claim_paths(self) -> tuple[str, ...]:
        return tuple(value.strip() for value in self.oidc_role_claim_paths.split(",") if value.strip())


auth_settings = AuthSettings()
