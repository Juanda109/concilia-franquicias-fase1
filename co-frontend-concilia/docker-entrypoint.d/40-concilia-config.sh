#!/bin/sh
# Genera /usr/share/nginx/html/config.js al arrancar el contenedor con los
# datos de Nauthilus del ambiente (dev, QA, prod), en vez de dejarlos fijos
# dentro de la imagen. La misma imagen sirve para todos los ambientes.
#
# Variables (en OKD las inyecta el Deployment):
#   OIDC_CLIENT_ID      -> Secret concilia-oidc
#   OIDC_AUTH_ENDPOINT  -> ConfigMap concilia-config
#   OIDC_REDIRECT_URI   -> ConfigMap concilia-config
#
# Sin OIDC_CLIENT_ID no se toca nada: queda el config.js de la imagen, que no
# trae client_id y muestra "configuración incompleta" en vez de entrar en
# silencio con el client de otro ambiente. En local, docker compose monta
# config.local.js encima y tampoco define estas variables.
set -eu

DESTINO=/usr/share/nginx/html/config.js

if [ -z "${OIDC_CLIENT_ID:-}" ]; then
  echo "40-concilia-config: OIDC_CLIENT_ID no definido, se deja config.js de la imagen"
  exit 0
fi

: "${OIDC_AUTH_ENDPOINT:?OIDC_AUTH_ENDPOINT es obligatorio cuando se define OIDC_CLIENT_ID}"
: "${OIDC_REDIRECT_URI:?OIDC_REDIRECT_URI es obligatorio cuando se define OIDC_CLIENT_ID}"

# Los valores van dentro de un string JS: se rechaza cualquier caracter que
# pudiera cerrar el string o inyectar codigo.
for valor in "$OIDC_CLIENT_ID" "$OIDC_AUTH_ENDPOINT" "$OIDC_REDIRECT_URI"; do
  case "$valor" in
    *\'*|*\"*|*\\*|*\<*|*\>*|*' '*)
      echo "40-concilia-config: valor con caracteres no permitidos" >&2
      exit 1
      ;;
  esac
done

cat > "$DESTINO" <<EOF
window.AppConfig = {
  USE_NAUTILUS_AUTH: true,
  USE_PKCE: true,
  clientId: '${OIDC_CLIENT_ID}',
  authEndpoint: '${OIDC_AUTH_ENDPOINT}',
  redirectUri: '${OIDC_REDIRECT_URI}',
};
EOF

echo "40-concilia-config: config.js generado (redirectUri=${OIDC_REDIRECT_URI})"
