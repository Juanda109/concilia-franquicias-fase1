const API = '/api/v1';
const el = (id) => document.getElementById(id);

const fechaInput = el('fecha');
const tblArchivos = el('tblArchivos');
const tblMeta = el('tblMeta');
const drawer = el('drawer');
const drawerContent = el('drawerContent');
const toastEl = el('toast');
const noDataModal = el('noDataModal');
const detalleInsumoContent = el('detalleInsumoContent');
let insumosScrollY = 0;

let toastTimer = null;
let pendingIdArchivoUpload = null;
const pollers = new Map(); // idArchivo -> intervalId, para no duplicar polling si se sube el mismo archivo dos veces

// Íconos minimalistas (SVG en línea, trazo simple, sin dependencias externas)
const ICON_EYE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
const ICON_UPLOAD = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>';

function toISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function fechaCorta(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  let dia = new Date(y, m - 1, d).toLocaleDateString('es-ES', { weekday: 'short' }).replace('.', '');
  dia = dia.charAt(0).toUpperCase() + dia.slice(1);
  return `${dia} ${String(d).padStart(2, '0')}`;
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

// ---- Insumos: Fecha de conciliación -> jornada(s) contable(s) (backend) ----
let idJornadaActiva = null;
let jornadasEjecucion = []; // última respuesta de GET /jornadas?fechaConciliacion=

async function actualizarFechaConciliacion() {
  const host = el('fechaContablesEjecucion');
  host.innerHTML = '<span class="muted">Consultando…</span>';
  try {
    const r = await fetch(`${API}/jornadas?fechaConciliacion=${encodeURIComponent(fechaInput.value)}`);
    if (r.status === 204) {
      jornadasEjecucion = [];
      host.innerHTML = '';
      idJornadaActiva = null;
      tblArchivos.innerHTML = `<tr><td colspan="8" class="muted">Sin información para esta fecha.</td></tr>`;
      actualizarHero(null);
      showNoData();
      return;
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    jornadasEjecucion = data.jornadas;
    seleccionarJornada(jornadasEjecucion[jornadasEjecucion.length - 1].idJornada);
  } catch (e) {
    host.innerHTML = `<span class="muted">Error consultando jornadas: ${e.message}</span>`;
  }
}

function renderFechasContables() {
  const host = el('fechaContablesEjecucion');
  host.innerHTML = jornadasEjecucion.map((j) => `
    <button type="button" class="fechaChip${j.idJornada === idJornadaActiva ? ' active' : ''}" data-id="${j.idJornada}">
      <small>Fecha contable</small><b>${fechaCorta(j.fechaContable)}</b>${badge(j.estado)}
    </button>`).join('');
  host.querySelectorAll('.fechaChip').forEach((btn) => {
    btn.addEventListener('click', () => seleccionarJornada(Number(btn.dataset.id)));
  });
}

function seleccionarJornada(idJornada) {
  idJornadaActiva = idJornada;
  hideNoData();
  renderFechasContables();
  cargarJornada();
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
    const r = await fetch(`${API}/jornadas/${idJornadaActiva}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    tblMeta.textContent = `${d.archivosRecibidos} de ${d.archivosEsperados} insumos recibidos`;
    actualizarHero(d);
    renderTablaInsumos(d.insumos);
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
    const verBtn = acciones.includes('VER_CONTENIDO')
      ? `<button type="button" class="iconBtn btnView" data-id="${a.idArchivo}" title="Ver detalle">${ICON_EYE}</button>` : '';
    const cargarBtn = acciones.includes('CARGAR_ARCHIVO_ORIGINAL')
      ? `<button type="button" class="iconBtn btnUpload" data-id="${a.idArchivo}" title="Cargar archivo original">${ICON_UPLOAD}</button>` : '';
    return `
    <tr data-id="${a.idArchivo}">
      <td>${a.idArchivo}</td>
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
      pendingIdArchivoUpload = Number(btn.dataset.id);
      const input = el('uploadFileHidden');
      input.value = '';
      input.click();
    });
  });
}

// ---- Vista dedicada de detalle de un insumo ----
let detalleIdArchivo = null;
let detallePagina = 0;
const DETALLE_PAGE_SIZE = 30;

function abrirDetalle(idArchivo) {
  detalleIdArchivo = idArchivo;
  detallePagina = 0;
  insumosScrollY = window.scrollY;
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el('detalleInsumo').classList.add('active');
  window.scrollTo(0, 0);
  cargarContenidoDetalle();
}

function volverAInsumos() {
  detalleIdArchivo = null;
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  el('insumos').classList.add('active');
  requestAnimationFrame(() => window.scrollTo(0, insumosScrollY));
}
el('btnVolverInsumos').addEventListener('click', volverAInsumos);

async function cargarContenidoDetalle() {
  const idArchivo = detalleIdArchivo;
  try {
    const r = await fetch(`${API}/archivos/${idArchivo}/contenido?page=${detallePagina}&pageSize=${DETALLE_PAGE_SIZE}`);
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
  const { page, pageSize, totalItems, totalPages } = d.pagination;
  const start = totalItems ? page * pageSize + 1 : 0;
  const end = Math.min(page * pageSize + d.items.length, totalItems);

  const contenidoHtml = !d.items.length
    ? '<div class="emptyDetail">El archivo no tiene contenido disponible para visualizar en esta página.</div>'
    : (() => {
        const thead = `<tr>${d.headers.map((c) => `<th>${c.label}</th>`).join('')}</tr>`;
        const tbody = d.items.map((row) => `<tr>${d.headers.map((c) => `<td>${row[c.key] ?? ''}</td>`).join('')}</tr>`).join('');
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
    </div>

    <details class="techDetails">
      <summary>Información técnica</summary>
      <div class="techGrid">
        <b>ID de archivo</b><span>${d.idArchivo}</span>
        <b>Correlation ID</b><span>${d.correlationId ?? '-'}</span>
      </div>
    </details>`;

  el('btnDetalleAnterior')?.addEventListener('click', () => cambiarPaginaDetalle(-1));
  el('btnDetalleSiguiente')?.addEventListener('click', () => cambiarPaginaDetalle(1));
}

function cambiarPaginaDetalle(delta) {
  detallePagina += delta;
  cargarContenidoDetalle();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---- Carga manual del archivo original ----
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
    const r = await fetch(`${API}/jornadas/${idJornadaActiva}/archivos`, { method: 'POST', body: form });
    if (!r.ok) {
      // El cuerpo del error no siempre es JSON (ej. nginx devuelve HTML en un
      // 413 "archivo muy grande") — probar JSON primero, caer a texto plano
      // si falla, para no confundir esto con un error de red real.
      let detalle = `HTTP ${r.status}`;
      try { detalle = (await r.json()).detail ?? detalle; } catch { /* cuerpo no es JSON */ }
      if (r.status === 413) detalle = 'El archivo es demasiado grande para el límite configurado.';
      resultado.textContent = `Error: ${detalle}`;
      toast(`Error al cargar el archivo: ${detalle}`, true);
      return;
    }
    await r.json();
    await cargarJornada();
    iniciarPolling(idArchivo);
  } catch (e) {
    resultado.textContent = `Error de red: ${e.message}`;
    toast('Error de red al cargar el archivo', true);
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
        else toast(`${a.tipoInsumo}: error en el procesamiento`, true);
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

fechaInput.value = toISO(new Date());
fechaInput.addEventListener('change', actualizarFechaConciliacion);

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

checkHealth();
actualizarFechaConciliacion();
