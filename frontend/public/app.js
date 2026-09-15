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

function todayISO() { return new Date().toISOString().slice(0, 10); }
fechaInput.value = todayISO();

function badge(estado) {
  if (!estado) return '<span class="badge info">-</span>';
  const e = estado.toUpperCase();
  let cls = 'info';
  if (e.includes('ERROR')) cls = 'bad';
  else if (['CARGADO', 'PROCESADO', 'VALIDADO', 'RECIBIDO', 'DISPONIBLE'].includes(e)) cls = 'ok';
  else if (e.includes('PENDIENTE') || e.includes('NO_INICIAD') || e.includes('REINTENTANDO')) cls = 'warn';
  return `<span class="badge ${cls}">${estado}</span>`;
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
  const recibidos = items.length;
  const procesados = items.filter((a) => a.estadoProcesamiento === 'PROCESADO').length;
  const cargados = items.filter((a) => a.estadoCarga === 'CARGADO').length;
  const conError = items.some((a) => [a.estadoValidacion, a.estadoProcesamiento, a.estadoCarga].some((e) => (e || '').includes('ERROR')));
  el('heroTitulo').textContent = `Jornada ${fecha}`;
  const estado = conError ? 'CON_ERRORES' : (cargados >= totalEsperados ? 'COMPLETA' : (recibidos > 0 ? 'EN_PROCESO' : 'SIN_DATOS'));
  const cls = conError ? 'bad' : (estado === 'COMPLETA' ? 'ok' : (estado === 'SIN_DATOS' ? 'info' : 'warn'));
  el('heroBadge').outerHTML = `<span id="heroBadge" class="badge ${cls}">${estado}</span>`;
  const pct = totalEsperados ? (100 * cargados / totalEsperados) : 0;
  el('heroPct').textContent = `${pct.toFixed(0)}%`;
  el('heroBar').style.width = `${Math.min(100, pct)}%`;
  el('kpiEsperados').textContent = totalEsperados ?? '-';
  el('kpiRecibidos').textContent = recibidos;
  el('kpiProcesados').textContent = procesados;
  el('kpiCargados').textContent = cargados;
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
  const fecha = fechaInput.value;
  if (!fecha) return;
  tblArchivos.innerHTML = `<tr><td colspan="10" class="muted">Buscando...</td></tr>`;
  tblMeta.textContent = '';
  try {
    const r = await fetch(`${API}/archivos?fechaContable=${encodeURIComponent(fecha)}`);
    if (r.status === 204) {
      tblArchivos.innerHTML = `<tr><td colspan="10" class="muted">Sin archivos para ${fecha}.</td></tr>`;
      actualizarHeroDesdeArchivos(fecha, [], 12);
      showNoData();
      return;
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    tblMeta.textContent = `${data.items.length} de ${data.totalEsperados} insumos`;
    actualizarHeroDesdeArchivos(fecha, data.items, data.totalEsperados);
    if (!data.items.length) {
      tblArchivos.innerHTML = `<tr><td colspan="10" class="muted">Sin archivos para ${fecha}.</td></tr>`;
      return;
    }
    tblArchivos.innerHTML = data.items.map((a) => `
      <tr class="clickable" data-id="${a.idArchivo}">
        <td>${a.idArchivo}</td>
        <td>${a.fuente}</td>
        <td>${a.tipoInsumo}</td>
        <td>${a.nombreArchivo ?? '-'}</td>
        <td>${a.totalRegistros ?? '-'}</td>
        <td>${badge(a.estadoRecepcion)}</td>
        <td>${badge(a.estadoValidacion)}</td>
        <td>${badge(a.estadoProcesamiento)}</td>
        <td>${badge(a.estadoCarga)}</td>
        <td>${a.disponible ? '<span class="badge ok">SI</span>' : '<span class="badge warn">NO</span>'}</td>
      </tr>`).join('');
    tblArchivos.querySelectorAll('tr.clickable').forEach((row) => {
      row.addEventListener('click', () => abrirDetalle(Number(row.dataset.id)));
    });
  } catch (e) {
    tblArchivos.innerHTML = `<tr><td colspan="10" class="muted">Error consultando archivos: ${e.message}</td></tr>`;
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
        ${kv('Validación', badge(d.estadoValidacion))}
        ${kv('Procesamiento', badge(d.estadoProcesamiento))}
        ${kv('Carga', badge(d.estadoCarga))}
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

async function cargarArchivo() {
  const fecha = fechaInput.value;
  const tipoInsumo = el('tipoInsumo').value;
  const resultado = el('cargaResultado');
  if (!fecha) {
    resultado.textContent = 'Selecciona una fecha contable.';
    return;
  }
  resultado.textContent = 'Buscando en la ruta estática y procesando...';
  try {
    const r = await fetch(`${API}/archivos?fechaContable=${encodeURIComponent(fecha)}&tipoInsumo=${encodeURIComponent(tipoInsumo)}`, { method: 'POST' });
    const data = await r.json();
    if (!r.ok) {
      const detalle = data.detail === 'ARCHIVO_NO_ENCONTRADO_EN_RUTA'
        ? 'No hay ningún archivo en backend/data/incoming/ que coincida con el patrón de este insumo.'
        : (data.detail ?? r.status);
      resultado.textContent = `Error: ${detalle}`;
      toast(`Error al procesar: ${detalle}`, true);
      return;
    }
    resultado.textContent =
      `${data.nombreArchivo} (${data.rutaOrigen}) · Carga: ${data.estadoCarga} · Registros insertados: ${data.registrosInsertados}` +
      (data.errores?.length ? ` · Errores: ${data.errores.length}` : '');
    toast(`${tipoInsumo} procesado: ${data.registrosInsertados} registros`);
    await buscarArchivos();
    await cargarJornadaActualBadge();
  } catch (e) {
    resultado.textContent = `Error de red: ${e.message}`;
    toast('Error de red al cargar el archivo', true);
  }
}

fechaInput.addEventListener('change', () => { hideNoData(); buscarArchivos(); });
el('btnCargar').addEventListener('click', cargarArchivo);

checkHealth();
cargarJornadaActualBadge();
buscarArchivos();
