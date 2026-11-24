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
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, ''); // en base64 '=' solo aparece como relleno final
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
  void cargarPorFechaContable();
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
// Nombre para mostrar de cada insumo. El codigo (tipoInsumo) no cambia:
// lo usan la base de datos, el parseo y la validacion de nombres de archivo.
const NOMBRE_INSUMO = {
  ISS: 'Visa Internacional Posición Neta',
  VSS: 'Visa Internacional VSS',
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
  if (link) link.textContent = origen === 'conciliacion' ? '← Volver a Conciliación' : '← Volver a Insumos';
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
  // Se separa con indexOf en vez de un regex con \s* seguido de .* (backtracking
  // super-lineal señalado por SonarQube).
  const texto = detalle || '';
  const sep = texto.indexOf(':');
  const prefijo = sep > 0 ? texto.slice(0, sep) : '';
  const conCodigo = /^[A-Z_]+$/.test(prefijo);
  const codigo = conCodigo ? prefijo : texto.trim();
  const resto = conCodigo ? texto.slice(sep + 1).trimStart() : detalle;
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
    // "el archivo X no cumple la estructura esperada para TIPO. Formato esperado: F"
    // Se parte con indexOf (sin regex) para evitar backtracking super-lineal.
    const INICIO = 'el archivo ';
    const MARCA = ' no cumple la estructura esperada para ';
    const FORMATO = 'Formato esperado:';
    const i = resto.indexOf(MARCA);
    if (resto.startsWith(INICIO) && i > INICIO.length) {
      const nombre = resto.slice(INICIO.length, i);
      let cola = resto.slice(i + MARCA.length);
      let formato = '';
      const j = cola.indexOf(FORMATO);
      if (j >= 0) { formato = cola.slice(j + FORMATO.length).trim(); cola = cola.slice(0, j); }
      const tipo = cola.split('.')[0].trim();
      const base = `El nombre «${nombre}» no tiene la estructura que se espera para ${nombreInsumo(tipo)}.`;
      return formato ? `${base} Formato esperado: ${formato}` : base;
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
  void cargarPorFechaContable();
});

// ---- Navegación de pestañas (Insumos / Conciliación / Agente IA) ----
function go(id, btn) {
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el(id).classList.add('active');
  document.querySelectorAll('.nav button').forEach((b) => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  window.scrollTo(0, 0);
  if (id === 'conciliacion') { void cargarCierreCredibanco(); void cargarCierreRedeban(); void cargarConciliacionVisa(); }
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

// Tarjeta "FECHA CONTABLE" en Conciliación: solo muestra la jornada activa
// (idJornadaActiva, compartida con Insumos) - no se selecciona desde acá,
// la fecha se elige en Insumos y esta vista solo la refleja. No depende de
// ningun arreglo de jornadas cargado por Insumos (esa pantalla puede ser el
// selector simple de fecha o el de rango, segun la rama) - solo usa lo que
// cargarCierreCredibanco() ya trae en la respuesta de cierre-credibanco.
function renderFechasConciliacion(activa) {
  const host = el('reconFechasContables');
  if (!host) return;
  if (!activa) {
    host.innerHTML = '<span class="reconDateEmpty">Sin fecha contable seleccionada en Insumos.</span>';
    return;
  }
  host.innerHTML = `
    <span class="fechaChip reconDateChip active" aria-disabled="true">
      <small>FECHA CONTABLE</small><b>${esc(activa.fecha)}</b>
      <span class="reconDateId">Jornada ${activa.idJornada}</span>
    </span>`;
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
function construirFilasResultado(d) {
  const cruces = d.cruces_host_credibanco_diagnosticos || [];
  const hostPorCuenta = new Map();
  for (const h of d.host_por_cuenta_y_fuente || []) {
    if (!hostPorCuenta.has(h.cuenta)) hostPorCuenta.set(h.cuenta, {});
    hostPorCuenta.get(h.cuenta)[h.fuente] = h;
  }
  return cruces.map((c) => {
    const concepto = CONCEPTO_REGLA[c.id_regla] || '—';
    let cantidad = '—';
    let interc = '—';
    let total = '—';
    if (c.insumo === 'CANT' || c.insumo === 'CAET') {
      const t = totalPorConceptoCanje(d.totales_diagnosticos, concepto);
      if (t) {
        cantidad = t.B;
        interc = t.C != null ? fmtMoney(t.C) : '—';
        total = t.D != null ? fmtMoney(t.D) : '—';
      }
    } else if (c.insumo === 'DEPO') {
      const t = totalPorConceptoDepo(d.depo_agregados_crudos, concepto);
      if (t) {
        cantidad = t.cantidad;
        interc = t.interc != null ? fmtMoney(t.interc) : '—';
        total = t.total != null ? fmtMoney(t.total) : '—';
      }
    }
    const fuentes = hostPorCuenta.get(c.cuenta_host) || {};
    const idArchivo = (fuentes.HA22 || fuentes.HA26 || fuentes.HA32)?.archivos?.[0];
    const cuentaJs = esc(JSON.stringify(c.cuenta_host || ''));
    const accion = idArchivo != null
      ? `<button type="button" class="btn" onclick="abrirDetalle(${Number(idArchivo)},'conciliacion')">Ver evidencia</button>`
      : `<button type="button" class="btn" onclick="abrirDetalleCuentaCredibanco(${cuentaJs})">Ver detalle</button>`;
    return `<tr data-cuenta="${esc(c.cuenta_host || '')}" data-concepto="${esc(concepto)}" data-estado="${esc(c.estado || '')}" data-franquicia="CREDIBANCO">
      <td>CREDIBANCO</td>
      <td><a href="#" onclick="abrirDetalleCuentaCredibanco(${cuentaJs});return false;">${esc(c.cuenta_host || '—')}</a></td>
      <td>${esc(concepto)}</td>
      <td class="num">${cantidad}</td>
      <td class="num">${interc}</td>
      <td class="num">${total}</td>
      <td class="num">${c.valor_franquicia != null ? fmtMoney(c.valor_franquicia) : '—'}</td>
      <td class="num">${celdaFuente(fuentes, 'HA22', 'debe')}</td>
      <td class="num">${celdaFuente(fuentes, 'HA22', 'haber')}</td>
      <td class="num">${celdaFuente(fuentes, 'HA22', 'neto_debe_menos_haber')}</td>
      <td class="num">${celdaFuente(fuentes, 'HA26', 'debe')}</td>
      <td class="num">${celdaFuente(fuentes, 'HA26', 'haber')}</td>
      <td class="num">${celdaFuente(fuentes, 'HA26', 'neto_debe_menos_haber')}</td>
      <td class="num">${celdaFuente(fuentes, 'HA32', 'debe')}</td>
      <td class="num">${celdaFuente(fuentes, 'HA32', 'haber')}</td>
      <td class="num">${celdaFuente(fuentes, 'HA32', 'neto_debe_menos_haber')}</td>
      <td class="num">${c.valor_host != null ? fmtMoney(c.valor_host) : '—'}</td>
      <td class="num">${c.diferencia != null ? fmtMoney(c.diferencia) : '—'}</td>
      <td><span class="tag ${badgeFor(c.estado)}" title="${esc(c.estado || '')}">${esc(labelEstadoConciliacion(c.estado))}</span>${c.diferencia != null && c.aprobada === false ? ' <span class="tag warn" title="La regla no tiene version+evidencia_aprobacion firmadas; este valor es un calculo provisional.">⚠ sin aprobar</span>' : ''}</td>
      <td>${accion}</td>
    </tr>`;
  }).join('');
}

function filterResultadoRows() {
  const q = (el('reconQ')?.value || '').toLowerCase();
  const fr = el('reconFr')?.value || '';
  const st = el('reconSt')?.value || '';
  document.querySelectorAll('#reconBody tr').forEach((r) => {
    const okq = !q || (r.dataset.cuenta || '').toLowerCase().includes(q) || (r.dataset.concepto || '').toLowerCase().includes(q);
    const okfr = !fr || r.dataset.franquicia === fr;
    const okst = !st || r.dataset.estado === st;
    r.style.display = okq && okfr && okst ? 'table-row' : 'none';
  });
}

function toggleTrazabilidadHost() {
  const card = el('trazabilidadHostCard');
  const btn = el('btnTrazabilidadHost');
  if (!card || !btn) return;
  const mostrar = card.style.display === 'none';
  card.style.display = mostrar ? '' : 'none';
  btn.textContent = btn.textContent.replace(mostrar ? 'Ver' : 'Ocultar', mostrar ? 'Ocultar' : 'Ver');
  if (mostrar) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
  // Una cuenta puede tener varias reglas (p. ej. 838: consignados vs Debe y reversiones vs Haber).
  const crucesCuenta = (d.cruces_host_credibanco_diagnosticos || []).filter((c) => c.cuenta_host === cuenta);
  const cruce = crucesCuenta[0] || null;

  const filasHostHtml = filasHost
    .map((f) => {
      const idArchivo = (f.archivos || [])[0];
      const accion = idArchivo != null
        ? `<button type="button" class="btn" onclick="abrirDetalle(${Number(idArchivo)},'conciliacion')">Ver evidencia</button>`
        : '—';
      return `<tr><td>${esc(f.fuente)}</td><td>${idArchivo ?? '—'}</td><td class="num">${f.cantidad ?? '—'}</td><td class="num">${fmtMoney(f.debe)}</td><td class="num">${fmtMoney(f.haber)}</td><td class="num">${fmtMoney(f.neto_debe_menos_haber)}</td><td><span class="tag ${badgeFor(f.estado)}">${esc(f.estado)}</span></td><td>${accion}</td></tr>`;
    })
    .join('');

  const cruceHtml = crucesCuenta.length
    ? crucesCuenta.map((c) => `<div class="explain"><b>Regla de cruce:</b> ${esc(c.id_regla)} (${esc(c.insumo)}) · <span class="tag ${badgeFor(c.estado)}" title="${esc(c.estado || '')}">${esc(labelEstadoConciliacion(c.estado))}</span>${c.valor_franquicia != null ? ` · Franquicia: ${fmtMoney(c.valor_franquicia)} · Diferencia: ${fmtMoney(c.diferencia)}` : ''}${c.diferencia != null && c.aprobada === false ? ' <span class="tag warn" title="La regla no tiene version+evidencia_aprobacion firmadas; este valor es un calculo provisional.">⚠ sin aprobar</span>' : ''}</div>`).join('')
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
  } else if (cruce && cruce.insumo === 'PLANTILLA') {
    const p = d.plantilla_maestra || {};
    const recibido = (p.bloques || []).find((b) => b.codigo === 'TOTAL_CANJE_RECIBIDO') || { filas: [] };
    const i57 = (p.controles || {}).I57_CUENTA_302 || {};
    const filasHtml = recibido.filas
      .filter((f) => f.fila >= 57 && f.fila <= 62)
      .map((f) => `<tr><td class="num">${f.fila}</td><td>${esc(f.concepto)}</td><td class="num">${f.debito != null ? fmtMoney(f.debito) : '—'}</td><td class="num">${f.credito != null ? fmtMoney(f.credito) : '—'}</td><td><span class="tag ${badgeForPlantilla(f.estado)}" title="${esc(f.formula_excel || '')}">${esc(f.estado)}</span></td></tr>`)
      .join('');
    seccionB = `
      <h3>B. Plantilla Maestra · filas 57 a 62</h3>
      <p class="friendlyNote">Neto I57 = F57 − G58 − G59 − G61 − G60 + F62 = <b>${i57.valor != null ? fmtMoney(i57.valor) : '—'}</b>. Es el valor de franquicia que se compara contra HA32 de esta cuenta (nota de la Plantilla: "VALI CTA 302 HA 32").</p>
      <div class="tableScroll"><table class="reconTable"><thead><tr><th>Fila</th><th>Concepto</th><th>Débito</th><th>Crédito</th><th>Estado</th></tr></thead>
      <tbody>${filasHtml || '<tr><td colspan="5" class="muted">Sin filas de la Plantilla.</td></tr>'}</tbody></table></div>`;
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
    renderFechasConciliacion(null);
    el('reconJornada').textContent = 'Seleccione una fecha contable en Insumos.';
    cont.innerHTML = '<div class="emptyDetail">Selecciona una fecha contable en Insumos para ver el diagnóstico de esta jornada.</div>';
    return;
  }
  cont.innerHTML = '<div class="emptyDetail">Cargando diagnóstico…</div>';
  let r;
  try {
    r = await apiFetch(`${API}/jornadas/${idJornadaActiva}/cierre-credibanco`);
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
  renderFechasConciliacion({ fecha: d.fecha_contable, idJornada: d.id_jornada });
  el('reconJornada').textContent = `Fecha contable: ${d.fecha_contable} · Jornada ${d.id_jornada}`;
  const cc = d.control_canje_carta || {};
  const l3 = cc.L3_comisiones_canje || {};
  const l5 = cc.L5_carta_componente_G || {};
  const l8 = cc.L8_diferencia || {};
  const neta = d.carta_posicion_neta || {};

  const pendRows = (d.pendientes || [])
    .map((p) => `<tr><td>${esc(p.codigo || p.estado || '')}</td><td>${esc(p.detalle || p.mensaje || JSON.stringify(p))}</td></tr>`)
    .join('');

  const cruces = d.cruces_host_credibanco_diagnosticos || [];
  const filasHost = construirFilasHost(d.host_por_cuenta_y_fuente, cruces);
  const coincidencias = cruces.filter((c) => c.estado === 'COINCIDE').length;
  const diferencias = cruces.filter((c) => c.estado === 'CON_DIFERENCIA').length;

  // "Incorporados maestro": cuentas con regla de cruce definida que ya
  // tienen al menos un movimiento Host cargado para esta jornada (HA22/26/32)
  // - es decir, con datos reales ya incorporados a este cuadro para poder
  // compararse, independientemente de si la regla ya fue aprobada.
  const incorporadosMaestro = filasHost.filter((f) => f.cruce && Object.keys(f.fuentes).length > 0).length;
  const filasResultado = construirFilasResultado(d);

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
    <div class="flow summaryFlow">
      <div class="fc"><small>POSICIÓN NETA CARTA</small><b class="tag ${badgeFor(neta.estado)}">${esc(neta.estado || '—')}</b></div>
      <div class="fc"><small>L3 · COMISIONES CANJE</small><b>${fmtMoney(l3.valor)}</b></div>
      <div class="fc"><small>L5 · CARTA (COMPONENTE G)</small><b>${fmtMoney(l5.valor)}</b></div>
      <div class="fc"><small>L8 · DIFERENCIA (L5-L3-L6)</small><b>${l8.l8 !== undefined ? fmtMoney(l8.l8) : '—'}</b></div>
    </div>
    <div class="explain">Estado general: <span class="tag ${badgeFor(d.estado)}">${esc(d.estado || '—')}</span>. Las reglas de cruce y L8 se aplican según el catálogo aprobado; una diferencia no genera asientos contables automáticos.</div>
    <div class="flow summaryFlow">
      <div class="fc"><small>CUENTAS / CRUCES</small><b>${cruces.length}</b></div>
      <div class="fc"><small>CONCILIADOS</small><b>${coincidencias}</b></div>
      <div class="fc"><small>DIFERENCIAS</small><b>${diferencias}</b></div>
      <div class="fc"><small>INCORPORADOS MAESTRO</small><b>${incorporadosMaestro}</b></div>
    </div>
    <div class="card section">
      <div class="toolbar">
        <input id="reconQ" class="search" onkeyup="filterResultadoRows()" placeholder="Buscar cuenta o concepto...">
        <select id="reconFr" class="select" onchange="filterResultadoRows()">
          <option value="">Todas las franquicias</option>
          <option value="CREDIBANCO">Credibanco</option>
        </select>
        <select id="reconSt" class="select" onchange="filterResultadoRows()">
          <option value="">Todos los estados</option>
          <option value="COINCIDE">Conciliado</option>
          <option value="CON_DIFERENCIA">Con diferencia</option>
          <option value="PENDIENTE_APROBACION_REGLA">Pendiente de aprobación</option>
        </select>
      </div>
      <div class="title">Resultados de conciliación <span class="muted">(${cruces.length} registros)</span></div>
      <div class="tableScroll"><table class="reconTable"><thead><tr>
        <th>Franquicia</th><th>Cuenta</th><th>Concepto</th><th>Cantidad*</th><th>VL Interc*</th><th>VL Total*</th><th>Valor intercambio</th>
        <th>HA22 Debe</th><th>HA22 Haber</th><th>HA22 Neto*</th>
        <th>HA26 Debe</th><th>HA26 Haber</th><th>HA26 Neto*</th>
        <th>HA32 Debe</th><th>HA32 Haber</th><th>HA32 Neto*</th>
        <th>Total Host</th><th>Diferencia</th><th>Estado conciliación</th><th>Acción</th>
      </tr></thead><tbody id="reconBody">${filasResultado || '<tr><td colspan="20" class="muted">Sin resultados consultados.</td></tr>'}</tbody></table></div>
      <p class="filterHint">*: diagnóstico no homologado, puede repetirse entre conceptos de una misma cuenta. —: no disponible / sin cruce homologado. Los resultados Host sin correspondencia se consultan en trazabilidad separada; no se inventan cruces ni totales.</p>
      <div class="actionbar" style="justify-content:flex-end;margin-top:12px"><button type="button" class="btn" id="btnTrazabilidadHost" onclick="toggleTrazabilidadHost()">Ver trazabilidad Host (${filasHost.length})</button></div>
    </div>
    <div class="card section" id="trazabilidadHostCard" style="display:none">
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
  if (!idJornadaActiva) {
    cont.innerHTML = '<div class="emptyDetail">Selecciona una fecha contable en Insumos para ver el cuadre Redeban de esta jornada.</div>';
    return;
  }
  cont.innerHTML = '<div class="emptyDetail">Cargando cuadre Redeban…</div>';
  let r;
  try {
    r = await apiFetch(`${API}/jornadas/${idJornadaActiva}/cierre-redeban`);
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

// ---- Conciliación VISA: liquidación de la Plantilla Maestra (ver conciliacion-visa) ----
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
  if (!idJornadaActiva) {
    cont.innerHTML = '<div class="emptyDetail">Selecciona una fecha contable en Insumos para ver la conciliación VISA de esta jornada.</div>';
    return;
  }
  cont.innerHTML = '<div class="emptyDetail">Cargando conciliación VISA…</div>';
  let r;
  try {
    r = await apiFetch(`${API}/jornadas/${idJornadaActiva}/conciliacion-visa`);
  } catch (e) {
    cont.innerHTML = `<div class="emptyDetail">No se pudo cargar la conciliación VISA: ${esc(e.message || e)}</div>`;
    return;
  }
  if (!r.ok) {
    cont.innerHTML = `<div class="emptyDetail">No se pudo cargar la conciliación VISA (HTTP ${r.status}).</div>`;
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
    <div class="explain">Liquidación VISA de la Plantilla Maestra (fila 5 y filas 161-181). Las celdas que la plantilla digita a mano se capturan abajo y quedan versionadas; el resto son las mismas fórmulas. El asiento se compara contra Host por cuenta, HA22, HA26 y HA32 por separado (positivo = débito). <b>*</b> marca la fuente que se consulta para esa cuenta.</div>
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
    r = await apiFetch(`${API}/jornadas/${idJornadaActiva}/conciliacion-visa/capturas`, {
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
