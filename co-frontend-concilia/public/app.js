const API = '/api/v1';
const el = (id) => document.getElementById(id);
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
  if (!authEnabled) {
    showApplication({ name: 'Modo local' });
    return;
  }
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
  el('currentUser').textContent = user.name || user.email || user.sub || '';
  el('logoutButton').hidden = !authEnabled;
  el('authGate').hidden = true;
  el('appRoot').hidden = false;
  if (appStarted) return;
  appStarted = true;
  fechaInput.value = toISO(new Date());
  actualizarFechaEjecucion();
  checkHealth();
  cargarJornadaActualBadge();
}

el('authRetry').addEventListener('click', () => { void redirectToLogin(); });
el('logoutButton').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/v0/auth/logout', {
      method: 'POST', credentials: 'include',
    });
    if (!response.ok) throw new Error();
    sessionStorage.removeItem('oidc_state');
    sessionStorage.removeItem('oidc_code_verifier');
    for (const timer of pollers.values()) clearInterval(timer);
    pollers.clear();
    appStarted = false;
    showAuthMessage('Sesión cerrada. Puedes volver a entrar cuando quieras.');
  } catch {
    toast('No fue posible cerrar la sesión.', true);
  }
});

const fechaInput = el('fecha');
const tblArchivos = el('tblArchivos');
const tblMeta = el('tblMeta');
const drawer = el('drawer');
const drawerContent = el('drawerContent');
const toastEl = el('toast');
const noDataModal = el('noDataModal');

let contenidoState = { idArchivo: null, page: 0, size: 30, tipoInsumo: null };
let toastTimer = null;
let pendingTipoUpload = null;
const pollers = new Map(); // idArchivo -> intervalId, para no duplicar polling si se sube el mismo archivo dos veces
let drawerIdArchivo = null; // idArchivo que el drawer tiene abierto actualmente, para saber si refrescarlo en vivo

// Íconos minimalistas (SVG en línea, trazo simple, sin dependencias externas)
const ICON_EYE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
const ICON_UPLOAD = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>';

function toISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function addDays(d, n) { const r = new Date(d); r.setDate(r.getDate() + n); return r; }
function fechaCorta(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  let dia = new Date(y, m - 1, d).toLocaleDateString('es-ES', { weekday: 'short' }).replace('.', '');
  dia = dia.charAt(0).toUpperCase() + dia.slice(1);
  return `${dia} ${String(d).padStart(2, '0')}`;
}

// fechaInput = "fecha de conciliación" (la que elige el usuario en el
// calendario), de la que se DERIVA la(s) fecha(s) contable(s) real(es) que
// se consultan al backend. Regla: si la fecha de conciliación cae en martes,
// se derivan 3 fechas contables (sábado/domingo/lunes anteriores, por el
// rezago de fin de semana sin operación bancaria); cualquier otro día se
// deriva solo 1: el día hábil inmediatamente anterior. Esto se recalcula
// cada vez que cambia la fecha de conciliación — el calendario queda libre
// para navegar a cualquier fecha.
let fechaContableActiva = null;

function derivarFechasContables(fechaEjecucionISO) {
  const [y, m, d] = fechaEjecucionISO.split('-').map(Number);
  const fe = new Date(y, m - 1, d);
  if (fe.getDay() === 2) return [addDays(fe, -3), addDays(fe, -2), addDays(fe, -1)];
  let b = addDays(fe, -1);
  while (b.getDay() === 0 || b.getDay() === 6) b = addDays(b, -1);
  return [b];
}

// Estado de progreso de una jornada (Completa/Con novedad/Pendiente/Error)
// a partir de sus insumos — misma regla que usa el hero.
function calcularEstadoJornada(items, totalEsperados) {
  const recibidos = items.filter((a) => a.estadoRecepcion === 'Recibido').length;
  const procesados = items.filter((a) => a.estadoProcesamiento === 'Procesado').length;
  const conError = items.some((a) => a.estadoProcesamiento === 'Error');
  if (conError) return 'Error';
  if (procesados >= totalEsperados) return 'Completa';
  if (recibidos > 0 && recibidos < totalEsperados) return 'Con novedad';
  return 'Pendiente';
}

// Pinta las fichas (resaltando la activa) y luego consulta el estado de
// progreso real de cada fecha contable para mostrarlo debajo de la fecha.
async function renderFechasContables() {
  const host = el('fechaContablesEjecucion');
  const candidatos = derivarFechasContables(fechaInput.value).map(toISO);
  host.innerHTML = candidatos.map((iso) => `
    <button type="button" class="fechaChip${iso === fechaContableActiva ? ' active' : ''}" data-fecha="${iso}">
      <small>Fecha contable</small><b>${fechaCorta(iso)}</b><span class="chipStatus muted">Cargando…</span>
    </button>`).join('');
  host.querySelectorAll('.fechaChip').forEach((btn) => {
    btn.addEventListener('click', () => seleccionarFechaContable(btn.dataset.fecha));
  });
  await Promise.all(candidatos.map(async (iso) => {
    try {
      const r = await apiFetch(`${API}/archivos?fechaContable=${encodeURIComponent(iso)}`);
      if (!r.ok) return;
      const data = await r.json();
      const estado = calcularEstadoJornada(data.items, data.totalEsperados);
      const span = host.querySelector(`.fechaChip[data-fecha="${iso}"] .chipStatus`);
      if (span) span.outerHTML = badge(estado);
    } catch { /* deja el placeholder si falla la consulta */ }
  }));
}

// Cambia la fecha contable activa y refresca todo lo que depende de ella.
function seleccionarFechaContable(iso) {
  fechaContableActiva = iso;
  hideNoData();
  renderFechasContables();
  buscarArchivos();
}

// Se llama al cambiar (o inicializar) la fecha de conciliación: recalcula las
// fechas contables derivadas y selecciona la más reciente de ellas por defecto.
function actualizarFechaEjecucion() {
  const candidatos = derivarFechasContables(fechaInput.value).map(toISO);
  seleccionarFechaContable(candidatos[candidatos.length - 1]);
}

// Vocabulario de estados restringido al del mockup de referencia:
// Recepción: Recibido / No recibido — Procesamiento: Procesado / Pendiente / Procesando / Error
// Jornada: Completa / Con novedad / Pendiente / Error
const BADGE_CLASS = {
  Recibido: 'ok', Procesado: 'ok', Completa: 'ok',
  'No recibido': 'warn', 'Con novedad': 'warn',
  Pendiente: 'info', Procesando: 'info', Esperado: 'info',
  Error: 'bad',
};
function badge(estado) {
  if (!estado) return '<span class="badge info">-</span>';
  return `<span class="badge ${BADGE_CLASS[estado] ?? 'info'}">${estado}</span>`;
}

// Columna "Registros" de la tabla principal: mientras está "Procesando" se ve
// el avance en vivo (X / Y + barra); en cualquier otro estado, el total final.
function celdaRegistros(a) {
  if (a.estadoProcesamiento !== 'Procesando') return a.totalRegistros ?? '-';
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
function closeDrawer() { drawer.className = 'drawer'; drawerIdArchivo = null; }
el('btnCerrarDrawer').addEventListener('click', closeDrawer);

function showNoData() { noDataModal.className = 'modalBack show'; }
function hideNoData() { noDataModal.className = 'modalBack'; }
el('btnCerrarModal').addEventListener('click', hideNoData);

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

// El hero/KPIs se calculan a partir de la lista real de archivos de la fecha
// seleccionada (buscarArchivos), NO de /jornadas/actual: esa jornada no
// respeta la fecha elegida y sus contadores (archivosRecibidos/Procesados/
// totalRegistros) nunca los actualiza el backend, así que no son fiables.
function actualizarHeroDesdeArchivos(fecha, items, totalEsperados) {
  const recibidos = items.filter((a) => a.estadoRecepcion === 'Recibido').length;
  const procesados = items.filter((a) => a.estadoProcesamiento === 'Procesado').length;
  const estado = calcularEstadoJornada(items, totalEsperados);
  el('heroTitulo').textContent = `Jornada ${fecha}`;
  el('heroBadge').outerHTML = `<span id="heroBadge" class="badge ${BADGE_CLASS[estado]}">${estado}</span>`;
  const pct = totalEsperados ? (100 * procesados / totalEsperados) : 0;
  el('heroPct').textContent = `${pct.toFixed(0)}%`;
  el('heroBar').style.width = `${Math.min(100, pct)}%`;
  el('kpiEsperados').textContent = totalEsperados ?? '-';
  el('kpiRecibidos').textContent = recibidos;
  el('kpiProcesados').textContent = procesados;
  el('kpiErrores').textContent = items.filter((a) => a.estadoProcesamiento === 'Error').length;
}

async function cargarJornadaActualBadge() {
  const b = el('jornadaActualBadge');
  try {
    const r = await apiFetch(`${API}/jornadas/actual`);
    if (r.status === 204) { b.textContent = 'Jornada actual: sin registrar'; b.className = 'badge warn'; return; }
    if (!r.ok) throw new Error();
    const j = await r.json();
    b.textContent = `Jornada actual: ${j.fechaContable} (${j.estado})`;
    b.className = 'badge info';
  } catch {
    b.textContent = 'Jornada actual: n/d';
  }
}

async function buscarArchivos() {
  const fecha = fechaContableActiva;
  if (!fecha) return;
  tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Buscando...</td></tr>`;
  tblMeta.textContent = '';
  try {
    const r = await apiFetch(`${API}/archivos?fechaContable=${encodeURIComponent(fecha)}`);
    if (r.status === 204) {
      tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Sin archivos para ${fecha}.</td></tr>`;
      actualizarHeroDesdeArchivos(fecha, [], 12);
      showNoData();
      return;
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const recibidos = data.items.filter((a) => a.estadoRecepcion === 'Recibido').length;
    tblMeta.textContent = `${recibidos} de ${data.totalEsperados} insumos recibidos`;
    actualizarHeroDesdeArchivos(fecha, data.items, data.totalEsperados);
    if (!data.items.length) {
      tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Sin insumos configurados.</td></tr>`;
      return;
    }
    tblArchivos.innerHTML = data.items.map((a) => {
      const completo = a.estadoRecepcion === 'Recibido' && a.estadoProcesamiento === 'Procesado';
      const verBtn = a.idArchivo
        ? `<button type="button" class="iconBtn btnView" data-id="${a.idArchivo}" title="Ver detalle">${ICON_EYE}</button>` : '';
      const cargarBtn = !completo
        ? `<button type="button" class="iconBtn btnUpload" data-tipo="${a.tipoInsumo}" title="Cargar archivo">${ICON_UPLOAD}</button>` : '';
      return `
      <tr data-id="${a.idArchivo ?? ''}">
        <td>${a.idArchivo ?? '-'}</td>
        <td>${a.fuente}</td>
        <td>${a.tipoInsumo}</td>
        <td>${a.nombreArchivo ?? '-'}</td>
        <td>${celdaRegistros(a)}</td>
        <td>${badge(a.estadoRecepcion)}</td>
        <td>${badge(a.estadoProcesamiento)}</td>
        <td class="actionCell">${verBtn}${cargarBtn}</td>
      </tr>`;
    }).join('');
    tblArchivos.querySelectorAll('.btnView').forEach((btn) => {
      btn.addEventListener('click', () => abrirDetalle(Number(btn.dataset.id)));
    });
    tblArchivos.querySelectorAll('.btnUpload').forEach((btn) => {
      btn.addEventListener('click', () => {
        pendingTipoUpload = btn.dataset.tipo;
        const input = el('uploadFileHidden');
        input.value = '';
        input.click();
      });
    });
  } catch (e) {
    tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Error consultando archivos: ${e.message}</td></tr>`;
  }
}

async function abrirDetalle(idArchivo) {
  openDrawer();
  drawerIdArchivo = idArchivo;
  drawerContent.innerHTML = '<div class="muted">Cargando detalle...</div>';
  try {
    await pintarDetalle(idArchivo, true);
  } catch (e) {
    drawerContent.innerHTML = `<div class="muted">Error consultando detalle: ${e.message}</div>`;
  }
}

// Separado de abrirDetalle para poder llamarlo en cada tick del polling y
// refrescar solo los datos (registros/estado + tabla de contenido), sin
// recrear el drawer completo cada vez (perdería la página de paginación, el
// scroll, etc.)
async function pintarDetalle(idArchivo, primeraVez) {
  const r = await apiFetch(`${API}/archivos/${idArchivo}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const d = await r.json();
  const kv = (label, value) => `<div class="kv"><b>${label}</b><span>${value ?? '-'}</span></div>`;
  const registrosHtml = d.estadoProcesamiento === 'Procesando'
    ? celdaRegistros({ estadoProcesamiento: d.estadoProcesamiento, totalRegistros: d.totalRegistros, registrosProcesados: d.registrosProcesados })
    : (d.totalRegistros ?? '-');
  if (primeraVez) {
    contenidoState = { idArchivo, page: 0, size: 30, tipoInsumo: null };
    drawerContent.innerHTML = `
      <h2>${d.nombreArchivo ?? '(sin nombre)'}</h2>
      <div class="muted">Archivo #${d.idArchivo}</div>
      <div class="detailGrid section">
        <div class="kv" id="kvRegistros"><b>Registros</b><span>${registrosHtml}</span></div>
        <div class="kv" id="kvRecepcion"><b>Recepción</b><span>${badge(d.estadoRecepcion)}</span></div>
        <div class="kv" id="kvProcesamiento"><b>Procesamiento</b><span>${badge(d.estadoProcesamiento)}</span></div>
        ${kv('Correlation ID', d.correlationId)}
      </div>
      <h3>Contenido <span id="contenidoTotal" class="muted"></span></h3>
      <div class="tableScroll"><table id="tblContenido"><thead></thead><tbody></tbody></table></div>
      <div class="pager">
        <button id="btnPrev" class="btn">&laquo; Anterior</button>
        <span id="pagerInfo" class="muted"></span>
        <button id="btnNext" class="btn">Siguiente &raquo;</button>
      </div>`;
    el('btnPrev').addEventListener('click', () => { if (contenidoState.page > 0) { contenidoState.page -= 1; cargarContenido(); } });
    el('btnNext').addEventListener('click', () => { contenidoState.page += 1; cargarContenido(); });
    await cargarContenido();
  } else {
    const kvR = el('kvRegistros'); if (kvR) kvR.querySelector('span').innerHTML = registrosHtml;
    const kvRec = el('kvRecepcion'); if (kvRec) kvRec.querySelector('span').innerHTML = badge(d.estadoRecepcion);
    const kvProc = el('kvProcesamiento'); if (kvProc) kvProc.querySelector('span').innerHTML = badge(d.estadoProcesamiento);
    // Mientras procesa, se re-consulta la página actual para ver cómo va
    // creciendo el contenido guardado en base; ya terminado se refresca una
    // última vez para mostrar el resultado final.
    await cargarContenido();
  }
}

async function cargarContenido() {
  const { idArchivo, page, size } = contenidoState;
  const tbl = el('tblContenido');
  if (!tbl) return;
  tbl.querySelector('thead').innerHTML = '';
  tbl.querySelector('tbody').innerHTML = `<tr><td class="muted">Cargando...</td></tr>`;
  el('contenidoTotal').textContent = '';
  try {
    const r = await apiFetch(`${API}/archivos/${idArchivo}/contenido?page=${page}&size=${size}`);
    if (r.status === 409) {
      tbl.querySelector('tbody').innerHTML = `<tr><td class="muted">Archivo aún no disponible.</td></tr>`;
      el('pagerInfo').textContent = '';
      return;
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    el('contenidoTotal').textContent = `(${data.total} registros — ${data.tipoInsumo})`;
    const items = data.items || [];
    if (!items.length) {
      tbl.querySelector('tbody').innerHTML = `<tr><td class="muted">Sin registros.</td></tr>`;
    } else if (Array.isArray(items[0])) {
      tbl.querySelector('tbody').innerHTML = items.map((row) =>
        `<tr>${row.map((v) => `<td>${v === null || v === undefined ? '' : v}</td>`).join('')}</tr>`).join('');
    } else {
      const cols = Object.keys(items[0]);
      tbl.querySelector('thead').innerHTML = `<tr>${cols.map((c) => `<th>${c}</th>`).join('')}</tr>`;
      tbl.querySelector('tbody').innerHTML = items.map((row) =>
        `<tr>${cols.map((c) => `<td>${row[c] ?? ''}</td>`).join('')}</tr>`).join('');
    }
    const totalPages = Math.max(1, Math.ceil(data.total / size));
    el('pagerInfo').textContent = `Página ${page + 1} de ${totalPages}`;
    el('btnPrev').disabled = page <= 0;
    el('btnNext').disabled = page + 1 >= totalPages;
  } catch (e) {
    tbl.querySelector('tbody').innerHTML = `<tr><td class="muted">Error: ${e.message}</td></tr>`;
  }
}

async function subirArchivo(tipoInsumo, file) {
  const fecha = fechaContableActiva;
  const resultado = el('cargaResultado');
  if (!fecha) { toast('Selecciona una fecha contable.', true); return; }
  resultado.innerHTML = `Subiendo ${tipoInsumo}...`;
  const form = new FormData();
  form.append('fechaContable', fecha);
  form.append('tipoInsumo', tipoInsumo);
  form.append('file', file);
  try {
    // La subida ya no espera a que termine el parseo (puede tardar minutos en
    // archivos grandes) — responde apenas el archivo queda en MinIO, y el
    // avance real se sigue con polling en iniciarPolling().
    const r = await apiFetch(`${API}/archivos`, { method: 'POST', body: form });
    const data = await r.json();
    if (!r.ok) {
      resultado.textContent = `Error: ${data.detail ?? r.status}`;
      toast(`Error al cargar ${tipoInsumo}: ${data.detail ?? r.status}`, true);
      return;
    }
    await buscarArchivos();
    iniciarPolling(data.idArchivo, tipoInsumo);
  } catch (e) {
    resultado.textContent = `Error de red: ${e.message}`;
    toast('Error de red al cargar el archivo', true);
  }
}

// Sondea GET /api/v1/archivos/{id} cada segundo mientras el archivo está en
// "Procesando", actualizando: (1) el panel de carga con una barra de
// progreso, (2) la tabla principal (fila del insumo), y (3) el drawer de
// detalle si está abierto mostrando este mismo archivo. Se detiene solo al
// llegar a un estado terminal (Procesado/Error).
function iniciarPolling(idArchivo, tipoInsumo) {
  if (pollers.has(idArchivo)) return; // ya hay un polling activo para este archivo
  const resultado = el('cargaResultado');
  const tick = async () => {
    try {
      const r = await apiFetch(`${API}/archivos/${idArchivo}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      resultado.innerHTML = `
        <div class="progressMeta"><b>${d.nombreArchivo ?? tipoInsumo}</b><span>${badge(d.estadoProcesamiento)}</span></div>
        ${celdaRegistros(d)}` + (d.motivoEstado ? `<div class="muted">${d.motivoEstado}</div>` : '');
      await buscarArchivos();
      if (drawerIdArchivo === idArchivo) await pintarDetalle(idArchivo, false);
      if (d.estadoProcesamiento === 'Procesado' || d.estadoProcesamiento === 'Error') {
        clearInterval(pollers.get(idArchivo));
        pollers.delete(idArchivo);
        await cargarJornadaActualBadge();
        if (d.estadoProcesamiento === 'Procesado') toast(`${tipoInsumo} cargado: ${d.totalRegistros ?? d.registrosProcesados} registros`);
        else toast(`${tipoInsumo}: error en el procesamiento — ${d.motivoEstado ?? ''}`, true);
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
  if (file && pendingTipoUpload) subirArchivo(pendingTipoUpload, file);
  pendingTipoUpload = null;
});

fechaInput.addEventListener('change', actualizarFechaEjecucion);

// ---- Navegación de pestañas (Insumos / Conciliación / Agente IA) ----
function go(id, btn) {
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el(id).classList.add('active');
  document.querySelectorAll('.nav button').forEach((b) => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  window.scrollTo(0, 0);
}

// ---- Conciliación (datos de ejemplo, ver aviso en la pantalla) ----
function filterReconRows() {
  const q = (el('reconQ').value || '').toLowerCase();
  const fr = el('reconFr').value || '';
  const st = el('reconSt').value || '';
  document.querySelectorAll('#recon tbody tr').forEach((r) => {
    const okq = r.innerText.toLowerCase().includes(q);
    const okfr = !fr || r.dataset.franchise === fr;
    const okst = !st || r.dataset.filterStatus === st;
    r.style.display = okq && okfr && okst ? 'table-row' : 'none';
  });
}

function verDetalleRecon(cta, tx, vf, vh) {
  drawerContent.innerHTML = `<h2>Detalle de conciliación (ejemplo)</h2><span class="badge info">${cta}</span>
    <div class="explain"><b>Origen Host:</b> ${tx} · dato de ejemplo, no consultado del backend real.</div>
    <table><thead><tr><th>Lado</th><th>Valor</th></tr></thead><tbody>
      <tr><td>Franquicia</td><td>${vf}</td></tr>
      <tr><td>Host</td><td>${vh}</td></tr>
      <tr><td>Resultado</td><td>${vf === vh ? 'Conciliado' : 'Diferencia'}</td></tr>
    </tbody></table>`;
  openDrawer();
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

bootstrapAuth();
