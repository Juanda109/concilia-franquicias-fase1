# Servicio de autorización (co_pqrs_authorization) — qué es y cómo probarlo

**Rama:** `feature/E2Esubidanivel` · **Fecha:** 03/09/2026

## Qué se hizo y por qué

La subida de nivel (el push a la App BBVA, la consulta del estado, el plazo de
180 segundos, el resultado) vivía dentro del flujo TXNR, repartida entre el
agente y el servicio de transacción no reconocida. El pliego de Luis pidió
sacarla a un servicio propio, `co_pqrs_authorization`, para que cualquier
workflow que necesite autorización la use sin reimplementarla. Doble Cobro será
el primer reutilizador cuando exista.

Se hizo en fases, sin tocar reglas de negocio de TXNR ni la numeración 2.x.x.x.

### Reparto de responsabilidades

- **El agente** orquesta la conversación.
- **`co_pqrs_authorization`** orquesta el ciclo de vida de la autorización.
- **TXNR** sigue con su negocio: productos, movimientos, clasificación, bloqueo.

El servicio no conoce reglas de ningún workflow. `workflow` y `step` viajan como
metadatos opacos: entran en la creación y vuelven en el resultado, y el servicio
nunca los interpreta. No hay ningún `if workflow == "trx_no_reconocida"` dentro.

### Decisión de Luis (03/09): el servicio NO dispara el push

TXNR mantiene la ceremonia del push (user-status, 403, 401, el
`authenticationdata` de tarjetas). El servicio recibe el `challenge` ya creado y
desde ahí es dueño del resto: persistir, consultar order-chanel, cumplir el
plazo, resolver y publicar.

## Cómo funciona por dentro

Estados de negocio: `PENDING`, `ACCEPTED`, `REJECTED`, `EXPIRED`.
Estados técnicos de la última consulta: `SUCCESS`, `BUSINESS_RESULT`,
`TECHNICAL_ERROR`. Van separados a propósito: un fallo del ASO no se convierte en
`REJECTED`. "El usuario rechazó" y "no pude preguntar" son cosas distintas.

El **worker** es durable. Los jobs viven en OpenSearch (índice `authorizations`),
no en memoria. Cada tick:

1. busca jobs `PENDING` con `next_check_at` vencido y sin lease activo,
2. hace claim con concurrencia optimista (`if_seq_no`) — si dos pods compiten,
   solo uno gana; el otro recibe 409 y suelta el job,
3. consulta order-chanel una vez,
4. resuelve: `accepted`/`rejected` terminales; `pending` reprograma;
   deadline vencido a `EXPIRED`; fallo técnico se reintenta,
5. si es terminal, publica el resultado una sola vez.

El plazo de 180 segundos lo cumple el worker desde el backend. No hace falta que
el usuario vuelva a pulsar "Continuar" para que el estado avance, y no hay
ninguna petición HTTP abierta esperando la autorización.

### Cómo entra el agente (Fase 4)

- Al enviar el push (gate 2.4.0.1.16.1 / 17.1), el agente registra la
  autorización en el servicio y guarda el `authorization_id` en el estado de la
  conversación. Es fail-open: si el servicio no responde, el flujo sigue.
- Al pulsar "Continuar" (gate .16.2 / 17.2), el agente lee el estado ya resuelto
  por el worker y lo mapea: `ACCEPTED` → aceptado, `REJECTED` → rechazado,
  `EXPIRED` → vencido, `PENDING` → pendiente.
- Si el servicio no está configurado (`AUTHORIZATION_SERVICE_URL` vacía) o no
  responde, el agente cae a la consulta directa de siempre. Comportamiento
  idéntico al anterior. El rollout es gradual por entorno.

### Idempotencia

El `authorization_id` deriva de la `idempotency_key`
(`conversation:step:challenge` por defecto) con create-if-absent en OpenSearch.
Dos registros equivalentes (doble clic, reintento, dos pods) devuelven el mismo
job: un solo push registrado. El resultado terminal se publica una vez, con un
claim sobre el flag `result_published`.

## Ficheros

Servicio nuevo `co_pqrs_authorization/`:

- `src/domain/authorization/models.py` — job, estados, normalización, `resolver_consulta`.
- `src/application/authorization/service.py` — crear (idempotente), consultar.
- `src/application/authorization/worker.py` — el loop con claim.
- `src/infrastructure/persistence/authorizations_store.py` — OpenSearch + claim.
- `src/infrastructure/persistence/aso_client.py` — granting + order-chanel.
- `src/infrastructure/messaging/result_publisher.py` — puerto de eventos (impl. log).
- `src/infrastructure/entrypoint/` — FastAPI + router v1.
- 23 tests.

Agente:

- `src/infrastructure/persistence/authorization_client.py` — adapter fail-open.
- Cambios mínimos en `chat_service.py` (registro + consulta con fallback) y
  `config.py` (`load_authorization_service_url`). 8 tests de Fase 4.

IaC:

- `IaC/backend/co_pqrs_authorization/` — configmap, deployment (8005), service,
  template del índice y Job de bootstrap.
- `AUTHORIZATION_SERVICE_URL` en el configmap del agente.

## Contrato de la API

```
POST /v1/authorizations
  {conversation_id, workflow, step, challenge, idempotency_key?, metadata?}
  -> 201 {authorization_id, status: "PENDING", deadline, ...}

GET /v1/authorizations/{authorization_id}
  -> {authorization_id, conversation_id, workflow, step, status, technical_status, deadline, attempts}

GET /v1/authorizations?conversation_id=...
  -> [ ... ]
```

---

# Cómo probar en local

## Opción A: todo con run_local.py

`scripts/run_local.py` ya levanta el servicio de autorización en el 8005 y le
pasa al agente `AUTHORIZATION_SERVICE_URL=http://127.0.0.1:8005`.

```bash
python3 scripts/run_local.py
```

Levanta simulador (8050), TXNR (8004), back_data (8003), **authorization
(8005)**, agente (8000) y front (8501). Necesita OpenSearch local en el 9200
(el servicio de autorización crea su índice al arrancar).

Requisito de datos: para que el push complete, el `account_id` del cliente de
pruebas tiene que estar en Postgres. El refactor reciente lo movió del CSV a
`ada_info_detail`. Para `1010223694`:

```bash
docker exec trx-postgres-dev psql -U pqr_user -d pqr_db \
  -c "UPDATE ada_info_detail SET account_id='00130067000200942156' \
      WHERE customer_id='1010223694' AND last_four_pan_id='4979';"
```

## Opción B: solo el servicio de autorización, aislado

```bash
cd co_pqrs_authorization
uv sync
uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --port 8005
```

Con el simulador (8050) y OpenSearch (9200) arriba. Prueba directa del ciclo:

```bash
# 1. crear un reto real en el simulador (queda pending)
curl -s -X POST "http://localhost:8050/cards/v2/operations" \
  -H "Content-Type: application/json" -H "authenticationtype: 241" \
  -H "authenticationdata: deviceId=BB-04-X,profileId=CC1,channel=12000035" \
  -d '{"card": {"cardId": "4912680517940099"}}'

# 2. registrar la autorización con ese challenge
curl -s -X POST "http://127.0.0.1:8005/v1/authorizations" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"c1","workflow":"trx_no_reconocida","step":"2.4.0.1.17.1","challenge":"sim-0099-challenge"}'
# -> guarda el authorization_id de la respuesta

# 3. consultar: sigue PENDING mientras nadie apruebe
curl -s "http://127.0.0.1:8005/v1/authorizations/<authorization_id>"

# 4. aprobar externamente (el cliente en su app) y esperar un tick del worker
curl -s -X POST "http://localhost:8050/security/v0/order-chanel/sim-0099-challenge/approve"
sleep 5
curl -s "http://127.0.0.1:8005/v1/authorizations/<authorization_id>"
# -> status ACCEPTED, technical_status BUSINESS_RESULT
```

Para probar los otros desenlaces: `/reject` (→ REJECTED), `/expire`
(→ EXPIRED), o esperar 180 s sin aprobar (→ EXPIRED por deadline).

## Opción C: el flujo completo por la UI

Con `run_local.py` arriba, abre `http://localhost:8501`, usa el cliente
`1010223694` y recorre: "No reconozco esta compra" → compra presencial → 1 →
Empezar ahora → Sí continuar → tarjeta → rango → fecha `06/08/2026` →
movimiento → reporte → investigación → bloqueo. En el paso del push, el agente
registra la autorización; al pulsar "Continuar", lee el estado del servicio.
En los logs del agente aparece `TXNR AUTH CHECK A1 AUTHORIZATION status=...`.

## Tests

```bash
cd co_pqrs_authorization && uv run pytest -q          # 23, el servicio
cd co_pqrs_back_agent && uv run pytest -q \
  tests/test_application/test_trx_autorizacion_fase4.py \
  tests/test_infrastructure/test_persistence/test_authorization_client.py
```

---

# Cómo probar en OKD (DEV)

## Desplegar

1. Construir la imagen `co_pqrs_authorization:test_v1.0.0` desde la rama y subirla
   al Quay (Containerfile en la raíz del servicio).
2. Aplicar la kustomization de backend. Eso crea: el configmap, el deployment
   (8005), el service, el template del índice y el Job de bootstrap. El agente
   toma `AUTHORIZATION_SERVICE_URL` en su siguiente rollout.
3. Verificar el Job de bootstrap: deja el índice `authorizations` con mapping
   explícito. El servicio también lo crea al arrancar como respaldo.

Credenciales del granting (`TRX_API_USER_ID`, `TRX_API_PASSWORD`): las mismas que
consume TXNR, por secret del entorno. En DEV `ASO_SOURCE=simulator`; en QA/PRD se
cambia a `real` con `ASO_REAL_URL`, sin tocar código.

## Verificar

```bash
oc rsh deploy/co-pqrs-authorization
# desde el pod, contra el propio servicio:
curl -s http://localhost:8005/health
```

Para ver el ciclo con el agente: recorrer la subida de nivel en el front de DEV
con un usuario que tenga dispositivo enrolado, y seguir los logs:

```bash
oc logs -f deploy/co-pqrs-back-agent | grep -E "AUTH CHECK A1|AUTH REGISTRADA"
oc logs -f deploy/co-pqrs-authorization | grep -E "AUTHORIZATION RESULT|Worker job"
```

`AUTH REGISTRADA` en el agente (registró la autorización), `Worker job -> resuelto`
en el servicio (el worker la resolvió), `AUTH CHECK A1 AUTHORIZATION status=ACCEPTED`
en el agente (leyó el resultado).

## Apagarlo sin desplegar nada

Si algo va mal, vaciar `AUTHORIZATION_SERVICE_URL` en el configmap del agente y
reiniciar: el agente vuelve a la consulta directa de siempre. El servicio puede
quedarse arriba sin efecto.

---

# Lo que falta

- Fase 5: que Luis valide en DEV, con Postgres y ASO reales, que TXNR se comporta
  igual que antes.
- Fase 6: Doble Cobro reutilizando el servicio, cuando exista el módulo.
- Construir y subir la imagen `test_v1.0.0`.

# Observabilidad y trazas

El servicio emite trazas a MinIO por la misma via que el agente y TXNR:
`schedule_trace_event` (fire-and-forget) hacia `error_handler`
(`ERROR_HANDLER_SERVICE_URL`). Dos puntos:

- `authorization_created` (o `authorization_duplicate` si fue idempotente) al
  registrar la autorizacion.
- `authorization_resolved` cuando el worker la deja terminal, con `outcome` =
  accepted/rejected/expired y el `technical_status`.

Ambas llevan `component: co_pqrs_authorization`, `conversation_id`, `workflow`,
`step` y los intentos. Con eso el flujo OOB es auditable de punta a punta por
MinIO, igual que el resto. Si `ERROR_HANDLER_SERVICE_URL` esta vacio, no se
emite nada (no-op) y no pasa nada.

Ademas, cada autorizacion es una traza completa en el indice `authorizations`
de OpenSearch: `status`, `technical_status`, `attempts`, `created_at`,
`deadline`, `next_check_at`, `resolved_at`, `last_error`, `result_published`.

## Cómo ver las trazas

**En MinIO** (igual que las de TXNR): en el bucket de trazas del error_handler,
las de este servicio traen `component: co_pqrs_authorization`. Se filtran por
`conversation_id` o por `operation`:

- `authorization_created` / `authorization_duplicate`
- `authorization_resolved` (mira `outcome`: accepted / rejected / expired)

El `conversation_id` es el mismo que el de la conversación del agente, así que
una autorización se cruza con el resto de trazas del flujo (productos,
movimientos, bloqueo) por ese campo.

**En OpenSearch** (el estado durable, más rico que una traza suelta):

```bash
# una autorización por su id
GET authorizations/_doc/<authorization_id>

# todas las de una conversación (Dev Tools o curl)
POST authorizations/_search
{ "query": { "term": { "conversation_id": "13083558_20260903" } } }
```

**En logs del pod** (OKD), útil para seguir el ciclo en vivo:

```bash
oc logs -f deploy/co-pqrs-authorization | grep -E "Worker job|AUTHORIZATION RESULT"
```


# Notas de entorno

- El OpenSearch local se llena de disco y bloquea la creación de índices
  (`create_index blocked`). Si el servicio no puede crear su índice al arrancar,
  liberar disco y quitar el bloqueo:
  `PUT _cluster/settings {"transient":{"cluster.blocks.create_index":null}}`.
- El worker corre en el mismo pod que la API. Los jobs viven en OpenSearch, así
  que un reinicio no pierde nada y con varias réplicas el claim arbitra.
