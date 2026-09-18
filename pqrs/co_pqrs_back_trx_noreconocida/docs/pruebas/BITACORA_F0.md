# Bitácora F0 — base de trabajo sobre el esqueleto (13/08/2026)

**Rama:** `feature/trx-esqueleto` (desde `origin/feature/PQRSdev` @ `2d5c26b`).
Respaldo de la rama antigua: `~/patches/trxnoreconocida-17commits-20260813.bundle`.

## Stack local que funciona

| Pieza | Cómo | Estado |
|---|---|---|
| Postgres | contenedor `trx-postgres-dev` (:5433), **tabla recreada con el DDL del esqueleto** (el viejo no tenía `card_type`…) + `ALTER card_flag` + seed de `DATOS_PRUEBA_POSTGRES.md` | 12 clientes de la matriz |
| Simulador ASO | `cd co_pqrs_back_trx_aso_simulator && uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --port 8050` (en host; `main:app` **no** funciona: import path) | :8050 ok |
| Servicio trx | imagen `trx-esqueleto:local`, contenedor `trx-esqueleto` con `ASO_SOURCE=simulator`, `ASO_SIMULATOR_URL=http://host.docker.internal:8050`, `TRX_PRODUCTS_SOURCE=postgres`, DB→:5433, y `TRX_SALESFORCE_SOURCE=aso` (desde F2; el mount de workaround del 13/08 por la mañana ya no hace falta) | :8004, 8 endpoints `/v1/trx` |
| Agente | contenedor `co-pqrs-back-agent` (monta `./src` → reinicio basta al cambiar de rama) | :8000 |

> **Tras tocar el código del servicio trx hay que reiniciar su contenedor**
> (`docker restart trx-esqueleto`): monta `src` como volumen, pero el proceso ya
> tiene los módulos cargados y sigue sirviendo el código anterior. El síntoma es
> traicionero — el fichero está bien y la respuesta es la vieja. Mismo caso que
> el agente.

## Línea base de suites (esqueleto + ports)

| Suite | Resultado |
|---|---|
| Agente | **294 pasan · 10 fallan** (los 10 son línea base del esqueleto, previos a los ports) |
| Servicio trx | **30 pasan** |
| Simulador | **sin suite ejecutable** (`uv run pytest` falla por fichero inexistente — anotar a Fabián) |

## Lo hecho

1. **Ports aplicados**: D-02 (cherry-pick limpio `f64aaa4`) y D-03 (re-aplicación, con
   sus pruebas). Verificado en vivo: una opción no reconocida responde al instante en
   vez de colgar 60+ s — el propio humo de F0 lo reprodujo antes del port.
2. **Bloqueante encontrado y corregido — recurrencia-bot auto-disparada**: el gate
   `2.4.0.1` registraba el hito `entered_op4` **antes** de leer la recurrencia, y el
   contador contaba la entrada recién escrita (`count=1 ≥ MAX=1`): **todo cliente era
   derivado a PQR en su primera entrada**; nadie podía pasar de la opción 4. Ahora se
   decide primero y se registra después. Verificado con C y H, índice limpio.
3. **Humo de la matriz** (índice `trx-no-reconocida-cases` limpio antes):
   - **A** recurrencia → PQR ✅ (con el workaround de abajo)
   - **B** `card_flag=false` → *"no tienes productos activos… app BBVA"* ✅
   - **C** → llega al selector con *Tarjeta de Crédito \*0060* desde Postgres, card-id
     por financial-overview y movimientos del simulador ✅ (cadena completa de costuras)
   - **H/I** → recorren; la verificación fina del mensaje queda para F1 (guion renumerado)

## Hallazgos nuevos (para `Hallazgos` y F2)

- **La recurrencia del servicio no consulta al simulador**: lee
  `TRX_SALESFORCE_MOCK_FILE` (default `data/aso_salesforce.json`, un volcado de otro
  cliente) y `aso_client.salesforce_issues()` es **código muerto** — nadie lo llama.
  El cliente A de la matriz no puede funcionar como está documentado sin el
  **workaround** del mount (arriba). El cableado real `salesforce_source=aso →
  aso_client` es trabajo de F2 (mi tramo).
- El simulador no tiene suite ejecutable.
- La fecha del esqueleto se pide en **DD/MM/AAAA** (¡ya alineada al tablero!) — los
  casos del protocolo viejo (aaaa/mm/dd) quedan obsoletos también en esto.

## Pendiente inmediato (F1)

Renumerar protocolo + `suite.py` al árbol `2.4.0.1.x` con la matriz de 12 clientes, y
recorrer las ramas de gate con verificación de contenido (no sólo de botones).

## Origen de los datos de prueba (revisado el 18/08)

| Fuente | Contenido | Naturaleza |
|---|---|---|
| `docs/trx no reconocida/CLIENTES_SIMULADOR.md` + `DATOS_PRUEBA_POSTGRES.md` | los 12 `customer_id` de la matriz | **sintéticos**, de Fabián (13/08). Nombres `CLIENTE A…I`, correos `@mail.com`, identificadores en secuencia |
| `co_pqrs_back_trx_aso_simulator/data/` | fixtures por PAN del simulador | **sintéticos** (`CLIENTE A PRUEBA`, doc `1013634958`) |
| `co_pqrs_back_trx_noreconocida/data/aso_salesforce.json` | 693 registros con nombre, cédula, 36 correos y teléfonos | **sintético de sandbox**, confirmado por Fabián el 18/08. Se revisó por tener aspecto de volcado real (correos con dominio corporativo); queda constancia aquí para no volver a levantarlo |

Ningún `user_id` en uso proviene de cartera real.
