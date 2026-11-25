const API = '/api/v1';
const el = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---- Autenticación Nauthilus (OIDC) ----
// window.AppConfig lo define config.js (real, con endpoint/clientId de
// Nauthilus) o config.local.js (USE_NAUTILUS_AUTH:false, para desarrollo
// local sin depender del IdP corporativo).
const authConfig = window.AppConfig || {};
const authEnabled = authConfig.USE_NAUTILUS_AUTH ?? true;
let authRedirectStarted = false;
let appStarted = false;

function showAuthMessage(message, retry = true) {
  el('appRoot').hidden = true;
  el('authGate').hidden = false;
  el('authMessage').textContent = message;
  el('authRetry').hidden = !retry;
}

function clearOidcReturn() {
  window.history.replaceState({}, document.title, window.location.pathname + window.location.hash);
}

function base64Url(bytes) {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

async function redirectToLogin() {
  if (authRedirectStarted) return;
  authRedirectStarted = true;
  if (!authConfig.clientId || !authConfig.authEndpoint || !authConfig.redirectUri) {
    showAuthMessage('La configuración de autenticación está incompleta.');
    authRedirectStarted = false;
    return;
  }
  try {
    const state = crypto.randomUUID();
    sessionStorage.setItem('oidc_state', state);
    const query = new URLSearchParams({
      response_type: 'code',
      client_id: authConfig.clientId,
      redirect_uri: authConfig.redirectUri,
      scope: 'openid profile email',
      state,
    });
    if (authConfig.USE_PKCE) {
      const verifier = base64Url(crypto.getRandomValues(new Uint8Array(32)));
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
      sessionStorage.setItem('oidc_code_verifier', verifier);
      query.set('code_challenge', base64Url(new Uint8Array(digest)));
      query.set('code_challenge_method', 'S256');
    }
    window.location.assign(`${authConfig.authEndpoint}?${query}`);
  } catch {
    authRedirectStarted = false;
    showAuthMessage('No fue posible iniciar la autenticación.');
  }
}

// Envoltura de fetch para las llamadas al API propio: manda la cookie de
// sesión y, si venció (401), redirige a Nauthilus en vez de dejar la
// pantalla rota a medio cargar.
async function apiFetch(url, options = {}) {
  const response = await fetch(url, { ...options, credentials: 'include' });
  if (authEnabled && response.status === 401 && url.startsWith(API)) {
    showAuthMessage('La sesión venció. Redirigiendo a Nauthilus…', false);
    for (const timer of pollers.values()) clearInterval(timer);
    pollers.clear();
    void redirectToLogin();
  }
  return response;
}

async function bootstrapAuth() {
  if (!authEnabled) { showApplication(null); return; }
  const params = new URLSearchParams(window.location.search);
  if (params.has('error')) {
    sessionStorage.removeItem('oidc_state');
    sessionStorage.removeItem('oidc_code_verifier');
    clearOidcReturn();
    showAuthMessage('Nauthilus no completó el inicio de sesión.');
    return;
  }
  const code = params.get('code');
  if (code) {
    const expectedState = sessionStorage.getItem('oidc_state');
    const verifier = sessionStorage.getItem('oidc_code_verifier');
    sessionStorage.removeItem('oidc_state');
    sessionStorage.removeItem('oidc_code_verifier');
    const validState = expectedState && params.get('state') === expectedState;
    clearOidcReturn();
    if (!validState || (authConfig.USE_PKCE && !verifier)) {
      showAuthMessage('No se pudo validar el retorno de Nauthilus.');
      return;
    }
    try {
      const response = await fetch('/api/v0/auth/oidc/exchange', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          code,
          redirect_uri: authConfig.redirectUri,
          code_verifier: verifier || null,
        }),
      });
      if (!response.ok) {
        const message = response.status === 403
          ? 'Tu usuario no tiene un rol GIAM autorizado para Concilia.'
          : response.status === 401
            ? 'El código de acceso venció o no pudo validarse.'
            : 'No fue posible establecer la sesión. Inténtalo más tarde.';
        showAuthMessage(message);
        return;
      }
    } catch {
      showAuthMessage('No fue posible conectar con el backend.');
      return;
    }
  }
  try {
    const response = await fetch('/api/v0/me', { credentials: 'include', cache: 'no-store' });
    if (response.status === 401) {
      if (code) showAuthMessage('La sesión no pudo establecerse.');
      else void redirectToLogin();
      return;
    }
    if (!response.ok) {
      showAuthMessage('No fue posible verificar la sesión.');
      return;
    }
    showApplication(await response.json());
  } catch {
    showAuthMessage('No fue posible conectar con el backend.');
  }
}

function showApplication(user) {
  if (user) el('currentUser').textContent = user.name || user.email || user.sub || '';
  el('logoutButton').hidden = !authEnabled;
  el('authGate').hidden = true;
  el('appRoot').hidden = false;
  if (appStarted) return;
  appStarted = true;
  void checkHealth();
  void cargarPorFecha();
}

el('authRetry').addEventListener('click', () => { void redirectToLogin(); });
el('logoutButton').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/v0/auth/logout', { method: 'POST', credentials: 'include' });
    if (!response.ok) throw new Error();
    const data = await response.json().catch(() => ({}));
    sessionStorage.removeItem('oidc_state');
    sessionStorage.removeItem('oidc_code_verifier');
    for (const timer of pollers.values()) clearInterval(timer);
    pollers.clear();
    appStarted = false;
    authRedirectStarted = false;
    // Si el backend pudo armar el RP-Initiated Logout contra Nauthilus,
    // hay que ir ahí (cierra también la sesión SSO del IdP) y no al
    // authorize de siempre, que solo la retomaría en silencio.
    if (data.endSessionUrl) window.location.assign(data.endSessionUrl);
    else void redirectToLogin();
  } catch {
    toast('No se pudo cerrar la sesión. Intenta de nuevo.', true);
  }
});

const tblArchivos = el('tblArchivos');
const tblMeta = el('tblMeta');
const rangoTrigger = el('rangoTrigger');
const rangoTexto = el('rangoTexto');
const rangoPopover = el('rangoPopover');
const rangoMesAnterior = el('rangoMesAnterior');
const rangoMesSiguiente = el('rangoMesSiguiente');
const rangoMesLabel = el('rangoMesLabel');
const rangoDiasLabel = el('rangoDiasLabel');
const rangoGrid = el('rangoGrid');
const rangoAyuda = el('rangoAyuda');
const rangoHoy = el('rangoHoy');
const drawer = el('drawer');
const drawerContent = el('drawerContent');
const toastEl = el('toast');
const erroresProcesamientoModal = el('erroresProcesamientoModal');
const detalleInsumoContent = el('detalleInsumoContent');
let insumosScrollY = 0;

let toastTimer = null;
let pendingIdArchivoUpload = null;
const pollers = new Map(); // idArchivo -> intervalId, para no duplicar polling si se sube el mismo archivo dos veces

// Íconos minimalistas (SVG en línea, trazo simple, sin dependencias externas)
const ICON_EYE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
const ICON_UPLOAD = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>';
const ICON_TRASH = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
const ICON_ERROR = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';

function toISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
// Vocabulario de estados del contrato ENT-01 v2.4.0 (siempre en MAYÚSCULA,
// resueltos por backend: fecha(s) contable(s), estado de jornada,
// estadoRecepcion/estadoProcesamiento y accionesPermitidas). El frontend solo
// pinta lo que llega, no deriva ni calcula nada de esto localmente.
const BADGE_CLASS = {
  RECIBIDO: 'ok', PROCESADO: 'ok', COMPLETA: 'ok',
  NO_RECIBIDO: 'warn', CON_NOVEDAD: 'warn', RECHAZADO: 'warn',
  PENDIENTE: 'info', PROCESANDO: 'info', ESPERADO: 'info', EN_PROCESO: 'info',
  ERROR: 'bad',
};
const ESTADO_LABEL = {
  RECIBIDO: 'Recibido', PROCESADO: 'Procesado', COMPLETA: 'Completa',
  NO_RECIBIDO: 'No recibido', CON_NOVEDAD: 'Con novedad', RECHAZADO: 'Rechazado',
  PENDIENTE: 'Pendiente', PROCESANDO: 'Procesando', ESPERADO: 'Esperado', EN_PROCESO: 'En proceso',
  ERROR: 'Error',
};
// Nombre para mostrar de cada fuente (franquicia). El codigo no cambia.
const NOMBRE_FUENTE = { VISA: 'VISA INTERNACIONAL' };
function nombreFuente(fuente) {
  return NOMBRE_FUENTE[fuente] ?? fuente;
}
// Nombre para mostrar de cada insumo. El codigo (tipoInsumo) no cambia:
// lo usan la base de datos, el parseo y la validacion de nombres de archivo.
const NOMBRE_INSUMO = {
  ISS: 'Posición Neta',
  VSS: 'VSS',
};
function nombreInsumo(tipo) {
  return NOMBRE_INSUMO[tipo] ?? tipo;
}
function badge(estado) {
  if (!estado) return '<span class="badge info">-</span>';
  return `<span class="badge ${BADGE_CLASS[estado] ?? 'info'}">${ESTADO_LABEL[estado] ?? estado}</span>`;
}

// Columna "Registros" de la tabla principal: mientras está "Procesando" se ve
// el avance en vivo (X / Y + barra); en cualquier otro estado, el total final.
function celdaRegistros(a) {
  if (a.estadoProcesamiento !== 'PROCESANDO') return a.totalRegistros ?? '-';
  const total = a.totalRegistros;
  const hechos = a.registrosProcesados ?? 0;
  if (!total) return `<span class="muted">Iniciando…</span>`;
  const pct = Math.min(100, Math.round((100 * hechos) / total));
  return `
    <div class="progressWrap">
      <div class="progressMeta"><span>${hechos.toLocaleString('es-CO')} / ${total.toLocaleString('es-CO')}</span></div>
      <div class="progress"><span style="width:${pct}%"></span></div>
    </div>`;
}

function toast(msg, isErr) {
  toastEl.textContent = msg;
  toastEl.className = 'toast show' + (isErr ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.className = 'toast'; }, 4500);
}

function openDrawer() { drawer.className = 'drawer show'; }
function closeDrawer() { drawer.className = 'drawer'; }
el('btnCerrarDrawer').addEventListener('click', closeDrawer);

function hideErroresProcesamiento() { erroresProcesamientoModal.className = 'modalBack'; }
el('btnCerrarErroresProcesamiento').addEventListener('click', hideErroresProcesamiento);

// Ventana emergente única para cualquier error de archivo (rechazo al subir
// o falla de procesamiento): título + subtítulo opcional (tipo · nombre) +
// motivo.
function mostrarModalError({ titulo, tipoInsumo, nombreArchivo, motivo }) {
  el('erroresProcesamientoTitulo').textContent = titulo;
  const subtitulo = el('erroresProcesamientoSubtitulo');
  if (tipoInsumo || nombreArchivo) {
    subtitulo.hidden = false;
    el('erroresProcesamientoTipo').textContent = nombreInsumo(tipoInsumo) ?? '';
    el('erroresProcesamientoNombre').textContent = nombreArchivo ?? '';
  } else {
    subtitulo.hidden = true;
  }
  el('erroresProcesamientoMotivo').textContent = motivo ?? '';
  erroresProcesamientoModal.className = 'modalBack show';
}

function mostrarErrorCarga(mensaje) {
  mostrarModalError({ titulo: 'No se pudo cargar el archivo', motivo: mensaje });
}

// MOTIVO_ESTADO a veces es el mensaje crudo de una excepción de Python/una
// librería (ej. openpyxl rechazando un .pdf), no un texto pensado para la
// analista — se traducen los casos conocidos, igual que mensajeErrorCarga()
// hace con los códigos de rechazo al subir. Si no se reconoce el patrón, se
// muestra el texto tal cual (mejor mostrar algo que ocultar información).
function causaProcesamiento(motivo) {
  if (!motivo) return '';
  if (/does not support .* file format/i.test(motivo)) {
    return 'El archivo no tiene el formato esperado para este insumo (revisa que sea el archivo correcto para este tipo).';
  }
  if (/^API_PARSEO_NO_DISPONIBLE/.test(motivo)) {
    return 'No se pudo conectar con el servicio de parseo. Intenta cargar el archivo de nuevo en unos minutos.';
  }
  return motivo;
}

// Reconsulta el motivo guardado (MOTIVO_ESTADO, vía GET /archivos/{id}/errores)
// para poder reabrir el detalle de un rechazo/error en cualquier momento, no
// solo en el instante en que ocurrió. `traducir` decide cómo pasar de código
// crudo a texto en español: causaProcesamiento para fallas de procesamiento,
// mensajeErrorCarga para rechazos al momento de subir (nombre/fecha).
async function mostrarMotivoGuardado(idArchivo, tipoInsumo, nombreArchivo, titulo, traducir) {
  mostrarModalError({ titulo, tipoInsumo, nombreArchivo, motivo: 'Consultando detalle…' });
  try {
    const r = await apiFetch(`${API}/archivos/${idArchivo}/errores`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    mostrarModalError({ titulo, tipoInsumo, nombreArchivo, motivo: traducir(d.motivoEstado) });
  } catch (e) {
    mostrarModalError({ titulo, tipoInsumo, nombreArchivo, motivo: `No se pudo consultar el detalle: ${e.message}` });
  }
}

function mostrarErroresProcesamiento(idArchivo, tipoInsumo, nombreArchivo) {
  return mostrarMotivoGuardado(idArchivo, tipoInsumo, nombreArchivo, 'No se pudo procesar el archivo', causaProcesamiento);
}

async function checkHealth() {
  const badgeEl = el('apiStatus');
  try {
    const r = await fetch('/health');
    if (!r.ok) throw new Error();
    badgeEl.textContent = 'API OK'; badgeEl.className = 'badge ok';
  } catch {
    badgeEl.textContent = 'API SIN CONEXIÓN'; badgeEl.className = 'badge bad';
  }
}

// ---- Insumos: una sola fecha contable -> jornada (backend) ----
// El backend sigue exponiendo GET /jornadas?fechaDesde&fechaHasta (acepta
// un rango), pero el frontend ya solo permite elegir un día: se consulta
// siempre con fechaDesde == fechaHasta == fechaContableSel.
let idJornadaActiva = null;
let jornadaActual = null;

function _renderJornada(d) {
  tblMeta.textContent = `${d.archivosRecibidos} de ${d.archivosEsperados} insumos recibidos`;
  actualizarHero(d);
  renderTablaInsumos(d.insumos);
}

async function cargarPorFecha() {
  try {
    const r = await apiFetch(`${API}/jornadas?fechaDesde=${encodeURIComponent(fechaContableSel)}&fechaHasta=${encodeURIComponent(fechaContableSel)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    jornadaActual = d.jornadas[0] ?? null;
    idJornadaActiva = jornadaActual ? jornadaActual.idJornada : null;
    if (jornadaActual) _renderJornada(jornadaActual);
    else {
      tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Sin jornada para esta fecha.</td></tr>`;
      actualizarHero(null);
    }
  } catch (e) {
    jornadaActual = null;
    idJornadaActiva = null;
    tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Error consultando la fecha: ${e.message}</td></tr>`;
    actualizarHero(null);
  }
}

function actualizarHero(d) {
  if (!d) {
    el('heroTitulo').textContent = 'Jornada —';
    el('heroBadge').outerHTML = `<span id="heroBadge" class="badge info">—</span>`;
    el('heroPct').textContent = '0%';
    el('heroBar').style.width = '0%';
    ['kpiEsperados', 'kpiRecibidos', 'kpiProcesados', 'kpiErrores'].forEach((id) => { el(id).textContent = '-'; });
    return;
  }
  el('heroTitulo').textContent = `Jornada ${d.fechaContable}`;
  el('heroBadge').outerHTML = `<span id="heroBadge" class="badge ${BADGE_CLASS[d.estado] ?? 'info'}">${ESTADO_LABEL[d.estado] ?? d.estado}</span>`;
  const pct = d.archivosEsperados ? (100 * d.archivosProcesados / d.archivosEsperados) : 0;
  el('heroPct').textContent = `${pct.toFixed(0)}%`;
  el('heroBar').style.width = `${Math.min(100, pct)}%`;
  el('kpiEsperados').textContent = d.archivosEsperados ?? '-';
  el('kpiRecibidos').textContent = d.archivosRecibidos ?? '-';
  el('kpiProcesados').textContent = d.archivosProcesados ?? '-';
  el('kpiErrores').textContent = d.archivosConError ?? '-';
}

async function cargarJornada() {
  if (!idJornadaActiva) return;
  try {
    const r = await apiFetch(`${API}/jornadas/${idJornadaActiva}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    jornadaActual = d;
    _renderJornada(d);
    return d;
  } catch (e) {
    tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Error consultando la jornada: ${e.message}</td></tr>`;
  }
}

function renderTablaInsumos(insumos) {
  if (!insumos.length) {
    tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Sin insumos configurados.</td></tr>`;
    return;
  }
  tblArchivos.innerHTML = insumos.map((a) => {
    const acciones = a.accionesPermitidas ?? [];
    const conError = a.estadoProcesamiento === 'ERROR' || a.estadoRecepcion === 'RECHAZADO';
    const verBtn = acciones.includes('VER_CONTENIDO')
      ? `<button type="button" class="iconBtn btnView${conError ? ' btnViewError' : ''}" data-id="${a.idArchivo}" title="${conError ? 'Ver error' : 'Ver detalle'}">${conError ? ICON_ERROR : ICON_EYE}</button>` : '';
    const cargarBtn = acciones.includes('CARGAR_ARCHIVO_ORIGINAL')
      ? `<button type="button" class="iconBtn btnUpload" data-id="${a.idArchivo}" title="Cargar archivo original">${ICON_UPLOAD}</button>` : '';
    const eliminarBtn = acciones.includes('ELIMINAR_ARCHIVO')
      ? `<button type="button" class="iconBtn btnEliminar" data-id="${a.idArchivo}" title="Eliminar archivo cargado">${ICON_TRASH}</button>` : '';
    return `
    <tr data-id="${a.idArchivo}">
      <td>${a.idArchivo}</td>
      <td>${nombreFuente(a.fuente)}</td>
      <td>${nombreInsumo(a.tipoInsumo)}</td>
      <td>${a.nombreArchivo ?? '-'}</td>
      <td>${celdaRegistros(a)}</td>
      <td>${badge(a.estadoRecepcion)}</td>
      <td>${badge(a.estadoProcesamiento)}</td>
      <td class="actionCell">${verBtn}${cargarBtn}${eliminarBtn}</td>
    </tr>`;
  }).join('');
  tblArchivos.querySelectorAll('.btnView').forEach((btn) => {
    btn.addEventListener('click', () => abrirDetalle(Number(btn.dataset.id)));
  });
  tblArchivos.querySelectorAll('.btnUpload').forEach((btn) => {
    btn.addEventListener('click', () => {
      pendingIdArchivoUpload = Number(btn.dataset.id);
      const input = el('uploadFileHidden');
      input.value = '';
      input.click();
    });
  });
  tblArchivos.querySelectorAll('.btnEliminar').forEach((btn) => {
    btn.addEventListener('click', () => eliminarArchivo(Number(btn.dataset.id)));
  });
}

async function eliminarArchivo(idArchivo) {
  if (!confirm('¿Eliminar el archivo cargado para este insumo? Se borrará también la información ya procesada en base de datos. Esta acción no se puede deshacer.')) return;
  try {
    const r = await apiFetch(`${API}/archivos/${idArchivo}`, { method: 'DELETE' });
    if (!r.ok) {
      let detalle = `HTTP ${r.status}`;
      try { detalle = (await r.json()).detail ?? detalle; } catch { /* body no es JSON */ }
      toast(`No se pudo eliminar: ${detalle}`, true);
      return;
    }
    toast('Archivo eliminado.');
    await cargarJornada();
  } catch (e) {
    toast(`Error de red al eliminar: ${e.message}`, true);
  }
}

// ---- Vista dedicada de detalle de un insumo ----
// Columnas que nunca se muestran en el visor de evidencia (PAN/tarjeta y
// similares): el backend ya excluye ID_* y FECHA_CREACION, pero CAET/CANT
// (TARJETA) y DEPO (NO_TARJETA) sí persisten estas columnas.
const COLUMNAS_SENSIBLES_RE = /(^|_)(PAN|TARJETA|NUMERO_TARJETA|NRO_TARJETA|NO_TARJETA|CVV|CVC|DOCUMENTO_IDENTIDAD|NUMERO_DOCUMENTO|NUM_DOCUMENTO|TRACK|RAW)(_|$)/i;
let detalleIdArchivo = null;
let detallePagina = 0;
let detalleOrigenPanel = 'insumos';
const DETALLE_PAGE_SIZE = 30;

function abrirDetalle(idArchivo, origen = 'insumos') {
  detalleIdArchivo = idArchivo;
  detallePagina = 0;
  detalleOrigenPanel = origen;
  if (origen === 'insumos') insumosScrollY = window.scrollY;
  const link = el('btnVolverInsumos');
  const VOLVER_A = { conciliacion: '← Volver a Conciliación', detalleCuentaCredibanco: '← Volver al detalle de la cuenta' };
  if (link) link.textContent = VOLVER_A[origen] || '← Volver a Insumos';
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el('detalleInsumo').classList.add('active');
  window.scrollTo(0, 0);
  void cargarContenidoDetalle();
}

function volverAInsumos() {
  detalleIdArchivo = null;
  const origen = detalleOrigenPanel;
  detalleOrigenPanel = 'insumos';
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el(origen).classList.add('active');
  if (origen === 'insumos') requestAnimationFrame(() => window.scrollTo(0, insumosScrollY));
  else window.scrollTo(0, 0);
}
el('btnVolverInsumos').addEventListener('click', volverAInsumos);

async function cargarContenidoDetalle() {
  const idArchivo = detalleIdArchivo;
  try {
    const r = await apiFetch(`${API}/archivos/${idArchivo}/contenido?page=${detallePagina}&pageSize=${DETALLE_PAGE_SIZE}`);
    if (r.status === 409) {
      detalleInsumoContent.innerHTML = '<div class="card emptyDetail">El archivo aún se encuentra en procesamiento y no tiene contenido consultable.</div>';
      return;
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    renderDetallePagina(d);
  } catch (e) {
    detalleInsumoContent.innerHTML = `<div class="card emptyDetail">Error consultando el contenido: ${e.message}</div>`;
  }
}

function renderDetallePagina(d) {
  // Error de procesamiento o rechazo al subir: no hay contenido tabular que
  // paginar, se muestra el motivo guardado (MOTIVO_ESTADO) en su lugar -
  // antes esto llegaba aquí como un 409 genérico ("aún se encuentra en
  // procesamiento"), que era engañoso para un archivo que en realidad falló
  // o fue rechazado, no uno que sigue en curso.
  if (d.motivoEstado) {
    // Un rechazo al subir también queda con estadoProcesamiento=ERROR (para
    // que el estado de la jornada lo refleje), pero el badge/traducción debe
    // seguir siendo el de RECHAZADO -más específico- cuando aplica.
    const esRechazo = d.estadoRecepcion === 'RECHAZADO';
    const motivo = esRechazo ? mensajeErrorCarga(d.motivoEstado) : causaProcesamiento(d.motivoEstado);
    detalleInsumoContent.innerHTML = `
      <div class="detailPageHead">
        <div>
          <h1>${d.nombreArchivo ?? '(sin nombre)'}</h1>
          <div class="sub">${nombreInsumo(d.tipoInsumo)}</div>
        </div>
        <div class="detailStatus">${badge(esRechazo ? d.estadoRecepcion : d.estadoProcesamiento)}</div>
      </div>
      <div class="detailMetrics">
        <div class="detailMetric"><small>Recepción</small><strong>${ESTADO_LABEL[d.estadoRecepcion] ?? d.estadoRecepcion}</strong></div>
        <div class="detailMetric"><small>Procesamiento</small><strong>${ESTADO_LABEL[d.estadoProcesamiento] ?? d.estadoProcesamiento}</strong></div>
      </div>
      <div class="card detailTableCard section">
        <div class="detailTableTop"><div class="title">Motivo</div></div>
        <div class="emptyDetail">${motivo}</div>
      </div>`;
    return;
  }
  const { page, pageSize, totalItems, totalPages } = d.pagination;
  const start = totalItems ? page * pageSize + 1 : 0;
  const end = Math.min(page * pageSize + d.items.length, totalItems);

  const headersVisibles = (d.headers || []).filter((c) => !COLUMNAS_SENSIBLES_RE.test(c.key));
  const contenidoHtml = !d.items.length
    ? '<div class="emptyDetail">El archivo no tiene contenido disponible para visualizar en esta página.</div>'
    : (() => {
        const thead = `<tr>${headersVisibles.map((c) => `<th>${c.label}</th>`).join('')}</tr>`;
        const tbody = d.items.map((row) => `<tr>${headersVisibles.map((c) => `<td>${row[c.key] ?? ''}</td>`).join('')}</tr>`).join('');
        return `
          <div class="detailTableWrap" aria-label="Contenido paginado del archivo">
            <table class="detailDataTable"><thead>${thead}</thead><tbody>${tbody}</tbody></table>
          </div>
          <div class="detailPager">
            <span class="pagerInfo">Registros ${start}-${end} de ${totalItems} · ${pageSize} por página</span>
            <div class="pager">
              <button class="btn" id="btnDetalleAnterior" ${page === 0 ? 'disabled' : ''}>‹ Anterior</button>
              <span class="muted">Página ${page + 1} de ${Math.max(1, totalPages)}</span>
              <button class="btn" id="btnDetalleSiguiente" ${page >= totalPages - 1 ? 'disabled' : ''}>Siguiente ›</button>
            </div>
          </div>`;
      })();

  detalleInsumoContent.innerHTML = `
    <div class="detailPageHead">
      <div>
        <h1>${d.nombreArchivo ?? '(sin nombre)'}</h1>
        <div class="sub">${nombreInsumo(d.tipoInsumo)}</div>
      </div>
      <div class="detailStatus">${badge(d.estadoProcesamiento)}</div>
    </div>

    <div class="detailMetrics">
      <div class="detailMetric"><small>Registros</small><strong>${totalItems}</strong></div>
      <div class="detailMetric"><small>Recepción</small><strong>${ESTADO_LABEL[d.estadoRecepcion] ?? d.estadoRecepcion}</strong></div>
      <div class="detailMetric"><small>Procesamiento</small><strong>${ESTADO_LABEL[d.estadoProcesamiento] ?? d.estadoProcesamiento}</strong></div>
    </div>

    <div class="card detailTableCard section">
      <div class="detailTableTop">
        <div class="title">Contenido del archivo</div>
        <div class="detailCount">${totalItems} registros · ${nombreInsumo(d.tipoInsumo)}</div>
      </div>
      ${contenidoHtml}
    </div>`;

  el('btnDetalleAnterior')?.addEventListener('click', () => cambiarPaginaDetalle(-1));
  el('btnDetalleSiguiente')?.addEventListener('click', () => cambiarPaginaDetalle(1));
}

function cambiarPaginaDetalle(delta) {
  detallePagina += delta;
  void cargarContenidoDetalle();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---- Carga manual del archivo original ----

// Traduce los códigos de error que devuelve el backend (ej.
// "FECHA_NO_COINCIDE_CON_ARCHIVO: el archivo X corresponde a Y, no a Z") a un
// mensaje legible para la analista, sin el código técnico ni el formato
// crudo. Si el código no se reconoce, se muestra el detalle tal cual llegó
// (mejor mostrar algo que ocultar información).
function fechaDDMMAAAA(iso) {
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}
function mensajeErrorCarga(detalle) {
  // El backend a veces manda solo el código ("CARGA_NO_PERMITIDA") y a veces
  // "CODIGO: resto del mensaje" (ej. FECHA_NO_COINCIDE_CON_ARCHIVO) — hay que
  // detectar ambas formas antes de intentar traducir.
  const texto = detalle || '';
  const sep = texto.indexOf(':');
  const prefijo = sep === -1 ? '' : texto.slice(0, sep);
  const esCodigo = prefijo !== '' && /^[A-Z_]+$/.test(prefijo);
  const codigo = esCodigo ? prefijo : texto.trim();
  const resto = esCodigo ? texto.slice(sep + 1).trimStart() : detalle;
  if (codigo === 'FECHA_NO_COINCIDE_CON_ARCHIVO') {
    // PMD y VSS traen la fecha del dia anterior: el backend agrega
    // "(jornada AAAA-MM-DD)" cuando la fecha esperada no es la de la jornada.
    const mm = /el archivo (.+) corresponde a (\d{4}-\d{2}-\d{2}), no a (\d{4}-\d{2}-\d{2})(?: \(jornada (\d{4}-\d{2}-\d{2})\))?/.exec(resto);
    if (mm && mm[4] && mm[4] !== mm[3]) {
      return `El archivo «${mm[1]}» corresponde al ${fechaDDMMAAAA(mm[2])}. Para la jornada del ${fechaDDMMAAAA(mm[4])} se espera el archivo del ${fechaDDMMAAAA(mm[3])}.`;
    }
    if (mm) return `El archivo «${mm[1]}» corresponde al ${fechaDDMMAAAA(mm[2])}, pero esta jornada es del ${fechaDDMMAAAA(mm[3])}.`;
  }
  if (codigo === 'NOMBRE_ARCHIVO_INVALIDO') {
    const mm = /el archivo (.+) no cumple la estructura esperada para ([^.]+)\.?(?:\s*Formato esperado:\s*(.+))?$/.exec(resto);
    if (mm) {
      const base = `El nombre «${mm[1]}» no tiene la estructura que se espera para ${nombreInsumo(mm[2])}.`;
      return mm[3] ? `${base} Formato esperado: ${mm[3]}` : base;
    }
  }
  if (codigo === 'CARGA_NO_PERMITIDA') return 'Este insumo ya no admite carga manual en este momento.';
  if (['ARCHIVO_NO_PERTENECE_A_JORNADA', 'ARCHIVO_NO_ENCONTRADO', 'JORNADA_NO_ENCONTRADA'].includes(codigo)) {
    return 'No se pudo identificar el archivo para esta jornada. Actualiza la página e intenta de nuevo.';
  }
  return resto || detalle;
}

async function subirArchivo(idArchivo, file) {
  const resultado = el('cargaResultado');
  if (!idJornadaActiva) { toast('Selecciona una fecha contable.', true); return; }
  resultado.innerHTML = `Subiendo archivo...`;
  const form = new FormData();
  form.append('idArchivo', idArchivo);
  form.append('archivo', file);
  try {
    // La subida ya no espera a que termine el parseo (puede tardar minutos en
    // archivos grandes) — responde apenas el archivo queda en storage, y el
    // avance real se sigue con polling en iniciarPolling().
    const r = await apiFetch(`${API}/jornadas/${idJornadaActiva}/archivos`, { method: 'POST', body: form });
    if (!r.ok) {
      // El cuerpo del error no siempre es JSON (ej. nginx devuelve HTML en un
      // 413 "archivo muy grande") — probar JSON primero, caer a texto plano
      // si falla, para no confundir esto con un error de red real.
      let detalle = `HTTP ${r.status}`;
      try { detalle = (await r.json()).detail ?? detalle; } catch { /* cuerpo no es JSON */ }
      if (r.status === 413) detalle = 'El archivo es demasiado grande para el límite configurado.';
      resultado.innerHTML = '';
      // El rechazo (400/409) ya actualizó el estado del insumo en el backend
      // (ver marcar_rechazado) - sin este refresco la tabla se queda con el
      // estado viejo hasta que algo más la vuelva a cargar.
      await cargarJornada();
      mostrarErrorCarga(mensajeErrorCarga(detalle));
      return;
    }
    await r.json();
    await cargarJornada();
    iniciarPolling(idArchivo);
  } catch (e) {
    resultado.innerHTML = '';
    mostrarErrorCarga('Error de red al cargar el archivo. Verifica tu conexión e intenta de nuevo.');
  }
}

// Sondea GET /api/v1/jornadas/{idJornada} cada segundo mientras el archivo
// está en "PROCESANDO", actualizando: (1) el panel de carga, (2) la tabla
// principal (vía cargarJornada, que ya repinta todo), y (3) la página de
// detalle dedicada si está abierta mostrando este mismo archivo. Se detiene
// solo al llegar a un estado terminal (PROCESADO/ERROR).
function iniciarPolling(idArchivo) {
  if (pollers.has(idArchivo)) return; // ya hay un polling activo para este archivo
  const resultado = el('cargaResultado');
  const tick = async () => {
    try {
      const d = await cargarJornada();
      if (!d) return;
      const a = d.insumos.find((x) => x.idArchivo === idArchivo);
      if (!a) return;
      resultado.innerHTML = `
        <div class="progressMeta"><b>${a.nombreArchivo ?? nombreInsumo(a.tipoInsumo)}</b><span>${badge(a.estadoProcesamiento)}</span></div>
        ${celdaRegistros(a)}`;
      if (detalleIdArchivo === idArchivo) await cargarContenidoDetalle();
      if (a.estadoProcesamiento === 'PROCESADO' || a.estadoProcesamiento === 'ERROR') {
        clearInterval(pollers.get(idArchivo));
        pollers.delete(idArchivo);
        if (a.estadoProcesamiento === 'PROCESADO') toast(`${nombreInsumo(a.tipoInsumo)} cargado: ${a.totalRegistros ?? '-'} registros`);
        else void mostrarErroresProcesamiento(idArchivo, a.tipoInsumo, a.nombreArchivo);
      }
    } catch (e) {
      // Error de red puntual durante el polling: se reintenta en el próximo tick,
      // no se corta el seguimiento por una falla transitoria.
    }
  };
  pollers.set(idArchivo, setInterval(tick, 1000));
  void tick();
}

el('uploadFileHidden').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file && pendingIdArchivoUpload) void subirArchivo(pendingIdArchivoUpload, file);
  pendingIdArchivoUpload = null;
});

// Se puede elegir cualquier fecha contable (un solo día, no un rango) para
// CONSULTAR y tambien para CARGAR/ELIMINAR archivos (dias anteriores
// incluidos, sin restriccion) - lo unico que sigue bloqueado es seleccionar
// una fecha futura, en el calendario propio (sin dependencias externas).
const HOY_ISO = toISO(new Date());
let fechaContableSel = HOY_ISO;
let rangoMesVista = fromISO(HOY_ISO);
rangoMesVista.setDate(1);

function fromISO(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function formatoFechaCorta(iso) {
  return fromISO(iso).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
}

function actualizarTextoRango() {
  rangoTexto.textContent = formatoFechaCorta(fechaContableSel);
}

function diasDelMes(mesVista) {
  const primero = new Date(mesVista.getFullYear(), mesVista.getMonth(), 1);
  const diaSemana = (primero.getDay() + 6) % 7; // 0 = lunes, calendario arranca en lunes
  const inicioGrid = new Date(primero);
  inicioGrid.setDate(primero.getDate() - diaSemana);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(inicioGrid);
    d.setDate(inicioGrid.getDate() + i);
    return d;
  });
}

function renderRangoCalendario() {
  rangoMesLabel.textContent = rangoMesVista.toLocaleDateString('es-CO', { month: 'long', year: 'numeric' });
  rangoGrid.innerHTML = diasDelMes(rangoMesVista).map((d) => {
    const iso = toISO(d);
    const futura = iso > HOY_ISO;
    const clases = ['rangoDia'];
    if (d.getMonth() !== rangoMesVista.getMonth()) clases.push('fueraDeMes');
    if (iso === fechaContableSel) clases.push('extremo');
    return `<button type="button" class="${clases.join(' ')}" data-iso="${iso}" ${futura ? 'disabled' : ''}>${d.getDate()}</button>`;
  }).join('');
  rangoGrid.querySelectorAll('.rangoDia').forEach((btn) => {
    btn.addEventListener('click', () => seleccionarFechaContable(btn.dataset.iso));
  });
}

function seleccionarFechaContable(iso) {
  if (iso > HOY_ISO) return; // ya viene disabled; verificación extra por si acaso
  fechaContableSel = iso;
  actualizarTextoRango();
  cerrarRangoPopover();
  void cargarPorFecha();
}

function abrirRangoPopover() {
  rangoMesVista = fromISO(fechaContableSel);
  rangoMesVista.setDate(1);
  renderRangoCalendario();
  rangoPopover.hidden = false;
  rangoTrigger.setAttribute('aria-expanded', 'true');
}

function cerrarRangoPopover() {
  rangoPopover.hidden = true;
  rangoTrigger.setAttribute('aria-expanded', 'false');
}

rangoDiasLabel.innerHTML = ['L', 'M', 'X', 'J', 'V', 'S', 'D'].map((d) => `<span>${d}</span>`).join('');
actualizarTextoRango();
rangoTrigger.addEventListener('click', () => {
  if (rangoPopover.hidden) abrirRangoPopover(); else cerrarRangoPopover();
});
document.addEventListener('click', (e) => {
  if (!rangoPopover.hidden && !rangoPopover.contains(e.target) && !rangoTrigger.contains(e.target)) cerrarRangoPopover();
});
rangoMesAnterior.addEventListener('click', () => {
  rangoMesVista.setMonth(rangoMesVista.getMonth() - 1);
  renderRangoCalendario();
});
rangoMesSiguiente.addEventListener('click', () => {
  rangoMesVista.setMonth(rangoMesVista.getMonth() + 1);
  renderRangoCalendario();
});
rangoHoy.addEventListener('click', () => {
  seleccionarFechaContable(HOY_ISO);
});

// ---- Navegación de pestañas (Insumos / Conciliación / Agente IA) ----
function go(id, btn) {
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el(id).classList.add('active');
  document.querySelectorAll('.nav button').forEach((b) => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  window.scrollTo(0, 0);
  if (id === 'conciliacion') entrarAConciliacion();
}

// ---- Conciliación: diagnóstico real Credibanco F2 (ver cierre-credibanco) ----
function fmtMoney(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  return n.toLocaleString('es-CO', { maximumFractionDigits: 0 });
}

function badgeFor(estado) {
  const e = String(estado || '');
  if (/^(CUADRA|COINCIDE|CALCULADO|PROCESADO)/.test(e)) return 'ok';
  if (/^(PENDIENTE|BLOQUEADO|DATO_INCOMPLETO)/.test(e)) return 'warn';
  if (e) return 'info';
  return 'info';
}

// Traducción legible de los códigos de estado de cierre_credibanco_v67 (ver
// evaluar_reglas_cruce/agrupar_host en el backend) - el motor siempre habla
// en código técnico explícito (nunca "OK"/"ERROR" genéricos) para que cada
// estado sea accionable; acá solo se traduce a español para la analista,
// sin perder el código (queda como title/tooltip).
const ESTADO_CONCILIACION_LABEL = {
  COINCIDE: 'Conciliado',
  CON_DIFERENCIA: 'Con diferencia',
  PLANTILLA_SIN_VALOR: 'Plantilla sin valor',
  PENDIENTE_APROBACION_REGLA: 'Pendiente de aprobación de la regla',
  CAMPO_ORIGEN_NO_PERMITIDO: 'Campo de origen no permitido',
  FUENTES_NO_DISPONIBLES: 'Fuentes no disponibles',
  CUENTA_CENTRO_INCORRECTOS: 'Cuenta/centro incorrectos',
  MONEDA_O_NATURALEZA_NO_APROBADA: 'Moneda o naturaleza no aprobada',
  SIGNO_NO_APROBADO: 'Signo no aprobado',
  FECHAS_HOST_NO_HOMOLOGADAS: 'Fechas Host no homologadas',
  FILTRO_TX_NO_APROBADO: 'Filtro TX no aprobado',
  FILTRO_MOVIMIENTO_NO_APROBADO: 'Filtro de movimiento no aprobado',
  MOTIVO_CARTA_NO_APROBADO: 'Motivo de Carta no aprobado',
  SIN_MOVIMIENTOS_FRANQUICIA: 'Sin movimientos de Franquicia',
  IMPORTES_FRANQUICIA_INCOMPLETOS: 'Importes de Franquicia incompletos',
  CARTA_CONTROL_MULTIPLE: 'Control de Carta múltiple',
  CRUDO_DEPO_NEGATIVO: 'Valor crudo DEPO negativo',
  HOST_NO_VALIDADO_O_SINTETICO: 'Host no validado o sintético',
  FECHA_HOST_NO_COINCIDE: 'Fecha Host no coincide',
  PENDIENTE_HOMOLOGACION_NATURALEZA_Y_FUENTE: 'Pendiente de homologación (naturaleza y fuente)',
  BLOQUEADO_SINTETICO: 'Bloqueado (movimiento sintético)',
  DATO_INCOMPLETO: 'Dato incompleto',
};
function labelEstadoConciliacion(estado) {
  if (!estado) return '—';
  return ESTADO_CONCILIACION_LABEL[estado] ?? estado;
}

let ultimoCierreCredibanco = null;
let cuentasHostObservadas = 0;

// ---- Conciliación: refleja solo la fecha contable elegida en Insumos ----
// No se elige fecha desde acá: la jornada es siempre la activa de Insumos.
let idJornadaConciliacion = null;
let fechaConciliacion = null;

function renderFechasConciliacion() {
  const host = el('reconFechasContables');
  if (!host) return;
  const activa = jornadaActual && jornadaActual.idJornada === idJornadaConciliacion ? jornadaActual : null;
  if (!activa) {
    host.innerHTML = '<span class="reconDateEmpty">Sin fecha contable seleccionada en Insumos.</span>';
    return;
  }
  host.innerHTML = `
    <span class="fechaChip reconDateChip active" aria-disabled="true">
      <small>FECHA CONTABLE</small><b>${esc(activa.fechaContable)}</b>
      <span class="reconDateState">${esc(ESTADO_LABEL[activa.estado] ?? activa.estado)}</span>
      <span class="reconDateId">Jornada ${Number(activa.idJornada)}</span>
    </span>`;
}

function entrarAConciliacion() {
  idJornadaConciliacion = idJornadaActiva;
  fechaConciliacion = jornadaActual?.fechaContable ?? null;
  void cargarConciliacion();
}

let cargaConciliacionSeq = 0;
async function cargarConciliacion() {
  const seq = ++cargaConciliacionSeq;
  if (idJornadaConciliacion) {
    el('reconJornada').textContent = `Fecha contable: ${fechaConciliacion} · Jornada ${idJornadaConciliacion}`;
  } else {
    el('reconJornada').textContent = 'Seleccione una fecha contable en Insumos.';
  }
  renderFechasConciliacion();
  const traz = el('reconTrazabilidad');
  if (traz) { traz.hidden = true; traz.replaceChildren(); }
  el('reconKpis').innerHTML = '';
  el('reconResultados').innerHTML = idJornadaConciliacion
    ? '<div class="emptyDetail">Cargando conciliación…</div>'
    : '<div class="emptyDetail">Selecciona una fecha contable en Insumos para ver la conciliación de esta jornada.</div>';
  await Promise.allSettled([cargarCierreCredibanco(), cargarCierreRedeban(), cargarConciliacionVisa()]);
  if (seq !== cargaConciliacionSeq) return; // llegó otra consulta mientras tanto
  renderReporteUnificado();
}

function celdaFuente(fuentes, tx, campo) {
  const f = fuentes[tx];
  if (!f || f[campo] == null) return '—';
  return fmtMoney(f[campo]);
}

// Una fila por cuenta Host, con HA22/HA26/HA32 lado a lado (Debe/Haber/Neto,
// nunca sumados entre sí) y la regla de cruce asociada si existe. Mismo
// diseño de tabla que ya traía gustavo-dev para esta pantalla, pero sobre
// datos reales de cierre_credibanco_v67 (host_por_cuenta_y_fuente /
// cruces_host_credibanco_diagnosticos), no sobre el endpoint v72 descartado.
function construirFilasHost(hostPorCuenta, cruces) {
  const porCuenta = new Map();
  for (const h of hostPorCuenta || []) {
    if (!porCuenta.has(h.cuenta)) porCuenta.set(h.cuenta, { cuenta: h.cuenta, fuentes: {} });
    porCuenta.get(h.cuenta).fuentes[h.fuente] = h;
  }
  const cruceDeCuenta = new Map((cruces || []).map((c) => [c.cuenta_host, c]));
  // Una regla del catálogo puede no tener todavía ningún movimiento Host
  // observado para su cuenta en esta jornada; igual debe listarse (con las
  // columnas HA22/26/32 en "—") para que no desaparezca de la vista.
  for (const c of cruces || []) {
    if (c.cuenta_host && !porCuenta.has(c.cuenta_host)) {
      porCuenta.set(c.cuenta_host, { cuenta: c.cuenta_host, fuentes: {} });
    }
  }
  return [...porCuenta.values()]
    .sort((a, b) => a.cuenta.localeCompare(b.cuenta))
    .map((row) => ({ ...row, cruce: cruceDeCuenta.get(row.cuenta) || null }));
}

// Concepto de origen de cada regla de cruce del catálogo
// (cierre_credibanco_v67.json), para poder mostrarlo en la tabla plana
// "Resultados de conciliación" sin que el backend tenga que exponerlo
// (el catálogo ya lo usa internamente para filtrar canje/depo por fila).
const CONCEPTO_REGLA = {
  'CB-F2-302-CANJE-CREDITO': '017-CANJE RECIBIDO TARJETA CREDITO (neto I57, filas 57-62)',
  'CB-F2-838-DEPO-NAL-CONSIGNADOS': '017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS',
  'CB-F2-838-DEPO-NAL-REVERSIONES': '017-VR. REVERSIONES D.E. NACIONAL',
  'CB-F2-839-DEPO-INT-CONSIGNADOS': '017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS',
  'CB-F2-839-DEPO-INT-REVERSIONES': '017-VR. REVERSIONES D.E. INTERNACIONAL',
};

// totales_diagnosticos ya viene agrupado por concepto (una fila por A).
function totalPorConceptoCanje(totales, concepto) {
  return (totales || []).find((t) => t.A === concepto) || null;
}

// depo_agregados_crudos es por fila (no agrupado) - se suma aquí por
// concepto para poder mostrar un solo número, igual que hace el backend
// para CAET/CANT en construir_totales_diagnosticos_canje.
function totalPorConceptoDepo(depo, concepto) {
  let cantidad = 0; let interc = 0; let total = 0; let huboInterc = false; let huboTotal = false; let filas = 0;
  for (const x of depo || []) {
    if (x.concepto !== concepto) continue;
    filas += 1;
    cantidad += x.cantidad || 0;
    if (x.valor_intercambio_crudo != null) { interc += Number(x.valor_intercambio_crudo); huboInterc = true; }
    if (x.valor_total_crudo != null) { total += Number(x.valor_total_crudo); huboTotal = true; }
  }
  if (!filas) return null;
  return { cantidad, interc: huboInterc ? interc : null, total: huboTotal ? total : null };
}

// Una fila por regla de cruce del catálogo (Franquicia/Cuenta/Concepto +
// HA22/HA26/HA32 + Total Host/Diferencia/Estado) - mismo diseño de columnas
// que traía gustavo-dev para "Resultados de conciliación", pero cada celda
// sale de un campo que cierre_credibanco_v67 realmente calcula (nunca de un
// endpoint v72/reporte-maestro-diagnostico descartado ni de datos QA
// inventados).
// ---- Resultados de conciliación unificados (Credibanco + Redeban + VISA) ----
// Una sola tabla, como la maqueta v3.0. Cada franquicia sale de su propio
// endpoint (cierre-credibanco, cierre-redeban, conciliacion-visa); acá solo se
// llevan a una fila común, sin recalcular importes ni diferencias.
const FUENTES_HOST = ['HA22', 'HA26', 'HA32'];
const GRUPOS_ESTADO = {
  CONCILIADO: ['Conciliado', 'ok'],
  CON_DIFERENCIA: ['Con diferencia', 'warn'],
  PENDIENTE: ['Pendiente de conciliación', 'info'],
  SIN_INFORMACION: ['Sin información suficiente', 'info'],
  NO_APLICA: ['No aplica', 'info'],
};

function grupoEstado(e) {
  const s = String(e || '');
  if (/^(COINCIDE|CONCILIADO|CUADRA)$/.test(s)) return 'CONCILIADO';
  if (/^(CON_DIFERENCIA|DESCUADRE)$/.test(s)) return 'CON_DIFERENCIA';
  if (s === 'SIN_CONSULTA_HOST') return 'NO_APLICA';
  if (/^(SIN_INFORMACION|FUENTES_NO_DISPONIBLES|DATO_INCOMPLETO|SIN_MOVIMIENTOS_FRANQUICIA|IMPORTES_FRANQUICIA_INCOMPLETOS|INSUMO_FALTANTE|SIN_FILAS_ESTRUCTURA|FECHA_HOST_NO_COINCIDE)$/.test(s)) return 'SIN_INFORMACION';
  return 'PENDIENTE';
}

function labelEstadoOrigen(e) {
  return ESTADO_CONCILIACION_LABEL[e] || ESTADO_VISA_LABEL[e] || e || '—';
}

const TAG_SIN_APROBAR = ' <span class="tag warn" title="La regla no tiene version+evidencia_aprobacion firmadas; este valor es un calculo provisional.">⚠ sin aprobar</span>';
const money = (v) => (v != null ? fmtMoney(v) : '—');

function hostDesdeCredibanco(fuentes, fuenteRegla) {
  const h = {};
  for (const tx of FUENTES_HOST) {
    const f = fuentes[tx];
    h[tx] = f
      ? { debe: f.debe, haber: f.haber, neto: f.neto_debe_menos_haber, movimientos: f.cantidad ?? null, archivos: f.archivos || [], consulta: tx === fuenteRegla, estado: f.estado }
      : { debe: null, haber: null, neto: null, movimientos: null, archivos: [], consulta: tx === fuenteRegla };
  }
  return h;
}

// Redeban y VISA traen la misma forma por cuenta: host[HA22|HA26|HA32] con
// debe/haber/neto/diferencia y "obligatoria" = la fuente que se compara.
function hostDesdeCuadre(host) {
  const h = {};
  for (const tx of FUENTES_HOST) {
    const f = (host || {})[tx] || {};
    h[tx] = { debe: f.debe ?? null, haber: f.haber ?? null, neto: f.neto ?? null, movimientos: f.movimientos ?? null, archivos: f.archivos || [], consulta: !!f.obligatoria, estado: f.estado, diferencia: f.diferencia ?? null };
  }
  return h;
}

function filasCredibanco(d) {
  if (!d) return [];
  const hostPorCuenta = new Map();
  for (const h of d.host_por_cuenta_y_fuente || []) {
    if (!hostPorCuenta.has(h.cuenta)) hostPorCuenta.set(h.cuenta, {});
    hostPorCuenta.get(h.cuenta)[h.fuente] = h;
  }
  return (d.cruces_host_credibanco_diagnosticos || []).map((c) => {
    const concepto = CONCEPTO_REGLA[c.id_regla] || null;
    let total = null;
    if (c.insumo === 'CANT' || c.insumo === 'CAET') total = totalPorConceptoCanje(d.totales_diagnosticos, concepto)?.D ?? null;
    else if (c.insumo === 'DEPO') total = totalPorConceptoDepo(d.depo_agregados_crudos, concepto)?.total ?? null;
    return {
      franquicia: 'CREDIBANCO',
      cuenta: c.cuenta_host || '',
      concepto,
      vlTotal: total,
      valorIntercambio: c.valor_franquicia ?? null,
      valorFranquicia: c.valor_franquicia ?? null,
      host: hostDesdeCredibanco(hostPorCuenta.get(c.cuenta_host) || {}, c.fuente_host),
      totalRechazos: null,
      valorHost: c.valor_host ?? null,
      diferencia: c.diferencia ?? null,
      estado: c.estado || '',
      aprobada: c.aprobada,
      cruce: c,
    };
  });
}

function filasCuadre(franquicia, cuentas, concepto) {
  return (cuentas || []).map((c) => {
    const host = hostDesdeCuadre(c.host);
    const consultada = FUENTES_HOST.find((tx) => host[tx].consulta);
    const valor = c.neto_pmd ?? c.esperado ?? null;
    return {
      franquicia,
      cuenta: c.cuenta,
      concepto: concepto(c),
      vlTotal: valor,
      valorIntercambio: null,
      valorFranquicia: valor,
      host,
      totalRechazos: null,
      valorHost: consultada ? host[consultada].neto : null,
      diferencia: consultada ? host[consultada].diferencia : null,
      estado: c.estado || '',
      aprobada: true,
      origen: c,
    };
  });
}

function construirFilasReporte() {
  const filas = filasCredibanco(ultimoCierreCredibanco);
  const rd = ultimoCierreRedeban;
  if (rd && rd.estado !== 'INSUMO_PMD_FALTANTE') {
    // Las cuentas sin fuente Host definida ("No aplica") van al final, para
    // que las que sí tienen resultado queden arriba (orden estable).
    const redeban = filasCuadre('REDEBAN', rd.cuentas, (c) => `${(c.operaciones || []).length} operaciones PMD`);
    filas.push(...redeban.filter((f) => grupoEstado(f.estado) !== 'NO_APLICA'),
      ...redeban.filter((f) => grupoEstado(f.estado) === 'NO_APLICA'));
  }
  const vd = ultimaConciliacionVisa;
  if (vd) {
    const liq = vd.liquidacion || {};
    const asiento = new Map((liq.asiento || []).map((a) => [a.cuenta, a]));
    filas.push(...filasCuadre('VISA', vd.cuentas, (c) => {
      const a = asiento.get(c.cuenta);
      return a ? ((liq.celdas || {})[a.celda]?.etiqueta || `Asiento ${a.celda}`) : null;
    }));
  }
  return filas;
}

let filasReporte = [];

// "resumida": 11 columnas, solo netos (maqueta v3.0).
// "detallada": Debe/Haber/Neto por fuente Host y el valor Host comparado.
const VISTAS_RESULTADO = ['resumida', 'detallada'];
let vistaResultado = 'resumida';
try {
  const guardada = localStorage.getItem('concilia.vistaResultado');
  if (VISTAS_RESULTADO.includes(guardada)) vistaResultado = guardada;
} catch { /* sin almacenamiento: se usa la vista por defecto */ }

const COLUMNAS_RESULTADO = {
  resumida: ['Franquicia', 'Cuenta', 'VL Total', 'Valor intercambio', 'HA22 Neto', 'HA26 Neto', 'HA32 Neto',
    'Total rechazos', 'Diferencia', 'Estado conciliación', 'Acción'],
  detallada: ['Franquicia', 'Cuenta', 'VL Total', 'Valor intercambio', 'HA22 Debe', 'HA22 Haber', 'HA22 Neto',
    'HA26 Debe', 'HA26 Haber', 'HA26 Neto', 'HA32 Debe', 'HA32 Haber', 'HA32 Neto', 'Valor Host',
    'Total rechazos', 'Diferencia', 'Estado conciliación', 'Acción'],
};

// Sin movimientos Host en esa fuente se muestra "—" (no hay dato), no 0.
function sinDatoHost(h) {
  return !h || h.neto == null || (h.movimientos === 0 && !(h.archivos || []).length);
}

function celdaHost(f, tx, campo) {
  const h = f.host[tx];
  const txt = sinDatoHost(h) ? '—' : money(h[campo]);
  if (h?.consulta && campo === 'neto') {
    return `<td class="num"><span class="fuenteConsulta" title="Fuente Host que se compara para esta cuenta">${txt}</span></td>`;
  }
  return `<td class="num">${txt}</td>`;
}

function estadoHtml(f) {
  const [txt, cls] = GRUPOS_ESTADO[grupoEstado(f.estado)];
  const origen = labelEstadoOrigen(f.estado);
  const sub = origen && origen !== txt && origen !== '—' ? `<span class="reconCuentaSub">${esc(origen)}</span>` : '';
  return `<span class="tag ${cls}" title="${esc(f.estado)}">${esc(txt)}</span>${f.diferencia != null && f.aprobada === false ? TAG_SIN_APROBAR : ''}${sub}`;
}

function filaReporteHtml(f, i, vista) {
  const cuenta = `<a href="#" onclick="abrirDetalleCuenta(${i});return false;">${esc(f.cuenta || '—')}</a>${f.concepto ? `<span class="reconCuentaSub">${esc(f.concepto)}</span>` : ''}`;
  const host = vista === 'resumida'
    ? FUENTES_HOST.map((tx) => celdaHost(f, tx, 'neto')).join('')
    : FUENTES_HOST.map((tx) => celdaHost(f, tx, 'debe') + celdaHost(f, tx, 'haber') + celdaHost(f, tx, 'neto')).join('')
      + `<td class="num">${money(f.valorHost)}</td>`;
  const texto = `${f.cuenta} ${f.concepto || ''}`.toLowerCase();
  return `<tr data-i="${i}" data-franquicia="${esc(f.franquicia)}" data-grupo="${grupoEstado(f.estado)}" data-texto="${esc(texto)}">
      <td>${esc(f.franquicia)}</td><td>${cuenta}</td>
      <td class="num">${money(f.vlTotal)}</td><td class="num">${money(f.valorIntercambio)}</td>${host}
      <td class="num">${money(f.totalRechazos)}</td><td class="num">${money(f.diferencia)}</td><td>${estadoHtml(f)}</td>
      <td><div class="actionbar" style="margin:0;flex-wrap:nowrap">
        <button type="button" class="btn" onclick="abrirDetalleCuenta(${i})">Detalle</button>
        <button type="button" class="btn" onclick="analizarConIA(${i})">Análisis IA</button>
      </div></td></tr>`;
}

function trmCardHtml() {
  const vd = ultimaConciliacionVisa;
  if (!vd) return '';
  const m = (vd.liquidacion?.celdas || {}).M169 || {};
  const vigente = m.valor != null
    ? `TRM vigente: <b>${numVisa(m.valor, 4)}</b>`
    : 'Sin TRM capturada: la liquidación VISA no se calcula hasta confirmarla.';
  return `<div class="trmCard">
      <div><h4>TRM de la jornada</h4><div class="muted" style="font-size:9px">${vigente}</div></div>
      <input type="text" inputmode="decimal" id="trmJornadaInput" placeholder="ej. 4012.3456" aria-label="TRM de la jornada">
      <button type="button" class="btn" id="btnConfirmarTrm">Confirmar TRM</button>
      <span id="trmMensaje" class="muted" role="status" aria-live="polite" style="font-size:9px"></span>
    </div>`;
}

async function confirmarTrm() {
  const v = (el('trmJornadaInput')?.value || '').trim();
  const msg = el('trmMensaje');
  if (!v) { msg.textContent = 'Escribe la TRM (ej. 4012.3456).'; return; }
  const boton = el('btnConfirmarTrm');
  boton.disabled = true;
  msg.textContent = 'Guardando…';
  let r;
  try {
    r = await apiFetch(`${API}/jornadas/${idJornadaConciliacion}/conciliacion-visa/capturas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ valores: { M169: v }, observacion: 'TRM confirmada desde Resultados de conciliación' }),
    });
  } catch (e) {
    msg.textContent = `No se pudo guardar: ${e.message || e}`;
    boton.disabled = false;
    return;
  }
  if (!r.ok) {
    let detalle = `HTTP ${r.status}`;
    try { const j = await r.json(); detalle = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* sin cuerpo */ }
    msg.textContent = `No se pudo guardar: ${detalle}`;
    boton.disabled = false;
    return;
  }
  ultimaConciliacionVisa = await r.json();
  renderConciliacionVisa('TRM guardada desde Resultados de conciliación.');
  renderReporteUnificado();
  toast('TRM confirmada.');
}

function renderReporteUnificado() {
  filasReporte = construirFilasReporte();
  const kp = el('reconKpis');
  const res = el('reconResultados');
  if (!kp || !res) return;
  if (!idJornadaConciliacion) {
    kp.innerHTML = '';
    res.innerHTML = '<div class="emptyDetail">Selecciona una fecha contable en Insumos para ver la conciliación de esta jornada.</div>';
    return;
  }
  const porGrupo = (g) => filasReporte.filter((f) => grupoEstado(f.estado) === g).length;
  // "Incorporados maestro": filas con al menos un movimiento Host cargado.
  const incorporados = filasReporte.filter((f) => FUENTES_HOST.some((tx) => !sinDatoHost(f.host[tx]))).length;
  kp.innerHTML = `<div class="flow summaryFlow">
      <div class="fc"><small>CUENTAS / CRUCES</small><b>${filasReporte.length}</b></div>
      <div class="fc"><small>CONCILIADOS</small><b>${porGrupo('CONCILIADO')}</b></div>
      <div class="fc"><small>DIFERENCIAS</small><b>${porGrupo('CON_DIFERENCIA')}</b></div>
      <div class="fc"><small>INCORPORADOS MAESTRO</small><b>${incorporados}</b></div>
    </div>`;
  const previos = { q: el('reconQ')?.value || '', fr: el('reconFr')?.value || '', st: el('reconSt')?.value || '' };
  const opcionesEstado = Object.entries(GRUPOS_ESTADO).map(([k, [t]]) => `<option value="${k}">${t}</option>`).join('');
  res.innerHTML = `
    <div class="toolbar section">
      <input id="reconQ" class="search" oninput="filterResultadoRows()" placeholder="Buscar cuenta o concepto..." aria-label="Buscar cuenta o concepto">
      <select id="reconFr" class="select" onchange="filterResultadoRows()" aria-label="Filtrar por franquicia">
        <option value="">Todas las franquicias</option>
        <option value="CREDIBANCO">Credibanco</option>
        <option value="REDEBAN">Redeban</option>
        <option value="VISA">Visa</option>
      </select>
      <select id="reconSt" class="select" onchange="filterResultadoRows()" aria-label="Filtrar por estado">
        <option value="">Todos los estados</option>${opcionesEstado}
      </select>
    </div>
    <div class="reconTitleRow">
      <h3>Resultados de conciliación</h3>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <span class="reconMeta" id="reconMetaTotal"></span>
        <button type="button" class="btn" id="btnVerPlantillaMaestra" onclick="abrirPlantillaMaestra()">Ver Plantilla Maestra</button>
        <div class="actionbar" role="group" aria-label="Vista de la tabla" style="margin-top:0">
          <button type="button" class="btn" data-vista-resultado="resumida" onclick="cambiarVistaResultado('resumida')">Vista resumida</button>
          <button type="button" class="btn" data-vista-resultado="detallada" onclick="cambiarVistaResultado('detallada')">Vista detallada</button>
        </div>
      </div>
    </div>
    ${trmCardHtml()}
    <div class="card" style="padding:0"><div class="tableScroll"><table class="reconTable"><thead id="reconHead"></thead><tbody id="reconBody"></tbody></table></div></div>
    <p class="filterHint">VL Total: valor de origen de la franquicia (Credibanco: total del concepto; Redeban: neto PMD; Visa: valor esperado del asiento). Valor intercambio: valor de la franquicia que compara la regla Credibanco. Subrayado: la fuente Host que se compara para esa cuenta; HA22, HA26 y HA32 no se suman entre sí. —: no disponible / sin movimientos Host. Total rechazos: sin fuente calculada todavía.</p>
    <div class="actionbar" style="justify-content:flex-end">
      <button type="button" class="btn" onclick="exportarResultadosCsv()">Exportar CSV</button>
      <button type="button" class="btn" onclick="toggleTrazabilidadHost()">Ver trazabilidad Host (${cuentasHostObservadas})</button>
    </div>`;
  el('reconQ').value = previos.q;
  el('reconFr').value = previos.fr;
  el('reconSt').value = previos.st;
  el('btnConfirmarTrm')?.addEventListener('click', () => { void confirmarTrm(); });
  renderTablaResultado();
}

function renderTablaResultado() {
  const head = el('reconHead');
  const body = el('reconBody');
  if (!head || !body) return;
  const cols = COLUMNAS_RESULTADO[vistaResultado];
  head.innerHTML = `<tr>${cols.map((c) => `<th>${esc(c)}</th>`).join('')}</tr>`;
  body.innerHTML = filasReporte.length
    ? filasReporte.map((f, i) => filaReporteHtml(f, i, vistaResultado)).join('')
    : `<tr><td colspan="${cols.length}" class="muted">Sin resultados para esta jornada (faltan insumos procesados).</td></tr>`;
  document.querySelectorAll('[data-vista-resultado]').forEach((b) => {
    const activa = b.dataset.vistaResultado === vistaResultado;
    b.classList.toggle('primary', activa);
    b.setAttribute('aria-pressed', String(activa));
  });
  filterResultadoRows();
}

function cambiarVistaResultado(vista) {
  if (!VISTAS_RESULTADO.includes(vista)) return;
  vistaResultado = vista;
  try { localStorage.setItem('concilia.vistaResultado', vista); } catch { /* opcional */ }
  renderTablaResultado();
}

function filterResultadoRows() {
  const q = (el('reconQ')?.value || '').toLowerCase().trim();
  const fr = el('reconFr')?.value || '';
  const st = el('reconSt')?.value || '';
  let visibles = 0;
  let conciliadas = 0;
  let diferencias = 0;
  document.querySelectorAll('#reconBody tr[data-i]').forEach((r) => {
    const ver = (!q || (r.dataset.texto || '').includes(q)) && (!fr || r.dataset.franquicia === fr) && (!st || r.dataset.grupo === st);
    r.style.display = ver ? '' : 'none';
    if (!ver) return;
    visibles += 1;
    if (r.dataset.grupo === 'CONCILIADO') conciliadas += 1;
    if (r.dataset.grupo === 'CON_DIFERENCIA') diferencias += 1;
  });
  const meta = el('reconMetaTotal');
  if (meta) meta.textContent = `${visibles} cuentas · ${conciliadas} conciliadas · ${diferencias} con diferencia`;
}

// CSV para Excel en español: separador ";", coma decimal y BOM UTF-8.
// Exporta la vista activa y solo las filas que dejan ver los filtros.
function celdaCsv(v) {
  if (v == null || v === '') return '';
  let s = String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`; // evita que Excel lo tome como fórmula
  return /[;"\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}
function numeroCsv(v) {
  if (v == null || v === '') return '';
  const n = Number(v);
  return Number.isFinite(n) ? String(n).replace('.', ',') : '';
}

function textoEstadoCsv(estado) {
  const grupo = GRUPOS_ESTADO[grupoEstado(estado)][0];
  const origen = labelEstadoOrigen(estado);
  return origen === grupo || origen === '—' ? grupo : `${grupo} (${origen})`;
}

function exportarResultadosCsv() {
  const visibles = [...document.querySelectorAll('#reconBody tr[data-i]')]
    .filter((r) => r.style.display !== 'none')
    .map((r) => filasReporte[Number(r.dataset.i)]);
  if (!visibles.length) { toast('No hay filas para exportar.'); return; }
  const host = (f, tx, campo) => (sinDatoHost(f.host[tx]) ? '' : numeroCsv(f.host[tx][campo]));
  const cols = ['Franquicia', 'Cuenta', 'Concepto', ...COLUMNAS_RESULTADO[vistaResultado].slice(2).filter((c) => c !== 'Acción')];
  const filas = visibles.map((f) => {
    const hostCols = vistaResultado === 'resumida'
      ? FUENTES_HOST.map((tx) => host(f, tx, 'neto'))
      : [...FUENTES_HOST.flatMap((tx) => [host(f, tx, 'debe'), host(f, tx, 'haber'), host(f, tx, 'neto')]), numeroCsv(f.valorHost)];
    return [celdaCsv(f.franquicia), celdaCsv(f.cuenta), celdaCsv(f.concepto), numeroCsv(f.vlTotal), numeroCsv(f.valorIntercambio),
      ...hostCols, numeroCsv(f.totalRechazos), numeroCsv(f.diferencia),
      celdaCsv(textoEstadoCsv(f.estado))].join(';');
  });
  const csv = [cols.map(celdaCsv).join(';'), ...filas].join('\r\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
  a.download = `Conciliacion_${fechaConciliacion || 'sin_fecha'}_${vistaResultado}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast(`Exportadas ${visibles.length} filas (${vistaResultado}).`);
}

// "Ver trazabilidad Host": muestra debajo de los resultados la tabla de
// cuentas Host observadas (se arma oculta en el diagnóstico Credibanco).
function toggleTrazabilidadHost() {
  const destino = el('reconTrazabilidad');
  if (!destino) return;
  if (!destino.hidden) { destino.hidden = true; return; }
  const card = el('trazabilidadHostCard');
  if (!card) { toast('Sin diagnóstico Credibanco para esta jornada.', true); return; }
  destino.replaceChildren(card);
  destino.hidden = false;
  destino.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// "Análisis IA": abre el Agente IA (vista previa, no funcional) con los
// valores reales de la fila.
function analizarConIA(i) {
  const f = filasReporte[i];
  if (!f) return;
  go('ia', document.querySelectorAll('.nav button')[2]);
  el('aiCaseTitle').textContent = `Caso · ${f.franquicia} / Cuenta ${f.cuenta}`;
  el('aiValFranquicia').textContent = money(f.valorFranquicia);
  el('aiValHost').textContent = money(f.valorHost);
  el('caseDiff').textContent = money(f.diferencia);
}

function filterCruceRows() {
  const q = (el('cruceQ')?.value || '').toLowerCase();
  const st = el('cruceSt')?.value || '';
  document.querySelectorAll('#cruceBody tr').forEach((r) => {
    const okq = !q || (r.dataset.cuenta || '').toLowerCase().includes(q);
    const okst = !st || r.dataset.estado === st;
    r.style.display = okq && okst ? 'table-row' : 'none';
  });
}

// Página completa de detalle por cuenta (maqueta v3.0): A. Contabilidad
// interna · Host, B. Insumos externos, C. Resultado de conciliación y
// Evidencias de origen. Sirve para las tres franquicias.
let detalleCuentaOrigenScrollY = 0;

function mostrarPanelDetalleCuenta() {
  detalleCuentaOrigenScrollY = window.scrollY;
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el('detalleCuentaCredibanco').classList.add('active');
  window.scrollTo(0, 0);
}

function abrirDetalleCuenta(i) {
  const f = filasReporte[i];
  if (!f) return;
  mostrarPanelDetalleCuenta();
  renderDetalleCuenta(f);
}

// Desde la tabla de cuentas Host observadas (diagnóstico Credibanco): usa la
// fila del reporte si la cuenta tiene regla; si no, solo el lado Host.
function abrirDetalleCuentaCredibanco(cuenta) {
  const i = filasReporte.findIndex((f) => f.franquicia === 'CREDIBANCO' && f.cuenta === cuenta);
  if (i >= 0) { abrirDetalleCuenta(i); return; }
  const fuentes = {};
  for (const h of ultimoCierreCredibanco?.host_por_cuenta_y_fuente || []) {
    if (h.cuenta === cuenta) fuentes[h.fuente] = h;
  }
  mostrarPanelDetalleCuenta();
  renderDetalleCuenta({ franquicia: 'CREDIBANCO', cuenta, concepto: null, host: hostDesdeCredibanco(fuentes, null), cruce: null });
}

function volverAConciliacion() {
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el('conciliacion').classList.add('active');
  requestAnimationFrame(() => window.scrollTo(0, detalleCuentaOrigenScrollY));
}
el('btnVolverConciliacion')?.addEventListener('click', volverAConciliacion);

// Sección B Credibanco: nunca se atribuye un total global de CAET/CANT a una
// cuenta (el motor no lo hace sin regla aprobada), salvo DEPO, donde
// agrupar_depo() ya calcula una cuenta_host_candidata explícita por fila.
function seccionBCredibanco(d, cuenta, cruce) {
  if (cruce && (cruce.insumo === 'CAET' || cruce.insumo === 'CANT')) {
    const filasHtml = (d.totales_diagnosticos || [])
      .map((t) => `<tr><td>${esc(t.A)}</td><td>${esc((t.insumos || []).join(', '))}</td><td class="num">${t.B ?? '—'}</td><td class="num">${money(t.C)}</td><td class="num">${money(t.D)}</td></tr>`)
      .join('');
    return `
      <h3>B. Insumos externos · CAET/CANT</h3>
      <p class="friendlyNote">Totales globales de origen por concepto persistido. No atribuidos automáticamente a esta cuenta: la regla de cruce es la única atribución aprobable. No sumar CAET y CANT entre sí.</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Concepto</th><th>Insumo</th><th>Cantidad</th><th>VL Interc</th><th>VL Total</th></tr></thead>
      <tbody>${filasHtml || '<tr><td colspan="5" class="muted">Sin totales disponibles.</td></tr>'}</tbody></table></div>`;
  }
  if (cruce && cruce.insumo === 'PLANTILLA') {
    const p = d.plantilla_maestra || {};
    const recibido = (p.bloques || []).find((b) => b.codigo === 'TOTAL_CANJE_RECIBIDO') || { filas: [] };
    const i57 = (p.controles || {}).I57_CUENTA_302 || {};
    const filasHtml = recibido.filas
      .filter((f) => f.fila >= 57 && f.fila <= 62)
      .map((f) => `<tr><td class="num">${f.fila}</td><td>${esc(f.concepto)}</td><td class="num">${money(f.debito)}</td><td class="num">${money(f.credito)}</td><td><span class="tag ${badgeForPlantilla(f.estado)}" title="${esc(f.formula_excel || '')}">${esc(f.estado)}</span></td></tr>`)
      .join('');
    return `
      <h3>B. Insumos externos · Plantilla Maestra filas 57 a 62</h3>
      <p class="friendlyNote">Neto I57 = F57 − G58 − G59 − G61 − G60 + F62 = <b>${money(i57.valor)}</b>. Es el valor de franquicia que se compara contra HA32 de esta cuenta (nota de la Plantilla: "VALI CTA 302 HA 32").</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fila</th><th>Concepto</th><th>Débito</th><th>Crédito</th><th>Estado</th></tr></thead>
      <tbody>${filasHtml || '<tr><td colspan="5" class="muted">Sin filas de la Plantilla.</td></tr>'}</tbody></table></div>`;
  }
  if (cruce && cruce.insumo === 'DEPO') {
    const filasHtml = (d.depo_agregados_crudos || [])
      .filter((x) => x.cuenta_host_candidata === cuenta)
      .map((x) => `<tr><td>${esc(x.concepto || x.concepto_persistido || '—')}</td><td class="num">${x.cantidad ?? '—'}</td><td class="num">${money(x.valor_total_crudo)}</td><td class="num">${money(x.valor_intercambio_crudo)}</td><td><span class="tag ${badgeFor(x.estado)}">${esc(x.estado)}</span></td></tr>`)
      .join('');
    return `
      <h3>B. Insumos externos · DEPO</h3>
      <p class="friendlyNote">Filas de DEPO cuya cuenta candidata (calculada por el motor a partir del concepto AU) coincide con esta cuenta. Candidato, no homologación aprobada.</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Concepto</th><th>Cantidad</th><th>Valor total crudo</th><th>Valor intercambio crudo</th><th>Estado</th></tr></thead>
      <tbody>${filasHtml || '<tr><td colspan="5" class="muted">Sin filas DEPO candidateadas a esta cuenta.</td></tr>'}</tbody></table></div>`;
  }
  return '<h3>B. Insumos externos · CREDIBANCO</h3><p class="muted">Sin regla de cruce asociada a esta cuenta; no hay insumo externo que mostrar aquí todavía.</p>';
}

function seccionBRedeban(f) {
  const c = f.origen || {};
  const ops = c.operaciones || [];
  const filasOps = ops.map((o) => `<tr><td class="num">${o.fila}</td><td>${esc(o.codigo_pmd)}</td><td>${esc(o.nombre_operacion || '')}</td><td>${esc(o.tipo || '')}</td><td class="num">${money(o.debito)}</td><td class="num">${money(o.credito)}</td><td class="num">${money(o.neto)}</td></tr>`).join('');
  const manual = (c.filas_captura_manual || []).length
    ? `<p class="filterHint">Filas de captura manual en ESTRUCTURA (no calculadas): ${(c.filas_captura_manual || []).map(Number).join(', ')}.</p>` : '';
  return `
    <h3>B. Insumos externos · REDEBAN</h3>
    <div class="tableScroll"><table class="reconTable"><thead><tr><th>Insumo</th><th>Débito</th><th>Crédito</th><th>Importe origen (neto)</th><th>Estado</th></tr></thead>
    <tbody><tr><td>PMD · ${Number(c.filas_estructura || 0)} filas de ESTRUCTURA</td><td class="num">${money(c.debito)}</td><td class="num">${money(c.credito)}</td><td class="num">${money(c.neto_pmd)}</td><td>${tagRedeban(c.estado)}</td></tr></tbody></table></div>
    ${manual}
    <details class="section"><summary style="cursor:pointer"><b>Operaciones PMD de la cuenta</b> <span class="tag info">${ops.length}</span></summary>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fila</th><th>Código PMD</th><th>Operación</th><th>Tipo</th><th>Débito</th><th>Crédito</th><th>Neto</th></tr></thead>
      <tbody>${filasOps || '<tr><td colspan="7" class="muted">Sin operaciones PMD para esta cuenta.</td></tr>'}</tbody></table></div>
    </details>`;
}

function seccionBVisa(f) {
  const vd = ultimaConciliacionVisa || {};
  const liq = vd.liquidacion || {};
  const celdas = liq.celdas || {};
  const filas = (liq.asiento || []).filter((a) => a.cuenta === f.cuenta).map((a) => {
    const c = celdas[a.celda] || {};
    return `<tr><td>Liquidación VISA · ${esc(c.etiqueta || a.celda)} (${esc(a.celda)}, fila ${Number(a.fila)})</td><td class="num">${money(a.valor)}</td><td>${esc(a.naturaleza || a.naturaleza_plantilla || '—')}</td><td>${tagVisa(c.estado)}</td></tr>`;
  }).join('');
  const insumos = vd.insumos || {};
  return `
    <h3>B. Insumos externos · VISA</h3>
    <div class="tableScroll"><table class="reconTable"><thead><tr><th>Insumo</th><th>Importe origen</th><th>Naturaleza</th><th>Estado</th></tr></thead>
    <tbody>${filas || '<tr><td colspan="4" class="muted">Sin asiento de liquidación para esta cuenta.</td></tr>'}</tbody></table></div>
    <p class="filterHint">Insumos de la liquidación: VSS ${insumos.VSS ? 'procesado' : 'faltante'} · Posición Neta (International SS) ${insumos.ISS ? 'procesado' : 'faltante'}. La TRM se confirma en "TRM de la jornada", en Resultados de conciliación.</p>`;
}

// Sección C para Redeban/VISA: la diferencia la calcula el motor por fuente;
// se muestran las tres y se resalta la que se compara.
function resultadoCuadre(f) {
  const consultada = FUENTES_HOST.find((tx) => f.host[tx].consulta);
  const g = grupoEstado(f.estado);
  const conclusiones = {
    CONCILIADO: 'Cuenta conciliada: la fuente Host que se compara coincide con el valor de la franquicia.',
    CON_DIFERENCIA: `Diferencia pendiente de ${money(f.diferencia)}${consultada ? ` contra ${consultada}` : ''}. No sumar fuentes Host.`,
    NO_APLICA: 'La plantilla no define una fuente Host para comparar esta cuenta.',
    SIN_INFORMACION: 'Sin información suficiente para conciliar esta cuenta.',
    PENDIENTE: `Pendiente de conciliación: ${labelEstadoOrigen(f.estado)}.`,
  };
  const filas = FUENTES_HOST.map((tx) => {
    const h = f.host[tx];
    return `<tr><td>${tx}${h.consulta ? ' <span class="tag info">Se compara</span>' : ''}</td><td class="num">${money(f.valorFranquicia)}</td><td class="num">${sinDatoHost(h) ? '—' : money(h.neto)}</td><td class="num">${money(h.diferencia)}</td><td>${tagVisa(h.estado)}</td></tr>`;
  }).join('');
  return `
    <h3>C. Resultado de conciliación</h3>
    <p class="friendlyNote"><span class="tag ${GRUPOS_ESTADO[g][1]}">${esc(GRUPOS_ESTADO[g][0])}</span> ${esc(conclusiones[g])}</p>
    <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fuente Host</th><th>Valor franquicia</th><th>Neto Host</th><th>Diferencia</th><th>Estado</th></tr></thead>
    <tbody>${filas}</tbody></table></div>
    <p class="filterHint">Diferencia calculada por el motor para cada fuente por separado. Una diferencia no genera asientos contables automáticos.</p>`;
}

function evidenciasHtml(f, crucesCuenta) {
  const evid = new Map();
  const add = (id, etiqueta) => { if (id != null && !evid.has(Number(id))) evid.set(Number(id), etiqueta); };
  for (const tx of FUENTES_HOST) (f.host[tx]?.archivos || []).forEach((id) => add(id, tx));
  if (f.franquicia === 'CREDIBANCO') {
    for (const c of crucesCuenta || []) (c.archivos_origen || []).forEach((id) => add(id, c.insumo));
  } else if (f.franquicia === 'VISA') {
    const vd = ultimaConciliacionVisa || {};
    ((vd.vss || {}).liquidaciones || []).forEach((l) => add(l.id_archivo, 'VSS'));
    (vd.iss || []).forEach((x) => add(x.id_archivo, 'Posición Neta'));
  } else if (f.franquicia === 'REDEBAN' && jornadaActual?.idJornada === idJornadaConciliacion) {
    (jornadaActual.insumos || []).filter((x) => x.tipoInsumo === 'PMD').forEach((x) => add(x.idArchivo, 'PMD'));
  }
  if (!evid.size) return '<p class="muted">Sin archivos de evidencia asociados a esta cuenta.</p>';
  return `<div class="evidencias">${[...evid].map(([id, etiqueta]) => `<button type="button" class="btn" onclick="abrirDetalle(${id},'detalleCuentaCredibanco')" title="Archivo ${id}">Ver ${esc(etiqueta)}</button>`).join('')}</div>`;
}

function renderDetalleCuenta(f) {
  const cont = el('detalleCuentaCredibancoContent');
  if (!cont) return;
  const filasA = FUENTES_HOST.map((tx) => {
    const h = f.host[tx] || {};
    const sin = sinDatoHost(h);
    return `<tr><td>${tx}${h.consulta ? ' <span class="tag info">Se compara</span>' : ''}</td><td class="num">${sin ? '—' : money(h.debe)}</td><td class="num">${sin ? '—' : money(h.haber)}</td><td class="num">${sin ? '—' : money(h.neto)}</td><td class="num">${h.movimientos ?? '—'}</td></tr>`;
  }).join('');
  let seccionB;
  let seccionC;
  let crucesCuenta = [];
  if (f.franquicia === 'CREDIBANCO') {
    const d = ultimoCierreCredibanco;
    crucesCuenta = (d?.cruces_host_credibanco_diagnosticos || []).filter((c) => c.cuenta_host === f.cuenta);
    seccionB = d ? seccionBCredibanco(d, f.cuenta, f.cruce || crucesCuenta[0] || null) : '<h3>B. Insumos externos</h3><p class="muted">Sin diagnóstico Credibanco.</p>';
    seccionC = renderResultadoCuenta(crucesCuenta);
  } else if (f.franquicia === 'REDEBAN') {
    seccionB = seccionBRedeban(f);
    seccionC = resultadoCuadre(f);
  } else {
    seccionB = seccionBVisa(f);
    seccionC = resultadoCuadre(f);
  }
  cont.innerHTML = `
    <div class="head"><div><h1>Detalle de conciliación · ${esc(f.cuenta)}</h1><p>${esc(f.franquicia)}${f.concepto ? ` · ${esc(f.concepto)}` : ''} · Fecha contable ${esc(fechaConciliacion || '—')}</p></div></div>
    <div class="card section">
      <h3>A. Contabilidad interna · Host</h3>
      <p class="friendlyNote">Neto = Debe − Haber. HA22, HA26 y HA32 no se suman entre sí.</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fuente</th><th>Debe</th><th>Haber</th><th>Neto</th><th>Movimientos</th></tr></thead>
      <tbody>${filasA}</tbody></table></div>
    </div>
    <div class="card section">${seccionB}</div>
    <div class="card section">${seccionC}</div>
    <div class="card section"><h3>Evidencias de origen</h3>${evidenciasHtml(f, crucesCuenta)}</div>`;
}

// Sección C: resultado de cada regla de cruce de la cuenta (franquicia vs la
// fuente Host que define la regla). Las diferencias de reglas distintas no se
// suman: cada una compara un lado distinto (p. ej. consignados vs Debe y
// reversiones vs Haber).
function renderResultadoCuenta(crucesCuenta) {
  if (!crucesCuenta.length) {
    return '<h3>C. Resultado de conciliación</h3><p class="muted">Sin regla de cruce para esta cuenta: no hay resultado que calcular todavía.</p>';
  }
  const conciliadas = crucesCuenta.filter((c) => c.estado === 'COINCIDE').length;
  const conDiferencia = crucesCuenta.filter((c) => c.estado === 'CON_DIFERENCIA').length;
  const sinResultado = crucesCuenta.length - conciliadas - conDiferencia;
  let conclusion;
  let tipo;
  if (conciliadas === crucesCuenta.length) {
    conclusion = 'Cuenta conciliada: todas las reglas coinciden con Host (diferencia 0).';
    tipo = 'ok';
  } else if (conDiferencia) {
    conclusion = `${conDiferencia} de ${crucesCuenta.length} regla(s) con diferencia. Revisar la evidencia de origen y la fuente Host de cada una.`;
    tipo = 'warn';
  } else {
    conclusion = 'Sin resultado calculable: falta información o la regla no se pudo evaluar (ver estado).';
    tipo = 'info';
  }
  if (sinResultado && conDiferencia) conclusion += ` ${sinResultado} regla(s) sin resultado calculable.`;
  const archivos = (ids) => (ids || []).map((id) => `<button type="button" class="btn" onclick="abrirDetalle(${Number(id)},'detalleCuentaCredibanco')">${Number(id)}</button>`).join(' ') || '—';
  const filas = crucesCuenta.map((c) => `<tr>
      <td>${esc(c.id_regla)}<br><small class="muted">v${esc(c.version || '?')}</small></td>
      <td>${esc(CONCEPTO_REGLA[c.id_regla] || '—')}</td>
      <td>${esc(c.insumo || '—')}</td>
      <td>${esc(c.fuente_host || '—')}</td>
      <td class="num">${money(c.valor_franquicia)}</td>
      <td class="num">${money(c.valor_host)}</td>
      <td class="num">${money(c.diferencia)}</td>
      <td><span class="tag ${badgeFor(c.estado)}" title="${esc(c.estado || '')}">${esc(labelEstadoConciliacion(c.estado))}</span>${c.diferencia != null && c.aprobada === false ? TAG_SIN_APROBAR : ''}</td>
      <td>${archivos(c.archivos_origen)}</td>
      <td>${archivos(c.archivo_host)}</td>
    </tr>`).join('');
  return `
    <h3>C. Resultado de conciliación</h3>
    <p class="friendlyNote"><span class="tag ${tipo}">${conciliadas} conciliada(s) · ${conDiferencia} con diferencia · ${sinResultado} sin resultado</span> ${esc(conclusion)}</p>
    <div class="tableScroll"><table class="reconTable"><thead><tr><th>Regla</th><th>Concepto</th><th>Insumo</th><th>Fuente Host</th><th>Valor franquicia</th><th>Valor Host</th><th>Diferencia</th><th>Estado</th><th>Archivo origen</th><th>Archivo Host</th></tr></thead>
    <tbody>${filas}</tbody></table></div>
    <p class="filterHint">Diferencia = valor franquicia − valor Host de la fuente indicada. Las diferencias de reglas distintas no se suman entre sí. Una diferencia no genera asientos contables automáticos.</p>`;
}

async function cargarCierreCredibanco() {
  const cont = el('cierreCredibancoContent');
  if (!cont) return;
  ultimoCierreCredibanco = null;
  if (!idJornadaConciliacion) {
    cont.innerHTML = '<div class="emptyDetail">Selecciona una fecha contable para ver el diagnóstico Credibanco de esta jornada.</div>';
    return;
  }
  cont.innerHTML = '<div class="emptyDetail">Cargando diagnóstico…</div>';
  let r;
  try {
    r = await apiFetch(`${API}/jornadas/${idJornadaConciliacion}/cierre-credibanco`);
  } catch (e) {
    cont.innerHTML = `<div class="emptyDetail">No se pudo cargar el diagnóstico: ${esc(e.message || e)}</div>`;
    return;
  }
  if (!r.ok) {
    cont.innerHTML = `<div class="emptyDetail">No se pudo cargar el diagnóstico (HTTP ${r.status}).</div>`;
    return;
  }
  const d = await r.json();
  ultimoCierreCredibanco = d;
  const pendRows = (d.pendientes || [])
    .map((p) => `<tr><td>${esc(p.codigo || p.estado || '')}</td><td>${esc(p.detalle || p.mensaje || JSON.stringify(p))}</td></tr>`)
    .join('');

  const cruces = d.cruces_host_credibanco_diagnosticos || [];
  const filasHost = construirFilasHost(d.host_por_cuenta_y_fuente, cruces);
  cuentasHostObservadas = filasHost.length;

  const cruceRows = filasHost
    .map((row) => {
      const cruce = row.cruce;
      const estadoFila = cruce ? cruce.estado : Object.values(row.fuentes)[0]?.estado;
      const idArchivo = (row.fuentes.HA22 || row.fuentes.HA26 || row.fuentes.HA32)?.archivos?.[0];
      const accion = idArchivo != null
        ? `<button type="button" class="btn" onclick="abrirDetalle(${Number(idArchivo)},'conciliacion')">Ver evidencia</button>`
        : '—';
      const cuentaJs = JSON.stringify(row.cuenta);
      return `<tr data-cuenta="${esc(row.cuenta)}" data-estado="${esc(estadoFila || '')}">
        <td><a href="#" onclick="abrirDetalleCuentaCredibanco(${esc(cuentaJs)});return false;">${esc(row.cuenta)}</a></td>
        <td class="num">${celdaFuente(row.fuentes, 'HA22', 'debe')}</td>
        <td class="num">${celdaFuente(row.fuentes, 'HA22', 'haber')}</td>
        <td class="num">${celdaFuente(row.fuentes, 'HA22', 'neto_debe_menos_haber')}</td>
        <td class="num">${celdaFuente(row.fuentes, 'HA26', 'debe')}</td>
        <td class="num">${celdaFuente(row.fuentes, 'HA26', 'haber')}</td>
        <td class="num">${celdaFuente(row.fuentes, 'HA26', 'neto_debe_menos_haber')}</td>
        <td class="num">${celdaFuente(row.fuentes, 'HA32', 'debe')}</td>
        <td class="num">${celdaFuente(row.fuentes, 'HA32', 'haber')}</td>
        <td class="num">${celdaFuente(row.fuentes, 'HA32', 'neto_debe_menos_haber')}</td>
        <td>${cruce ? esc(cruce.id_regla) : '<span class="muted">Sin regla</span>'}</td>
        <td class="num">${cruce && cruce.valor_franquicia != null ? fmtMoney(cruce.valor_franquicia) : '—'}</td>
        <td class="num">${cruce && cruce.diferencia != null ? fmtMoney(cruce.diferencia) : '—'}</td>
        <td><span class="tag ${badgeFor(estadoFila)}" title="${esc(estadoFila || '')}">${esc(labelEstadoConciliacion(estadoFila))}</span>${cruce && cruce.diferencia != null && cruce.aprobada === false ? ' <span class="tag warn" title="La regla no tiene version+evidencia_aprobacion firmadas; este valor es un calculo provisional.">⚠ sin aprobar</span>' : ''}</td>
        <td>${accion}</td>
      </tr>`;
    })
    .join('');

  cont.innerHTML = `
    <div class="card section" id="trazabilidadHostCard">
      <div class="title">Cuentas Host observadas <span class="muted">(${filasHost.length})</span></div>
      <div class="toolbar">
        <input id="cruceQ" class="search" onkeyup="filterCruceRows()" placeholder="Buscar cuenta..." aria-label="Buscar cuenta Host">
        <select id="cruceSt" class="select" onchange="filterCruceRows()" aria-label="Filtrar por estado">
          <option value="">Todos los estados</option>
          <option value="PENDIENTE_HOMOLOGACION_NATURALEZA_Y_FUENTE">Pendiente homologación</option>
          <option value="PENDIENTE_APROBACION_REGLA">Pendiente aprobación regla</option>
          <option value="BLOQUEADO_SINTETICO">Bloqueado sintético</option>
          <option value="DATO_INCOMPLETO">Dato incompleto</option>
          <option value="COINCIDE">Coincide</option>
          <option value="CON_DIFERENCIA">Con diferencia</option>
        </select>
      </div>
      <div class="filterHint">Diagnóstico por cuenta Host, nunca homologación contable. HA22/HA26/HA32 no se suman entre sí. "Sin regla" = cuenta observada en Host sin regla de cruce aprobada todavía.</div>
      <div class="tableScroll"><table class="reconTable"><thead><tr>
        <th>Cuenta</th><th>HA22 Debe</th><th>HA22 Haber</th><th>HA22 Neto</th>
        <th>HA26 Debe</th><th>HA26 Haber</th><th>HA26 Neto</th>
        <th>HA32 Debe</th><th>HA32 Haber</th><th>HA32 Neto</th>
        <th>Regla</th><th>Valor Franquicia</th><th>Diferencia</th><th>Estado</th><th>Acción</th>
      </tr></thead><tbody id="cruceBody">${cruceRows || '<tr><td colspan="15" class="muted">Sin cuentas Host observadas.</td></tr>'}</tbody></table></div>
    </div>
    ${renderPlantillaMaestra(d.plantilla_maestra)}
    <div class="card section">
      <div class="title">Pendientes (${(d.pendientes || []).length})</div>
      <div class="tableScroll"><table><thead><tr><th>Código</th><th>Detalle</th></tr></thead>
      <tbody>${pendRows || '<tr><td colspan="2" class="muted">Sin pendientes.</td></tr>'}</tbody></table></div>
    </div>`;
  renderTablaResultado();
}

// ---- Plantilla Maestra (hoja PLANTILLA (2)) reproducida por el backend ----
// Cada bloque corresponde a un subtotal de la Plantilla (filas 42, 56, 98, 122).
// Las filas de captura manual se listan aparte: en Excel las llena Operaciones
// y aquí cuentan como vacías, igual que en los SUM de la Plantilla.
function badgeForPlantilla(estado) {
  const e = String(estado || '');
  if (e === 'CALCULADO') return 'ok';
  if (/^(SIN_DATO_EXCEL|VALOR_FIJO_EXCEL|CELDA_MANUAL_VACIA|SIN_MOVIMIENTO_HOST)/.test(e)) return 'info';
  return 'warn';
}

function renderPlantillaMaestra(p) {
  if (!p) return '';
  const bloques = (p.bloques || []).map((b) => {
    const filas = (b.filas || [])
      .map((f) => `<tr>
          <td class="num">${f.fila}</td>
          <td>${esc(f.cuenta)}</td>
          <td>${esc(f.concepto)}</td>
          <td class="num">${f.debito != null ? fmtMoney(f.debito) : '—'}</td>
          <td class="num">${f.credito != null ? fmtMoney(f.credito) : '—'}</td>
          <td><span class="tag ${badgeForPlantilla(f.estado)}" title="${esc(f.nota ? `${f.nota} · ${f.formula_excel}` : f.formula_excel || '')}">${esc(f.estado)}</span></td>
        </tr>`)
      .join('');
    const manuales = (b.filas_captura_manual || [])
      .map((m) => `<tr><td class="num">${m.fila}</td><td>${esc(m.cuenta)}</td><td>${esc(m.concepto)}</td></tr>`)
      .join('');
    const aviso = b.subtotal_completo
      ? ''
      : `<p class="filterHint">⚠ Subtotal parcial: las filas ${esc((b.filas_sin_valor || []).join(', '))} no tienen valor y no entran en la suma.</p>`;
    return `<details class="section">
        <summary style="cursor:pointer"><b>${esc(b.titulo)}</b> <span class="muted">· subtotal fila ${b.fila_subtotal}: Débito ${fmtMoney(b.subtotal_debito)} · Crédito ${fmtMoney(b.subtotal_credito)}</span></summary>
        <div class="tableScroll"><table class="reconTable"><thead><tr>
          <th>Fila</th><th>Cuenta</th><th>Concepto</th><th>Débito</th><th>Crédito</th><th>Estado</th>
        </tr></thead><tbody>${filas}
          <tr><td></td><td></td><td><b>Subtotal (fila ${b.fila_subtotal})</b></td><td class="num"><b>${fmtMoney(b.subtotal_debito)}</b></td><td class="num"><b>${fmtMoney(b.subtotal_credito)}</b></td><td></td></tr>
        </tbody></table></div>
        ${aviso}
        ${manuales ? `<details><summary style="cursor:pointer" class="muted">Filas de captura manual (${(b.filas_captura_manual || []).length})</summary>
          <div class="tableScroll"><table><thead><tr><th>Fila</th><th>Cuenta</th><th>Concepto</th></tr></thead><tbody>${manuales}</tbody></table></div></details>` : ''}
      </details>`;
  }).join('');
  const controles = Object.entries(p.controles || {})
    .map(([codigo, c]) => {
      const valor = c.valor != null ? fmtMoney(c.valor) : (c.debito != null ? `D ${fmtMoney(c.debito)} · C ${fmtMoney(c.credito)}` : '—');
      return `<tr><td>${esc(codigo)}</td><td class="num">${valor}</td><td>${c.estado ? `<span class="tag ${badgeForPlantilla(c.estado)}">${esc(c.estado)}</span>` : '—'}</td><td class="muted">${esc(c.nota || c.formula_excel || '')}</td></tr>`;
    })
    .join('');
  const avisos = (p.advertencias || []).map((a) => `<p class="filterHint">⚠ ${esc(a)}</p>`).join('');
  return `<div class="card section">
      <div class="title">Plantilla Maestra (diagnóstico) <span class="muted">· ${esc(p.estado || '')}</span></div>
      <p class="filterHint">Filas de la hoja PLANTILLA (2) con fuente en Carta, TOTALES (CAET/CANT) y td cuadre (DEPO + HA22), con las mismas fórmulas que la Excel. Pasa el cursor sobre el estado para ver la fórmula. Fuera de alcance: ${esc((p.fuera_de_alcance || []).join('; '))}.</p>
      ${avisos}
      ${bloques}
      <details class="section"><summary style="cursor:pointer"><b>Controles de la Plantilla</b></summary>
        <div class="tableScroll"><table><thead><tr><th>Control</th><th>Valor</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>${controles}</tbody></table></div>
      </details>
    </div>`;
}

// ---- Página "Plantilla Maestra": la hoja como en el Excel ----
// Una sola tabla en orden de fila (Fila, Cuenta, Concepto, Débito, Crédito),
// con encabezado y subtotal por bloque, las filas de captura manual en su
// lugar, los controles de la plantilla y la liquidación VISA. Sale de los
// mismos datos ya cargados (cierre-credibanco y conciliacion-visa).
const ESTADO_PLANTILLA_LABEL = {
  CALCULADO: 'Calculado',
  SIN_DATO_EXCEL: 'Sin dato',
  VALOR_FIJO_EXCEL: 'Valor fijo',
  CELDA_MANUAL_VACIA: 'Captura manual',
  SIN_MOVIMIENTO_HOST: 'Sin movimiento Host',
};

function tagPlantilla(estado, titulo = '') {
  return `<span class="tag ${badgeForPlantilla(estado)}" title="${esc(titulo || estado || '')}">${esc(ESTADO_PLANTILLA_LABEL[estado] || estado || '—')}</span>`;
}

// La página sigue el formato de la hoja que diligencia Operaciones
// (PLANTILLA_MAESTRA_LAYOUT, generado del Excel del 13-nov): mismas filas,
// mismo orden, secciones y subtotales al pie con las fórmulas del Excel.
// Cada fila calculada por el motor se ubica por cuenta + concepto (no por
// número de fila, porque la plantilla del motor es una versión anterior).
const normConceptoPlantilla = (s) => String(s || '').replace(/\s+/g, ' ').trim().toUpperCase();

// Controles que la hoja calcula al lado de un subtotal.
const CONTROL_SUBTOTAL_PLANTILLA = {
  42: ['J40_VALIDACION_CANJE_ENVIADO', 'J40 · Validación canje enviado (debe dar 0)'],
  98: ['J90_VALIDACION_CANJE_RECIBIDO_CARTA', 'J90 · Validación canje recibido vs Carta (debe dar 0)'],
  123: ['H103_VALIDACION_DEPOSITOS', 'H103 · Validación depósitos'],
};

function ubicarFilasMotor(p, layout) {
  const lineas = layout.filter((x) => x.tipo === 'linea');
  const usadas = new Set();
  const porFila = new Map();
  const sinUbicar = [];
  for (const f of (p.bloques || []).flatMap((b) => b.filas || [])) {
    // Una misma cuenta + concepto puede repetirse en otra sección (p. ej. filas
    // 25 y 89): se toma la coincidencia más cercana a la fila del motor.
    const destino = lineas
      .filter((x) => !usadas.has(x.fila) && (x.cuenta || '') === (f.cuenta || '')
        && normConceptoPlantilla(x.concepto) === normConceptoPlantilla(f.concepto))
      .sort((x, y) => Math.abs(x.fila - f.fila) - Math.abs(y.fila - f.fila))[0];
    if (destino) { usadas.add(destino.fila); porFila.set(destino.fila, f); } else sinUbicar.push(f);
  }
  return { porFila, sinUbicar };
}

// Evalúa las fórmulas de subtotal del Excel: SUM(F6:F41), +F98+F56+F42, +F211-G211.
function evaluarFormulaPlantilla(formula, valores) {
  if (!formula) return null;
  let expr = String(formula).replace(/^=/, '');
  expr = expr.replace(/SUM\(([FG])(\d+):\1(\d+)\)/g, (_, col, a, b) => {
    let t = 0;
    for (let r = Number(a); r <= Number(b); r += 1) t += valores.get(r)?.[col] || 0;
    return `+${t}`;
  });
  let total = 0;
  const re = /([+-]?)\s*(?:([FG])(\d+)|(-?\d+(?:\.\d+)?))/g;
  let m;
  while ((m = re.exec(expr)) !== null) {
    const v = m[2] ? (valores.get(Number(m[3]))?.[m[2]] || 0) : Number(m[4]);
    total += m[1] === '-' ? -v : v;
  }
  return total;
}

function construirPlantillaExcel(p, vd) {
  const layout = PLANTILLA_MAESTRA_LAYOUT.filas;
  const { porFila, sinUbicar } = ubicarFilasMotor(p, layout);
  const valores = new Map();
  const f5 = (vd?.liquidacion?.celdas || {}).F5;
  const filas = [];
  for (const x of layout) {
    const fila = { ...x };
    if (x.tipo === 'linea') {
      const m = porFila.get(x.fila);
      if (m) {
        Object.assign(fila, { debito: m.debito, credito: m.credito, fuente: m.fuente, estado: m.estado, formula: m.formula_excel, notaMotor: m.nota });
      } else if (x.fila === 5 && f5) {
        Object.assign(fila, { debito: f5.valor, credito: null, fuente: 'VISA', estado: f5.estado, formula: f5.formula });
      }
      valores.set(x.fila, { F: Number(fila.debito || 0), G: Number(fila.credito || 0) });
    } else if (x.tipo === 'subtotal' || x.tipo === 'total') {
      fila.debito = evaluarFormulaPlantilla(x.fF, valores);
      fila.credito = evaluarFormulaPlantilla(x.fG, valores);
      valores.set(x.fila, { F: fila.debito, G: fila.credito });
    } else if (x.tipo === 'diferencia') {
      fila.diferencia = evaluarFormulaPlantilla(x.fG, valores);
    }
    filas.push(fila);
  }
  return { filas, sinUbicar };
}

function filaPlantillaExcelHtml(f, p) {
  if (f.tipo === 'titulo' || f.tipo === 'seccion') {
    return `<tr><td colspan="8" style="background:#eef6fa"><b>${esc(f.concepto)}</b></td></tr>`;
  }
  if (f.tipo === 'diferencia') {
    const ok = Math.abs(f.diferencia || 0) < 1;
    return `<tr><td class="num">${f.fila}</td><td></td><td><b>DIFERENCIA</b> <small class="muted">(F211 − G211)</small></td><td></td><td></td>
      <td class="num"><b>${money(f.diferencia)}</b></td><td></td><td><span class="tag ${ok ? 'ok' : 'warn'}">${ok ? 'Cuadra' : 'No cuadra'}</span></td></tr>`;
  }
  if (f.tipo === 'subtotal' || f.tipo === 'total') {
    const [cod, etiqueta] = CONTROL_SUBTOTAL_PLANTILLA[f.fila] || [];
    const c = cod ? (p.controles || {})[cod] : null;
    const control = c
      ? `<tr><td></td><td></td><td><i>${esc(etiqueta)}</i></td><td></td><td class="num" colspan="2"><i>${money(c.valor)}</i></td><td></td><td>${c.estado ? tagPlantilla(c.estado, c.formula_excel) : ''}</td></tr>`
      : '';
    const estilo = f.tipo === 'total' ? ' style="background:#f5f9ff"' : '';
    return `<tr${estilo}><td class="num"><b>${f.fila}</b></td><td></td><td><b>${esc(f.concepto)}</b> <small class="muted" title="Fórmula del Excel">${esc(f.fF || '')}</small></td><td></td>
      <td class="num"><b>${money(f.debito)}</b></td><td class="num"><b>${money(f.credito)}</b></td><td></td><td></td></tr>${control}`;
  }
  const conValor = f.fuente != null;
  const estado = conValor
    ? (f.fuente === 'VISA' ? tagVisa(f.estado) : tagPlantilla(f.estado, f.notaMotor ? `${f.notaMotor} · ${f.formula || ''}` : f.formula))
    : `<span class="tag info" title="La analista la diligencia en el Excel; el sistema todavía no tiene la fuente.">Sin fuente automática</span>`;
  return `<tr${conValor ? '' : ' class="muted"'}><td class="num">${f.fila}</td><td>${esc(f.cuenta || '')}</td>
    <td${f.nota ? ` title="${esc(f.nota)}"` : ''}>${esc(f.concepto)}${f.nota ? ' <small class="muted">ⓘ</small>' : ''}</td><td>${esc(f.nit || '')}</td>
    <td class="num">${conValor ? money(f.debito) : '—'}</td><td class="num">${conValor ? money(f.credito) : '—'}</td><td>${esc(f.fuente || '')}</td><td>${estado}</td></tr>`;
}

function liquidacionVisaHtml(vd) {
  if (!vd) return '<div class="card section"><h3>Liquidación VISA</h3><p class="muted">Sin datos VISA para esta jornada.</p></div>';
  const liq = vd.liquidacion || {};
  const celdas = Object.entries(liq.celdas || {}).map(([celda, c]) => `<tr>
      <td>${esc(celda)}</td><td>${esc(c.etiqueta || '')}${c.plantilla ? `<br><small class="muted">Plantilla: ${esc(c.plantilla)}</small>` : ''}</td>
      <td><code>${esc(c.formula || '')}</code></td>
      <td class="num">${c.valor != null ? numVisa(c.valor, celda === 'M169' ? 4 : 2) : '—'}${c.unidad ? ` <small class="muted">${esc(c.unidad)}</small>` : ''}</td>
      <td>${tagVisa(c.estado)}</td></tr>`).join('');
  const asiento = (liq.asiento || []).map((a) => `<tr><td class="num">${a.fila}</td><td>${esc(a.celda)}</td><td>${esc(a.cuenta || '—')}</td>
      <td>${esc(a.naturaleza_plantilla || '')}</td><td class="num">${money(a.valor)}</td><td>${esc(a.naturaleza || '—')}</td></tr>`).join('');
  const val = liq.validacion_canje_internacional || {};
  return `<div class="card section">
      <h3>Liquidación VISA (fila 5 y filas 161-181)</h3>
      <p class="friendlyNote">Validación canje internacional ${esc(val.formula || 'L163')}: <b>${money(val.valor)}</b> ${tagVisa(val.estado)}. Las celdas de captura manual (TRM, correo, pdf…) se confirman en "TRM de la jornada".</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Celda</th><th>Concepto</th><th>Fórmula</th><th>Valor</th><th>Estado</th></tr></thead><tbody>${celdas}</tbody></table></div>
      <h3 class="section">Asiento (columna M)</h3>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fila</th><th>Celda</th><th>Cuenta</th><th>Naturaleza plantilla</th><th>Valor (COP)</th><th>Naturaleza</th></tr></thead><tbody>${asiento}</tbody></table></div>
    </div>`;
}

function renderPaginaPlantillaMaestra() {
  const cont = el('plantillaMaestraContent');
  if (!cont) return;
  const d = ultimoCierreCredibanco;
  const p = d?.plantilla_maestra;
  if (!p) {
    cont.innerHTML = '<div class="emptyDetail">No hay Plantilla Maestra calculada para esta jornada (falta el diagnóstico Credibanco).</div>';
    return;
  }
  const { filas, sinUbicar } = construirPlantillaExcel(p, ultimaConciliacionVisa);
  const total = filas.find((f) => f.tipo === 'total') || {};
  const dif = filas.find((f) => f.tipo === 'diferencia') || {};
  const lineas = filas.filter((f) => f.tipo === 'linea');
  const conValor = lineas.filter((f) => f.fuente != null).length;
  const controles = Object.entries(p.controles || {}).map(([codigo, c]) => {
    const valor = c.valor != null ? money(c.valor) : (c.debito != null ? `D ${money(c.debito)} · C ${money(c.credito)}` : '—');
    return `<tr><td>${esc(codigo.replaceAll('_', ' '))}</td><td class="num">${valor}</td><td>${c.estado ? tagPlantilla(c.estado) : '—'}</td><td class="muted">${esc(c.nota || '')}${c.nota && c.formula_excel ? '<br>' : ''}<code>${esc(c.formula_excel || '')}</code></td></tr>`;
  }).join('');
  const sinUbicarHtml = sinUbicar.length
    ? `<div class="card section"><h3>Filas del motor que no están en la plantilla actual</h3>
        <p class="filterHint">Vienen de la versión anterior de la plantilla y no tienen fila equivalente en el Excel vigente; no entran en los totales.</p>
        <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fila (versión anterior)</th><th>Cuenta</th><th>Concepto</th><th>Débito</th><th>Crédito</th></tr></thead>
        <tbody>${sinUbicar.map((f) => `<tr><td class="num">${f.fila}</td><td>${esc(f.cuenta)}</td><td>${esc(f.concepto)}</td><td class="num">${money(f.debito)}</td><td class="num">${money(f.credito)}</td></tr>`).join('')}</tbody></table></div></div>`
    : '';
  cont.innerHTML = `
    <div class="head"><div><h1>Plantilla Maestra · Credibanco</h1><p>Fecha contable ${esc(d.fecha_contable || fechaConciliacion || '—')} · Jornada ${Number(d.id_jornada)} · Formato: ${esc(PLANTILLA_MAESTRA_LAYOUT.fuente)}</p></div></div>
    <div class="flow summaryFlow">
      <div class="fc"><small>TOTAL DÉBITO (F211)</small><b>${money(total.debito)}</b></div>
      <div class="fc"><small>TOTAL CRÉDITO (G211)</small><b>${money(total.credito)}</b></div>
      <div class="fc"><small>DIFERENCIA (F212)</small><b>${money(dif.diferencia)}</b></div>
      <div class="fc"><small>LÍNEAS CON VALOR AUTOMÁTICO</small><b>${conValor} de ${lineas.length}</b></div>
    </div>
    <p class="friendlyNote">Misma hoja que diligencia Operaciones: filas, secciones y subtotales en el mismo orden, con las fórmulas del Excel. Los valores que el sistema ya calcula (Carta de Compensación, TOTALES CAET/CANT, td cuadre DEPO + HA22 y la compensación VISA) se ubican por cuenta y concepto; el resto aparece como <b>Sin fuente automática</b> y cuenta como 0 en los subtotales, por eso la diferencia todavía no es la del cuadre real. Pasa el cursor sobre ⓘ para ver de dónde sale cada fila en el Excel.</p>
    <div class="card section" style="padding:0"><div class="tableScroll"><table class="reconTable"><thead><tr>
      <th>Fila</th><th>Cuenta</th><th>Concepto</th><th>NIT</th><th>Débito</th><th>Crédito</th><th>Fuente</th><th>Estado</th>
    </tr></thead><tbody>${filas.map((f) => filaPlantillaExcelHtml(f, p)).join('')}</tbody></table></div></div>
    ${sinUbicarHtml}
    <div class="card section"><h3>Controles de la Plantilla</h3>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Control</th><th>Valor</th><th>Estado</th><th>Detalle / fórmula</th></tr></thead><tbody>${controles || '<tr><td colspan="4" class="muted">Sin controles.</td></tr>'}</tbody></table></div>
    </div>
    ${liquidacionVisaHtml(ultimaConciliacionVisa)}`;
}

function abrirPlantillaMaestra() {
  detalleCuentaOrigenScrollY = window.scrollY;
  document.querySelectorAll('.panel').forEach((x) => x.classList.remove('active'));
  el('plantillaMaestraPanel').classList.add('active');
  window.scrollTo(0, 0);
  renderPaginaPlantillaMaestra();
}
el('btnVolverDesdePlantilla')?.addEventListener('click', volverAConciliacion);

// ---- Conciliación Redeban: cuadre con la hoja ESTRUCTURA (ver cierre-redeban) ----
// Cada código de operación PMD se asigna a una cuenta con la homologación de la
// plantilla de cuadre Redeban; cada cuenta se compara contra HA22, HA26 y HA32
// por separado (nunca se suman). "*" marca las fuentes que se consultan para la cuenta.
let ultimoCierreRedeban = null;
let redebanCuentasPagina = 0;
let redebanValidadorPagina = 0;
let redebanCuentaSel = null;
const REDEBAN_PAGE_SIZE = 10;
const FUENTES_REDEBAN = ['HA22', 'HA26', 'HA32'];

const ESTADO_REDEBAN_LABEL = {
  CONCILIADO: 'Conciliado',
  CON_DIFERENCIA: 'Con diferencia',
  PENDIENTE_CONCILIACION: 'Pendiente (falta fuente Host)',
  SIN_INFORMACION: 'Sin información PMD',
  SIN_CONSULTA_HOST: 'Sin consulta Host definida',
  CUADRA: 'Cuadra',
  DESCUADRE: 'Descuadre',
  SIN_FILAS_ESTRUCTURA: 'Sin filas en ESTRUCTURA',
};

function badgeForRedeban(estado) {
  const e = String(estado || '');
  if (/^(CONCILIADO|CUADRA|COINCIDE|CALCULADO)$/.test(e)) return 'ok';
  if (/^(SIN_CONSULTA_HOST|SIN_MOVIMIENTO)/.test(e)) return 'info';
  return 'warn';
}

function tagRedeban(estado) {
  return `<span class="tag ${badgeForRedeban(estado)}" title="${esc(estado || '')}">${esc(ESTADO_REDEBAN_LABEL[estado] || estado || '—')}</span>`;
}

function paginarRedeban(lista, pagina) {
  const total = lista.length;
  const paginas = Math.max(1, Math.ceil(total / REDEBAN_PAGE_SIZE));
  const p = Math.min(Math.max(pagina, 0), paginas - 1);
  const inicio = p * REDEBAN_PAGE_SIZE;
  return { p, paginas, total, inicio, items: lista.slice(inicio, inicio + REDEBAN_PAGE_SIZE) };
}

function pagerRedeban(pg, etiqueta, idPrev, idNext) {
  return `<div class="detailPager">
      <span class="pagerInfo">${etiqueta} ${pg.total ? pg.inicio + 1 : 0}-${pg.inicio + pg.items.length} de ${pg.total} · ${REDEBAN_PAGE_SIZE} por página</span>
      <div class="pager">
        <button class="btn" id="${idPrev}" ${pg.p === 0 ? 'disabled' : ''}>‹ Anterior</button>
        <span class="muted">Página ${pg.p + 1} de ${pg.paginas}</span>
        <button class="btn" id="${idNext}" ${pg.p >= pg.paginas - 1 ? 'disabled' : ''}>Siguiente ›</button>
      </div>
    </div>`;
}

const montoRedeban = (v) => (v != null ? fmtMoney(v) : '—');

function alertasRedeban(d) {
  const bloques = [
    ['Operaciones PMD sin fila en ESTRUCTURA', d.codigos_pmd_sin_estructura, ['Código PMD', 'Producto / servicio', 'Débito neto', 'Crédito neto'],
      (x) => [esc(x.codigo_pmd), esc(x.producto_servicio || ''), montoRedeban(x.debito_neto), montoRedeban(x.credito_neto)]],
    ['Operaciones con cobertura parcial (falta algún tipo A/B/C)', d.codigos_pmd_cobertura_parcial, ['Código PMD', 'Tipos en ESTRUCTURA', 'Neto PMD', 'Neto ESTRUCTURA', 'Diferencia'],
      (x) => [esc(x.codigo_pmd), esc((x.tipos_en_estructura || []).join(', ')), montoRedeban(x.neto_pmd), montoRedeban(x.neto_estructura), montoRedeban(x.diferencia)]],
    ['Movimientos PMD en filas sin cuenta contable', d.movimientos_pmd_sin_cuenta, ['Fila', 'Código PMD', 'Tipo', 'Neto', 'Estado'],
      (x) => [x.fila, esc(x.codigo_pmd), esc(x.tipo), montoRedeban(x.neto), esc(x.estado)]],
    ['Filas de ESTRUCTURA cuyo tipo no coincide con sus índices', d.filas_tipo_inconsistente, ['Fila', 'Cuenta', 'Código PMD', 'Tipo', 'Neto'],
      (x) => [x.fila, esc(x.cuenta), esc(x.codigo_pmd), esc(x.tipo), montoRedeban(x.neto)]],
  ].filter(([, lista]) => (lista || []).length);
  const avisos = (d.advertencias || []).map((a) => `<p class="filterHint">⚠ ${esc(a)}</p>`).join('');
  if (!bloques.length && !avisos) return '';
  const detalles = bloques.map(([titulo, lista, cabeceras, fila]) => `<details class="section">
      <summary style="cursor:pointer"><b>${esc(titulo)}</b> <span class="tag warn">${lista.length}</span></summary>
      <div class="tableScroll"><table class="reconTable"><thead><tr>${cabeceras.map((c) => `<th>${c}</th>`).join('')}</tr></thead>
      <tbody>${lista.map((x) => `<tr>${fila(x).map((v) => `<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    </details>`).join('');
  return `<div class="card section"><div class="title">Alertas del cuadre</div>${avisos}${detalles}</div>`;
}

async function cargarCierreRedeban() {
  const cont = el('cierreRedebanContent');
  if (!cont) return;
  ultimoCierreRedeban = null;
  if (!idJornadaConciliacion) {
    cont.innerHTML = '<div class="emptyDetail">Selecciona una fecha contable para ver el cuadre Redeban de esta jornada.</div>';
    return;
  }
  cont.innerHTML = '<div class="emptyDetail">Cargando cuadre Redeban…</div>';
  let r;
  try {
    r = await apiFetch(`${API}/jornadas/${idJornadaConciliacion}/cierre-redeban`);
  } catch (e) {
    cont.innerHTML = `<div class="emptyDetail">No se pudo cargar el cuadre Redeban: ${esc(e.message || e)}</div>`;
    return;
  }
  if (!r.ok) {
    cont.innerHTML = `<div class="emptyDetail">No se pudo cargar el cuadre Redeban (HTTP ${r.status}).</div>`;
    return;
  }
  const d = await r.json();
  ultimoCierreRedeban = d;
  redebanCuentasPagina = 0;
  redebanValidadorPagina = 0;
  redebanCuentaSel = null;

  if (d.estado === 'INSUMO_PMD_FALTANTE') {
    cont.innerHTML = '<div class="explain"><b>Sin archivo PMD procesado.</b> Carga el insumo PMD de esta jornada en Insumos para ver el cuadre Redeban.</div>';
    return;
  }

  const res = d.resumen || {};
  const cat = d.catalogo || {};
  cont.innerHTML = `
    <div class="explain">Homologación PMD → cuenta: hoja ESTRUCTURA de <b>${esc(cat.archivo || '')}</b> (${cat.filas ?? 0} filas, ${esc(cat.version || '')}). Fuentes Host procesadas: ${esc((d.fuentes_host_procesadas || []).join(', ') || 'ninguna')}. Cada cuenta se compara contra HA22, HA26 y HA32 por separado: diferencia = neto PMD − (debe − haber). <b>*</b> marca la fuente que se consulta para esa cuenta.</div>
    <div class="flow summaryFlow">
      <div class="fc"><small>CUENTAS</small><b>${res.cuentas ?? 0}</b></div>
      <div class="fc"><small>CONCILIADAS</small><b>${res.CONCILIADO ?? 0}</b></div>
      <div class="fc"><small>CON DIFERENCIA</small><b>${res.CON_DIFERENCIA ?? 0}</b></div>
      <div class="fc"><small>PENDIENTES</small><b>${res.PENDIENTE_CONCILIACION ?? 0}</b></div>
      <div class="fc"><small>SIN CONSULTA HOST</small><b>${res.SIN_CONSULTA_HOST ?? 0}</b></div>
      <div class="fc"><small>SIN INFORMACIÓN</small><b>${res.SIN_INFORMACION ?? 0}</b></div>
    </div>
    ${alertasRedeban(d)}
    <div class="card section">
      <div class="title">Cuadre por cuenta <span class="muted">(clic en la cuenta para ver sus operaciones)</span></div>
      <div id="redebanCuentasWrap"></div>
    </div>
    <div id="redebanOperacionesWrap"></div>
    <div class="card section">
      <div class="title">VALIDADOR · ESTRUCTURA vs PMD por nivel 1</div>
      <div id="redebanValidadorWrap"></div>
      <p class="filterHint">Control = neto de ESTRUCTURA + total PMD del nivel. Debe dar 0: si no, hay operaciones PMD que ESTRUCTURA no asigna completas (ver Alertas).</p>
    </div>`;
  renderRedebanCuentas();
  renderRedebanValidador();
}

function celdasHostRedeban(c) {
  return FUENTES_REDEBAN.map((f) => {
    const h = (c.host || {})[f] || {};
    const marca = h.obligatoria ? ' <b title="Fuente que se consulta para esta cuenta">*</b>' : '';
    return `<td class="num" title="${esc(h.estado || '')}">${montoRedeban(h.neto)}${marca}</td><td class="num">${montoRedeban(h.diferencia)}</td>`;
  }).join('');
}

function renderRedebanCuentas() {
  const wrap = el('redebanCuentasWrap');
  const d = ultimoCierreRedeban;
  if (!wrap || !d) return;
  const pg = paginarRedeban(d.cuentas || [], redebanCuentasPagina);
  redebanCuentasPagina = pg.p;
  const filas = pg.items.map((c) => `<tr>
      <td><a href="#" class="redebanCuentaLink" data-cuenta="${esc(c.cuenta)}">${esc(c.cuenta)}</a></td>
      <td class="num">${montoRedeban(c.neto_pmd)}</td>
      ${celdasHostRedeban(c)}
      <td>${tagRedeban(c.estado)}</td>
    </tr>`).join('');
  wrap.innerHTML = `
    <div class="tableScroll"><table class="reconTable"><thead><tr>
      <th>Cuenta</th><th>Neto PMD</th><th>HA22 Neto</th><th>HA22 Dif.</th><th>HA26 Neto</th><th>HA26 Dif.</th><th>HA32 Neto</th><th>HA32 Dif.</th><th>Estado</th>
    </tr></thead><tbody>${filas || '<tr><td colspan="9" class="muted">Sin cuentas en ESTRUCTURA.</td></tr>'}</tbody></table></div>
    ${pagerRedeban(pg, 'Cuentas', 'btnRedebanCuentasAnterior', 'btnRedebanCuentasSiguiente')}`;
  el('btnRedebanCuentasAnterior')?.addEventListener('click', () => { redebanCuentasPagina -= 1; renderRedebanCuentas(); });
  el('btnRedebanCuentasSiguiente')?.addEventListener('click', () => { redebanCuentasPagina += 1; renderRedebanCuentas(); });
  wrap.querySelectorAll('.redebanCuentaLink').forEach((a) => a.addEventListener('click', (e) => {
    e.preventDefault();
    redebanCuentaSel = a.dataset.cuenta;
    renderRedebanOperaciones();
  }));
}

function renderRedebanOperaciones() {
  const wrap = el('redebanOperacionesWrap');
  const d = ultimoCierreRedeban;
  if (!wrap || !d) return;
  const c = (d.cuentas || []).find((x) => x.cuenta === redebanCuentaSel);
  if (!c) { wrap.innerHTML = ''; return; }
  const ops = (c.operaciones || []).map((o) => `<tr>
      <td class="num">${o.fila}</td><td>${esc(o.codigo_pmd)}</td><td>${esc(o.nombre_operacion || '')}</td><td>${esc(o.tipo)}</td>
      <td class="num">${montoRedeban(o.debito)}</td><td class="num">${montoRedeban(o.credito)}</td><td class="num">${montoRedeban(o.neto)}</td>
      <td><span class="tag ${badgeForRedeban(o.estado)}">${esc(o.estado)}</span></td></tr>`).join('');
  const host = FUENTES_REDEBAN.map((f) => {
    const h = (c.host || {})[f] || {};
    return `<tr><td>${f}${h.obligatoria ? ' *' : ''}</td><td class="num">${h.movimientos ?? '—'}</td><td class="num">${montoRedeban(h.debe)}</td><td class="num">${montoRedeban(h.haber)}</td><td class="num">${montoRedeban(h.neto)}</td><td class="num">${montoRedeban(h.diferencia)}</td><td><span class="tag ${badgeForRedeban(h.estado)}">${esc(h.estado || '—')}</span></td></tr>`;
  }).join('');
  const manuales = (c.filas_captura_manual || []).length
    ? `<p class="filterHint">Filas de captura manual en ESTRUCTURA (no entran en el neto): ${c.filas_captura_manual.join(', ')}.</p>` : '';
  wrap.innerHTML = `<div class="card section">
      <div class="title">Cuenta ${esc(c.cuenta)} · ${tagRedeban(c.estado)} <button type="button" class="btn" id="btnCerrarOperacionesRedeban" style="float:right">Cerrar</button></div>
      <h3>A. Host (fuentes separadas)</h3>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fuente</th><th>Movimientos</th><th>Debe</th><th>Haber</th><th>Neto</th><th>Diferencia</th><th>Estado</th></tr></thead><tbody>${host}</tbody></table></div>
      <h3>B. Operaciones PMD asignadas (${(c.operaciones || []).length})</h3>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fila</th><th>Código PMD</th><th>Operación</th><th>Tipo</th><th>Débito (N)</th><th>Crédito (O)</th><th>Neto (P)</th><th>Estado</th></tr></thead>
      <tbody>${ops || '<tr><td colspan="8" class="muted">Sin movimiento PMD para esta cuenta en la jornada.</td></tr>'}</tbody></table></div>
      ${manuales}
    </div>`;
  el('btnCerrarOperacionesRedeban')?.addEventListener('click', () => { redebanCuentaSel = null; renderRedebanOperaciones(); });
  wrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderRedebanValidador() {
  const wrap = el('redebanValidadorWrap');
  const d = ultimoCierreRedeban;
  if (!wrap || !d) return;
  const pg = paginarRedeban(d.validador || [], redebanValidadorPagina);
  redebanValidadorPagina = pg.p;
  const filas = pg.items.map((v) => `<tr>
      <td>${esc(v.nivel_1)}</td><td class="num">${v.filas_estructura}</td>
      <td class="num">${montoRedeban(v.neto_estructura)}</td><td class="num">${montoRedeban(v.total_pmd)}</td>
      <td class="num">${montoRedeban(v.control)}</td><td>${tagRedeban(v.estado)}</td></tr>`).join('');
  wrap.innerHTML = `
    <div class="tableScroll"><table class="reconTable"><thead><tr>
      <th>Nivel 1</th><th>Filas ESTRUCTURA</th><th>Neto ESTRUCTURA</th><th>Total PMD</th><th>Control</th><th>Estado</th>
    </tr></thead><tbody>${filas || '<tr><td colspan="6" class="muted">Sin niveles.</td></tr>'}</tbody></table></div>
    ${pagerRedeban(pg, 'Niveles', 'btnRedebanValidadorAnterior', 'btnRedebanValidadorSiguiente')}`;
  el('btnRedebanValidadorAnterior')?.addEventListener('click', () => { redebanValidadorPagina -= 1; renderRedebanValidador(); });
  el('btnRedebanValidadorSiguiente')?.addEventListener('click', () => { redebanValidadorPagina += 1; renderRedebanValidador(); });
}

// ---- Conciliación VISA Internacional: liquidación de la Plantilla Maestra (ver conciliacion-visa) ----
// Fila 5 y filas 161-181 de la Plantilla: la TRM, el valor del pdf, el total del
// correo, etc. se digitan a mano (aquí se capturan y quedan versionados); el resto
// son las mismas fórmulas. El asiento resultante se compara contra Host por cuenta
// y fuente, sin sumar fuentes.
let ultimaConciliacionVisa = null;

const ESTADO_VISA_LABEL = {
  LIQUIDACION_CALCULADA: 'Liquidación calculada',
  CAPTURA_PENDIENTE: 'Captura pendiente',
  COINCIDE: 'Coincide',
  CON_DIFERENCIA: 'Con diferencia',
  SIN_LINEA_ISS: 'Sin línea en el PDF',
  INSUMO_FALTANTE: 'Insumo faltante',
  DATO_INCOMPLETO: 'Dato incompleto',
  CUADRA: 'Cuadra',
  SIN_CAPTURA_CARTA: 'Falta capturar carta (L162)',
  FALTA_TRM: 'Falta TRM',
  CAPTURADO: 'Capturado',
  SIN_CAPTURA: 'Sin captura (vale 0)',
  CALCULADO: 'Calculado',
  ...ESTADO_REDEBAN_LABEL,
};

function tagVisa(estado) {
  const e = String(estado || '');
  const tipo = /^(CONCILIADO|CUADRA|COINCIDE|CALCULADO|CAPTURADO|LIQUIDACION_CALCULADA)$/.test(e) ? 'ok'
    : /^(SIN_CONSULTA_HOST|SIN_MOVIMIENTO|SIN_CAPTURA$)/.test(e) ? 'info' : 'warn';
  return `<span class="tag ${tipo}" title="${esc(e)}">${esc(ESTADO_VISA_LABEL[e] || e || '—')}</span>`;
}

function numVisa(v, decimales = 2) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  return n.toLocaleString('es-CO', { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

// Referencias de los insumos para ayudar a digitar cada celda; nunca se copian solas.
// Guía por campo: de dónde sale el valor, cómo va el signo y un ejemplo.
// Los signos siguen la convención de la columna M de la plantilla
// (positivo = débito, negativo = crédito); pendientes de confirmar con Operaciones.
const AYUDA_CAPTURA_VISA = {
  M169: { donde: 'TRM que viene en el correo de VISA del día.', ejemplo: '4012.3456', signo: 'siempre positiva, hasta 4 decimales' },
  L170: { donde: 'Neto del PDF International SS para BBVA Colombia (FTSRE 1000804671).', ejemplo: '363512.54', signo: 'positivo si VISA abona a BBVA (CR), negativo si cobra (DB)' },
  L169: { donde: 'Total en USD del correo de VISA.', ejemplo: '0.00' },
  L172: { donde: 'Valor TII del archivo GOF, en USD.', ejemplo: '0.00' },
  N179: { donde: 'Controversia (dispute) en USD del correo; cuenta 196095001815.', ejemplo: '223.56' },
  N180: { donde: 'Segunda controversia (dispute) en USD, si la hay; cuenta 196095001815.', ejemplo: '15.52' },
  M177: { donde: 'Valor en pesos de la cuenta 196095001829.', ejemplo: '-1458000000', signo: 'negativo si en la plantilla va a crédito' },
  L162: { donde: 'Valor en pesos de la carta (canje internacional).', ejemplo: '0.00' },
};

function referenciaCapturaVisa(campo, d) {
  if (campo === 'L170') {
    const iss = (d.iss || []).map((f) => `${esc(f.ftsre)} ${esc(f.nombre || '')}: ${numVisa(f.monto_neto)} ${esc(f.naturaleza || '')}`);
    const vss = ((d.vss || {}).liquidaciones || []).map((l) => `VSS-115 ${esc(l.entidad || '')}: ${numVisa(l.neto)}`);
    return [...iss, ...vss].join('<br>') || '—';
  }
  if (campo === 'N179' || campo === 'N180') {
    const disputas = ((d.vss || {}).vss120 || []).filter((x) => /^DISPUTE/.test(x.concepto || ''));
    return disputas.map((x) => `${esc(x.concepto)} (${esc(x.moneda_clearing || '')}): ${numVisa(x.clearing)}`).join('<br>') || '—';
  }
  return '';
}

async function cargarConciliacionVisa() {
  const cont = el('conciliacionVisaContent');
  if (!cont) return;
  ultimaConciliacionVisa = null;
  if (!idJornadaConciliacion) {
    cont.innerHTML = '<div class="emptyDetail">Selecciona una fecha contable para ver la conciliación VISA Internacional de esta jornada.</div>';
    return;
  }
  cont.innerHTML = '<div class="emptyDetail">Cargando conciliación VISA Internacional…</div>';
  let r;
  try {
    r = await apiFetch(`${API}/jornadas/${idJornadaConciliacion}/conciliacion-visa`);
  } catch (e) {
    cont.innerHTML = `<div class="emptyDetail">No se pudo cargar la conciliación VISA Internacional: ${esc(e.message || e)}</div>`;
    return;
  }
  if (!r.ok) {
    cont.innerHTML = `<div class="emptyDetail">No se pudo cargar la conciliación VISA Internacional (HTTP ${r.status}).</div>`;
    return;
  }
  ultimaConciliacionVisa = await r.json();
  renderConciliacionVisa();
}

function renderConciliacionVisa(mensaje = '') {
  const cont = el('conciliacionVisaContent');
  const d = ultimaConciliacionVisa;
  if (!cont || !d) return;
  const liq = d.liquidacion || {};
  const celdas = liq.celdas || {};
  const res = d.resumen || {};
  const valor = (c) => (celdas[c] || {}).valor;

  const controles = (d.controles || []).map((c) => `<tr>
      <td>${esc(c.entidad || '—')}</td><td class="num">${numVisa(c.vss)}</td><td class="num">${numVisa(c.iss)}</td>
      <td class="num">${numVisa(c.diferencia)}</td><td>${tagVisa(c.estado)}</td><td>${esc(c.detalle || '')}</td></tr>`).join('');

  const camposCaptura = d.campos_captura || [];
  const faltantes = camposCaptura.filter((f) => f.requerido && (celdas[f.campo] || {}).valor == null);
  const captura = camposCaptura.map((f) => {
    const c = celdas[f.campo] || {};
    const ayuda = AYUDA_CAPTURA_VISA[f.campo] || {};
    const capturado = c.valor != null;
    const falta = f.requerido && !capturado;
    const vigente = capturado
      ? `${numVisa(c.valor, f.decimales)}<br><small class="muted">v${c.version ?? '?'} · ${esc(c.usuario || '')}</small>`
      : '<span class="muted">—</span>';
    const estado = capturado ? '<span class="tag ok">Capturado</span>'
      : falta ? '<span class="tag bad">Debes llenarlo</span>'
        : '<span class="tag info">Opcional · vale 0</span>';
    const placeholder = capturado ? 'Cambiar valor' : (ayuda.ejemplo ? `ej. ${ayuda.ejemplo}` : 'Escribe el valor');
    const estiloFila = falta ? ' style="background:var(--rb)"' : '';
    const estiloInput = falta ? 'width:9rem;border:2px solid var(--red)' : 'width:9rem';
    return `<tr${estiloFila}>
      <td><b>${esc(f.campo)}</b></td>
      <td>${esc(f.etiqueta)}${f.requerido ? ' <b style="color:var(--red)" title="Obligatorio para calcular">*</b>' : ''}<br><small class="muted">${esc(f.plantilla)}</small></td>
      <td>${estado}</td>
      <td><small>${esc(ayuda.donde || '')}${ayuda.signo ? `<br><b>Signo:</b> ${esc(ayuda.signo)}` : ''}</small></td>
      <td>${esc(f.unidad)}</td>
      <td class="num">${vigente}</td>
      <td><input type="text" inputmode="decimal" class="visaCapturaInput" data-campo="${esc(f.campo)}" aria-label="${esc(f.etiqueta)}${f.requerido ? ' (obligatorio)' : ''}" placeholder="${esc(placeholder)}" style="${estiloInput}"></td>
      <td><small>${referenciaCapturaVisa(f.campo, d)}</small></td></tr>`;
  }).join('');
  const avisoCaptura = faltantes.length
    ? `<div class="alert" style="margin-bottom:10px"><b>Falta llenar ${faltantes.length === 1 ? 'un campo obligatorio' : `${faltantes.length} campos obligatorios`}:</b>
        ${faltantes.map((f) => `${esc(f.campo)} (${esc(f.etiqueta)})`).join(' y ')}.
        <p>Escríbelos en la columna «Nuevo valor» y pulsa «Guardar captura». Sin ellos no se calcula la liquidación ni se compara con Host. Los demás campos son opcionales: si no aplican, déjalos vacíos y valen 0.</p></div>`
    : '<div class="friendlyNote" style="margin-bottom:10px">Los campos obligatorios están completos. Puedes llenar los opcionales que apliquen o cambiar cualquier valor; cada cambio guarda una versión nueva.</div>';

  const formulas = ['L171', 'N169', 'N170', 'N171', 'N172', 'F5', 'L161', 'L163'].map((k) => {
    const c = celdas[k] || {};
    const usd = k === 'L171';
    return `<tr><td><b>${k}</b></td><td>${esc(c.etiqueta || '')}</td><td><code>${esc(c.formula || '')}</code></td>
      <td class="num">${usd ? numVisa(c.valor) + ' USD' : numVisa(c.valor)}</td><td>${tagVisa(c.estado)}</td></tr>`;
  }).join('');

  const asiento = (liq.asiento || []).map((a) => `<tr>
      <td class="num">${a.fila}</td><td><code>${esc(a.celda)}</code></td><td>${esc(a.cuenta || '—')}</td>
      <td>${esc(a.naturaleza_plantilla || '')}</td><td class="num">${numVisa(a.valor)}</td><td>${esc(a.naturaleza || '—')}</td></tr>`).join('');

  const cuentas = (d.cuentas || []).map((c) => `<tr>
      <td>${esc(c.cuenta)}</td><td class="num">${numVisa(c.esperado)}</td>
      ${FUENTES_REDEBAN.map((f) => {
        const h = (c.host || {})[f] || {};
        const marca = h.obligatoria ? ' <b title="Fuente que se consulta para esta cuenta">*</b>' : '';
        return `<td class="num" title="${esc(h.estado || '')}">${numVisa(h.neto)}${marca}</td><td class="num">${numVisa(h.diferencia)}</td>`;
      }).join('')}
      <td>${tagVisa(c.estado)}</td></tr>`).join('');

  const vss120 = ((d.vss || {}).vss120 || []).map((x) => `<tr><td>${esc(x.seccion || '')}</td><td>${esc(x.concepto || '')}</td>
      <td>${esc(x.moneda_clearing || '')}</td><td class="num">${x.lineas}</td><td class="num">${numVisa(x.clearing)}</td>
      <td class="num">${numVisa(x.credito)}</td><td class="num">${numVisa(x.debito)}</td></tr>`).join('');

  const avisos = (d.advertencias || []).map((a) => `<p class="filterHint">⚠ ${esc(a)}</p>`).join('');
  const pendientes = (d.pendientes || []).map((p) => `<li>${esc(p)}</li>`).join('');
  const validacion = liq.validacion_canje_internacional || {};

  cont.innerHTML = `
    <div class="explain">Liquidación VISA Internacional de la Plantilla Maestra (fila 5 y filas 161-181). Las celdas que la plantilla digita a mano se capturan abajo y quedan versionadas; el resto son las mismas fórmulas. El asiento se compara contra Host por cuenta, HA22, HA26 y HA32 por separado (positivo = débito). <b>*</b> marca la fuente que se consulta para esa cuenta.</div>
    <div class="flow summaryFlow">
      <div class="fc"><small>ESTADO</small><b>${tagVisa(d.estado)}</b></div>
      <div class="fc"><small>TRM (M169)</small><b>${numVisa(valor('M169'), 4)}</b></div>
      <div class="fc"><small>COMPENSACIÓN VISA (F5)</small><b>${numVisa(valor('F5'))}</b></div>
      <div class="fc"><small>DIF. EN CAMBIO (M181)</small><b>${numVisa(valor('M181'))}</b></div>
      <div class="fc"><small>CUENTAS CONCILIADAS</small><b>${res.CONCILIADO ?? 0} de ${res.cuentas ?? 0}</b></div>
    </div>
    ${avisos ? `<div class="card section"><div class="title">Avisos</div>${avisos}</div>` : ''}
    <div class="card section">
      <div class="title">Control VSS vs International SS</div>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Entidad (FTSRE)</th><th>Neto VSS-115 (USD)</th><th>PDF International SS (USD)</th><th>Diferencia</th><th>Estado</th><th>Detalle</th></tr></thead>
      <tbody>${controles}</tbody></table></div>
    </div>
    <div class="card section">
      <div class="title">Captura manual · valores que debes digitar <span class="muted">(${camposCaptura.filter((f) => (celdas[f.campo] || {}).valor != null).length} de ${camposCaptura.length} con valor)</span></div>
      ${avisoCaptura}
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Celda</th><th>Concepto</th><th>Estado</th><th>De dónde sale</th><th>Unidad</th><th>Vigente</th><th>Nuevo valor</th><th>Referencia de los insumos</th></tr></thead>
      <tbody>${captura}</tbody></table></div>
      <p class="filterHint"><b style="color:var(--red)">*</b> Obligatorio. Usa punto como separador decimal (ej. 4012.3456) y signo menos para valores negativos (ej. -500000); las comas de miles se ignoran. La referencia de los insumos es solo para comparar: no se copia sola.</p>
      <div class="actionbar">
        <input type="text" id="visaObservacion" maxlength="500" placeholder="Observación (opcional)" aria-label="Observación de la captura" style="flex:1;min-width:12rem">
        <button type="button" class="btn primary" id="btnGuardarCapturaVisa">Guardar captura</button>
      </div>
      <div id="visaCapturaMensaje" role="status" aria-live="polite" class="muted">${mensaje}</div>
    </div>
    <div class="card section">
      <div class="title">Liquidación · ${tagVisa(validacion.estado)} <span class="muted">validación canje internacional L163 = ${numVisa(validacion.valor)}</span></div>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Celda</th><th>Concepto</th><th>Fórmula</th><th>Valor (COP)</th><th>Estado</th></tr></thead>
      <tbody>${formulas}</tbody></table></div>
    </div>
    <div class="card section">
      <div class="title">Asiento propuesto (columna M)</div>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fila</th><th>Celda</th><th>Cuenta</th><th>Plantilla</th><th>Valor (COP)</th><th>Naturaleza</th></tr></thead>
      <tbody>${asiento}</tbody></table></div>
    </div>
    <div class="card section">
      <div class="title">Asiento vs Host por cuenta</div>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Cuenta</th><th>Esperado</th><th>HA22 Neto</th><th>HA22 Dif.</th><th>HA26 Neto</th><th>HA26 Dif.</th><th>HA32 Neto</th><th>HA32 Dif.</th><th>Estado</th></tr></thead>
      <tbody>${cuentas}</tbody></table></div>
    </div>
    <details class="card section">
      <summary style="cursor:pointer"><b>VSS-120 por concepto</b> <span class="muted">(referencia)</span></summary>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Sección</th><th>Concepto</th><th>Moneda clearing</th><th>Líneas</th><th>Clearing</th><th>Crédito</th><th>Débito</th></tr></thead>
      <tbody>${vss120 || '<tr><td colspan="7" class="muted">Sin VSS-120 procesado.</td></tr>'}</tbody></table></div>
    </details>
    ${pendientes ? `<div class="card section"><div class="title">Pendiente</div><ul>${pendientes}</ul></div>` : ''}`;

  el('btnGuardarCapturaVisa')?.addEventListener('click', () => { void guardarCapturaVisa(); });
}

async function guardarCapturaVisa() {
  const valores = {};
  document.querySelectorAll('.visaCapturaInput').forEach((i) => {
    const v = i.value.trim();
    if (v !== '') valores[i.dataset.campo] = v;
  });
  const msg = el('visaCapturaMensaje');
  if (!Object.keys(valores).length) {
    if (msg) msg.textContent = 'No hay valores nuevos para guardar.';
    return;
  }
  const boton = el('btnGuardarCapturaVisa');
  if (boton) boton.disabled = true;
  if (msg) msg.textContent = 'Guardando…';
  const observacion = (el('visaObservacion')?.value || '').trim() || null;
  let r;
  try {
    r = await apiFetch(`${API}/jornadas/${idJornadaConciliacion}/conciliacion-visa/capturas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ valores, observacion }),
    });
  } catch (e) {
    if (msg) msg.textContent = `No se pudo guardar: ${e.message || e}`;
    if (boton) boton.disabled = false;
    return;
  }
  if (!r.ok) {
    let detalle = `HTTP ${r.status}`;
    try { const j = await r.json(); detalle = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* sin cuerpo */ }
    if (msg) msg.textContent = `No se pudo guardar: ${detalle}`;
    if (boton) boton.disabled = false;
    return;
  }
  ultimaConciliacionVisa = await r.json();
  renderConciliacionVisa(`Captura guardada (${Object.keys(valores).join(', ')}).`);
  renderReporteUnificado();
}

// ---- Agente IA (storyboard de UX, ver aviso en la pantalla — no hay IA real conectada) ----
function verIA(cta, diff) {
  const navBtn = document.querySelectorAll('.nav button')[2];
  go('ia', navBtn);
  el('caseDiff').textContent = diff;
  el('caseDiff').style.color = 'var(--red)';
  const st = el('aiState');
  st.className = 'tag warn';
  st.textContent = 'Excepción';
  el('aiResult').innerHTML =
    '<b>Excepción no resuelta por reglas vigentes</b><p>Las reglas vigentes no pudieron cerrar automáticamente esta diferencia de ejemplo.</p>' +
    '<button class="btn primary" onclick="runGovernedAI()">Analizar diferencia con IA (demo)</button>';
  ['afterAI', 'confirmedCause', 'reprocessResult'].forEach((id) => {
    const x = el(id);
    x.style.display = 'none';
    x.classList.remove('aiLocked');
  });
}

function runGovernedAI() {
  const state = el('aiState');
  const box = el('aiResult');
  state.className = 'tag info';
  state.textContent = 'Analizando';
  box.innerHTML = '<b>Analizando evidencia (demo)...</b><p>Cuenta, importe, fecha, referencia y movimientos relacionados.</p><div class="progress"><span id="govBar" style="width:8%"></span></div>';
  let n = 8;
  const t = setInterval(() => {
    n += 16;
    const b = el('govBar');
    if (b) b.style.width = `${Math.min(n, 100)}%`;
    if (n >= 100) {
      clearInterval(t);
      state.textContent = 'Propuesta IA';
      box.innerHTML = '<b>Análisis completado (demo)</b><p>Se encontró una hipótesis de ejemplo con evidencia suficiente para revisión.</p>';
      box.classList.add('aiLocked');
      const p = el('afterAI');
      p.style.display = 'block';
      p.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, 120);
}

function confirmCause() {
  el('afterAI').classList.add('aiLocked');
  const state = el('aiState');
  state.className = 'tag ok';
  state.textContent = 'Causa confirmada';
  const c = el('confirmedCause');
  c.style.display = 'block';
  toast('Causa confirmada (demo); los importes no cambiaron');
  setTimeout(() => c.scrollIntoView({ behavior: 'smooth', block: 'center' }), 80);
}

function discardCause() {
  el('afterAI').classList.add('aiLocked');
  const state = el('aiState');
  state.className = 'tag warn';
  state.textContent = 'Hipótesis descartada';
  toast('Hipótesis descartada (demo); la excepción permanece abierta');
}

function automateAndReprocess() {
  const btn = el('btnAutomatizar');
  if (btn) { btn.disabled = true; btn.textContent = 'Aplicando regla y reejecutando...'; }
  el('confirmedCause').classList.add('aiLocked');
  const result = el('reprocessResult');
  result.style.display = 'block';
  result.innerHTML =
    '<div class="title">Automatización en curso (demo) <span class="tag info">Procesando</span></div>' +
    '<div class="aiAutoFlow"><div id="auto1" class="aiAutoStep">1<b>Proponer regla</b></div><div id="auto2" class="aiAutoStep">2<b>Aplicar regla</b></div><div id="auto3" class="aiAutoStep">3<b>Reejecutar caso</b></div></div>' +
    '<div class="progress"><span id="autoBar" style="width:8%"></span></div>';
  result.scrollIntoView({ behavior: 'smooth', block: 'center' });
  let n = 8;
  const t = setInterval(() => {
    n += 12;
    const bar = el('autoBar');
    if (bar) bar.style.width = `${Math.min(n, 100)}%`;
    if (n >= 34) el('auto1')?.classList.add('done');
    if (n >= 66) el('auto2')?.classList.add('done');
    if (n >= 100) {
      el('auto3')?.classList.add('done');
      clearInterval(t);
      const diff = el('caseDiff');
      diff.textContent = '$0';
      diff.style.color = 'var(--green)';
      el('ruleVersion').textContent = 'Versión 19';
      const st = el('aiState');
      st.className = 'tag ok';
      st.textContent = 'Conciliado';
      result.innerHTML =
        '<div class="title">Resultado del reproceso (demo) <span class="tag ok">Conciliado</span></div>' +
        '<div class="aiAutoFlow"><div class="aiAutoStep done">1<b>Regla propuesta</b></div><div class="aiAutoStep done">2<b>Regla aplicada</b></div><div class="aiAutoStep done">3<b>Caso reejecutado</b></div></div>' +
        '<div class="friendlyNote"><b>Reporte Maestro actualizado (simulado).</b> La regla quedó aplicada y el caso fue reejecutado sin pasos adicionales para el usuario.</div>';
      toast('Regla aplicada y caso conciliado (demo)');
    }
  }, 110);
}

function openEmailDraft() {
  drawerContent.innerHTML = `<h2>Borrador de correo (demo)</h2>
    <div class="friendlyNote"><b>La IA genera el texto, pero no envía el correo ni accede al buzón del usuario.</b></div>
    <div class="emailDraft">
      <div class="subject"><b>Asunto:</b> Validación diferencia conciliación Redeban</div>
      Buenos días,<br><br>
      Durante el proceso de conciliación identificamos una diferencia de <b>${el('caseDiff').textContent}</b> asociada a la cuenta de ejemplo.<br><br>
      El análisis encontró un posible movimiento posterior en Host. Agradecemos validar la información correspondiente.<br><br>
      Gracias.
    </div>
    <div class="actionbar"><button class="btn" onclick="closeDrawer()">Cerrar</button></div>`;
  openDrawer();
}

// Si el navegador restaura la página desde bfcache (ej. botón "atrás" tras
// cerrar sesión), el DOM vuelve tal cual quedó en memoria - ya autenticado -
// sin volver a correr bootstrapAuth() ni pedir nada al backend. Forzamos un
// reload real para que se vuelva a verificar la sesión desde cero.
window.addEventListener('pageshow', (event) => {
  if (event.persisted) window.location.reload();
});

void bootstrapAuth();
