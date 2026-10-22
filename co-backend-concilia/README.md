# co-backend-concilia

FastAPI (control-plane) de Conciliación Franquicias Fase 1: jornadas, archivos y
estados; orquesta la subida a MinIO y la llamada a `co-api-parseo`.

## Autenticación Nauthilus

En OKD, el backend exige una sesión propia para todas las rutas `/api/v1`.
`POST /api/v0/auth/oidc/exchange` recibe el código OIDC, valida el `id_token`
contra Discovery/JWKS y exige uno de los roles GIAM configurados. Después firma
una cookie `session_token` de 8 horas (`HttpOnly`, `Secure`, `SameSite=Lax`).
`GET /api/v0/me` valida la cookie y `POST /api/v0/auth/logout` la elimina del
navegador. `/health` permanece pública.

La sesión es sin almacenamiento: todas las réplicas necesitan la misma
`SESSION_SIGN_KEY`, distinta de `OIDC_CLIENT_SECRET`. El cierre local no
revoca una copia previa de la cookie antes de que venza. No se guardan tokens
de Nauthilus en la sesión.

Las variables de configuración están documentadas en `.env.example`. El
backend solo acepta `AUTH_ENABLED=false` cuando `APP_ENV=local`. Si faltan los
secretos o la lista de roles con autenticación activa, el proceso no inicia.
En la prueba de desarrollo, `OIDC_ROLE_DIAGNOSTICS=true` registra `sub`, los
roles extraídos y el nombre del claim para identificar el formato real de
Nauthilus, sin registrar códigos, tokens ni secretos.
