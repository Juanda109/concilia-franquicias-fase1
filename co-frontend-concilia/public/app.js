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
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
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
  checkHealth();
  cargarPorFechaContable();
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

const fechaInput = el('fecha');
const tblArchivos = el('tblArchivos');
const tblMeta = el('tblMeta');
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
    el('erroresProcesamientoTipo').textContent = tipoInsumo ?? '';
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

// ---- Insumos: Fecha contable -> jornada (backend) ----
// La fecha contable ya no se deriva de una fecha de conciliación: el
// calendario selecciona la fecha contable directamente, 1:1 con la jornada.
let idJornadaActiva = null;

function _renderJornada(d) {
  tblMeta.textContent = `${d.archivosRecibidos} de ${d.archivosEsperados} insumos recibidos`;
  actualizarHero(d);
  renderTablaInsumos(d.insumos);
}

async function cargarPorFechaContable() {
  try {
    const r = await apiFetch(`${API}/jornadas?fechaContable=${encodeURIComponent(fechaInput.value)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    idJornadaActiva = d.idJornada;
    _renderJornada(d);
  } catch (e) {
    idJornadaActiva = null;
    tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Error consultando la jornada: ${e.message}</td></tr>`;
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
      <td>${a.fuente}</td>
      <td>${a.tipoInsumo}</td>
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
  if (link) link.textContent = origen === 'conciliacion' ? '← Volver a Conciliación' : '← Volver a Insumos';
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el('detalleInsumo').classList.add('active');
  window.scrollTo(0, 0);
  cargarContenidoDetalle();
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
          <div class="sub">${d.tipoInsumo}</div>
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
        <div class="sub">${d.tipoInsumo}</div>
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
        <div class="detailCount">${totalItems} registros · ${d.tipoInsumo}</div>
      </div>
      ${contenidoHtml}
    </div>`;

  el('btnDetalleAnterior')?.addEventListener('click', () => cambiarPaginaDetalle(-1));
  el('btnDetalleSiguiente')?.addEventListener('click', () => cambiarPaginaDetalle(1));
}

function cambiarPaginaDetalle(delta) {
  detallePagina += delta;
  cargarContenidoDetalle();
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
  const m = /^([A-Z_]+):\s*(.*)$/.exec(detalle || '');
  const codigo = m ? m[1] : (detalle || '').trim();
  const resto = m ? m[2] : detalle;
  if (codigo === 'FECHA_NO_COINCIDE_CON_ARCHIVO') {
    const mm = /el archivo (.+) corresponde a (\d{4}-\d{2}-\d{2}), no a (\d{4}-\d{2}-\d{2})/.exec(resto);
    if (mm) return `El archivo «${mm[1]}» corresponde al ${fechaDDMMAAAA(mm[2])}, pero esta jornada es del ${fechaDDMMAAAA(mm[3])}.`;
  }
  if (codigo === 'NOMBRE_ARCHIVO_INVALIDO') {
    const mm = /el archivo (.+) no cumple la estructura esperada para (.+)/.exec(resto);
    if (mm) return `El nombre «${mm[1]}» no tiene la estructura que se espera para ${mm[2]}.`;
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
        <div class="progressMeta"><b>${a.nombreArchivo ?? a.tipoInsumo}</b><span>${badge(a.estadoProcesamiento)}</span></div>
        ${celdaRegistros(a)}`;
      if (detalleIdArchivo === idArchivo) await cargarContenidoDetalle();
      if (a.estadoProcesamiento === 'PROCESADO' || a.estadoProcesamiento === 'ERROR') {
        clearInterval(pollers.get(idArchivo));
        pollers.delete(idArchivo);
        if (a.estadoProcesamiento === 'PROCESADO') toast(`${a.tipoInsumo} cargado: ${a.totalRegistros ?? '-'} registros`);
        else void mostrarErroresProcesamiento(idArchivo, a.tipoInsumo, a.nombreArchivo);
      }
    } catch (e) {
      // Error de red puntual durante el polling: se reintenta en el próximo tick,
      // no se corta el seguimiento por una falla transitoria.
    }
  };
  pollers.set(idArchivo, setInterval(tick, 1000));
  tick();
}

el('uploadFileHidden').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file && pendingIdArchivoUpload) subirArchivo(pendingIdArchivoUpload, file);
  pendingIdArchivoUpload = null;
});

// Se puede elegir cualquier fecha contable para CONSULTAR y tambien para
// CARGAR/ELIMINAR archivos (dias anteriores incluidos, sin restriccion) -
// lo unico que sigue bloqueado es seleccionar una fecha futura.
const HOY_ISO = toISO(new Date());
fechaInput.value = HOY_ISO;
fechaInput.max = HOY_ISO; // bloquea fechas futuras en el selector nativo; sin min, los días anteriores siguen disponibles
fechaInput.addEventListener('change', () => {
  if (fechaInput.value > HOY_ISO) {
    fechaInput.value = HOY_ISO;
    toast('No se pueden consultar fechas futuras.', true);
    return;
  }
  cargarPorFechaContable();
});

// ---- Navegación de pestañas (Insumos / Conciliación / Agente IA) ----
function go(id, btn) {
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el(id).classList.add('active');
  document.querySelectorAll('.nav button').forEach((b) => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  window.scrollTo(0, 0);
  if (id === 'conciliacion') void cargarCierreCredibanco();
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

let ultimoCierreCredibanco = null;

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

function filterCruceRows() {
  const q = (el('cruceQ')?.value || '').toLowerCase();
  const st = el('cruceSt')?.value || '';
  document.querySelectorAll('#cruceBody tr').forEach((r) => {
    const okq = !q || (r.dataset.cuenta || '').toLowerCase().includes(q);
    const okst = !st || r.dataset.estado === st;
    r.style.display = okq && okst ? 'table-row' : 'none';
  });
}

// Página completa de detalle por cuenta, con la misma estructura en dos
// bloques que usaba gustavo-dev para esta vista ("A. Contabilidad interna ·
// Host" / "B. Insumos externos"), pero construida solo con lo que
// cierre_credibanco_v67 realmente calcula - nunca atribuye un total global
// de CAET/CANT/DEPO a una cuenta sin que el motor mismo lo haya candidateado.
let detalleCuentaOrigenScrollY = 0;

function abrirDetalleCuentaCredibanco(cuenta) {
  const cont = el('detalleCuentaCredibancoContent');
  if (!cont) return;
  detalleCuentaOrigenScrollY = window.scrollY;
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el('detalleCuentaCredibanco').classList.add('active');
  window.scrollTo(0, 0);
  renderDetalleCuentaCredibanco(cuenta);
}

function volverAConciliacion() {
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el('conciliacion').classList.add('active');
  requestAnimationFrame(() => window.scrollTo(0, detalleCuentaOrigenScrollY));
}
el('btnVolverConciliacion')?.addEventListener('click', volverAConciliacion);

function renderDetalleCuentaCredibanco(cuenta) {
  const cont = el('detalleCuentaCredibancoContent');
  const d = ultimoCierreCredibanco;
  if (!cont || !d) return;

  const filasHost = (d.host_por_cuenta_y_fuente || []).filter((h) => h.cuenta === cuenta);
  const cruce = (d.cruces_host_credibanco_diagnosticos || []).find((c) => c.cuenta_host === cuenta) || null;

  const filasHostHtml = filasHost
    .map((f) => {
      const idArchivo = (f.archivos || [])[0];
      const accion = idArchivo != null
        ? `<button type="button" class="btn" onclick="abrirDetalle(${Number(idArchivo)},'conciliacion')">Ver evidencia</button>`
        : '—';
      return `<tr><td>${esc(f.fuente)}</td><td>${idArchivo ?? '—'}</td><td class="num">${f.cantidad ?? '—'}</td><td class="num">${fmtMoney(f.debe)}</td><td class="num">${fmtMoney(f.haber)}</td><td class="num">${fmtMoney(f.neto_debe_menos_haber)}</td><td><span class="tag ${badgeFor(f.estado)}">${esc(f.estado)}</span></td><td>${accion}</td></tr>`;
    })
    .join('');

  const cruceHtml = cruce
    ? `<div class="explain"><b>Regla de cruce:</b> ${esc(cruce.id_regla)} (${esc(cruce.insumo)}) · <span class="tag ${badgeFor(cruce.estado)}">${esc(cruce.estado)}</span>${cruce.valor_franquicia != null ? ` · Franquicia: ${fmtMoney(cruce.valor_franquicia)} · Diferencia: ${fmtMoney(cruce.diferencia)}` : ''}</div>`
    : '<div class="explain">Sin regla de cruce aprobada para esta cuenta todavía.</div>';

  // Seccion B: nunca se filtra un total global de CAET/CANT por cuenta (el
  // motor no hace esa atribucion sin regla aprobada), salvo DEPO, donde
  // agrupar_depo() ya calcula una cuenta_host_candidata explicita por fila.
  let seccionB;
  if (cruce && (cruce.insumo === 'CAET' || cruce.insumo === 'CANT')) {
    const filas = d.totales_diagnosticos || [];
    const filasHtml = filas
      .map((t) => `<tr><td>${esc(t.A)}</td><td>${esc((t.insumos || []).join(', '))}</td><td class="num">${t.B ?? '—'}</td><td class="num">${t.C != null ? fmtMoney(t.C) : '—'}</td><td class="num">${t.D != null ? fmtMoney(t.D) : '—'}</td></tr>`)
      .join('');
    seccionB = `
      <h3>B. Insumos externos · CAET/CANT</h3>
      <p class="friendlyNote">Totales globales de origen por concepto persistido (ver "Totales diagnósticos"). No atribuidos automáticamente a esta cuenta: la regla de cruce arriba es la única atribución aprobable, y sigue pendiente. No sumar CAET y CANT entre sí.</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Concepto</th><th>Insumo</th><th>Cantidad</th><th>VL Interc</th><th>VL Total</th></tr></thead>
      <tbody>${filasHtml || '<tr><td colspan="5" class="muted">Sin totales disponibles.</td></tr>'}</tbody></table></div>`;
  } else if (cruce && cruce.insumo === 'DEPO') {
    const filas = (d.depo_agregados_crudos || []).filter((x) => x.cuenta_host_candidata === cuenta);
    const filasHtml = filas
      .map((x) => `<tr><td>${esc(x.concepto || x.concepto_persistido || '—')}</td><td class="num">${x.cantidad ?? '—'}</td><td class="num">${x.valor_total_crudo != null ? fmtMoney(x.valor_total_crudo) : '—'}</td><td class="num">${x.valor_intercambio_crudo != null ? fmtMoney(x.valor_intercambio_crudo) : '—'}</td><td><span class="tag ${badgeFor(x.estado)}">${esc(x.estado)}</span></td></tr>`)
      .join('');
    seccionB = `
      <h3>B. Insumos externos · DEPO</h3>
      <p class="friendlyNote">Filas de DEPO cuya cuenta candidata (calculada por el motor a partir del concepto AU) coincide con esta cuenta. Candidato, no homologación aprobada.</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Concepto</th><th>Cantidad</th><th>Valor total crudo</th><th>Valor intercambio crudo</th><th>Estado</th></tr></thead>
      <tbody>${filasHtml || '<tr><td colspan="5" class="muted">Sin filas DEPO candidateadas a esta cuenta.</td></tr>'}</tbody></table></div>`;
  } else {
    seccionB = '<h3>B. Insumos externos</h3><p class="muted">Sin regla de cruce asociada a esta cuenta; no hay insumo externo que mostrar aquí todavía.</p>';
  }

  cont.innerHTML = `
    <div class="head"><div><h1>Detalle de conciliación · ${esc(cuenta)}</h1></div></div>
    ${cruceHtml}
    <div class="card section">
      <h3>A. Contabilidad interna · Host</h3>
      <p class="friendlyNote">Neto por fuente = Debe − Haber. HA22, HA26 y HA32 no se suman entre sí.</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fuente</th><th>Archivo ID</th><th>Movimientos</th><th>Debe</th><th>Haber</th><th>Neto</th><th>Estado</th><th>Acción</th></tr></thead>
      <tbody>${filasHostHtml || '<tr><td colspan="8" class="muted">Sin movimientos Host para esta cuenta.</td></tr>'}</tbody></table></div>
    </div>
    <div class="card section">${seccionB}</div>`;
}

async function cargarCierreCredibanco() {
  const cont = el('cierreCredibancoContent');
  if (!cont) return;
  if (!idJornadaActiva) {
    cont.innerHTML = '<div class="emptyDetail">Selecciona una fecha contable en Insumos para ver el diagnóstico de esta jornada.</div>';
    return;
  }
  cont.innerHTML = '<div class="emptyDetail">Cargando diagnóstico…</div>';
  let r, rJornada;
  try {
    [r, rJornada] = await Promise.all([
      apiFetch(`${API}/jornadas/${idJornadaActiva}/cierre-credibanco`),
      apiFetch(`${API}/jornadas/${idJornadaActiva}`),
    ]);
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
  // Mapeo tipoInsumo -> idArchivo, solo para habilitar el enlace "Ver
  // evidencia" por fila; si esta llamada falla no bloquea el diagnóstico.
  const archivoPorInsumo = new Map();
  if (rJornada.ok) {
    const jornadaDetalle = await rJornada.json();
    for (const i of jornadaDetalle.insumos || []) {
      if (i.idArchivo != null) archivoPorInsumo.set(i.tipoInsumo, i.idArchivo);
    }
  }
  const cc = d.control_canje_carta || {};
  const l3 = cc.L3_comisiones_canje || {};
  const l5 = cc.L5_carta_componente_G || {};
  const l8 = cc.L8_diferencia || {};
  const neta = d.carta_posicion_neta || {};

  const insumosRows = (d.insumos || [])
    .map((i) => {
      const idArchivo = archivoPorInsumo.get(i.insumo);
      const accion = idArchivo != null
        ? `<button type="button" class="btn" onclick="abrirDetalle(${Number(idArchivo)},'conciliacion')">Ver evidencia</button>`
        : '<span class="muted">—</span>';
      return `<tr><td>${esc(i.insumo)}</td><td>${i.cantidad_archivos}</td><td><span class="tag ${badgeFor(i.estado)}">${esc(i.estado)}</span></td><td>${accion}</td></tr>`;
    })
    .join('');

  const pendRows = (d.pendientes || [])
    .map((p) => `<tr><td>${esc(p.codigo || p.estado || '')}</td><td>${esc(p.detalle || p.mensaje || JSON.stringify(p))}</td></tr>`)
    .join('');

  const cruces = d.cruces_host_credibanco_diagnosticos || [];
  const filasHost = construirFilasHost(d.host_por_cuenta_y_fuente, cruces);
  const coincidencias = cruces.filter((c) => c.estado === 'COINCIDE_DIAGNOSTICO_NO_CERTIFICADO').length;
  const diferencias = cruces.filter((c) => c.estado === 'DIFERENCIA_DIAGNOSTICA_NO_CERTIFICADA').length;
  const conRegla = filasHost.filter((f) => f.cruce).length;

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
        <td><span class="tag ${badgeFor(estadoFila)}">${esc(estadoFila || '—')}</span></td>
        <td>${accion}</td>
      </tr>`;
    })
    .join('');

  cont.innerHTML = `
    <div class="flow summaryFlow">
      <div class="fc"><small>POSICIÓN NETA CARTA</small><b class="tag ${badgeFor(neta.estado)}">${esc(neta.estado || '—')}</b></div>
      <div class="fc"><small>L3 · COMISIONES CANJE</small><b>${fmtMoney(l3.valor)}</b></div>
      <div class="fc"><small>L5 · CARTA (COMPONENTE G)</small><b>${fmtMoney(l5.valor)}</b></div>
      <div class="fc"><small>L8 · DIFERENCIA (L5-L3-L6)</small><b>${l8.l8 !== undefined ? fmtMoney(l8.l8) : '—'}</b></div>
    </div>
    <div class="explain"><b>Diagnóstico, no certificación.</b> Estado general: <span class="tag ${badgeFor(d.estado)}">${esc(d.estado || '—')}</span>. Este resultado nunca certifica automáticamente una conciliación contable (<code>certificado:false</code> siempre); requiere revisión y aprobación de negocio.</div>
    <div class="flow summaryFlow">
      <div class="fc"><small>CUENTAS HOST</small><b>${filasHost.length}</b></div>
      <div class="fc"><small>CON REGLA DEFINIDA</small><b>${conRegla}</b></div>
      <div class="fc"><small>COINCIDENCIAS</small><b>${coincidencias}</b></div>
      <div class="fc"><small>DIFERENCIAS</small><b>${diferencias}</b></div>
    </div>
    <div class="card section">
      <div class="title">Insumos de la jornada</div>
      <div class="tableScroll"><table><thead><tr><th>Insumo</th><th>Archivos</th><th>Estado</th><th>Acción</th></tr></thead>
      <tbody>${insumosRows || '<tr><td colspan="4" class="muted">Sin insumos procesados.</td></tr>'}</tbody></table></div>
    </div>
    <div class="card section">
      <div class="title">Cuentas Host observadas <span class="muted">(${filasHost.length})</span></div>
      <div class="toolbar">
        <input id="cruceQ" class="search" onkeyup="filterCruceRows()" placeholder="Buscar cuenta..." aria-label="Buscar cuenta Host">
        <select id="cruceSt" class="select" onchange="filterCruceRows()" aria-label="Filtrar por estado">
          <option value="">Todos los estados</option>
          <option value="PENDIENTE_HOMOLOGACION_NATURALEZA_Y_FUENTE">Pendiente homologación</option>
          <option value="PENDIENTE_APROBACION_REGLA">Pendiente aprobación regla</option>
          <option value="BLOQUEADO_SINTETICO">Bloqueado sintético</option>
          <option value="DATO_INCOMPLETO">Dato incompleto</option>
          <option value="COINCIDE_DIAGNOSTICO_NO_CERTIFICADO">Coincide (no certificado)</option>
          <option value="DIFERENCIA_DIAGNOSTICA_NO_CERTIFICADA">Diferencia (no certificada)</option>
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
    <div class="card section">
      <div class="title">Pendientes (${(d.pendientes || []).length})</div>
      <div class="tableScroll"><table><thead><tr><th>Código</th><th>Detalle</th></tr></thead>
      <tbody>${pendRows || '<tr><td colspan="2" class="muted">Sin pendientes.</td></tr>'}</tbody></table></div>
    </div>`;
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

bootstrapAuth();
