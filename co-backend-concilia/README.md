# co-backend-concilia

FastAPI (control-plane) de Conciliación Franquicias Fase 1: jornadas, archivos y
estados; orquesta la subida a MinIO y la llamada a `co-api-parseo`.

## Autenticación Nauthilus

En OKD, el backend exige una sesión propia para todas las rutas `/api/v1`.
`POST /api/v0/auth/oidc/exchange` recibe el código OIDC, valida el `id_token`
contra Discovery/JWKS y exige uno de los roles GIAM configurados. Después
guarda la sesión en la tabla `CON_SESION_ACTIVA` (ver
`database/ddl/24_con_sesion_activa.sql`) y entrega una cookie `session_token`
de 8 horas (`HttpOnly`, `Secure`, `SameSite=Lax`) con un token opaco
aleatorio - no un JWT autocontenido. `GET /api/v0/me` y el middleware de
`/api/v1` resuelven la sesión consultando esa tabla en cada request.
`POST /api/v0/auth/logout` borra la fila (cierre real, no solo la cookie del
navegador) y, con el `id_token` original que se conserva ahí, arma un
RP-Initiated Logout contra el `end_session_endpoint` de Nauthilus para
también cerrar la sesión SSO del lado del IdP. `/health` permanece pública.

La sesión se administra 100% desde base: no hay clave de firma ni estado en
memoria del proceso, así que cualquier réplica ve la misma sesión. El `UNIQUE`
en `USUARIO_SUB` fuerza una sola sesión activa por usuario - loguearse en un
segundo equipo invalida la anterior.

Las variables de configuración están documentadas en `.env.example`. El
backend solo acepta `AUTH_ENABLED=false` cuando `APP_ENV=local`. Si faltan los
secretos o la lista de roles con autenticación activa, el proceso no inicia.
En la prueba de desarrollo, `OIDC_ROLE_DIAGNOSTICS=true` registra `sub`, los
roles extraídos y el nombre del claim para identificar el formato real de
Nauthilus, sin registrar códigos, tokens ni secretos.
