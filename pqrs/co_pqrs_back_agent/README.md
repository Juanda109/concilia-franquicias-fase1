# co_pqrs_back_agent

Backend para flujos guiados con `FastAPI`, `Pydantic` y un agente basado en `strands-agents`. El proyecto expone una API de inicio y chat, persiste el contexto conversacional en OpenSearch y navega workflows numerados definidos en archivos YAML.

## Objetivo

- Exponer una API simple para recibir mensajes del usuario.
- Reconstruir y persistir el contexto de cada conversacion.
- Guiar al usuario por workflows numerados como `Solicitud`, `Riesgo` o futuros flujos nuevos.
- Validar respuestas libres con el modelo y cerrar el flujo con una respuesta generada.

## Stack

- Python `>=3.14`
- `FastAPI`
- `Pydantic`
- `uv`
- `python-dotenv`
- `PyYAML`
- `httpx`
- `strands-agents`
- `openai` para endpoint OpenAI-compatible

## Estructura del proyecto

```text
co_pqrs_back_agent/
|-- .env
|-- .env.example
|-- .dockerignore
|-- Containerfile
|-- compose.yml
|-- pyproject.toml
|-- uv.lock
|-- README.md
|-- data/
|   |-- conversations.json
|   `-- messages.json
`-- src/
    |-- application/
    |   `-- chat/
    |       `-- chat_service.py
    |-- domain/
    |   |-- conversation/
    |   |   `-- models.py
    |   |-- genai/
    |   |   `-- llm/
    |   |       `-- models.py
    |   `-- workflow/
    |       |-- general.yml
    |       |-- Solicitud.yml
    |       |-- Riesgo.yml
    |       |-- workflow_engine.py
    |       `-- models.py
    `-- infrastructure/
        |-- core/
        |   |-- config.py
        |   `-- logger.py
        |-- entrypoint/
        |   |-- fastapi_app.py
        |   `-- api/
        |       |-- dependencies.py
        |       `-- router/
        |           |-- healthcheck/
        |           `-- v0/
        |-- genai/
        |   `-- llm/
        |       `-- strands_workflow_agent.py
        `-- persistence/
            |-- conversation_store.py
            `-- opensearch_client.py
```

## Arquitectura

- `application/`: casos de uso y orquestacion del flujo de chat.
- `domain/conversation/`: modelos de `Conversation`, `Message`, tokens y tiempos.
- `domain/workflow/`: motor del arbol de decisiones y definiciones YAML.
- `infrastructure/entrypoint/`: FastAPI, routers, dependencias y punto de entrada.
- `infrastructure/genai/`: integracion con el modelo via Strands.
- `infrastructure/persistence/`: persistencia de conversaciones y mensajes en OpenSearch.

## Organizacion de workflows

Los workflows ya no viven en un solo `workflows.yml`.

- `src/domain/workflow/general.yml` contiene el catalogo de routing del primer `POST /chat`, con los `general_workflow`, los subflujos disponibles, su descripcion y ejemplos.
- Cada flujo vive en su propio archivo:
  - `src/domain/workflow/Solicitud.yml`
  - `src/domain/workflow/Riesgo.yml`

El motor en `src/domain/workflow/workflow_engine.py` usa `general.yml` para clasificar el primer mensaje real enviado a `POST /chat`, pedir confirmacion al usuario y, una vez aceptado el flujo, cargar automaticamente el archivo YAML correspondiente para continuar la conversacion.

## Como agregar un workflow nuevo

Para agregar un flujo nuevo, por ejemplo `Test`, ya no necesitas modificar el motor.

1. Agrega un nuevo grupo o una nueva opcion dentro de un grupo en `general.yml`.
2. Crea un archivo `Test.yml` en la misma carpeta.
3. Define `description`, `examples`, `version`, `start_step` y `steps`.

Ejemplo conceptual:

```yaml
welcome:
  message: "Hola, soy tu asistente de PQRs. En que te puedo ayudar?"
  groups:
    - key: "guia_rapida"
      label: "Guia rapida"
      message: "Estas son las opciones disponibles en Guia rapida."
      options:
        - key: "test"
          label: "Test"
          description: "Explica para que sirve el flujo."
          examples:
            - "Necesito ayuda con test."
            - "Quiero iniciar el flujo test."
          workflow: "Test"
```

Luego creas `Test.yml`:

```yaml
version: 1
start_step: "1"
steps:
  "1":
    question: "Este es un flujo de prueba?"
    input_type: "terminal"
    terminal: true
```

Importante:

- El campo `general_workflow` en `Conversation` identifica el grupo superior seleccionado por el usuario.
- El campo `workflow` en `Conversation` ahora se persiste como `str`.
- Eso permite agregar nuevos nombres de workflow sin tocar enums en codigo.

## Persistencia

El backend persiste el estado conversacional en dos indices de OpenSearch:

- `conversations-reference`
- `conversations-messages`

Reglas actuales:

- `conversations-reference` guarda la conversacion sin el arreglo `messages`.
- `conversations-messages` guarda todos los mensajes de todas las conversaciones.
- Al leer una conversacion, el store reconstruye sus `Message` y los adjunta en memoria.

Los archivos locales:

- `data/conversations.json`
- `data/messages.json`

se mantienen como fuente util para pruebas y para migraciones iniciales hacia OpenSearch.

## Variables de entorno

El archivo `.env` recomendado debe vivir en:

- `.env`

Variables esperadas:

- `BOT_NAME`
- `END_CONVERSATION_CALLBACK_URL`
- `MAX_DAILY_SESSIONS`
- `API_KEY`
- `ENDPOINT`
- `LLM_MODEL`
- `LLM_EMBEDDINGS`
- `SSL_VERIFY`
- `OPENSEARCH_ENDPOINT`
- `OPENSEARCH_USER`
- `OPENSEARCH_PASSWORD`
- `OPENSEARCH_VERIFY_SSL`
- `OPENSEARCH_CONVERSATIONS_INDEX`
- `OPENSEARCH_MESSAGES_INDEX`
- `OPENSEARCH_TIMEOUT`
- `CORS_ALLOW_ORIGINS`
- `CORS_ALLOW_METHODS`
- `CORS_ALLOW_HEADERS`
- `CORS_EXPOSE_HEADERS`
- `CORS_ALLOW_CREDENTIALS`
- `CORS_MAX_AGE`

Puedes partir de:

- `.env.example`

Si corres la API dentro de un contenedor con Podman y tu OpenSearch esta en la maquina host, normalmente el endpoint debe ser:

- `https://host.containers.internal:9200`

Configuracion sugerida para un front web local:

- `CORS_ALLOW_ORIGINS=http://localhost:8501,http://127.0.0.1:8501`
- `CORS_ALLOW_METHODS=*`
- `CORS_ALLOW_HEADERS=*`
- `CORS_ALLOW_CREDENTIALS=false`

Nota:

- Si el navegador ve una peticion cruzada con `Content-Type: application/json` u otros headers no simples, primero enviara `OPTIONS` como preflight. Eso es esperado. Si CORS esta bien configurado, despues de ese `OPTIONS` llegara el `POST` real.

## Comandos de instalacion

Desde la carpeta del proyecto:

```powershell
cd co_pqrs_back_agent
uv sync
```

Si prefieres usar el entorno ya creado:

```powershell
cd co_pqrs_back_agent
.\.venv\Scripts\python.exe -m pip list
```

## Levantar la API

La forma recomendada es correr el servidor desde `co_pqrs_back_agent`, para que no haya ambiguedad con rutas de `src` ni con el `.env`.

Con `uv`:

```powershell
cd co_pqrs_back_agent
uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8000
```

Con el `.venv`:

```powershell
cd co_pqrs_back_agent
.\.venv\Scripts\python.exe -m uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8000
```

## Ejecutar con Podman

Para construir la imagen local:

```powershell
cd co_pqrs_back_agent
podman build -t co-pqrs-back-agent:local -f Containerfile .
```

La imagen copia el archivo `.env` dentro del contenedor para facilitar pruebas locales.

Para correr el contenedor directamente:

```powershell
cd co_pqrs_back_agent
podman run --rm -it `
  --name co-pqrs-back-agent `
  --env-file .env `
  -e PYTHONPATH=/app/src `
  -e OPENSEARCH_ENDPOINT=https://host.containers.internal:9200 `
  -p 8000:8000 `
  co-pqrs-back-agent:local
```

Para levantarlo con el archivo `compose.yml`:

```powershell
cd co_pqrs_back_agent
podman compose up --build
```

`compose.yml` ya deja configurado:

- el puerto `8000`
- el `PYTHONPATH` necesario para `src/`
- `OPENSEARCH_ENDPOINT=https://host.containers.internal:9200`
- volumenes para `src/` y `data/`

Si tu OpenSearch no corre en la maquina host sino en otro contenedor o en otra URL, ajusta `OPENSEARCH_ENDPOINT` en `compose.yml`.

Para desarrollo local esto es suficiente. Para ambientes reales, lo recomendado es inyectar variables de entorno en runtime y no hornear secretos dentro de la imagen.

## Endpoints principales

- `GET /health`
- `POST /start`
- `POST /chat`
- `POST /polling`
- `GET /polling/{conversation_id}`
- `POST /end`
- `GET /docs`

Base URL local:

```text
http://127.0.0.1:8000
```

## Consumo de la API

El ciclo conversacional ahora funciona asi:

1. `POST /start`
   - Crea la conversacion.
   - Recibe `user_id` y genera internamente el `conversation_id` con formato `user_id_yyyymmdd`.
   - Devuelve un saludo fijo con el nombre configurado en `BOT_NAME`.
   - No enruta workflows ni consume el mensaje inicial del usuario.
   - Reapertura: como el `conversation_id` es deterministico por usuario y dia, si la sesion previa de ese dia ya esta `CLOSED` se permite reabrir una nueva sesion sobre el mismo id (se limpian los mensajes de la sesion anterior). Si la sesion previa sigue `ACTIVE`, se responde `409` (conflicto).
   - Limite diario: cada usuario puede iniciar hasta `MAX_DAILY_SESSIONS` sesiones por dia calendario (por defecto `3`). Al superar el limite se responde `409` con el mensaje "Has alcanzado el límite de 3 sesiones diarias.". El contador se persiste en el indice `client-control-table` y se reinicia cada dia.
2. `POST /chat`
   - Continua la misma conversacion usando el mismo `conversation_id`.
   - El primer mensaje real del usuario dispara el agente de routing.
   - Si hay match, propone el flujo mas probable con una explicacion amigable y permite confirmarlo con `continuar` o rechazarlo con `salir`.
   - En `Guia rapida`, cuando el agente ya identifica una rama interna clara, entra directo a esa ruta y evita volver al menu general.
   - Una vez confirmado, sigue ejecutando el YAML del flujo paso a paso.
   - Si el turno tarda mas de 9 segundos, responde `204 No Content`, deja la conversacion en estado `Running` y el backend sigue procesando en segundo plano.
3. `POST /polling`
   - Se usa despues de un `204` de `POST /chat`.
   - Si la conversacion sigue procesando, responde `204 No Content`.
   - Si ya termino, responde `303 See Other` con `Location: /polling/{conversation_id}`.
4. `GET /polling/{conversation_id}`
   - Devuelve el ultimo mensaje del bot una vez que `POST /polling` ya indico `303`.

Reglas importantes:

- `conversation_id` debe tener formato `customer_id_yyyymmdd`, por ejemplo `03966512_20260421`.
- `POST /start` ya no recibe `conversation_id`; recibe `user_id` y te devuelve el identificador generado.
- Primero debes llamar `POST /start`.
- Si llamas `POST /chat` sin haber iniciado la conversacion, la API responde `404`.
- Si llamas `POST /start` otra vez para el mismo `user_id` en la misma fecha, la API responde `409`.
- Si `END_CONVERSATION_CALLBACK_URL` esta configurada, `POST /end` envia un `POST` a esa URL despues de marcar la conversacion como `Closed`.
  Usa la plantilla `http://127.0.0.1:8001/end/{conversation_id}` si el servicio externo espera el identificador dentro de la ruta.

## Ejemplos para Postman

### `GET /health`

```text
GET http://127.0.0.1:8000/health
```

Respuesta:

```json
{
  "status": "ok"
}
```

### `POST /start`

```text
POST http://127.0.0.1:8000/start
Content-Type: application/json
```

Body inicial:

```json
{
  "user_id": "03966512"
}
```

Respuesta esperada:

```json
{
  "status": "Active",
  "conversation_id": "03966512_20260421",
  "message": {
    "sender": "bot",
    "timestamp": "2026-04-20T10:30:00Z",
    "input_type": "text",
    "content": {
      "label": "Hola mucho gusto mi nombre es blue"
    }
  }
}
```

### `POST /chat`

Primer mensaje real del usuario:

```json
{
  "conversation_id": "03966512_20260421",
  "content": "Mi cuenta aparece embargada y tengo dudas de centrales de riesgo"
}
```

Respuesta esperada:

```json
{
  "status": "Active",
  "conversation_id": "03966512_20260421",
  "message": {
    "sender": "bot",
    "timestamp": "2026-04-20T10:31:00Z",
    "input_type": "choice",
    "content": {
      "label": "Segun el contexto que me das, entiendo que tu consulta habla de centrales de riesgo y del estado de tu cuenta. Creo que el flujo adecuado para ayudarte a avanzar es Guia rapida -> Cuenta Embargada, porque mencionas un reporte o novedad de riesgo sobre ese producto.\n\nQuieres continuar con el flujo encontrado?",
      "options": [
        {
          "key": "continuar",
          "label": "Continuar"
        },
        {
          "key": "salir",
          "label": "Salir"
        }
      ]
    }
  }
}
```

Si el backend termina dentro de la ventana de espera, `POST /chat` responde `200` con el payload anterior.

Si el procesamiento supera los 9 segundos, `POST /chat` responde:

```text
204 No Content
```

Confirmacion del flujo sugerido:

```json
{
  "conversation_id": "03966512_20260421",
  "content": "continuar"
}
```

Respuesta esperada:

```json
{
  "status": "Active",
  "conversation_id": "03966512_20260421",
  "message": {
    "sender": "bot",
    "timestamp": "2026-04-20T10:32:00Z",
    "input_type": "choice",
    "content": {
      "label": "Que inconveniente tienes con las centrales de riesgo?",
      "options": [
        {
          "key": "reporte_no_reconocido_o_incorrecto",
          "label": "No reconozco un reporte o creo que esta mal"
        },
        {
          "key": "consulta_sin_permiso",
          "label": "Consultaron mi informacion sin mi permiso"
        }
      ]
    }
  }
}
```

Si el flujo sugerido no corresponde, puedes rechazarlo en `POST /chat`:

```json
{
  "conversation_id": "03966512_20260421",
  "content": "salir, en realidad necesito mis extractos bancarios"
}
```

La API volvera a clasificar el texto y propondra otro flujo para confirmacion.

### `POST /polling`

Se usa cuando `POST /chat` respondio `204`:

```text
POST http://127.0.0.1:8000/polling
Content-Type: application/json
```

```json
{
  "conversation_id": "03966512_20260421"
}
```

Si el backend sigue trabajando:

```text
204 No Content
```

Si ya termino y el front puede ir por la respuesta final:

```text
303 See Other
Location: /polling/03966512_20260421
```

### `GET /polling/{conversation_id}`

```text
GET http://127.0.0.1:8000/polling/03966512_20260421
```

Respuesta esperada cuando ya existe un mensaje listo:

```json
{
  "status": "Active",
  "conversation_id": "03966512_20260421",
  "message": {
    "sender": "bot",
    "timestamp": "2026-04-20T10:33:00Z",
    "input_type": "choice",
    "content": {
      "label": "Que inconveniente tienes con las centrales de riesgo?",
      "options": [
        {
          "key": "reporte_no_reconocido_o_incorrecto",
          "label": "No reconozco un reporte o creo que esta mal"
        },
        {
          "key": "consulta_sin_permiso",
          "label": "Consultaron mi informacion sin mi permiso"
        }
      ]
    }
  }
}
```

Notas sobre el payload de respuesta:

- `status` refleja el estado actual de la conversacion, por ejemplo `Active`, `Running` o `Closed`.
- `message.sender` siempre devuelve `bot`.
- `message.timestamp` corresponde al momento en que se genero la respuesta del asistente.
- `message.input_type` indica el tipo de entrada que espera el siguiente paso y hoy puede ser `choice`, `text` o `terminal`.
- `message.content.label` contiene el texto principal que debe renderizar el front.
- En `POST /start`, `message.content` solo incluye `label`.
- En `POST /chat`, `message.content.options` contiene las opciones estructuradas cuando el paso es seleccionable.
- Si el paso de `POST /chat` es informativo o terminal, `options` llega vacio.
- Las respuestas `204 No Content` no incluyen body; el front debe interpretarlas como que la conversacion sigue en proceso y consultar `POST /polling`.

## Logs y trazabilidad

El proyecto ya registra:

- inicio y fin de funciones principales
- errores con `FAIL`
- `conversation_id`
- formato esperado: `customer_id_yyyymmdd`, por ejemplo `03966512_20260421`
- paso actual del workflow
- estado de la conversacion
- tokens y tiempos del turno

Esto facilita seguir el flujo completo entre API, aplicacion, motor de workflow, agente y persistencia.

## Notas de operacion

- Los tiempos del usuario y del asistente se miden sobre el mismo turno de procesamiento.
- Los pasos de opcion numerica suelen durar muy poco porque no llaman al modelo.
- Los pasos de texto libre o cierre final son los que normalmente consumen tokens del LLM.
- La persistencia principal del backend vive en OpenSearch.
- Los archivos `data/*.json` siguen siendo utiles para pruebas y para migraciones iniciales.
