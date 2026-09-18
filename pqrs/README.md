# agentepqr

Backend base para construir una API con `FastAPI`, modelos tipados con `Pydantic` y un agente que consume contexto conversacional estructurado.

## Objetivo del proyecto

Este proyecto busca separar claramente:

- la capa HTTP de la API
- la logica de aplicacion
- los modelos internos del agente
- la infraestructura y configuracion del sistema

La idea es que la API publica reciba entradas simples, mientras que el agente trabaje con un contexto mas rico y trazable, por ejemplo una conversacion completa con historial de mensajes, tokens y tiempos.

## Stack principal

- Python `>=3.14`
- `FastAPI`
- `Pydantic`
- `uv` para manejo de entorno y dependencias
- `strands-agents` para la capa de agentes

## Estructura del proyecto

```text
agentepqr/
|-- pyproject.toml
|-- uv.lock
|-- README.md
`-- src/
    `-- agentepqr/
        |-- api/
        |   |-- app.py
        |   `-- routes/
        |-- application/
        |-- agents/
        |-- core/
        |   |-- config.py
        |   `-- exceptions.py
        |-- infrastructure/
        `-- schemas/
            `-- agent/
                `-- agent.py
```

## Donde va el codigo del API

La configuracion y el codigo del API deben dividirse por responsabilidad:

### `src/agentepqr/api/app.py`

Este es el punto de entrada de `FastAPI`.

Aqui deberia vivir:

- la instancia principal de `FastAPI`
- el registro de routers
- middlewares
- handlers globales de errores
- eventos de arranque y cierre si luego hacen falta

### `src/agentepqr/api/routes/`

Aqui deben vivir los endpoints de la API, separados por modulo.

Ejemplos:

- `health.py`
- `messages.py`
- `conversations.py`

La idea es que cada archivo contenga rutas de un contexto especifico, sin meter logica de negocio pesada dentro del endpoint.

### `src/agentepqr/api/dependencies.py`

Este archivo se reserva para dependencias compartidas del API.

Ejemplos:

- autenticacion
- carga de configuracion
- servicios compartidos
- contexto por request

Si todavia no existe, se puede crear cuando empiece a haber dependencias reutilizables entre endpoints.

### `src/agentepqr/schemas/api/`

Aqui deben ir los modelos publicos de entrada y salida de la API.

Ejemplos:

- request models
- response models
- payloads validados para endpoints

Estos schemas no tienen por que ser iguales a los modelos internos del agente.

### `src/agentepqr/application/`

Aqui debe vivir la logica de aplicacion o los casos de uso.

La regla practica es:

- el router recibe la peticion
- valida con schemas
- delega la operacion a `application`

Esto ayuda a mantener endpoints limpios y faciles de probar.

### `src/agentepqr/core/config.py`

Aqui debe vivir la configuracion global del proyecto.

Ejemplos:

- variables de entorno
- settings del sistema
- configuracion base del servicio
- valores reutilizables del proyecto

### `src/agentepqr/infrastructure/`

Aqui van las integraciones externas.

Ejemplos:

- base de datos
- clientes HTTP
- adaptadores a servicios externos
- persistencia de contexto

## Modelos internos del agente

Los modelos internos del agente viven en `src/agentepqr/schemas/agent/agent.py`.

Estos modelos no estan pensados como contrato publico de la API, sino como estructura de trabajo interna para:

- dar contexto al agente
- mantener trazabilidad
- serializar conversaciones a JSON
- persistir ese contexto posteriormente en base de datos

Actualmente la idea principal es:

- `Message` representa un mensaje individual
- `Conversation` representa una conversacion completa
- `Conversation.messages` contiene el historial que se pasa al agente
- `tokens` y `timing` permiten guardar trazabilidad de consumo y tiempos

Esto permite que, en el futuro:

- la API reciba solo el ultimo mensaje del usuario
- la aplicacion reconstruya el contexto
- el agente reciba la conversacion completa
- ese mismo contexto se persista como JSON

## Flujo esperado

```text
API -> schema de entrada -> application -> contexto del agente -> agente -> respuesta
```

Mas adelante, ese flujo tambien puede extenderse asi:

```text
API -> application -> cargar contexto -> ejecutar agente -> actualizar contexto -> persistir JSON
```

## Comandos utiles

Instalar dependencias:

```powershell
uv sync
```

Ejecutar el proyecto con el entorno de `uv`:

```powershell
uv run python main.py
```

## Levantar el API en localhost

Desde la raiz del proyecto, puedes levantar el API con alguno de estos comandos.

Con `uv`:

```powershell
uv run uvicorn --app-dir co_pqrs_back_agent/src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8000

uv run uvicorn --app-dir co_pqrs_back_data/src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8002
```

Con el `.venv` directamente:

```powershell
.\.venv\Scripts\python.exe -m uvicorn --app-dir src agentepqr.api.app:app --reload --host 127.0.0.1 --port 8000
```

Una vez levantado, puedes abrir:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## Requests de ejemplo para Postman

Base URL:

```text
http://127.0.0.1:8000
```

### `GET /health`

Metodo:

```text
GET
```

URL:

```text
http://127.0.0.1:8000/health
```

Respuesta esperada:

```json
{
  "status": "ok"
}
```

### `POST /chat`

Metodo:

```text
POST
```

URL:

```text
http://127.0.0.1:8000/chat
```

Headers:

```text
Content-Type: application/json
```

Body:

```json
{
  "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
  "content": "Hola"
}
```

Respuesta esperada:

```json
{
  "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
  "message": "Hola, soy el asistente de flujos. Te puedo guiar por los workflows disponibles.\n\nFlujos disponibles:\n1. Solicitud\n2. Riesgo\n\nResponde con el nombre del workflow que deseas iniciar."
}
```

Nota:

- El API construye internamente los objetos `Message` y `Conversation`.
- Los `id` de los mensajes se generan con UUID en el backend.
- El estado completo de la conversacion se escribe en logs para inspeccion local.
- La conversacion y sus mensajes se persisten en archivos locales dentro de `data/`.
- En el primer mensaje, el asistente saluda y lista los workflows disponibles.
- A partir del segundo mensaje, el flujo avanza paso a paso usando el arbol definido en `src/agentepqr/agents/workflows.yml`.
- En cada interaccion se persisten tanto la conversacion como todos sus mensajes.

### Ejemplo de flujo `Solicitud`

Primer request:

```json
{
  "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
  "content": "Hola"
}
```

Respuesta:

```json
{
  "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
  "message": "Hola, soy el asistente de flujos. Te puedo guiar por los workflows disponibles.\n\nFlujos disponibles:\n1. Solicitud\n2. Riesgo\n\nResponde con el nombre del workflow que deseas iniciar."
}
```

Segundo request:

```json
{
  "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
  "content": "Solicitud"
}
```

Respuesta:

```json
{
  "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
  "message": "Paso 1\nQue tipo de solicitud es?\n\n1. Consulta\n2. Estado\n3. Actualizacion de datos\n4. Bloqueo o cancelacion"
}
```

Tercer request:

```json
{
  "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
  "content": "Consulta"
}
```

Respuesta:

```json
{
  "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
  "message": "Paso 1.1\nSobre que producto o servicio es la consulta?\n\n1. Cuenta\n2. Tarjeta\n3. Credito"
}
```

Si quieres probar rapidamente sin Postman, tambien puedes usar `curl`:

```bash
curl -X GET http://127.0.0.1:8000/health
```

```bash
curl -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "8a6f29bc-6898-45e2-a7f8-c58df7e6b7e1",
    "content": "Hola"
  }'
```

## Notas de diseno

- `src/` se usa para mantener un paquete Python limpio y evitar imports accidentales desde la raiz del repo.
- Los schemas del agente y los schemas publicos del API deben permanecer separados.
- La API debe ser delgada: validar, delegar y responder.
- La logica del agente debe consumir contexto interno estructurado, no directamente el payload crudo del endpoint.
- Las rutas principales del API ya quedaron en modo async para soportar multiples solicitudes concurrentes por worker.
- El store actual de conversaciones usa archivos JSON locales; si levantas 4 workers, cada worker seguira compartiendo la misma carpeta de datos, pero no tendras garantias fuertes de concurrencia entre procesos hasta mover esto a una base de datos o cache compartido.
