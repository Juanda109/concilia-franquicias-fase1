const API = '/api/v1';
const el = (id) => document.getElementById(id);

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

// Solo pinta las fichas y resalta la activa — nunca decide cuál es la activa.
function renderFechasContables() {
  const host = el('fechaContablesEjecucion');
  const candidatos = derivarFechasContables(fechaInput.value).map(toISO);
  host.innerHTML = candidatos.map((iso) => `
    <button type="button" class="fechaChip${iso === fechaContableActiva ? ' active' : ''}" data-fecha="${iso}">
      <small>Fecha contable</small><b>${fechaCorta(iso)}</b>
    </button>`).join('');
  host.querySelectorAll('.fechaChip').forEach((btn) => {
    btn.addEventListener('click', () => seleccionarFechaContable(btn.dataset.fecha));
  });
}

// Cambia la fecha contable activa y refresca todo lo que depende de ella.
function seleccionarFechaContable(iso) {
  fechaContableActiva = iso;
  hideNoData();
  renderFechasContables();
  cargarFechasChips();
  buscarArchivos();
}

// Se llama al cambiar (o inicializar) la fecha de conciliación: recalcula las
// fechas contables derivadas y selecciona la más reciente de ellas por defecto.
function actualizarFechaEjecucion() {
  const candidatos = derivarFechasContables(fechaInput.value).map(toISO);
  seleccionarFechaContable(candidatos[candidatos.length - 1]);
}

fechaInput.value = toISO(new Date());
actualizarFechaEjecucion();

// Vocabulario de estados restringido al del mockup de referencia:
// Recepción: Recibido / No recibido — Procesamiento: Procesado / Pendiente / Procesando / Error
// Jornada: Completa / Con novedad / Pendiente / Error
const BADGE_CLASS = {
  Recibido: 'ok', Procesado: 'ok', Completa: 'ok', Disponible: 'ok',
  'No recibido': 'warn', 'Con novedad': 'warn', 'No disponible': 'warn',
  Pendiente: 'info', Procesando: 'info', Esperado: 'info',
  Error: 'bad',
};
function badge(estado) {
  if (!estado) return '<span class="badge info">-</span>';
  return `<span class="badge ${BADGE_CLASS[estado] ?? 'info'}">${estado}</span>`;
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

// El hero/KPIs se calculan a partir de la lista real de archivos de la fecha
// seleccionada (buscarArchivos), NO de /jornadas/actual: esa jornada no
// respeta la fecha elegida y sus contadores (archivosRecibidos/Procesados/
// totalRegistros) nunca los actualiza el backend, así que no son fiables.
function actualizarHeroDesdeArchivos(fecha, items, totalEsperados) {
  const recibidos = items.filter((a) => a.estadoRecepcion === 'Recibido').length;
  const procesados = items.filter((a) => a.estadoProcesamiento === 'Procesado').length;
  const conError = items.some((a) => a.estadoProcesamiento === 'Error');
  el('heroTitulo').textContent = `Jornada ${fecha}`;
  // Vocabulario de jornada tomado del mockup: Completa / Con novedad / Pendiente / Error
  const estado = conError ? 'Error'
    : procesados >= totalEsperados ? 'Completa'
    : (recibidos > 0 && recibidos < totalEsperados) ? 'Con novedad'
    : 'Pendiente';
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
    const r = await fetch(`${API}/jornadas/actual`);
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
  tblArchivos.innerHTML = `<tr><td colspan="9" class="muted">Buscando...</td></tr>`;
  tblMeta.textContent = '';
  try {
    const r = await fetch(`${API}/archivos?fechaContable=${encodeURIComponent(fecha)}`);
    if (r.status === 204) {
      tblArchivos.innerHTML = `<tr><td colspan="9" class="muted">Sin archivos para ${fecha}.</td></tr>`;
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
      tblArchivos.innerHTML = `<tr><td colspan="9" class="muted">Sin insumos configurados.</td></tr>`;
      return;
    }
    tblArchivos.innerHTML = data.items.map((a) => `
      <tr class="${a.idArchivo ? 'clickable' : ''}" data-id="${a.idArchivo ?? ''}">
        <td>${a.idArchivo ?? '-'}</td>
        <td>${a.fuente}</td>
        <td>${a.tipoInsumo}</td>
        <td>${a.nombreArchivo ?? '-'}</td>
        <td>${a.totalRegistros ?? '-'}</td>
        <td>${badge(a.estadoRecepcion)}</td>
        <td>${badge(a.estadoProcesamiento)}</td>
        <td>${badge(a.estadoDisponibilidad)}</td>
        <td><button type="button" class="btn primary btnUpload" data-tipo="${a.tipoInsumo}">Cargar</button></td>
      </tr>`).join('');
    tblArchivos.querySelectorAll('tr.clickable').forEach((row) => {
      row.addEventListener('click', () => abrirDetalle(Number(row.dataset.id)));
    });
    tblArchivos.querySelectorAll('.btnUpload').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        pendingTipoUpload = btn.dataset.tipo;
        const input = el('uploadFileHidden');
        input.value = '';
        input.click();
      });
    });
  } catch (e) {
    tblArchivos.innerHTML = `<tr><td colspan="9" class="muted">Error consultando archivos: ${e.message}</td></tr>`;
  }
}

async function cargarFechasChips() {
  const host = el('fechaChips');
  try {
    const r = await fetch(`${API}/jornadas/fechas?limit=14`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    if (!data.items.length) { host.innerHTML = ''; return; }
    host.innerHTML = data.items.map((j) => `
      <button type="button" class="fechaChip${j.fechaContable === fechaContableActiva ? ' active' : ''}" data-fecha="${j.fechaContable}">
        <small>Fecha contable</small><b>${fechaCorta(j.fechaContable)}</b>${badge(j.estado)}
      </button>`).join('');
    host.querySelectorAll('.fechaChip').forEach((btn) => {
      btn.addEventListener('click', () => seleccionarFechaContable(btn.dataset.fecha));
    });
  } catch {
    host.innerHTML = '';
  }
}

async function abrirDetalle(idArchivo) {
  openDrawer();
  drawerContent.innerHTML = '<div class="muted">Cargando detalle...</div>';
  try {
    const r = await fetch(`${API}/archivos/${idArchivo}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    contenidoState = { idArchivo, page: 0, size: 30, tipoInsumo: null };
    const kv = (label, value) => `<div class="kv"><b>${label}</b><span>${value ?? '-'}</span></div>`;
    drawerContent.innerHTML = `
      <h2>${d.nombreArchivo ?? '(sin nombre)'}</h2>
      <div class="muted">Archivo #${d.idArchivo}</div>
      <div class="detailGrid section">
        ${kv('Registros', d.totalRegistros)}
        ${kv('Recepción', badge(d.estadoRecepcion))}
        ${kv('Procesamiento', badge(d.estadoProcesamiento))}
        ${kv('Disponibilidad', badge(d.estadoDisponibilidad))}
        ${kv('Disponible', d.disponible ? 'Sí' : 'No')}
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
  } catch (e) {
    drawerContent.innerHTML = `<div class="muted">Error consultando detalle: ${e.message}</div>`;
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
    const r = await fetch(`${API}/archivos/${idArchivo}/contenido?page=${page}&size=${size}`);
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
  resultado.textContent = `Cargando ${tipoInsumo}...`;
  const form = new FormData();
  form.append('fechaContable', fecha);
  form.append('tipoInsumo', tipoInsumo);
  form.append('file', file);
  try {
    const r = await fetch(`${API}/archivos`, { method: 'POST', body: form });
    const data = await r.json();
    if (!r.ok) {
      resultado.textContent = `Error: ${data.detail ?? r.status}`;
      toast(`Error al cargar ${tipoInsumo}: ${data.detail ?? r.status}`, true);
      return;
    }
    resultado.textContent =
      `${data.nombreArchivo} · Procesamiento: ${data.estadoProcesamiento} · Registros insertados: ${data.registrosInsertados}` +
      (data.errores?.length ? ` · Errores: ${data.errores.length}` : '');
    toast(`${tipoInsumo} cargado: ${data.registrosInsertados} registros`);
    await buscarArchivos();
    await cargarJornadaActualBadge();
    await cargarFechasChips();
  } catch (e) {
    resultado.textContent = `Error de red: ${e.message}`;
    toast('Error de red al cargar el archivo', true);
  }
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

checkHealth();
cargarJornadaActualBadge();
