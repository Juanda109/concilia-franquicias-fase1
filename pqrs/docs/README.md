# Documentación del proyecto PQRS

> Última actualización: **2026-09-10**, rama `feature/PQRSllmops`.

## Por dónde empezar

| Documento | Para qué |
|---|---|
| [`ARQUITECTURA_BACK_AGENT.md`](./ARQUITECTURA_BACK_AGENT.md) | Cómo decide el agente en cada turno: guardrails, ruteo, aclaración, timeouts |
| [`trx no reconocida/ESPECIFICACION_FLUJO.md`](./trx%20no%20reconocida/ESPECIFICACION_FLUJO.md) | El flujo TXNR nodo por nodo, **tal como está hoy** |
| [`trx no reconocida/ESTADO_Y_CONFIG.md`](./trx%20no%20reconocida/ESTADO_Y_CONFIG.md) | Estado, persistencia y todas las variables por ambiente |
| [`trx no reconocida/CSV_TANTIA.md`](./trx%20no%20reconocida/CSV_TANTIA.md) | El CSV para el RPA de Tantia |
| [`trx no reconocida/DATOS_PRUEBA_POSTGRES.md`](./trx%20no%20reconocida/DATOS_PRUEBA_POSTGRES.md) | Clientes de prueba en Postgres |
| [`trx no reconocida/CLIENTES_SIMULADOR.md`](./trx%20no%20reconocida/CLIENTES_SIMULADOR.md) | Clientes canónicos del simulador ASO |
| [`METRICAS_CAMPOS_Y_VISUALIZACIONES.md`](./METRICAS_CAMPOS_Y_VISUALIZACIONES.md) · [`METRICS.md`](./METRICS.md) | Analítica: índices, diccionario de campos (conversación **y benchmark**), tableros, alerta del canario |
| [`INFORME_TECNICO_IA.md`](./INFORME_TECNICO_IA.md) | Informe técnico para RCS en formato banco, generado por `scripts/build_informe_tecnico.py` a partir de los documentos de esta carpeta (regenerar tras cambiar cualquiera) |
| [`MATRIZ_EVIDENCIAS_RCS.md`](./MATRIZ_EVIDENCIAS_RCS.md) · [`INVENTARIO_TESTS.md`](./INVENTARIO_TESTS.md) | Los 28 controles de RCS con qué existe, qué captura falta en dev y de quién depende; guía de captura; inventario de tests por control generado desde las suites |
| [`DOCUMENTO_RCS_TNR.md`](./DOCUMENTO_RCS_TNR.md) · [`EVIDENCIAS_TNR_RCS.md`](./EVIDENCIAS_TNR_RCS.md) | El informe funcional de transacción no reconocida para RCS, y el cuaderno de evidencias con el formato del banco (capturas en `evidencias_rcs/`) |
| [`PLAN_DE_PRUEBAS_IA.md`](./PLAN_DE_PRUEBAS_IA.md) · [`GOBIERNO_Y_OPERACION_IA.md`](./GOBIERNO_Y_OPERACION_IA.md) · [`REGISTRO_HALLAZGOS.md`](./REGISTRO_HALLAZGOS.md) | Plan de pruebas para firma (capas, datasets, umbrales, cuándo se corre qué), roles, gestión de cambios, contingencia y el registro de hallazgos con retest (KYNS IT 1 e IT 2) |
| [`CATALOGO_CAPACIDADES.md`](./CATALOGO_CAPACIDADES.md) · [`AUTONOMIA_E_INTEGRIDAD.md`](./AUTONOMIA_E_INTEGRIDAD.md) | Allowlist de acciones generada del YAML, puertas antes de cada acción con efecto, idempotencia, límites y aislamiento (KYNS IT 4) |
| [`TRAZAS_DATOS_SENSIBLES.md`](./TRAZAS_DATOS_SENSIBLES.md) | Qué nunca se persiste en las trazas (granting, TSEC, PAN), las tres capas de enmascarado y el barrido de MinIO |
| [`GUIA_OSD_PASO_A_PASO.md`](./GUIA_OSD_PASO_A_PASO.md) · [`DESPLIEGUE_ANALITICA_OKD.md`](./DESPLIEGUE_ANALITICA_OKD.md) | Despliegue de analítica (incluye benchmark/canario en el pipeline y la alerta) |

Obsoletos, conservados con nota de redirección: `EXCEL_TANTIA.md`.

---

## Cambios recientes (septiembre 2026)

### Documentos de gobierno y ficha de versión (10/09, frente 5)
- `PLAN_DE_PRUEBAS_IA.md` (para firma), `GOBIERNO_Y_OPERACION_IA.md` (roles, cambios,
  catálogo, contingencia, monitoreo) y `REGISTRO_HALLAZGOS.md` (16 hallazgos con severidad,
  dueño y retest). `scripts/build_release_card.py` genera la ficha de versión (imágenes,
  modelo, portones, huella del catálogo, prompts, guardrail y datasets); `run_all_local.sh`
  la deja junto a cada corrida.

### Catálogo de capacidades e integridad financiera (9/09, frente 4)
- `co_pqrs_back_agent/scripts/build_capability_catalog.py` genera `CATALOGO_CAPACIDADES.md`:
  34 acciones clasificadas, 4 con efecto, y para cada una los pasos por los que pasa todo
  camino del YAML (confirmación del cliente, reglas, autorización en la App). Tests de
  contrato, idempotencia, concurrencia y aislamiento. Evidencia IT 4 en
  `AUTONOMIA_E_INTEGRIDAD.md`.

### Grounding: lo que el bot dice sale de su fuente (9/09, frente 3)
- El benchmark aprende `must_not_invent` (fallo `invented`), `must_contain` (fallo `grounding`)
  y `user_id`; el saludo de `POST /start` entra en la comprobación y el agente reporta
  `response_source` (quién redactó: modelo, YAML o respaldo local). Dataset
  `co_pqrs_benchmark/datasets/grounding.json` (23 casos: saludo, cierre de guía, aclaración del
  router, validación de fecha) y tablero *PQRS · Grounding*. Primer hallazgo: a una persona
  jurídica se la saluda por su razón social ("Hola, Inversiones El Roble Sas").

### Dataset de ruteo de trx_no_reconocida (9/09, frente 3)
- `co_pqrs_benchmark/datasets/trx_no_reconocida_routing.json`: 36 casos (sanity,
  generalización, frontera con los siete vecinos del catálogo y desambiguación multiturno).
  Test de contrato contra `general.yml`, incluido en el ConfigMap del CronJob. Piso en
  contingencia 55,6 %; la medida real sale con el LLM.

### Trazas sin datos sensibles (9/09, KYNS IT 3)
- La contraseña del granting y el TSEC completo **ya no pueden** escribirse en las trazas:
  los flags `ASO_TRACE_PASSWORD_FULL` y `ASO_TRACE_TSEC_FULL` se retiraron del código. El
  volcado E2E guarda `body_full_masked` (PAN a últimos 4, sin correos). El error handler
  aplica un sanitizador sin flag antes de MinIO. Detalle y barrido de lo histórico en
  `TRAZAS_DATOS_SENSIBLES.md`.

### Benchmark y canario en la analítica
- **Eventos propios por el mismo pipeline.** `co_pqrs_benchmark` publica `benchmark.case`
  (uno por caso) y `benchmark.run` (uno por corrida) al exchange `pqr.events`, con las mismas
  variables `RABBITMQ_*` que el agente y fire-and-forget: sin RabbitMQ el job loguea y sigue
  escribiendo su NDJSON y su resumen. Aterrizan en `pqr-benchmark-runs-YYYY.MM` (ISM 365 d).
- **Las conversaciones sintéticas ya no contaminan `pqr-metrics-*`.** El agente marca con
  `source: benchmark` toda conversación abierta con `X-Benchmark-Mode` en `/start`; todos sus
  eventos posteriores heredan la marca y Logstash los desvía a
  `pqr-benchmark-conversations-YYYY.MM` (ISM 90 d). Un agente viejo (sin `source`) sigue
  cayendo donde caía: **nada de lo visible hoy cambia**.
- **Tablero "PQRS Benchmark"** paso a paso (precisión por corrida, fallos por tipología, p95
  de ruteo/e2e, tokens por caso, últimas corridas) en la guía de métricas §4.4.
- **Alerta del canario.** Monitor de OpenSearch Alerting cada 30 min: si el último
  `benchmark.run` con `source: canario` tiene `precision_pct` bajo el umbral, correo por el
  relay SMTP interno (el del reporte, sin Secret). **Umbral provisional 90 %, decisión de
  Fabián** (`CANARIO_PRECISION_THRESHOLD` en `IaC/elk/opensearch-analytics/12-job-bootstrap-alerting.yaml`).

---

## Cambios anteriores (agosto 2026)

### Guardrails
- **Corregido un falso positivo grave.** El patrón antiinyección `\bDAN\b` coincidía
  con el verbo español *"dan"* y bloqueaba quejas legítimas ("en el banco no me
  **dan** razón"). Medido: 8 de 12 frases reales quedaban bloqueadas. Los patrones
  se reescribieron exigiendo contexto; verificado con 0 falsos positivos y 0 falsos
  negativos.
- **Red de seguridad en el juez de alcance.** Un mensaje con cualquier señal
  bancaria (producto, monto, PQRS, fraude, canal) **no puede** bloquearse, aunque el
  LLM lo marque fuera de alcance.
- **Mensajes propios** para entrada vacía y demasiado larga, en vez del mensaje de
  "fuera de alcance", que era desconcertante para una queja larga y legítima.

### Ruteo
- **Camino de aclaración.** El formulario PQR pasó a ser el último recurso: el 1er
  no-match pide reformular y solo el 2º consecutivo entrega el formulario.
- **Sin texto del LLM al cliente.** Se eliminaron `clarification_message`,
  `assistant_message` y una función muerta que filtraba el `rationale`. El cierre de
  flujos guía se apagó con `LLM_CLOSURE_ENABLED=false`; era la razón por la que el
  bot imitaba el dialecto del cliente.
- **Corregida una regresión propia** de la similitud difusa: `queja`, `saldo`,
  `cuenta` y `estafa` se trataban como saludos.
- **Meta-peticiones posesivas** (`tengo una queja`) ahora piden el motivo.

### Flujo TXNR
- **Portón de despliegue (canario).** El flujo entra cerrado en producción y se
  abre por conversación con un token de chat.
- **Filtro de productos** acepta `VIGENTE` y `ACTIVO` en `contract_status_type_desc`.
- **Guardrail anti-mock**: `TRX_ALLOW_MOCKS=false` en producción y QA.

### Tantia
- **El Excel se reemplazó por un CSV** de 20 columnas con **una fila por
  transacción**, a las 16:00 en días hábiles. Requirió acumular las transacciones
  en `tantia_items`, porque antes el dato se sobrescribía en cada vuelta del bucle.
- **El índice inexistente ya no es un error**: el job sale limpio en vez de fallar.
- **Ventana de corte por día hábil**: el fichero de cada día hábil cubre desde el
  corte anterior (16:00 del día hábil previo) hasta el corte de hoy. El lunes incluye
  viernes tras el corte, sábado y domingo; después de un festivo, incluye el festivo.
  Ventanas **contiguas**: ninguna transacción se pierde ni se entrega dos veces.
- **Festivos colombianos calculados** con la librería `holidays` (Ley Emiliani y
  festivos pascuales incluidos), no una lista que haya que mantener cada año.
- **El fichero se entrega siempre**, tenga datos o no, porque es un fichero de corte.
  Excepción: un fallo de conexión hace fallar el job en vez de entregar un fichero
  vacío que diría "no hubo abonos".

> Las garantías del modelo, con el test que sostiene cada una, están en
> [`CSV_TANTIA.md`](./trx%20no%20reconocida/CSV_TANTIA.md) §6.

---

## Pendientes conocidos

| # | Tema | Detalle |
|---|---|---|
| 1 | **Timeouts anidados al revés** | `back_trx→ASO` (30 s) supera `agente→back_trx` (10 s). Ver `ARQUITECTURA_BACK_AGENT.md` §7 |
| 2 | **TSEC sin caché** | Se pide en cada operación; encadenar 3 llamadas agota el presupuesto del turno |
| 3 | **Secretos en configmaps** | `OPENSEARCH_PASSWORD` y `COMMERCIAL_INFO_API_PASSWORD` están en texto plano y versionados. Mover a `Secret` y **rotar** |
| 4 | **PVC `smb-pvc-tx`** | Referenciado por 4 cronjobs pero no definido en el IaC |
| 5 | **Calidad del ruteo LLM** | El harness mide solo las capas deterministas; `cuota de manejo` y `paz y salvo` no matchearon en producción. El benchmark/canario (`co_pqrs_benchmark`) ahora lo mide contra el LLM real y lo grafica en OSD |
| 6 | **Umbral de la alerta del canario** | 90 % es provisional; Fabián decide el definitivo (guía de métricas §6) |

---

## Comandos de verificación

```bash
# Agente (esperado: 12 fallas preexistentes; otro número = regresión)
cd co_pqrs_back_agent && PYTHONPATH=src uv run python -m unittest discover -s tests -p 'test_*.py'

# Evaluación del ruteo con 376 casos reales
cd co_pqrs_back_agent && PYTHONPATH=src uv run python tests/eval_routing.py

# Back TXNR
cd co_pqrs_back_trx_noreconocida && PYTHONPATH=src:tests python3 -m unittest discover -s tests -p 'test_*.py'

# Exportador CSV y simulador
cd co_pqrs_back_trx_tantia_export && uv run --extra dev pytest -q
cd co_pqrs_back_trx_aso_simulator && uv run --extra dev pytest -q

# IaC
kubectl kustomize IaC > /dev/null && echo OK
```
