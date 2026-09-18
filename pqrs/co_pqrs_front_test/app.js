const STORAGE_KEY = "pqrs-static-front-v1";
const CSV_PATH = "./Muestra_tabla_embargos.csv";
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_METRICS_CONFIG = {
  proxyUrl: "http://127.0.0.1:8090",
  endpoint: "https://localhost:9200",
  user: "admin",
  password: "admin",
  conversationsIndex: "conversations-reference",
  messagesIndex: "conversations-messages",
  timeoutSeconds: 10,
};
const WELCOME_SUGGESTIONS = ["Hola", "Solicitud", "Riesgo"];

(function installMultiSelectStyles() {
  if (document.getElementById("multi-select-inline-styles")) return;
  const style = document.createElement("style");
  style.id = "multi-select-inline-styles";
  style.textContent = `
    .multi-select-options { display: grid; gap: 8px; margin-top: 12px; }
    .multi-select-option { width: 100%; display: flex; align-items: flex-start; gap: 10px; text-align: left; border: 1px solid rgba(23,50,77,.12); border-radius: 14px; padding: 12px 14px; background: #fff; color: inherit; cursor: pointer; }
    .multi-select-option.selected { border-color: rgba(23,50,77,.28); background: rgba(23,50,77,.05); }
    .multi-select-check { font-size: 18px; line-height: 1; flex: 0 0 auto; }
  `;
  document.head.appendChild(style);
})();

const state = {
  apiBaseUrl: DEFAULT_API_BASE_URL,
  currentView: "chat",
  messages: [],
  healthStatus: null,
  healthMessage: "",
  selectedCustomerId: "",
  conversationDate: todayInputValue(),
  conversationId: "",
  conversationStatus: null,
  pendingPollingConversationId: "",
  draftCustomerId: "",
  draftCustomerIdManual: "",
  draftProductId: "",
  draftConversationDate: todayInputValue(),
  chatDraft: "",
  chatNotice: null,
  customerOptions: [],
  csvStatus: "idle",
  csvError: "",
  metricsConfig: { ...DEFAULT_METRICS_CONFIG },
  metricsSnapshot: null,
  metricsError: "",
  metricsLoading: false,
  metricsConfigDirty: false,
  metricsConfigExpanded: false,
  lastMetricsLoadedAt: null,
  toasts: [],
  busy: {
    health: false,
    chat: false,
    endConversation: false,
    polling: false,
    deleteConversation: false,
    csv: false,
  },
};

document.addEventListener("DOMContentLoaded", () => {
  hydrateState();
  normalizeConversationState();
  renderApp();
  void loadCustomerOptions();
});

function hydrateState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return;
    }

    const saved = JSON.parse(raw);
    if (!saved || typeof saved !== "object") {
      return;
    }

    state.apiBaseUrl = normalizeBaseUrl(saved.apiBaseUrl || DEFAULT_API_BASE_URL);
    state.currentView = ["chat", "metrics", "health"].includes(saved.currentView)
      ? saved.currentView
      : "chat";
    state.messages = Array.isArray(saved.messages) ? saved.messages : [];
    state.selectedCustomerId = cleanString(saved.selectedCustomerId);
    state.conversationDate = normalizeInputDate(saved.conversationDate) || todayInputValue();
    state.conversationId = cleanString(saved.conversationId);
    state.conversationStatus = cleanString(saved.conversationStatus);
    state.pendingPollingConversationId = cleanString(saved.pendingPollingConversationId);
    state.draftCustomerId = cleanString(saved.draftCustomerId);
    state.draftCustomerIdManual = cleanString(saved.draftCustomerIdManual);
    state.draftProductId = cleanString(saved.draftProductId);
    state.draftConversationDate =
      normalizeInputDate(saved.draftConversationDate) || state.conversationDate;
    state.chatDraft = cleanString(saved.chatDraft);
    const savedMetricsConfig =
      saved.metricsConfig && typeof saved.metricsConfig === "object" ? saved.metricsConfig : {};
    state.metricsConfig = {
      ...DEFAULT_METRICS_CONFIG,
      ...savedMetricsConfig,
    };
    state.metricsConfig.proxyUrl =
      cleanString(state.metricsConfig.proxyUrl) || DEFAULT_METRICS_CONFIG.proxyUrl;
    state.metricsConfig.endpoint = cleanString(state.metricsConfig.endpoint) || DEFAULT_METRICS_CONFIG.endpoint;
    state.metricsConfig.user = Object.prototype.hasOwnProperty.call(savedMetricsConfig, "user")
      ? cleanString(savedMetricsConfig.user)
      : cleanString(state.metricsConfig.user) || DEFAULT_METRICS_CONFIG.user;
    state.metricsConfig.password = Object.prototype.hasOwnProperty.call(savedMetricsConfig, "password")
      ? cleanString(savedMetricsConfig.password)
      : cleanString(state.metricsConfig.password) || DEFAULT_METRICS_CONFIG.password;
    state.metricsConfig.conversationsIndex =
      cleanString(state.metricsConfig.conversationsIndex) || DEFAULT_METRICS_CONFIG.conversationsIndex;
    state.metricsConfig.messagesIndex =
      cleanString(state.metricsConfig.messagesIndex) || DEFAULT_METRICS_CONFIG.messagesIndex;
    state.metricsConfig.timeoutSeconds = normalizePositiveNumber(
      state.metricsConfig.timeoutSeconds,
      DEFAULT_METRICS_CONFIG.timeoutSeconds,
    );
    state.metricsConfigDirty = Boolean(saved.metricsConfigDirty);
    state.metricsConfigExpanded = Boolean(saved.metricsConfigExpanded);
  } catch (error) {
    console.error("No pude restaurar el estado local:", error);
  }
}

function persistState() {
  const payload = {
    apiBaseUrl: state.apiBaseUrl,
    currentView: state.currentView,
    messages: state.messages,
    selectedCustomerId: state.selectedCustomerId,
    conversationDate: state.conversationDate,
    conversationId: state.conversationId,
    conversationStatus: state.conversationStatus,
    pendingPollingConversationId: state.pendingPollingConversationId,
    draftCustomerId: state.draftCustomerId,
    draftCustomerIdManual: state.draftCustomerIdManual,
    draftProductId: state.draftProductId,
    draftConversationDate: state.draftConversationDate,
    chatDraft: state.chatDraft,
    metricsConfig: state.metricsConfig,
    metricsConfigDirty: state.metricsConfigDirty,
    metricsConfigExpanded: state.metricsConfigExpanded,
  };

  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

function renderApp() {
  const root = document.getElementById("app");
  if (!root) {
    return;
  }

  root.className = "";

  root.innerHTML = `
    <div class="page-shell">
      ${renderTopbar()}
      <div class="app-shell">
        ${renderSidebar()}
        <main class="main-shell">
          ${renderCurrentView()}
        </main>
      </div>
    </div>
  `;

  bindEvents();
  renderToasts();
  persistState();

  if (state.currentView === "chat") {
    scrollChatToBottom();
  }
}

function renderCurrentView() {
  if (state.currentView === "metrics") {
    return renderMetricsView();
  }

  if (state.currentView === "health") {
    return renderHealthView();
  }

  return renderChatView();
}

function renderBbvaLogo() {
  return `
    <span class="bbva-logo" role="img" aria-label="BBVA">
      <svg viewBox="0 0 168 42" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
        <text x="0" y="31" class="bbva-logo-text">BBVA</text>
      </svg>
    </span>
  `;
}

function renderTopbar() {
  return `
    <header class="topbar">
      <div class="topbar-brand">
        ${renderBbvaLogo()}
        <span class="topbar-divider" aria-hidden="true"></span>
        <div class="topbar-copy">
          <strong>Agente PQRs</strong>
          <p class="brand-tagline">AMBIENTE DE EXPERIMENTACIÓN INTERNO</p>
        </div>
      </div>

      <nav class="topbar-nav" aria-label="Navegacion principal">
        <button
          class="site-link ${state.currentView === "chat" ? "active" : ""}"
          data-view="chat"
          type="button"
        >
          Chat
        </button>
        <button
          class="site-link ${state.currentView === "metrics" ? "active" : ""}"
          data-view="metrics"
          type="button"
        >
          Metricas
        </button>
      </nav>

      <div class="topbar-actions">
        <button
          id="top-health-button"
          class="site-action site-action-soft ${state.currentView === "health" ? "active" : ""}"
          type="button"
          ${state.busy.health ? "disabled" : ""}
        >
          <span class="site-action-label">${state.busy.health ? "Probando..." : "Health"}</span>
          <span class="site-action-meta">${escapeHtml(healthPillLabel())}</span>
        </button>
        <div class="site-action site-action-primary site-action-static">
          <span class="site-action-label">Conversacion</span>
          <strong
            class="site-action-id"
            title="${escapeHtml(state.conversationId || "Sin conversation_id activo")}"
          >
            ${escapeHtml(state.conversationId || "N/D")}
          </strong>
        </div>
      </div>
    </header>
  `;
}

function renderSidebar() {
  const customerSelectHtml = renderCustomerInput();
  const effectiveDraftCustomerId = getEffectiveDraftCustomerId();
  const selectedCustomer = findCustomerOption(effectiveDraftCustomerId);
  const availableProducts = selectedCustomer ? selectedCustomer.productIds : [];
  const selectedProduct = selectedCustomer
    ? selectedCustomer.productOptions.find((option) => option.productId === state.draftProductId)
    : null;
  const generatedConversationId = buildConversationId(
    effectiveDraftCustomerId,
    state.draftConversationDate,
  );
  const pendingConversationChange =
    generatedConversationId !== cleanString(state.conversationId);

  return `
    <aside class="sidebar">
      <section class="brand-card">
        <div class="brand-header">
          ${renderBbvaLogo()}
        </div>
        <h1>Agente PQRs</h1>
        <p class="brand-tagline">AMBIENTE DE EXPERIMENTACIÓN INTERNO</p>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Conversacion</h2>
            <p>Gestiona el caso activo desde el CSV o con un customer_id manual.</p>
          </div>
          ${renderCsvStatusPill()}
        </div>
        <div class="field-grid">
          <div class="field">
            <label for="csv-file-input">CSV de prueba</label>
            <input id="csv-file-input" type="file" accept=".csv,text/csv">
            <p class="field-help">
              Se intenta leer <code>Muestra_tabla_embargos.csv</code> automaticamente. Si no carga,
              puedes seleccionarlo manualmente aqui.
            </p>
          </div>
          <button
            id="reload-csv-button"
            class="button button-ghost"
            type="button"
            ${state.busy.csv ? "disabled" : ""}
          >
            ${state.busy.csv ? "Leyendo CSV..." : "Recargar CSV local"}
          </button>
          ${state.csvError ? renderAlertInline("warning", state.csvError) : ""}

          ${customerSelectHtml}

          ${
            availableProducts.length
              ? `
                <div class="field">
                  <label for="draft-product-id">Producto de referencia</label>
                  <select id="draft-product-id">
                    ${availableProducts
                      .map(
                        (productId) => `
                          <option
                            value="${escapeHtml(productId)}"
                            ${productId === state.draftProductId ? "selected" : ""}
                          >
                            ${escapeHtml(productId)}
                          </option>
                        `,
                      )
                      .join("")}
                  </select>
                  ${
                    selectedProduct
                      ? `
                        <p class="field-help">
                          Contratos visibles: <code>${escapeHtml(contractPreview(selectedProduct.contractIds))}</code>
                        </p>
                      `
                      : ""
                  }
                </div>
              `
              : ""
          }

          <div class="field">
            <label for="draft-conversation-date">Fecha del conversation_id</label>
            <input
              id="draft-conversation-date"
              type="date"
              value="${escapeHtml(state.draftConversationDate)}"
            >
            <p class="field-help">Se enviara al backend como <code>yyyymmdd</code>.</p>
          </div>

          <div class="field">
            <label>Conversation ID generado</label>
            <div class="code-box">${escapeHtml(generatedConversationId || "Selecciona o escribe un customer_id")}</div>
            ${
              pendingConversationChange
                ? `
                  <p class="field-help">
                    Cambio pendiente. Actual: <code>${escapeHtml(state.conversationId || "N/D")}</code>
                  </p>
                `
                : ""
            }
          </div>

          <div class="button-column">
            <button id="apply-customer-button" class="button button-primary" type="button">
              Aplicar caso
            </button>
            <button id="new-conversation-button" class="button button-secondary" type="button">
              Nueva conversacion
            </button>
          </div>
        </div>
      </section>

      <section class="hint-card">
        <p>
          Para que el CSV, el JavaScript y los fetch funcionen bien, sirve esta carpeta por HTTP
          en lugar de abrir <code>index.html</code> con <code>file://</code>.
        </p>
        <p>
          La <code>Base URL</code> del backend se ajusta desde la vista <code>Health</code>.
        </p>
      </section>
    </aside>
  `;
}

function renderCustomerInput() {
  const customerOptions = buildCustomerSelectOptions();
  const listField = customerOptions.length
    ? `
      <div class="field">
        <label for="draft-customer-id">Caso de prueba</label>
        <select id="draft-customer-id">
          ${customerOptions
            .map(
              (option) => `
                <option
                  value="${escapeHtml(option.customerId)}"
                  ${option.customerId === state.draftCustomerId ? "selected" : ""}
                >
                  ${escapeHtml(option.label)}
                </option>
              `,
            )
            .join("")}
        </select>
        <p class="field-help">
          Los casos vienen del CSV de embargos y priorizan clientes con varios productos.
        </p>
      </div>
    `
    : `
      <div class="field">
        <label>Casos de prueba</label>
        <p class="field-help">
          No encontre casos multi-producto cargados. Puedes continuar en modo manual.
        </p>
      </div>
    `;

  return `
    ${listField}
    <div class="field">
      <label for="draft-customer-id-manual">Customer ID manual</label>
      <input
        id="draft-customer-id-manual"
        type="text"
        value="${escapeHtml(state.draftCustomerIdManual)}"
        placeholder="Escribe un customer_id si no quieres usar la lista"
      >
      <p class="field-help">
        Si escribes un valor aqui, tendra prioridad sobre la lista. Borra el campo o cambia la lista para volver al CSV.
      </p>
    </div>
  `;
}

function renderChatView() {
  const activeConversation = hasActiveConversation();
  const hasConversationId = Boolean(cleanString(state.conversationId));
  const pendingPolling = hasPendingPolling();

  return `
    <section class="hero-card">
      <span class="eyebrow">Agente PQRs</span>
      <h1>Canal conversacional de pruebas</h1>
      <p>
        Consola web para probar conversaciones, revisar contexto local y operar
        casos de manera mas clara y ordenada.
      </p>
    </section>

    ${state.chatNotice ? renderAlert(state.chatNotice.level, state.chatNotice.message) : ""}

    <section class="status-grid">
      ${renderStatusCard("Backend", state.apiBaseUrl, "URL configurada para el API")}
      ${renderStatusCard("Caso aplicado", state.selectedCustomerId || "N/D", "customer_id activo")}
      ${renderStatusCard("Caso en edicion", getEffectiveDraftCustomerId() || "N/D", "borrador actual")}
      ${renderStatusCard("Conversacion activa", state.conversationId || "N/D", "ID que viaja al backend")}
      ${renderStatusCard("Mensajes locales", formatNumber(state.messages.length), "persistidos en este navegador")}
    </section>

    <section class="content-card chat-board">
      <div class="section-head">
        <div>
          <h2>Conversacion</h2>
          <p>
            El primer envio abre <code>/start</code> sin <code>content</code> y luego manda
            el texto real por <code>/chat</code>. Los siguientes usan <code>/chat</code> con
            fallback automatico cuando el backend lo sugiere.
          </p>
        </div>
        <div class="section-head-actions">
          <button
            id="poll-pending-message-button"
            class="button button-secondary${pendingPolling ? " button-secondary--pending" : ""}"
            type="button"
            ${state.busy.polling ? "disabled" : ""}
          >
            ${state.busy.polling ? "Consultando..." : "Consultar respuesta"}
          </button>
          ${
            activeConversation
              ? `
                <button
                  id="end-conversation-button"
                  class="button button-danger"
                  type="button"
                  ${state.busy.endConversation ? "disabled" : ""}
                >
                  ${state.busy.endConversation ? "Finalizando..." : "Finalizar conversacion"}
                </button>
              `
              : ""
          }
        </div>
      </div>

      <div id="chat-log" class="chat-log">
        ${renderMessages()}
      </div>

      ${
        pendingPolling
          ? renderAlertInline(
              "warning",
              "El backend sigue procesando el ultimo mensaje. Usa el boton para consultar la respuesta pendiente.",
            )
          : ""
      }

      ${
        state.messages.length === 0
          ? `
            <div>
              <p class="caption">Accesos rapidos</p>
              <div class="quick-actions">
                ${WELCOME_SUGGESTIONS
                  .map(
                    (suggestion) => `
                      <button
                        class="chip-button"
                        type="button"
                        data-suggestion="${escapeHtml(suggestion)}"
                      >
                        ${escapeHtml(suggestion)}
                      </button>
                    `,
                  )
                  .join("")}
              </div>
            </div>
          `
          : ""
      }

      <form id="chat-form" class="composer">
        <div class="field">
          <label for="chat-input">Mensaje</label>
          <textarea
            id="chat-input"
            placeholder="Escribe tu mensaje para Agente PQRs"
            ${state.busy.chat || pendingPolling ? "disabled" : ""}
          >${escapeHtml(state.chatDraft)}</textarea>
        </div>
        <button
          class="button button-primary"
          type="submit"
          ${state.busy.chat || pendingPolling ? "disabled" : ""}
        >
          ${state.busy.chat ? "Consultando..." : "Enviar"}
        </button>
      </form>
    </section>
  `;
}

function renderHealthView() {
  return `
    <section class="hero-card">
      <span class="eyebrow">Health</span>
      <h1>Control de conectividad</h1>
      <p>
        Esta vista valida conectividad con <code>GET /health</code> y muestra el resultado
        en el area principal, sin ocupar espacio en el panel izquierdo.
      </p>
    </section>

    <section class="health-shell">
      <section class="content-card health-panel">
        <div class="section-head">
          <div>
            <h2>Chequeo actual</h2>
            <p>
              Endpoint: <code>${escapeHtml(normalizeBaseUrl(state.apiBaseUrl) || "N/D")}/health</code>
            </p>
          </div>
          ${renderStatusPill(state.healthStatus, healthPillLabel())}
        </div>

        <div class="field">
          <label for="api-base-url">Base URL</label>
          <input
            id="api-base-url"
            type="url"
            placeholder="http://127.0.0.1:8000"
            value="${escapeHtml(state.apiBaseUrl)}"
          >
          <p class="field-help">
            No incluyas <code>/start</code>, <code>/chat</code> ni <code>/health</code>.
          </p>
        </div>

        <div class="health-actions">
          <button
            id="health-check-button"
            class="button button-primary"
            type="button"
            ${state.busy.health ? "disabled" : ""}
          >
            ${state.busy.health ? "Probando..." : "Probar health"}
          </button>
        </div>

        ${
          state.busy.health
            ? `
              <section class="empty-state">
                <strong>Consultando el backend.</strong>
                <p>Estoy esperando la respuesta de <code>/health</code>.</p>
              </section>
            `
            : state.healthMessage
              ? renderAlert(state.healthStatus || "info", state.healthMessage)
              : `
                <section class="empty-state">
                  <strong>Aun no has ejecutado esta validacion.</strong>
                  <p>
                    Usa la accion superior <code>Health</code> o <code>Probar health</code> para
                    verificar conectividad.
                  </p>
                </section>
              `
        }

        <section class="status-grid health-status-grid">
          ${renderStatusCard("Backend", state.apiBaseUrl || "N/D", "URL base configurada")}
          ${renderStatusCard("Estado", healthPillLabel(), "resultado visible del ultimo chequeo")}
          ${renderStatusCard("Conversation activa", state.conversationId || "N/D", "contexto local actual")}
        </section>
      </section>
    </section>
  `;
}

function renderMessageOptions(message) {
  if (!Array.isArray(message.options) || !message.options.length) {
    return "";
  }

  if (message.input_type === "multi_select") {
    return `
      <div class="message-options multi-select-options">
        ${message.options
          .map((option) => {
            const rawLabel = cleanString(option.label);
            const selected = rawLabel.startsWith("☑");
            const label = rawLabel.replace(/^[☑☐]\s*/, "");
            return `
              <button
                class="multi-select-option ${selected ? "selected" : ""}"
                type="button"
                data-option-key="${escapeHtml(option.key)}"
                data-option-label="${escapeHtml(rawLabel)}"
              >
                <span class="multi-select-check" aria-hidden="true">${selected ? "☑" : "☐"}</span>
                <span>${escapeHtml(label)}</span>
              </button>
            `;
          })
          .join("")}
      </div>
    `;
  }

  return `
    <div class="message-options">
      ${message.options
        .map(
          (option) => `
            <button
              class="chip-button"
              type="button"
              data-option-key="${escapeHtml(option.key)}"
              data-option-label="${escapeHtml(option.label)}"
            >
              ${escapeHtml(option.label)}
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderMessages() {
  if (!state.messages.length) {
    return `
      <section class="empty-state">
        <strong>Todavia no hay mensajes en esta sesion.</strong>
        <p>
          Puedes empezar con <code>Hola</code> para listar workflows disponibles o elegir uno de
          los accesos rapidos.
        </p>
      </section>
    `;
  }

  const actionableIndex = state.messages.length - 1;

  return state.messages
    .map((message, index) => {
      const roleClass = message.role === "user" ? "message-user" : "message-assistant";
      const isError = message.kind === "error";
      const isPending = message.kind === "pending";
      const isActionable =
        index === actionableIndex &&
        message.role === "assistant" &&
        Array.isArray(message.options) &&
        message.options.length;

      return `
        <article class="message ${roleClass} ${isError ? "message-error" : ""} ${isPending ? "message-pending" : ""}">
          <div class="message-bubble">
            <div class="message-meta">
              <span>${message.role === "user" ? "Tu" : "Agente PQRs"}</span>
              ${message.timestamp ? `<time>${escapeHtml(message.timestamp)}</time>` : ""}
            </div>
            <div class="message-content">${escapeHtml(message.content)}</div>
            ${isActionable ? renderMessageOptions(message) : ""}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderMetricsConfigPanel() {
  const proxyUrl = cleanString(state.metricsConfig.proxyUrl) || "N/D";
  const endpoint = cleanString(state.metricsConfig.endpoint) || "N/D";
  const indicesSummary = `${cleanString(state.metricsConfig.conversationsIndex) || "N/D"} / ${cleanString(state.metricsConfig.messagesIndex) || "N/D"}`;

  return `
    <section class="content-card">
      <div class="section-head">
        <div>
          <h2>Configuracion OpenSearch</h2>
          <p>Este bloque alimenta metricas y borrado remoto a traves del mini backend.</p>
        </div>
        <div class="section-head-actions">
          ${renderStatusPill(
            state.metricsConfigDirty ? "warning" : "neutral",
            state.metricsConfigDirty ? "Cambios sin refrescar" : "Configuracion lista",
          )}
          <button
            id="toggle-metrics-config-button"
            class="button button-ghost button-compact"
            type="button"
            aria-expanded="${state.metricsConfigExpanded ? "true" : "false"}"
          >
            ${state.metricsConfigExpanded ? "Ocultar configuracion" : "Mostrar configuracion"}
          </button>
        </div>
      </div>

      <div class="config-summary">
        <span><strong>Proxy:</strong> ${escapeHtml(proxyUrl)}</span>
        <span><strong>OpenSearch:</strong> ${escapeHtml(endpoint)}</span>
        <span><strong>Indices:</strong> ${escapeHtml(indicesSummary)}</span>
      </div>

      ${
        state.metricsConfigExpanded
          ? `
            <div class="field-grid">
              <div class="field">
                <label for="metrics-proxy-url">Proxy URL</label>
                <input
                  id="metrics-proxy-url"
                  type="url"
                  data-config-key="proxyUrl"
                  value="${escapeHtml(state.metricsConfig.proxyUrl)}"
                  placeholder="http://127.0.0.1:8090"
                >
                <p class="field-help">
                  El proxy local hace la conexion real a OpenSearch con Python, asi evitamos bloqueos
                  del navegador por CORS y certificados locales.
                </p>
              </div>
              <div class="field">
                <label for="metrics-endpoint">Endpoint</label>
                <input
                  id="metrics-endpoint"
                  type="url"
                  data-config-key="endpoint"
                  value="${escapeHtml(state.metricsConfig.endpoint)}"
                  placeholder="https://localhost:9200"
                >
              </div>
              <div class="mini-grid">
                <div class="field">
                  <label for="metrics-user">Usuario</label>
                  <input
                    id="metrics-user"
                    type="text"
                    data-config-key="user"
                    value="${escapeHtml(state.metricsConfig.user)}"
                  >
                </div>
                <div class="field">
                  <label for="metrics-password">Password</label>
                  <input
                    id="metrics-password"
                    type="password"
                    data-config-key="password"
                    value="${escapeHtml(state.metricsConfig.password)}"
                  >
                </div>
              </div>
              <p class="field-help">
                Si tu OpenSearch local no exige autenticacion, deja <code>Usuario</code> y
                <code>Password</code> vacios para que el proxy no envie credenciales innecesarias.
              </p>
              <div class="field">
                <label for="conversations-index">Indice conversaciones</label>
                <input
                  id="conversations-index"
                  type="text"
                  data-config-key="conversationsIndex"
                  value="${escapeHtml(state.metricsConfig.conversationsIndex)}"
                >
              </div>
              <div class="field">
                <label for="messages-index">Indice mensajes</label>
                <input
                  id="messages-index"
                  type="text"
                  data-config-key="messagesIndex"
                  value="${escapeHtml(state.metricsConfig.messagesIndex)}"
                >
              </div>
              <div class="field">
                <label for="metrics-timeout">Timeout (segundos)</label>
                <input
                  id="metrics-timeout"
                  type="number"
                  min="1"
                  step="1"
                  data-config-key="timeoutSeconds"
                  value="${escapeHtml(String(state.metricsConfig.timeoutSeconds))}"
                >
                <p class="field-help">
                  Este valor se usa como base; los snapshots y el borrado remoto aplican un margen mayor automaticamente.
                </p>
              </div>
              <button
                id="refresh-metrics-button"
                class="button button-secondary"
                type="button"
                ${state.metricsLoading ? "disabled" : ""}
              >
                ${state.metricsLoading ? "Cargando metricas..." : "Refrescar metricas"}
              </button>
            </div>
          `
          : `
            <div class="config-summary-actions">
              <button
                id="refresh-metrics-button"
                class="button button-secondary button-compact"
                type="button"
                ${state.metricsLoading ? "disabled" : ""}
              >
                ${state.metricsLoading ? "Cargando metricas..." : "Refrescar metricas"}
              </button>
            </div>
          `
      }
    </section>
  `;
}

function renderMetricsView() {
  const snapshot = state.metricsSnapshot;

  return `
      <section class="hero-card">
        <span class="eyebrow">Metricas</span>
        <h1>Panel operativo de Agente PQRs</h1>
        <p>
          Lee OpenSearch a traves del mini backend para resumir volumen, tokens, latencias,
          estados y actividad reciente sin cargar esa conexion en el navegador.
        </p>
      </section>

    ${renderMetricsConfigPanel()}

    ${state.metricsError ? renderAlert("danger", state.metricsError) : ""}
    ${
      state.metricsConfigDirty && snapshot
        ? renderAlert(
            "info",
            "La configuracion de OpenSearch cambio desde la ultima lectura. Refresca para ver datos alineados con esos nuevos valores.",
          )
        : ""
    }

    ${
      state.metricsLoading
        ? `
          <section class="content-card">
            <div class="section-head">
              <div>
                <h2>Consultando OpenSearch</h2>
                <p>Estoy leyendo conversaciones y mensajes para recalcular el snapshot.</p>
              </div>
            </div>
          </section>
        `
        : ""
    }

    ${
      snapshot
        ? `
          <section class="content-card">
            <div class="section-head">
              <div>
                <h2>Resumen</h2>
                <p>
                  Fuente actual: <code>${escapeHtml(snapshot.source)}</code>.
                  Ultima actividad detectada: <code>${escapeHtml(formatTimestamp(snapshot.latestActivity))}</code>.
                </p>
              </div>
              <button class="button button-ghost" id="inline-refresh-metrics-button" type="button" ${state.metricsLoading ? "disabled" : ""}>
                ${state.metricsLoading ? "Refrescando..." : "Refrescar ahora"}
              </button>
            </div>

            ${
              snapshot.missingSources.length
                ? renderAlertInline(
                    "warning",
                    `Faltan indices en OpenSearch: ${snapshot.missingSources.join(", ")}. Las metricas visibles se calcularon con lo que si estaba disponible.`,
                  )
                : ""
            }

            <div class="metric-grid">
              ${renderMetricCard("Conversaciones", formatNumber(snapshot.conversationCount), "total persistido")}
              ${renderMetricCard("Activas", formatNumber(snapshot.activeCount), "status = Active")}
              ${renderMetricCard("Cerradas", formatNumber(snapshot.closedCount), "status = Closed")}
              ${renderMetricCard("Fallidas", formatNumber(snapshot.errorCount), "status = Error")}
              ${renderMetricCard("Mensajes", formatNumber(snapshot.messageCount), "todas las entradas")}
              ${renderMetricCard("Tokens totales", formatNumber(snapshot.totalTokens), "solo turns de assistant")}
              ${renderMetricCard("Resp. prom. asistente", formatDurationMs(snapshot.avgAssistantResponseMs), "latencia media")}
              ${renderMetricCard("P95 resp. asistente", formatDurationMs(snapshot.p95AssistantResponseMs), "cola de latencia")}
              ${renderMetricCard("Turns con modelo", formatNumber(snapshot.turnsWithModelUsage), "total_tokens > 0")}
              ${renderMetricCard("Input tokens", formatNumber(snapshot.totalInputTokens), "assistant usage")}
              ${renderMetricCard("Output tokens", formatNumber(snapshot.totalOutputTokens), "assistant usage")}
              ${renderMetricCard("Latencia prom. turno", formatDurationMs(snapshot.avgUserTurnMs), "timing del usuario")}
            </div>
          </section>

          ${renderTableCard("Workflows", "Volumen, turns y tokens por workflow.", snapshot.workflowRows)}
          ${renderTableCard("Conversaciones recientes", "Ultimas 10 conversaciones detectadas.", snapshot.recentRows)}
          ${renderTableCard("Conversaciones fallidas", "Solo registros con status = Error.", snapshot.errorRows)}
        `
        : `
          <section class="empty-state">
            <strong>No hay un snapshot cargado todavia.</strong>
            <p>
              Entrar a <code>Metricas</code> ya no dispara una consulta automatica. Usa
              <code>Refrescar metricas</code> en esta misma vista para consultar OpenSearch
              a traves del proxy cuando tengas listo el endpoint.
            </p>
            <div class="quick-actions">
              <button
                id="empty-refresh-metrics-button"
                class="button button-primary"
                type="button"
                ${state.metricsLoading ? "disabled" : ""}
              >
                ${state.metricsLoading ? "Consultando..." : "Cargar metricas"}
              </button>
            </div>
          </section>
        `
    }
  `;
}

function renderTableCard(title, copy, rows) {
  return `
    <section class="table-card">
      <div class="table-head">
        <div>
          <h2>${escapeHtml(title)}</h2>
          <p>${escapeHtml(copy)}</p>
        </div>
      </div>
      ${
        rows && rows.length
          ? `
            <div class="table-wrap">
              ${renderTable(rows)}
            </div>
          `
          : `
            <section class="empty-state">
              <strong>Sin datos para mostrar.</strong>
              <p>Esta seccion se llenara cuando haya registros disponibles en OpenSearch.</p>
            </section>
          `
      }
    </section>
  `;
}

function renderTable(rows) {
  const headers = Object.keys(rows[0] || {});

  return `
    <table>
      <thead>
        <tr>
          ${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                ${headers.map((header) => `<td>${escapeHtml(String(row[header] ?? "N/D"))}</td>`).join("")}
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderMetricCard(label, value, detail) {
  return `
    <article class="metric-card">
      <small>${escapeHtml(label)}</small>
      <strong>${escapeHtml(value)}</strong>
      <p>${escapeHtml(detail)}</p>
    </article>
  `;
}

function renderStatusCard(label, value, detail) {
  return `
    <article class="metric-card status-card">
      <small>${escapeHtml(label)}</small>
      <strong>${escapeHtml(value)}</strong>
      <p>${escapeHtml(detail)}</p>
    </article>
  `;
}

function renderAlert(level, message) {
  return `
    <section class="alert alert-${alertClass(level)}">
      <strong>${alertTitle(level)}</strong>
      <p>${escapeHtml(message)}</p>
    </section>
  `;
}

function renderAlertInline(level, message) {
  return `
    <div class="alert alert-${alertClass(level)}">
      <strong>${alertTitle(level)}</strong>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function renderStatusPill(level, text) {
  return `<span class="status-pill ${statusClass(level)}">${escapeHtml(text)}</span>`;
}

function renderCsvStatusPill() {
  if (state.csvStatus === "loading") {
    return renderStatusPill("neutral", "Leyendo CSV");
  }

  if (state.csvStatus === "ready") {
    return renderStatusPill("success", `${formatNumber(state.customerOptions.length)} casos cargados`);
  }

  if (state.csvStatus === "manual") {
    return renderStatusPill("success", "CSV manual cargado");
  }

  if (state.csvStatus === "error") {
    return renderStatusPill("warning", "CSV no disponible");
  }

  return renderStatusPill("neutral", "Pendiente");
}

function bindEvents() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextView = button.getAttribute("data-view");
      if (!nextView || nextView === state.currentView) {
        return;
      }

      state.currentView = nextView === "metrics" ? "metrics" : "chat";
      renderApp();
    });
  });

  const apiBaseUrlInput = document.getElementById("api-base-url");
  if (apiBaseUrlInput) {
    apiBaseUrlInput.addEventListener("input", (event) => {
      state.apiBaseUrl = normalizeBaseUrl(event.target.value);
      state.healthStatus = null;
      state.healthMessage = "";
      persistState();
    });

    apiBaseUrlInput.addEventListener("change", () => {
      renderApp();
    });
  }

  const healthButton = document.getElementById("top-health-button");
  if (healthButton) {
    healthButton.addEventListener("click", () => {
      state.currentView = "health";
      renderApp();
      void performHealthCheck();
    });
  }

  const healthCheckButton = document.getElementById("health-check-button");
  if (healthCheckButton) {
    healthCheckButton.addEventListener("click", () => {
      void performHealthCheck();
    });
  }

  const toggleMetricsConfigButton = document.getElementById("toggle-metrics-config-button");
  if (toggleMetricsConfigButton) {
    toggleMetricsConfigButton.addEventListener("click", () => {
      state.metricsConfigExpanded = !state.metricsConfigExpanded;
      renderApp();
    });
  }

  document.querySelectorAll("[data-config-key]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const key = event.target.getAttribute("data-config-key");
      if (!key) {
        return;
      }

      state.metricsConfig[key] =
        key === "timeoutSeconds"
          ? normalizePositiveNumber(event.target.value, DEFAULT_METRICS_CONFIG.timeoutSeconds)
          : cleanString(event.target.value);
      state.metricsConfigDirty = true;
      persistState();
    });

    input.addEventListener("change", () => {
      renderApp();
    });
  });

  const refreshMetricsButton = document.getElementById("refresh-metrics-button");
  if (refreshMetricsButton) {
    refreshMetricsButton.addEventListener("click", () => {
      void loadMetricsSnapshot();
    });
  }

  const inlineRefreshMetricsButton = document.getElementById("inline-refresh-metrics-button");
  if (inlineRefreshMetricsButton) {
    inlineRefreshMetricsButton.addEventListener("click", () => {
      void loadMetricsSnapshot();
    });
  }

  const emptyRefreshMetricsButton = document.getElementById("empty-refresh-metrics-button");
  if (emptyRefreshMetricsButton) {
    emptyRefreshMetricsButton.addEventListener("click", () => {
      void loadMetricsSnapshot();
    });
  }

  const reloadCsvButton = document.getElementById("reload-csv-button");
  if (reloadCsvButton) {
    reloadCsvButton.addEventListener("click", () => {
      void loadCustomerOptions();
    });
  }

  const csvFileInput = document.getElementById("csv-file-input");
  if (csvFileInput) {
    csvFileInput.addEventListener("change", async (event) => {
      const [file] = event.target.files || [];
      if (!file) {
        return;
      }

      try {
        const text = await readFileAsText(file);
        applyCustomerOptionsFromCsv(text, "manual");
        pushToast("success", "CSV cargado manualmente.");
        renderApp();
      } catch (error) {
        state.csvStatus = "error";
        state.csvError = `No pude leer el archivo manual: ${error.message}`;
        renderApp();
      }
    });
  }

  const draftCustomerSelect = document.getElementById("draft-customer-id");
  if (draftCustomerSelect) {
    draftCustomerSelect.addEventListener("change", (event) => {
      state.draftCustomerId = cleanString(event.target.value);
      state.draftCustomerIdManual = "";
      syncDraftProductFromCustomer();
      renderApp();
    });
  }

  const draftCustomerManual = document.getElementById("draft-customer-id-manual");
  if (draftCustomerManual) {
    draftCustomerManual.addEventListener("input", (event) => {
      state.draftCustomerIdManual = cleanString(event.target.value);
      state.draftProductId = "";
      persistState();
    });

    draftCustomerManual.addEventListener("change", () => {
      renderApp();
    });
  }

  const draftProductSelect = document.getElementById("draft-product-id");
  if (draftProductSelect) {
    draftProductSelect.addEventListener("change", (event) => {
      state.draftProductId = cleanString(event.target.value);
      renderApp();
    });
  }

  const draftConversationDate = document.getElementById("draft-conversation-date");
  if (draftConversationDate) {
    draftConversationDate.addEventListener("change", (event) => {
      state.draftConversationDate = normalizeInputDate(event.target.value) || todayInputValue();
      renderApp();
    });
  }

  const applyCustomerButton = document.getElementById("apply-customer-button");
  if (applyCustomerButton) {
    applyCustomerButton.addEventListener("click", () => {
      applyDraftConversation();
    });
  }

  const newConversationButton = document.getElementById("new-conversation-button");
  if (newConversationButton) {
    newConversationButton.addEventListener("click", () => {
      startNewConversation();
    });
  }

  const endConversationButton = document.getElementById("end-conversation-button");
  if (endConversationButton) {
    endConversationButton.addEventListener("click", () => {
      void handleEndConversation();
    });
  }

  const pollPendingMessageButton = document.getElementById("poll-pending-message-button");
  if (pollPendingMessageButton) {
    pollPendingMessageButton.addEventListener("click", () => {
      void handlePendingPolling();
    });
  }

  document.querySelectorAll("[data-suggestion]").forEach((button) => {
    button.addEventListener("click", () => {
      const suggestion = cleanString(button.getAttribute("data-suggestion"));
      if (suggestion) {
        void handleUserPrompt({ content: suggestion, displayContent: suggestion });
      }
    });
  });

  document.querySelectorAll("[data-option-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const optionKey = cleanString(button.getAttribute("data-option-key"));
      const optionLabel =
        cleanString(button.getAttribute("data-option-label")) || optionKey;
      if (optionKey) {
        void handleUserPrompt({ content: optionKey, displayContent: optionLabel });
      }
    });
  });

  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  if (chatInput) {
    autoResizeTextarea(chatInput);
    chatInput.addEventListener("input", (event) => {
      state.chatDraft = event.target.value;
      autoResizeTextarea(event.target);
      persistState();
    });
  }

  if (chatForm) {
    chatForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void handleUserPrompt(state.chatDraft);
    });
  }
}

async function loadCustomerOptions() {
  state.busy.csv = true;
  state.csvStatus = "loading";
  state.csvError = "";
  renderApp();

  try {
    const response = await fetch(`${CSV_PATH}?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const csvText = await response.text();
    applyCustomerOptionsFromCsv(csvText, "ready");
  } catch (error) {
    state.customerOptions = [];
    state.csvStatus = "error";
    state.csvError =
      "No pude leer `Muestra_tabla_embargos.csv` con fetch. Sirve el proyecto por HTTP o carga el archivo manualmente.";
    normalizeConversationState();
  } finally {
    state.busy.csv = false;
    renderApp();
  }
}

function applyCustomerOptionsFromCsv(csvText, status) {
  state.customerOptions = loadEmbargoCustomerOptions(csvText);
  state.csvStatus = status;
  state.csvError = "";
  normalizeConversationState();
}

function normalizeConversationState() {
  const defaultCustomerId = state.customerOptions[0]?.customerId || "";
  const parsedConversation = parseConversationId(state.conversationId);

  if (parsedConversation.customerId && parsedConversation.dateInput) {
    state.selectedCustomerId = parsedConversation.customerId;
    state.conversationDate = parsedConversation.dateInput;
  } else {
    state.selectedCustomerId = cleanString(state.selectedCustomerId) || defaultCustomerId;
    state.conversationDate = normalizeInputDate(state.conversationDate) || todayInputValue();
  }

  if (!state.conversationId) {
    state.conversationId = buildConversationId(state.selectedCustomerId, state.conversationDate);
  }

  state.draftCustomerId = cleanString(state.draftCustomerId) || state.selectedCustomerId || defaultCustomerId;
  state.draftConversationDate =
    normalizeInputDate(state.draftConversationDate) || state.conversationDate || todayInputValue();

  syncDraftProductFromCustomer();
}

function syncDraftProductFromCustomer() {
  const draftCustomer = findCustomerOption(getEffectiveDraftCustomerId());
  const availableProducts = draftCustomer ? draftCustomer.productIds : [];

  if (availableProducts.length && !availableProducts.includes(state.draftProductId)) {
    state.draftProductId = availableProducts[0];
  }

  if (!availableProducts.length) {
    state.draftProductId = "";
  }
}

function getEffectiveDraftCustomerId() {
  return cleanString(state.draftCustomerIdManual) || cleanString(state.draftCustomerId);
}

function buildCustomerSelectOptions() {
  const options = [...state.customerOptions];
  const draftCustomerId = cleanString(state.draftCustomerId);

  if (
    draftCustomerId &&
    !options.some((option) => option.customerId === draftCustomerId)
  ) {
    options.unshift({
      customerId: draftCustomerId,
      label: `${draftCustomerId} | customer_id manual`,
      productIds: [],
      productOptions: [],
      rowCount: 0,
      productCount: 0,
    });
  }

  return options;
}

function applyDraftConversation() {
  const draftCustomerId = getEffectiveDraftCustomerId();
  if (!draftCustomerId) {
    showChatNotice("danger", "Debes elegir un customer_id antes de aplicar el caso.");
    return;
  }

  resetChat({
    customerId: draftCustomerId,
    conversationDate: state.draftConversationDate,
  });
  showChatNotice(
    "success",
    `Caso de prueba aplicado con formato ${state.conversationId}.`,
  );
}

function startNewConversation() {
  const draftCustomerId = getEffectiveDraftCustomerId();
  if (!draftCustomerId) {
    showChatNotice("danger", "Debes elegir un customer_id antes de crear una conversacion.");
    return;
  }

  const today = todayInputValue();
  const newConversationId = buildConversationId(draftCustomerId, today);
  const currentConversationId = cleanString(state.conversationId);

  resetChat({ customerId: draftCustomerId, conversationDate: today });
  if (newConversationId === currentConversationId) {
    showChatNotice(
      "warning",
      "Con el formato actual customer_id_yyyymmdd, este ID ya era el activo. Cambia el customer_id o la fecha para abrir uno distinto.",
    );
    return;
  }

  showChatNotice("success", "Se creo una nueva conversacion local para hoy.");
}

function resetChat({ customerId, conversationDate }) {
  const normalizedCustomerId = cleanString(customerId || state.selectedCustomerId);
  const normalizedConversationDate =
    normalizeInputDate(conversationDate) || normalizeInputDate(state.conversationDate) || todayInputValue();

  state.selectedCustomerId = normalizedCustomerId;
  state.conversationDate = normalizedConversationDate;
  state.conversationId = buildConversationId(normalizedCustomerId, normalizedConversationDate);
  state.conversationStatus = null;
  state.pendingPollingConversationId = "";
  state.messages = [];
  state.chatDraft = "";
  state.draftCustomerId = normalizedCustomerId;
  state.draftConversationDate = normalizedConversationDate;
  syncDraftProductFromCustomer();
  renderApp();
}

function clearLocalConversation() {
  state.messages = [];
  state.chatDraft = "";
  state.pendingPollingConversationId = "";
}

function hasActiveConversation() {
  return (
    Boolean(cleanString(state.conversationId)) &&
    state.messages.length > 0 &&
    !["Closed", "Inactive"].includes(cleanString(state.conversationStatus))
  );
}

function hasPendingPolling() {
  return Boolean(cleanString(state.pendingPollingConversationId));
}

function clearPendingPollingState() {
  state.pendingPollingConversationId = "";
  state.messages = state.messages.filter((message) => message.kind !== "pending");
}

function markConversationAsPending(conversationId) {
  state.pendingPollingConversationId = cleanString(conversationId) || cleanString(state.conversationId);
  state.messages = state.messages.filter((message) => message.kind !== "pending");
  addChatMessage(
    "assistant",
    "Procesando tu solicitud. Usa el boton para consultar el mensaje en espera.",
    { kind: "pending" },
  );
}

async function handleEndConversation() {
  const activeConversationId = cleanString(state.conversationId);
  if (!activeConversationId) {
    showChatNotice("danger", "No hay un conversation_id activo para finalizar.");
    return;
  }

  state.busy.endConversation = true;
  renderApp();

  try {
    const result = await sendMessageRequest({
      baseUrl: state.apiBaseUrl,
      endpointPath: "/end",
      conversationId: activeConversationId,
      customerId: state.selectedCustomerId,
      content: null,
    });

    if (result.ok) {
      clearPendingPollingState();
      state.conversationId = result.conversationId;
      state.conversationStatus = cleanString(result.conversationStatus) || "Closed";
      const payload = result.messagePayload || {
        content: result.message,
        options: [],
        timestamp: null,
      };
      addChatMessage("assistant", payload.content, {
        options: payload.options,
        input_type: payload.input_type,
        timestamp: payload.timestamp,
      });
      showChatNotice(
        "success",
        `El backend finalizo ${state.conversationId} via /end con estado ${state.conversationStatus}.`,
      );
    } else {
      showChatNotice("danger", result.message);
    }
  } catch (error) {
    showChatNotice("danger", error.message);
  } finally {
    state.busy.endConversation = false;
    renderApp();
  }
}

async function handlePendingPolling() {
  const activeConversationId =
    cleanString(state.pendingPollingConversationId) || cleanString(state.conversationId);
  if (!activeConversationId) {
    showChatNotice("warning", "No hay un mensaje pendiente para consultar.");
    return;
  }

  state.busy.polling = true;
  renderApp();

  try {
    const result = await pollConversationMessage({
      baseUrl: state.apiBaseUrl,
      conversationId: activeConversationId,
    });

    if (result.ok && result.pending) {
      markConversationAsPending(activeConversationId);
      showChatNotice("warning", "El backend sigue pensando la respuesta.");
      return;
    }

    if (result.ok) {
      clearPendingPollingState();
      state.conversationId = result.conversationId;
      state.conversationStatus = cleanString(result.conversationStatus);
      const payload = result.messagePayload || {
        content: result.message,
        options: [],
        timestamp: null,
      };
      addChatMessage("assistant", payload.content, {
        options: payload.options,
        input_type: payload.input_type,
        timestamp: payload.timestamp,
      });
      showChatNotice("success", "Llego la respuesta pendiente del backend.");
      return;
    }

    addChatMessage("assistant", result.message, { kind: "error" });
  } catch (error) {
    addChatMessage("assistant", error.message, { kind: "error" });
  } finally {
    state.busy.polling = false;
    renderApp();
  }
}

async function performHealthCheck() {
  state.busy.health = true;
  state.healthStatus = null;
  state.healthMessage = "";
  renderApp();

  try {
    const response = await fetchWithTimeout(`${normalizeBaseUrl(state.apiBaseUrl)}/health`, {
      method: "GET",
      timeoutMs: 8000,
    });

    const payload = await safeJson(response);
    if (!response.ok) {
      throw new Error(extractResponseMessage(response, payload));
    }

    if (payload?.status === "ok") {
      state.healthStatus = "success";
      state.healthMessage = "Conexion lista. El backend respondio `status: ok`.";
      pushToast("success", "Conexion validada con /health.");
    } else {
      state.healthStatus = "warning";
      state.healthMessage = `/health respondio, pero con un payload inesperado: ${JSON.stringify(payload)}`;
      pushToast("warning", "El backend respondio, pero con un payload no esperado.");
    }
  } catch (error) {
    const probeSucceeded = await probeOpaqueRequest(
      `${normalizeBaseUrl(state.apiBaseUrl)}/health`,
      {
        method: "GET",
        timeoutMs: 8000,
      },
    );

    if (probeSucceeded) {
      state.healthStatus = "success";
      state.healthMessage =
        "El backend respondio en `/health`, pero el navegador no dejo leer el JSON por CORS. Para este entorno de prueba voy a tomarlo como conectividad valida.";
      pushToast("success", "Hay conectividad con /health.");
    } else {
      state.healthStatus = "danger";
      state.healthMessage = formatBackendFetchError(state.apiBaseUrl, "/health", "GET", error);
    }
  } finally {
    state.busy.health = false;
    renderApp();
  }
}

async function handleUserPrompt(prompt) {
  const { content, displayContent } = resolvePromptRequest(prompt);
  if (!content || state.busy.chat) {
    return;
  }

  if (hasPendingPolling()) {
    showChatNotice("warning", "Hay una respuesta pendiente. Consulta ese mensaje antes de enviar otro.");
    renderApp();
    return;
  }

  const useStart = !hasActiveConversation();
  state.busy.chat = true;
  addChatMessage("user", displayContent);
  state.chatDraft = "";
  renderApp();

  try {
    const result = await sendConversationMessage({
      baseUrl: state.apiBaseUrl,
      conversationId: state.conversationId,
      customerId: state.selectedCustomerId,
      content,
      useStart,
    });

    if (result.ok && result.pending) {
      state.conversationId = result.conversationId || state.conversationId;
      state.conversationStatus = cleanString(result.conversationStatus);
      const pendingPayload = result.messagePayload || {
        content: result.message,
        options: [],
        timestamp: null,
      };
      addChatMessage("assistant", pendingPayload.content, {
        options: pendingPayload.options,
        input_type: pendingPayload.input_type,
        timestamp: pendingPayload.timestamp,
      });
      markConversationAsPending(state.conversationId);
      showChatNotice("warning", "El backend sigue procesando. Usa \"Consultar mensaje en espera\" cuando este listo.");
      return;
    }

    if (result.ok) {
      clearPendingPollingState();
      state.conversationId = result.conversationId;
      state.conversationStatus = cleanString(result.conversationStatus);
      if (result.compatMode === "start_requires_conversation_id") {
        showChatNotice(
          "warning",
          "El backend activo no esta usando el contrato publicado para `/start`. El front aplico modo compatibilidad con `conversation_id`.",
        );
      }
      const parsedConversation = parseConversationId(result.conversationId);
      if (parsedConversation.customerId && parsedConversation.dateInput) {
        state.selectedCustomerId = parsedConversation.customerId;
        state.conversationDate = parsedConversation.dateInput;
        state.draftCustomerId = parsedConversation.customerId;
        state.draftConversationDate = parsedConversation.dateInput;
        syncDraftProductFromCustomer();
      }

      const payload = result.messagePayload || {
        content: result.message,
        options: [],
        timestamp: null,
      };
      addChatMessage("assistant", payload.content, {
        options: payload.options,
        input_type: payload.input_type,
        timestamp: payload.timestamp,
      });
    } else {
      addChatMessage("assistant", result.message, { kind: "error" });
    }
  } catch (error) {
    addChatMessage("assistant", error.message, { kind: "error" });
  } finally {
    state.busy.chat = false;
    renderApp();
  }
}

function addChatMessage(role, content, options = {}) {
  state.messages.push({
    role,
    content: cleanString(content),
    kind: options.kind || "message",
    options: Array.isArray(options.options) ? options.options : [],
    input_type: cleanString(options.input_type) || "choice",
    timestamp: cleanString(options.timestamp) || null,
  });
}

function resolvePromptRequest(prompt) {
  if (typeof prompt === "string") {
    const normalizedPrompt = cleanString(prompt);
    return {
      content: normalizedPrompt,
      displayContent: normalizedPrompt,
    };
  }

  return {
    content: cleanString(prompt?.content),
    displayContent: cleanString(prompt?.displayContent) || cleanString(prompt?.content),
  };
}

async function sendConversationMessage({ baseUrl, conversationId, customerId, content, useStart }) {
  if (useStart) {
    const startResult = await sendMessageRequest({
      baseUrl,
      endpointPath: "/start",
      conversationId,
      customerId,
      content: null,
    });

    if (startResult.ok) {
      const continuedChatResult = await sendMessageRequest({
        baseUrl,
        endpointPath: "/chat",
        conversationId: startResult.conversationId,
        customerId,
        content,
      });
      if (continuedChatResult.ok && startResult.compatMode) {
        continuedChatResult.compatMode = startResult.compatMode;
      }
      return continuedChatResult;
    }

    if (shouldRetryStartWithConversationId(startResult)) {
      const fallbackConversationId =
        cleanString(conversationId) || buildConversationId(customerId, todayInputValue());
      const compatStartResult = await sendMessageRequest({
        baseUrl,
        endpointPath: "/start",
        conversationId: fallbackConversationId,
        customerId,
        content: null,
        preferConversationIdForStart: true,
      });
      if (!compatStartResult.ok) {
        return compatStartResult;
      }

      compatStartResult.compatMode = "start_requires_conversation_id";
      const continuedChatResult = await sendMessageRequest({
        baseUrl,
        endpointPath: "/chat",
        conversationId: compatStartResult.conversationId,
        customerId,
        content,
      });
      if (continuedChatResult.ok) {
        continuedChatResult.compatMode = compatStartResult.compatMode;
      }
      return continuedChatResult;
    }

    if (shouldRetryWithChat(startResult)) {
      const fallbackResult = await sendMessageRequest({
        baseUrl,
        endpointPath: "/chat",
        conversationId,
        customerId,
        content,
      });
      if (fallbackResult.ok) {
        fallbackResult.fallbackFrom = "/start";
      }
      return fallbackResult;
    }

    return startResult;
  }

  const primaryResult = await sendMessageRequest({
    baseUrl,
    endpointPath: "/chat",
    conversationId,
    customerId,
    content,
  });

  if (primaryResult.ok) {
    return primaryResult;
  }

  if (shouldRetryWithStart(primaryResult)) {
    const fallbackResult = await sendMessageRequest({
      baseUrl,
      endpointPath: "/start",
      conversationId,
      customerId,
      content: null,
    });
    if (fallbackResult.ok) {
      fallbackResult.fallbackFrom = "/chat";
    }
    return fallbackResult;
  }

  return primaryResult;
}

async function sendMessageRequest({
  baseUrl,
  endpointPath,
  conversationId,
  customerId,
  content,
  preferConversationIdForStart = false,
}) {
  const payload = buildBackendPayload(
    endpointPath,
    conversationId,
    content,
    customerId,
    preferConversationIdForStart,
  );

  try {
    const response = await fetchWithTimeout(`${normalizeBaseUrl(baseUrl)}${endpointPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: buildJsonBody(payload),
      timeoutMs: 45000,
    });

    if (response.status === 204) {
      return {
        ok: true,
        pending: true,
        statusCode: 204,
        conversationId: cleanString(conversationId),
        endpointPath,
        message: "El backend sigue procesando este mensaje.",
      };
    }

    const data = await safeJson(response);

    if (!response.ok) {
      return {
        ok: false,
        statusCode: response.status,
        message: extractResponseMessage(response, data),
      };
    }

    const normalizedMessage = normalizeBackendMessage(data?.message);
    const returnedConversationId = cleanString(data?.conversation_id) || conversationId;

    if (!normalizedMessage) {
      return {
        ok: false,
        statusCode: response.status,
        message: `El payload de ${endpointPath} no tiene un campo message valido: ${JSON.stringify(data)}`,
      };
    }

    const conversationStatus = cleanString(data?.status);
    return {
      ok: true,
      statusCode: response.status,
      conversationStatus,
      pending: conversationStatus.toLowerCase() === "running",
      message: normalizedMessage.content,
      messagePayload: normalizedMessage,
      conversationId: returnedConversationId,
      endpointPath,
    };
  } catch (error) {
    return {
      ok: false,
      statusCode: null,
      message: formatBackendFetchError(baseUrl, endpointPath, "POST", error),
    };
  }
}

function buildBackendPayload(
  endpointPath,
  conversationId,
  content,
  customerId,
  preferConversationIdForStart = false,
) {
  if (endpointPath === "/start") {
    if (preferConversationIdForStart) {
      return {
        conversation_id: cleanString(conversationId),
      };
    }

    const userId = resolveUserId(customerId, conversationId);
    if (!userId) {
      throw new Error("No pude resolver el `user_id` requerido por `/start`.");
    }

    return {
      user_id: userId,
    };
  }

  if (endpointPath === "/end") {
    return {
      conversation_id: cleanString(conversationId),
    };
  }

  return {
    conversation_id: cleanString(conversationId),
    content: cleanString(content),
  };
}

function buildJsonBody(payload) {
  return JSON.stringify(payload);
}

function normalizeBackendMessage(message) {
  if (typeof message === "string") {
    const content = cleanString(message);
    if (!content) {
      return null;
    }

    return {
      content,
      options: [],
      sender: "bot",
      timestamp: null,
    };
  }

  if (!message || typeof message !== "object") {
    return null;
  }

  const rawContent = message.content;
  let content = "";
  const options = [];

  if (rawContent && typeof rawContent === "object") {
    content = cleanString(rawContent.label);
    if (Array.isArray(rawContent.options)) {
      rawContent.options.forEach((option) => {
        if (!option || typeof option !== "object") {
          return;
        }

        const optionKey = cleanString(option.key);
        const optionLabel = cleanString(option.label);
        if (optionKey && optionLabel) {
          options.push({ key: optionKey, label: optionLabel });
        }
      });
    }
  } else {
    content = cleanString(message.label);
  }

  if (!content) {
    return null;
  }

  return {
    content,
    options,
    sender: cleanString(message.sender) || "bot",
    timestamp: cleanString(message.timestamp) || null,
  };
}

function shouldRetryWithChat(result) {
  const message = cleanString(result.message).toLowerCase();
  return result.statusCode === 409 || message.includes("post /chat");
}

function shouldRetryWithStart(result) {
  const message = cleanString(result.message).toLowerCase();
  return result.statusCode === 404 || message.includes("post /start");
}

function shouldRetryStartWithConversationId(result) {
  if (![406, 422].includes(result.statusCode)) {
    return false;
  }

  const message = cleanString(result.message).toLowerCase();
  return (
    message.includes("body.conversation_id") &&
    message.includes("field required") &&
    message.includes("body.user_id") &&
    message.includes("extra inputs are not permitted")
  );
}

async function pollConversationMessage({ baseUrl, conversationId }) {
  const normalizedConversationId = cleanString(conversationId);
  const statusResult = await sendPollingStatusRequest({
    baseUrl,
    conversationId: normalizedConversationId,
  });

  if (!statusResult.ok || statusResult.pending) {
    return statusResult;
  }

  if (statusResult.messagePayload) {
    return statusResult;
  }

  return fetchPollingMessage({
    baseUrl,
    conversationId: normalizedConversationId,
  });
}

async function sendPollingStatusRequest({ baseUrl, conversationId }) {
  try {
    const response = await fetchWithTimeout(`${normalizeBaseUrl(baseUrl)}/polling`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: buildJsonBody({ conversation_id: cleanString(conversationId) }),
      timeoutMs: 45000,
      redirect: "manual",
    });

    if (response.type === "opaqueredirect" || response.status === 303) {
      return {
        ok: true,
        pending: false,
        ready: true,
        statusCode: response.status || 303,
        conversationId: cleanString(conversationId),
      };
    }

    if (response.status === 201) {
      const data = await safeJson(response);

      // PollingResponse { data: { status: "running" } } → sigue procesando, habilitar polling
      if (data?.data?.status === "running") {
        return {
          ok: true,
          pending: true,
          statusCode: 201,
          conversationId: cleanString(conversationId),
          message: "El backend sigue procesando este mensaje.",
        };
      }

      // ChatResponse con status Active → mensaje listo
      const normalizedMessage = normalizeBackendMessage(data?.message);
      const returnedConversationId = cleanString(data?.conversation_id) || conversationId;
      if (!normalizedMessage) {
        return {
          ok: false,
          statusCode: 201,
          message: `El payload de /polling no tiene un campo message valido: ${JSON.stringify(data)}`,
        };
      }

      return {
        ok: true,
        pending: false,
        statusCode: 201,
        conversationStatus: cleanString(data?.status),
        message: normalizedMessage.content,
        messagePayload: normalizedMessage,
        conversationId: returnedConversationId,
        endpointPath: "/polling",
      };
    }

    const data = await safeJson(response);
    if (!response.ok) {
      return {
        ok: false,
        statusCode: response.status,
        message: extractResponseMessage(response, data),
      };
    }

    const normalizedMessage = normalizeBackendMessage(data?.message);
    const returnedConversationId = cleanString(data?.conversation_id) || conversationId;
    if (!normalizedMessage) {
      return {
        ok: false,
        statusCode: response.status,
        message: `El payload de /polling no tiene un campo message valido: ${JSON.stringify(data)}`,
      };
    }

    return {
      ok: true,
      pending: false,
      statusCode: response.status,
      conversationStatus: cleanString(data?.status),
      message: normalizedMessage.content,
      messagePayload: normalizedMessage,
      conversationId: returnedConversationId,
      endpointPath: "/polling",
    };
  } catch (error) {
    return {
      ok: false,
      statusCode: null,
      message: formatBackendFetchError(baseUrl, "/polling", "POST", error),
    };
  }
}

async function fetchPollingMessage({ baseUrl, conversationId }) {
  try {
    const endpointPath = `/polling/${encodeURIComponent(cleanString(conversationId))}`;
    const response = await fetchWithTimeout(`${normalizeBaseUrl(baseUrl)}${endpointPath}`, {
      method: "GET",
      timeoutMs: 45000,
    });

    if (response.status === 204) {
      return {
        ok: true,
        pending: true,
        statusCode: 204,
        conversationId: cleanString(conversationId),
        message: "El backend sigue procesando este mensaje.",
      };
    }

    const data = await safeJson(response);
    if (!response.ok) {
      return {
        ok: false,
        statusCode: response.status,
        message: extractResponseMessage(response, data),
      };
    }

    const normalizedMessage = normalizeBackendMessage(data?.message);
    const returnedConversationId = cleanString(data?.conversation_id) || conversationId;
    if (!normalizedMessage) {
      return {
        ok: false,
        statusCode: response.status,
        message: `El payload de ${endpointPath} no tiene un campo message valido: ${JSON.stringify(data)}`,
      };
    }

    return {
      ok: true,
      pending: false,
      statusCode: response.status,
      conversationStatus: cleanString(data?.status),
      message: normalizedMessage.content,
      messagePayload: normalizedMessage,
      conversationId: returnedConversationId,
      endpointPath,
    };
  } catch (error) {
    return {
      ok: false,
      statusCode: null,
      message: formatBackendFetchError(baseUrl, `/polling/${cleanString(conversationId)}`, "GET", error),
    };
  }
}

async function loadMetricsSnapshot() {
  state.metricsLoading = true;
  state.metricsError = "";
  renderApp();

  try {
    state.metricsSnapshot = await buildMetricsSnapshot(state.metricsConfig);
    state.metricsConfigDirty = false;
    state.lastMetricsLoadedAt = new Date().toISOString();
    pushToast("success", "Metricas actualizadas desde OpenSearch.");
  } catch (error) {
    state.metricsError = error.message;
  } finally {
    state.metricsLoading = false;
    renderApp();
  }
}

async function buildMetricsSnapshot(config) {
  return openSearchProxyRequest(
    config,
    "/proxy/opensearch/snapshot",
    { config },
    {
      timeoutMs: resolveOpenSearchSnapshotTimeoutMs(config),
    },
  );
}

async function loadOpenSearchDocuments(config, indexName, pageSize = 500) {
  if (!indexName) {
    throw new Error("Debes indicar los indices de conversaciones y mensajes.");
  }

  const documents = [];
  let searchAfter = null;

  while (true) {
    const body = {
      size: pageSize,
      track_total_hits: true,
      sort: [{ _id: { order: "asc" } }],
    };
    if (searchAfter) {
      body.search_after = searchAfter;
    }

    const response = await openSearchRequest({
      config,
      method: "POST",
      path: `/${encodeURIComponent(indexName)}/_search`,
      jsonPayload: body,
      expectedStatuses: [200, 404],
    });

    if (response.status === 404) {
      return { documents: [], found: false };
    }

    const payload = await safeJson(response);
    const hits = payload?.hits?.hits || [];
    if (!hits.length) {
      break;
    }

    hits.forEach((hit) => {
      if (hit && typeof hit._source === "object") {
        documents.push(hit._source);
      }
    });

    searchAfter = hits[hits.length - 1]?.sort;
    if (hits.length < pageSize || !searchAfter) {
      break;
    }
  }

  return { documents, found: true };
}

function buildSnapshotFromRecords({ conversations, messages, sourceLabel, sourceDetails }) {
  const statusCounts = new Map();
  const workflowCounts = new Map();
  const messagesByConversation = new Map();

  messages.forEach((message) => {
    const conversationId = String(message?.conversation_id || "Sin ID");
    if (!messagesByConversation.has(conversationId)) {
      messagesByConversation.set(conversationId, []);
    }
    messagesByConversation.get(conversationId).push(message);
  });

  conversations.forEach((conversation) => {
    const status = String(conversation?.status || "Sin estado");
    const workflowName = resolveWorkflowName(conversation);
    statusCounts.set(status, (statusCounts.get(status) || 0) + 1);
    workflowCounts.set(workflowName, (workflowCounts.get(workflowName) || 0) + 1);
  });

  const assistantMessages = messages.filter(
    (message) => String(message?.role || "").toLowerCase() === "assistant",
  );
  const userMessages = messages.filter(
    (message) => String(message?.role || "").toLowerCase() === "user",
  );

  const assistantResponseDurations = assistantMessages
    .map(messageDurationMs)
    .filter((value) => value !== null);
  const userTurnDurations = userMessages
    .map(messageDurationMs)
    .filter((value) => value !== null);

  const totalInputTokens = assistantMessages.reduce(
    (sum, message) => sum + messageTokenValue(message, "input_tokens"),
    0,
  );
  const totalOutputTokens = assistantMessages.reduce(
    (sum, message) => sum + messageTokenValue(message, "output_tokens"),
    0,
  );
  const totalTokens = assistantMessages.reduce(
    (sum, message) => sum + messageTokenValue(message, "total_tokens"),
    0,
  );
  const turnsWithModelUsage = assistantMessages.filter(
    (message) => messageTokenValue(message, "total_tokens") > 0,
  ).length;

  const workflowTokens = new Map();
  const workflowDurations = new Map();
  const workflowMessages = new Map();
  const workflowAssistantTurns = new Map();

  const activityDates = conversations
    .map((conversation) => parseDateTime(conversation?.last_msg_date))
    .filter(Boolean);
  const latestActivity =
    activityDates.length > 0
      ? new Date(Math.max(...activityDates.map((value) => value.getTime())))
      : null;

  const conversationRows = conversations.map((conversation) => {
    const conversationId = String(conversation?.conversation_id || "Sin ID");
    const workflowName = resolveWorkflowName(conversation);
    const status = String(conversation?.status || "Sin estado");
    const conversationMessages = messagesByConversation.get(conversationId) || [];
    const conversationAssistantMessages = conversationMessages.filter(
      (message) => String(message?.role || "").toLowerCase() === "assistant",
    );
    const conversationDurations = conversationAssistantMessages
      .map(messageDurationMs)
      .filter((value) => value !== null);
    const conversationTotalTokens = conversationAssistantMessages.reduce(
      (sum, message) => sum + messageTokenValue(message, "total_tokens"),
      0,
    );
    const averageResponseMs = meanOrNull(conversationDurations);
    const maxResponseMs = conversationDurations.length
      ? Math.max(...conversationDurations)
      : null;
    const lastMsgDate = parseDateTime(conversation?.last_msg_date);

    workflowTokens.set(
      workflowName,
      (workflowTokens.get(workflowName) || 0) + conversationTotalTokens,
    );
    workflowMessages.set(
      workflowName,
      (workflowMessages.get(workflowName) || 0) + conversationMessages.length,
    );
    workflowAssistantTurns.set(
      workflowName,
      (workflowAssistantTurns.get(workflowName) || 0) + conversationAssistantMessages.length,
    );
    if (!workflowDurations.has(workflowName)) {
      workflowDurations.set(workflowName, []);
    }
    workflowDurations.get(workflowName).push(...conversationDurations);

    return {
      _sortLastMsgTs: lastMsgDate ? lastMsgDate.getTime() : Number.NEGATIVE_INFINITY,
      "Conversation ID": conversationId,
      Workflow: workflowName,
      Estado: status,
      "Paso actual": String(conversation?.current_step || "N/D"),
      Mensajes: conversationMessages.length,
      "Turns asistente": conversationAssistantMessages.length,
      Tokens: conversationTotalTokens,
      "Resp. prom. asistente": formatDurationMs(averageResponseMs),
      "Resp. max. asistente": formatDurationMs(maxResponseMs),
      "Ultima actividad": formatTimestamp(lastMsgDate),
    };
  });

  conversationRows.sort((left, right) => right._sortLastMsgTs - left._sortLastMsgTs);

  const workflowRows = Array.from(workflowCounts.entries())
    .sort((left, right) => right[1] - left[1])
    .map(([workflowName, count]) => ({
      Workflow: workflowName,
      Conversaciones: count,
      Mensajes: workflowMessages.get(workflowName) || 0,
      "Turns asistente": workflowAssistantTurns.get(workflowName) || 0,
      Tokens: workflowTokens.get(workflowName) || 0,
      "Resp. prom. asistente": formatDurationMs(
        meanOrNull(workflowDurations.get(workflowName) || []),
      ),
    }));

  const errorRows = conversationRows
    .filter((row) => row.Estado === "Error")
    .map(stripPrivateFields);
  const recentRows = conversationRows.slice(0, 10).map(stripPrivateFields);

  return {
    source: sourceLabel,
    conversationsIndex: sourceDetails.conversationsIndex,
    messagesIndex: sourceDetails.messagesIndex,
    knownSources: sourceDetails.knownSources,
    missingSources: sourceDetails.missingSources,
    sourceType: sourceDetails.sourceType,
    conversationCount: conversations.length,
    messageCount: messages.length,
    assistantMessageCount: assistantMessages.length,
    userMessageCount: userMessages.length,
    activeCount: statusCounts.get("Active") || 0,
    closedCount: statusCounts.get("Closed") || 0,
    errorCount: statusCounts.get("Error") || 0,
    totalInputTokens,
    totalOutputTokens,
    totalTokens,
    turnsWithModelUsage,
    avgAssistantResponseMs: meanOrNull(assistantResponseDurations),
    p95AssistantResponseMs: percentile(assistantResponseDurations, 95),
    avgUserTurnMs: meanOrNull(userTurnDurations),
    latestActivity,
    workflowRows,
    recentRows,
    errorRows,
  };
}

async function handleRemoteConversationDelete() {
  const activeConversationId = cleanString(state.conversationId);
  if (!activeConversationId) {
    showChatNotice("danger", "No hay un conversation_id activo para borrar.");
    return;
  }

  state.busy.deleteConversation = true;
  renderApp();

  try {
    const deletionResult = await deleteConversationFromOpenSearch(activeConversationId);
    clearLocalConversation();
    const deletedSummary = Object.entries(deletionResult.deletedByIndex)
      .map(([indexName, deletedCount]) => `${indexName}: ${deletedCount}`)
      .join(", ");

    const warningParts = [];
    if (deletionResult.missingIndices.length) {
      warningParts.push(
        `indices no encontrados: ${deletionResult.missingIndices.join(", ")}`,
      );
    }
    warningParts.push(...deletionResult.warnings);

    const noticeLevel =
      deletionResult.deletedTotal === 0 || warningParts.length ? "warning" : "success";
    let noticeMessage =
      `OpenSearch borro ${activeConversationId} en ${deletionResult.endpoint}. ` +
      `Documentos eliminados: ${deletionResult.deletedTotal} (${deletedSummary}).`;
    if (warningParts.length) {
      noticeMessage += ` Avisos: ${warningParts.join("; ")}.`;
    }

    showChatNotice(noticeLevel, noticeMessage);
  } catch (error) {
    showChatNotice("danger", error.message);
  } finally {
    state.busy.deleteConversation = false;
    renderApp();
  }
}

async function deleteConversationFromOpenSearch(conversationId) {
  const normalizedConversationId = cleanString(conversationId);
  if (!normalizedConversationId) {
    throw new Error("No hay un conversation_id activo para borrar.");
  }

  return openSearchProxyRequest(
    state.metricsConfig,
    "/proxy/opensearch/delete",
    {
      conversationId: normalizedConversationId,
      config: state.metricsConfig,
    },
    {
      timeoutMs: resolveOpenSearchDeleteTimeoutMs(state.metricsConfig),
    },
  );
}

async function openSearchProxyRequest(config, path, payload, options = {}) {
  const proxyUrl = normalizeBaseUrl(config?.proxyUrl || DEFAULT_METRICS_CONFIG.proxyUrl);
  if (!looksLikeUrl(proxyUrl)) {
    throw new Error(
      "Debes indicar una URL valida para el mini backend de OpenSearch, por ejemplo http://127.0.0.1:8090.",
    );
  }

  const timeoutMs =
    options.timeoutMs ||
    normalizePositiveNumber(config?.timeoutSeconds, DEFAULT_METRICS_CONFIG.timeoutSeconds) * 1000;
  const requestUrl = `${proxyUrl}${path}`;

  let response;
  try {
    response = await fetchWithTimeout(requestUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      timeoutMs,
    });
  } catch (error) {
    throw new Error(formatOpenSearchProxyFetchError(proxyUrl, error));
  }

  const responsePayload = await safeJson(response);
  if (!response.ok) {
    throw new Error(
      `El proxy OpenSearch devolvio HTTP ${response.status} en ${path}. Detalle: ${extractResponseMessage(response, responsePayload)}`,
    );
  }

  if (!responsePayload || typeof responsePayload !== "object") {
    throw new Error("El proxy OpenSearch respondio un payload vacio o invalido.");
  }

  return responsePayload;
}

function resolveOpenSearchDeleteTimeoutMs(config) {
  const baseTimeoutSeconds = normalizePositiveNumber(
    config?.timeoutSeconds,
    DEFAULT_METRICS_CONFIG.timeoutSeconds,
  );
  return Math.max(baseTimeoutSeconds, 60) * 1000;
}

function resolveOpenSearchSnapshotTimeoutMs(config) {
  const baseTimeoutSeconds = normalizePositiveNumber(
    config?.timeoutSeconds,
    DEFAULT_METRICS_CONFIG.timeoutSeconds,
  );
  return Math.max(baseTimeoutSeconds, 75) * 1000;
}

async function loadOpenSearchDocumentIds(config, indexName, conversationId, pageSize = 200) {
  const query = buildOpenSearchConversationQuery(conversationId).query;
  const documentIds = [];
  let searchAfter = null;

  while (true) {
    const body = {
      size: pageSize,
      _source: false,
      query,
      sort: [{ _id: { order: "asc" } }],
    };
    if (searchAfter) {
      body.search_after = searchAfter;
    }

    const response = await openSearchRequest({
      config,
      method: "POST",
      path: `/${encodeURIComponent(indexName)}/_search`,
      jsonPayload: body,
      expectedStatuses: [200, 404],
    });

    if (response.status === 404) {
      return { documentIds: [], indexExists: false };
    }

    const payload = await safeJson(response);
    const hits = payload?.hits?.hits || [];
    if (!hits.length) {
      break;
    }

    hits.forEach((hit) => {
      if (hit?._id !== undefined && hit?._id !== null) {
        documentIds.push(String(hit._id));
      }
    });

    searchAfter = hits[hits.length - 1]?.sort;
    if (hits.length < pageSize || !searchAfter) {
      break;
    }
  }

  return { documentIds, indexExists: true };
}

async function deleteOpenSearchDocumentById(config, indexName, documentId) {
  const response = await openSearchRequest({
    config,
    method: "DELETE",
    path: `/${encodeURIComponent(indexName)}/_doc/${encodeURIComponent(documentId)}`,
    params: { refresh: "false" },
    expectedStatuses: [200, 404],
  });

  if (response.status === 404) {
    return { deleted: false, indexExists: false };
  }

  const payload = await safeJson(response);
  const result = cleanString(payload?.result);
  if (result === "not_found") {
    return { deleted: false, indexExists: true };
  }

  return { deleted: true, indexExists: true };
}

async function bulkDeleteOpenSearchDocuments(config, indexName, documentIds, chunkSize = 200) {
  if (!documentIds.length) {
    return { deletedCount: 0, failures: [] };
  }

  let deletedCount = 0;
  const failures = [];

  for (let start = 0; start < documentIds.length; start += chunkSize) {
    const chunk = documentIds.slice(start, start + chunkSize);
    const operations = chunk
      .map((documentId) =>
        `${JSON.stringify({ delete: { _index: indexName, _id: documentId } })}\n`,
      )
      .join("");

    const response = await openSearchRequest({
      config,
      method: "POST",
      path: "/_bulk",
      dataPayload: operations,
      params: { refresh: "false" },
      headers: { "Content-Type": "application/x-ndjson" },
      expectedStatuses: [200],
    });

    const payload = await safeJson(response);
    (payload?.items || []).forEach((item) => {
      const result = item?.delete || {};
      const status = Number(result.status || 0);
      if (status === 200 || status === 202) {
        deletedCount += 1;
        return;
      }
      if (status === 404) {
        return;
      }
      failures.push(String(result.error || JSON.stringify(result)));
    });
  }

  return { deletedCount, failures };
}

async function refreshOpenSearchIndex(config, indexName) {
  const response = await openSearchRequest({
    config,
    method: "POST",
    path: `/${encodeURIComponent(indexName)}/_refresh`,
    expectedStatuses: [200, 404],
  });

  return response.status !== 404;
}

async function openSearchRequest({
  config,
  method,
  path,
  jsonPayload = null,
  dataPayload = null,
  params = null,
  headers = {},
  expectedStatuses = [200],
}) {
  const endpoint = cleanString(config.endpoint).replace(/\/$/, "");
  if (!endpoint) {
    throw new Error("Debes indicar un endpoint de OpenSearch.");
  }

  const timeoutMs = normalizePositiveNumber(config.timeoutSeconds, 10) * 1000;
  const url = new URL(`${endpoint}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      url.searchParams.set(key, value);
    });
  }

  const mergedHeaders = { ...headers };
  if (cleanString(config.user) || cleanString(config.password)) {
    mergedHeaders.Authorization = `Basic ${btoa(`${config.user}:${config.password}`)}`;
  }

  let body = undefined;
  if (dataPayload !== null && dataPayload !== undefined) {
    body = dataPayload;
  } else if (jsonPayload !== null && jsonPayload !== undefined) {
    body = JSON.stringify(jsonPayload);
    if (!mergedHeaders["Content-Type"]) {
      mergedHeaders["Content-Type"] = "application/json";
    }
  }

  let response;
  try {
    response = await fetchWithTimeout(url.toString(), {
      method,
      headers: mergedHeaders,
      body,
      timeoutMs,
    });
  } catch (error) {
    throw new Error(formatOpenSearchFetchError(endpoint, error));
  }

  if (!expectedStatuses.includes(response.status)) {
    const payload = await safeJson(response);
    throw new Error(
      `OpenSearch devolvio HTTP ${response.status} en ${path}. Detalle: ${extractResponseMessage(response, payload)}`,
    );
  }

  return response;
}

function buildOpenSearchConversationQuery(conversationId) {
  const normalizedConversationId = cleanString(conversationId);
  return {
    query: {
      bool: {
        should: [
          { term: { "conversation_id.keyword": normalizedConversationId } },
          { term: { conversation_id: normalizedConversationId } },
          { match_phrase: { conversation_id: normalizedConversationId } },
        ],
        minimum_should_match: 1,
      },
    },
  };
}

function formatOpenSearchProxyFetchError(proxyUrl, error) {
  const detail = cleanString(error?.message) || "Sin detalle adicional.";
  const normalizedDetail = detail.toLowerCase();

  if (normalizedDetail.includes("excedio")) {
    return (
      `La consulta al mini backend de OpenSearch en ${proxyUrl} supero el tiempo de espera. ` +
      "Para snapshots grandes, el front ya da mas margen automatico, asi que si vuelve a pasar " +
      "conviene revisar la carga de OpenSearch o subir el `Timeout` en la configuracion. " +
      `Detalle: ${detail}`
    );
  }

  if (normalizedDetail.includes("failed to fetch")) {
    return (
      `No pude comunicarme con el mini backend de OpenSearch en ${proxyUrl}. ` +
      "Verifica que `opensearch_proxy.py` este levantado y que el `Proxy URL` de la UI apunte a ese puerto. " +
      `Detalle: ${detail}`
    );
  }

  return `No pude comunicarme con el mini backend de OpenSearch en ${proxyUrl}. Detalle: ${detail}`;
}

function formatOpenSearchFetchError(endpoint, error) {
  const detail = cleanString(error?.message) || "Sin detalle adicional.";
  const normalizedDetail = detail.toLowerCase();

  if (normalizedDetail.includes("failed to fetch")) {
    return (
      `No pude comunicarme con OpenSearch en ${endpoint}. En navegador, ` +
      "esto suele significar CORS bloqueado, certificado HTTPS no confiado, " +
      "header Authorization rechazado o endpoint no alcanzable. " +
      "La lectura ya esta alineada con el Streamlit (`POST _search` con JSON), " +
      "pero el navegador no puede replicar `verify_ssl=False`. " +
      `Prueba abrir ${endpoint} directamente en el navegador; si tu cluster no requiere auth, deja usuario y password vacios en la UI y vuelve a refrescar. Detalle: ${detail}`
    );
  }

  return `No pude comunicarme con OpenSearch en ${endpoint}. Detalle: ${detail}`;
}

function formatBackendFetchError(baseUrl, endpointPath, method, error) {
  const endpoint = `${normalizeBaseUrl(baseUrl)}${endpointPath}`;
  const detail = cleanString(error?.message) || "Sin detalle adicional.";
  const normalizedDetail = detail.toLowerCase();

  if (normalizedDetail.includes("failed to fetch")) {
    if (method === "GET") {
      return (
        `No pude leer la respuesta de ${endpoint}. El navegador suele mostrar este fallo ` +
        "cuando el backend responde pero no habilita CORS para este origen, " +
        `o cuando hay un problema de certificado/red. Detalle: ${detail}`
      );
    }

    return (
      `No pude completar ${method} ${endpoint}. Si en la red ves un ` +
      "`OPTIONS` pero nunca sale el `POST`, el backend no esta habilitando CORS " +
      "para este frontend. En navegador, un `POST` JSON correcto suele requerir " +
      `preflight, y el navegador sigue bloqueando la llamada. Detalle: ${detail}`
    );
  }

  return `No pude comunicarme con el backend en ${endpoint}. Detalle: ${detail}`;
}

async function probeOpaqueRequest(url, options = {}) {
  try {
    await fetchWithTimeout(url, {
      method: options.method || "GET",
      mode: "no-cors",
      timeoutMs: options.timeoutMs || 8000,
    });
    return true;
  } catch (error) {
    return false;
  }
}

function loadEmbargoCustomerOptions(csvText) {
  const rows = parseDelimitedCsv(csvText, ";");
  if (!rows.length) {
    return [];
  }

  const header = rows[0].map((value, index) =>
    index === 0 ? value.replace(/^\uFEFF/, "") : value,
  );
  const groupedRows = new Map();

  rows.slice(1).forEach((cells) => {
    if (!cells.some((value) => cleanString(value))) {
      return;
    }

    const row = Object.fromEntries(
      header.map((column, index) => [column, cells[index] ?? ""]),
    );
    const customerId = cleanString(row.customer_id);
    if (!customerId) {
      return;
    }

    if (!groupedRows.has(customerId)) {
      groupedRows.set(customerId, []);
    }

    groupedRows.get(customerId).push({
      contractId: cleanString(row.contract_id),
      productId: cleanString(row.contract_product_id),
    });
  });

  const options = [];
  groupedRows.forEach((customerRows, customerId) => {
    const productIds = [...new Set(customerRows.map((row) => row.productId).filter(Boolean))].sort();
    if (productIds.length < 2) {
      return;
    }

    const productOptions = productIds.map((productId) => {
      const contractIds = uniquePreservingOrder(
        customerRows
          .filter((row) => row.productId === productId && row.contractId)
          .map((row) => row.contractId),
      );
      let contractPreview = contractIds.length
        ? contractIds.slice(0, 3).join(", ")
        : "Sin contratos";
      if (contractIds.length > 3) {
        contractPreview = `${contractPreview}...`;
      }

      return {
        productId,
        contractIds,
        label: `Producto ${productId} | contratos: ${contractPreview}`,
      };
    });

    options.push({
      customerId,
      rowCount: customerRows.length,
      productCount: productIds.length,
      productIds,
      productOptions,
      label: `${customerId} | productos ${productIds.join(", ")} | ${customerRows.length} registro(s)`,
    });
  });

  options.sort((left, right) => {
    if (right.productCount !== left.productCount) {
      return right.productCount - left.productCount;
    }
    if (right.rowCount !== left.rowCount) {
      return right.rowCount - left.rowCount;
    }
    return left.customerId.localeCompare(right.customerId);
  });

  return options;
}

function parseDelimitedCsv(text, delimiter) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];

    if (char === "\"") {
      if (inQuotes && text[index + 1] === "\"") {
        cell += "\"";
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === delimiter && !inQuotes) {
      row.push(cell);
      cell = "";
      continue;
    }

    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && text[index + 1] === "\n") {
        index += 1;
      }
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
      continue;
    }

    cell += char;
  }

  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }

  return rows;
}

function parseConversationId(value) {
  const normalizedValue = cleanString(value);
  const separatorIndex = normalizedValue.lastIndexOf("_");
  if (separatorIndex <= 0) {
    return { customerId: null, dateInput: null };
  }

  const customerId = normalizedValue.slice(0, separatorIndex);
  const rawDate = normalizedValue.slice(separatorIndex + 1);
  if (!/^\d{8}$/.test(rawDate)) {
    return { customerId: null, dateInput: null };
  }

  const dateInput = `${rawDate.slice(0, 4)}-${rawDate.slice(4, 6)}-${rawDate.slice(6, 8)}`;
  if (!normalizeInputDate(dateInput)) {
    return { customerId: null, dateInput: null };
  }

  return { customerId, dateInput };
}

function resolveUserId(customerId, conversationId) {
  const normalizedCustomerId = cleanString(customerId);
  if (normalizedCustomerId) {
    return normalizedCustomerId;
  }

  return cleanString(parseConversationId(conversationId).customerId);
}

function buildConversationId(customerId, conversationDate) {
  const normalizedCustomerId = cleanString(customerId);
  const normalizedConversationDate = normalizeInputDate(conversationDate) || todayInputValue();
  if (!normalizedCustomerId) {
    return "";
  }

  return `${normalizedCustomerId}_${normalizedConversationDate.replaceAll("-", "")}`;
}

function findCustomerOption(customerId) {
  const normalizedCustomerId = cleanString(customerId);
  return state.customerOptions.find(
    (option) => String(option.customerId) === normalizedCustomerId,
  ) || null;
}

function contractPreview(contractIds) {
  const preview = contractIds.slice(0, 4).join(", ");
  return contractIds.length > 4 ? `${preview}...` : preview || "Sin contratos visibles";
}

function statusClass(level) {
  if (level === "success") {
    return "status-success";
  }
  if (level === "warning") {
    return "status-warning";
  }
  if (level === "danger") {
    return "status-danger";
  }
  return "status-neutral";
}

function alertClass(level) {
  if (level === "success") {
    return "success";
  }
  if (level === "warning") {
    return "warning";
  }
  if (level === "danger") {
    return "danger";
  }
  return "info";
}

function alertTitle(level) {
  if (level === "success") {
    return "Listo";
  }
  if (level === "warning") {
    return "Ojo";
  }
  if (level === "danger") {
    return "Problema";
  }
  return "Info";
}

function healthPillLabel() {
  if (state.busy.health) {
    return "Probando";
  }
  if (state.healthStatus === "success") {
    return "Backend listo";
  }
  if (state.healthStatus === "warning") {
    return "Payload raro";
  }
  if (state.healthStatus === "danger") {
    return "Sin conexion";
  }
  return "Pendiente";
}

function statusCardMeta(level, message) {
  if (!message) {
    return "usa /health para validar";
  }
  if (level === "success") {
    return "conexion validada";
  }
  if (level === "warning") {
    return "revisa el payload";
  }
  if (level === "danger") {
    return "error de conectividad";
  }
  return "sin validar";
}

function showChatNotice(level, message) {
  state.chatNotice = { level, message };
  pushToast(level === "danger" ? "danger" : level, message);
  renderApp();
}

function pushToast(level, message) {
  const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  state.toasts = [...state.toasts, { id, level, message }];
  renderToasts();

  window.setTimeout(() => {
    state.toasts = state.toasts.filter((toast) => toast.id !== id);
    renderToasts();
  }, 4200);
}

function renderToasts() {
  const stack = document.getElementById("toast-stack");
  if (!stack) {
    return;
  }

  stack.innerHTML = state.toasts
    .map(
      (toast) => `
        <section class="toast toast-${alertClass(toast.level)}">
          <strong>${escapeHtml(alertTitle(toast.level))}</strong>
          <p>${escapeHtml(toast.message)}</p>
        </section>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function cleanString(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
}

function uniquePreservingOrder(values) {
  return [...new Set(values.filter(Boolean))];
}

function formatNumber(value) {
  return new Intl.NumberFormat("es-CO").format(Number(value || 0));
}

function normalizeBaseUrl(value) {
  return cleanString(value).replace(/\/$/, "");
}

function todayInputValue() {
  return new Date().toISOString().slice(0, 10);
}

function normalizeInputDate(value) {
  const normalized = cleanString(value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    return "";
  }

  const date = new Date(`${normalized}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return normalized;
}

function normalizePositiveNumber(value, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return parsed;
}

function autoResizeTextarea(textarea) {
  textarea.style.height = "0px";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
}

function scrollChatToBottom() {
  const chatLog = document.getElementById("chat-log");
  if (chatLog) {
    chatLog.scrollTop = chatLog.scrollHeight;
  }
}

function formatDurationMs(value) {
  if (value === null || value === undefined) {
    return "N/D";
  }

  const duration = Number(value);
  if (duration < 1000) {
    return `${Math.round(duration)} ms`;
  }

  return `${(duration / 1000).toFixed(2)} s`;
}

function formatTimestamp(value) {
  if (!value) {
    return "N/D";
  }

  const date = value instanceof Date ? value : parseDateTime(value);
  if (!date) {
    return "N/D";
  }

  return new Intl.DateTimeFormat("es-CO", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function parseDateTime(value) {
  if (!cleanString(value)) {
    return null;
  }

  const normalized = cleanString(value).replace("Z", "+00:00");
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function resolveWorkflowName(conversation) {
  const workflowName = cleanString(conversation?.workflow);
  if (workflowName) {
    return workflowName;
  }

  const flowAnswers = conversation?.flow_answers;
  if (flowAnswers && typeof flowAnswers === "object") {
    for (const key of ["workflow", "workflow_name", "flow_name"]) {
      const candidate = cleanString(flowAnswers[key]);
      if (candidate) {
        return candidate;
      }
    }
  }

  const capturedData = conversation?.captured_data;
  if (capturedData && typeof capturedData === "object") {
    for (const key of ["workflow", "workflow_name", "flow_name"]) {
      const candidate = cleanString(capturedData[key]);
      if (candidate) {
        return candidate;
      }
    }
  }

  return "Sin workflow";
}

function messageTokenValue(message, fieldName) {
  const tokens = message?.tokens;
  if (!tokens || typeof tokens !== "object") {
    return 0;
  }

  return asInt(tokens[fieldName]);
}

function messageDurationMs(message) {
  const timing = message?.timing;
  if (!timing || typeof timing !== "object") {
    return null;
  }

  if (timing.total_duration_ms === null || timing.total_duration_ms === undefined) {
    return null;
  }

  return asInt(timing.total_duration_ms);
}

function asInt(value) {
  if (typeof value === "boolean") {
    return Number(value);
  }
  if (typeof value === "number") {
    return Math.trunc(value);
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.trunc(parsed) : 0;
  }
  return 0;
}

function meanOrNull(values) {
  if (!values.length) {
    return null;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function percentile(values, percentileValue) {
  if (!values.length) {
    return null;
  }

  const ordered = [...values].sort((left, right) => left - right);
  const position = Math.max(Math.ceil(ordered.length * (percentileValue / 100)) - 1, 0);
  return ordered[position];
}

function stripPrivateFields(row) {
  const result = {};
  Object.entries(row).forEach(([key, value]) => {
    if (!key.startsWith("_")) {
      result[key] = value;
    }
  });
  return result;
}

function looksLikeUrl(value) {
  const normalized = cleanString(value).toLowerCase();
  return normalized.startsWith("http://") || normalized.startsWith("https://");
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs || 10000;
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(`La solicitud excedio ${Math.round(timeoutMs / 1000)} segundos.`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function safeJson(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch (error) {
    return { _rawText: text };
  }
}

function extractResponseMessage(response, payload) {
  if (payload && typeof payload === "object") {
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
    if (payload.detail !== undefined && payload.detail !== null) {
      return String(payload.detail);
    }
    if (typeof payload._rawText === "string" && payload._rawText.trim()) {
      return payload._rawText.trim();
    }
  }

  return `HTTP ${response.status}`;
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("No pude leer el archivo."));
    reader.readAsText(file, "utf-8");
  });
}
