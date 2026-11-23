// Valor por defecto de la imagen: SIN client_id a proposito. En OKD este
// archivo se reemplaza al arrancar el pod (docker-entrypoint.d/
// 40-concilia-config.sh) con OIDC_CLIENT_ID del Secret concilia-oidc y las
// URLs del ConfigMap concilia-config. Si esas variables faltan, el front
// muestra "La configuración de autenticación está incompleta." en vez de
// entrar con el client de otro ambiente.
window.AppConfig = {
  USE_NAUTILUS_AUTH: true,
  USE_PKCE: true,
};
