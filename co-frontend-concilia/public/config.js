window.AppConfig = {
  USE_NAUTILUS_AUTH: true,
  USE_PKCE: true,
  // No es un secreto: es el client_id público de OIDC, el mismo que viaja
  // en claro en la URL de /oidc/authorize en cada login. El scanner lo
  // marca por tener forma de GUID (regla "Generic API Key"), falso
  // positivo confirmado - no requiere rotación.
  clientId: '1c29829d-3ddd-4110-8d7f-2eb8466645fd',
  authEndpoint: 'https://preidp.work.global.platform.bbva.com/oidc/authorize',
  redirectUri: 'https://co-ccrcs-frontend-concilia-ccrcs-genai-dev.apps.work.ocp.co.igrupobbva/',
};
