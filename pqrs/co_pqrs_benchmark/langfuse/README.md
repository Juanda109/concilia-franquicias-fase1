# PoC Langfuse — observabilidad y evals del benchmark

Stack Langfuse v3 **self-hosted** para el PoC de LLMOps del flujo doble cobro:
demuestra que las corridas del benchmark pueden vivir dentro de la
infraestructura del banco (sin SaaS, sin sacar conversaciones del perímetro),
con trazas, scores y comparación entre versiones del catálogo.

## Arranque

```bash
cd co_pqrs_benchmark/langfuse
podman compose -f compose.yml up -d        # o: docker compose -f compose.yml up -d
```

Primer arranque: descarga imágenes (~2 GB) y corre migraciones; espera ~1-2
minutos a que `langfuse-web` responda.

| Qué | Dónde |
|---|---|
| UI | http://localhost:3000 |
| Usuario | `admin@pqrs.local` / `pqrsbenchmark2026` |
| API keys del proyecto | `pk-lf-doble-cobro-poc` / `sk-lf-doble-cobro-poc` |

La inicialización es **headless** (`LANGFUSE_INIT_*` en el compose): el
proyecto `Agente PQRS - Doble Cobro` y sus keys existen desde el primer
arranque, sin pasos manuales en la UI. Todas las credenciales del compose son
de laboratorio local; en OKD van como `Secret` en `IaC/`.

## Publicar una corrida del benchmark

```bash
cd co_pqrs_benchmark
uv run scripts/publish_to_langfuse.py <corrida.ndjson> --run-name baseline-doble-cobro
```

El NDJSON es el que escribe `benchmark/job.py` (en MinIO o en
`.data/output_data/`). Cada caso se convierte en una traza con:

- **input/output**: mensaje del cliente y respuesta final del bot;
- **generation** con modelo y tokens (entrada/salida/cache);
- **scores**: `acierto` (misma evaluación del job, incluida la normalización
  matched/other; los casos sin resolver no puntúan), `routing_s`, `e2e_s`;
- **tags**: `run:<nombre>` y `catalogo:<sha corto>` — la clave del ciclo de
  prompt tuning: dos corridas con distinto SHA del catálogo se comparan lado a
  lado en la UI filtrando por tag.

## Humo sin agente

`demo_run.ndjson` es una corrida **sintética** (6 casos, modelo
`demo-sintetico`, 4 aciertos / 1 fallo de workflow / 1 sin resolver) con el
esquema real del job. Sirve para validar el stack y poblar la UI en una demo:

```bash
uv run scripts/publish_to_langfuse.py langfuse/demo_run.ndjson --run-name demo-sintetica
```

No confundir con una corrida real: el tag y el modelo la delatan a propósito.

## Qué mirar en la UI (demo del lunes)

1. **Traces**: cada conversación del benchmark con su input/output y metadatos
   (workflow esperado vs obtenido, camino de outcomes, turnos).
2. **Scores**: precisión de la corrida (`acierto`), latencias por caso.
3. **Comparación de corridas**: filtrar por `run:...` / `catalogo:...` — así se
   ve el efecto de un cambio de prompt o de catálogo con números, que es el
   argumento central de la estrategia.

## Camino a OKD

Este compose es el equivalente local del despliegue en OKD: mismos
componentes (web, worker, PostgreSQL, ClickHouse, Redis, MinIO — MinIO ya
existe en el clúster). El paso siguiente es transcribirlo a manifiestos
kustomize en `IaC/`, con credenciales en Secrets y el publicador como paso
final del Job de benchmark (`MINIO_ENABLED` ya decide dónde queda el NDJSON).
