# Protocolo de pruebas — flujo trx sobre el esqueleto (árbol 2.4.0.1.x)

**Documento vivo.** Sustituye a `PROTOCOLO_PRUEBAS.md` (árbol viejo `2.4.0.x`), que queda
como histórico. **Última ejecución: 14/08/2026 · 17 casos · 17 OK** · Ajustes de Fabián aplicados: validación silenciosa (el camino común tiene un turno menos), últimos 4 seguros, journey en logs (`docker logs | grep 'TXNR paso'`). (ampliado tras el double-check de cobertura: sucesos 1-3, rangos fuera de límite, "ya reconozco", reenganches encadenados y finalizar en contacto).

**Alcance mío:** hasta la **confirmación de la compra (`2.4.0.1.11`)**. Los casos que
cruzan a la zona de Luis (investigación, bloqueo, devolución) verifican sólo **la
entrega en la frontera**: que el gate `.12` rutee y aparezca la pregunta de
investigación. Su tramo se prueba en su protocolo.

## Entorno

El stack exacto está en [`BITACORA_F0.md`](./BITACORA_F0.md). En corto: Postgres :5433
con el seed de la matriz, simulador ASO :8050, servicio :8004
(`ASO_SOURCE=simulator`), agente :8000. **Sin `TRX_SERVICE_URL` los gates se saltan en
silencio** y todo parece no-op: verificarlo antes de diagnosticar nada.

**Verificadores automáticos** (este directorio), a correr antes de cada push:

| Script | Qué garantiza |
|---|---|
| `suite_esqueleto.py` | los 17 casos E2E del tramo |
| `verificar_contrato.py` | las 25 claves de la frontera con Luis |
| `verificar_mensajes.py` | **61 comprobaciones** de los 4 mensajes dinámicos: procedencia del dato, formato del tablero, degradación sin crudos y ciclo de vida |

**Automático:** `python3 suite_esqueleto.py` (este directorio) recorre los casos
verificando contenido. Limpiar antes el índice de casos:
`curl -sk -u admin:admin -X DELETE https://localhost:9200/trx-no-reconocida-cases` — si no, la recurrencia-bot
del día anterior desvía a PQR y parece un fallo.

## La matriz (de `docs/trx no reconocida/CLIENTES_SIMULADOR.md`)

Un cliente = un escenario, cableado en los fixtures del simulador. **Fecha con
movimientos: `06/08/2026`** (absoluta: envejece). Una conversación por cliente y día.

## Casos y resultado del 13/08

| # | Cliente | Recorrido | Esperado | 13/08 |
|---|---|---|---|---|
| E1 | A `1013634958` | frase → suceso 4 | recurrencia Salesforce → *"gestión reciente"* + Formulario PQR | ✅ |
| E2 | B `1013634959` | tramo común | `.4.exit`: *"no tienes productos activos… app BBVA"* | ✅ |
| E3 | Tres `98787954` | cantidad **Más de 3** | `.1.1.pqr`: formulario en *"un solo trámite"* | ✅ |
| E4 | H `1013634965` | MASTERCARD + fecha `01/01/2025` | `.7.exit`: plazo de franquicias, **sin consultar ASO** | ✅ |
| E5 | I `1013634966` | fecha `06/08/2026`, transactions vacío | `.8.return` con **tres salidas** (otra fecha / otro producto / terminar) | ✅ |
| E6 | C `1013634960` | feliz completo | listado 3 movs **con** botón *"No encuentro…"* → confirmación con **2 botones** → frontera: pregunta de investigación | ✅ |
| E7 | D `1013634961` | 1 movimiento | listado **sin** botón *"No encuentro…"* (defecto conocido H-02) → confirmación → frontera | ✅ (defecto presente) |
| E8 | G `1013634964` | movimiento pendiente | `.12.exit`: *"estado pendiente… podría liberarla o anularla"* | ✅ |
| E9 | Uno `10482895` | fecha válida **sin** movimientos `05/08/2026` | `.8.return` — **prueba que el filtro por fecha funciona** | ✅ |
| E10 | Dos `01576905` | fechas ilegibles `99/99/9999` y `hola`, luego la buena | repregunta dos veces y con `06/08/2026` lista | ✅ (tras corregir H-01) |
| E11 | E/F/G | sucesos 1-3 | los tres → Formulario PQR sin más preguntas | ✅ |
| E12 | F `1013634963` | rango **Menor a $35.000** | `.6.pqr` → formulario | ✅ |
| E13 | E `1013634962` | rango **Mayor a $500.000** | `.6.pqr` → formulario | ✅ |
| E14 | Uno `10482895` | confirmación → **"ya reconozco la transacción"** | cierra por feedback, sin radicar | ✅ |
| E15 | C + I | reenganches encadenados: `.9.exit` → nueva fecha → día vacío → otra fecha → listado; y `.8.return` → otra fecha / otro producto | cada vuelta re-consulta sin arrastrar estado | ✅ |
| E17 | J `1013634967` | recorrido normal | **`*4321`** en selector y confirmación — el PAN de financial-overview, no el `9999` de ADA/contrato | ✅ |
| E16 | Dos `01576905` | **Finalizar conversación** en datos de contacto | cierra por feedback | ✅ |

## Hallazgos abiertos

| # | Hallazgo | Gravedad | Estado |
|---|---|---|---|
| H-01 | La fecha ilegible no se validaba: el gate `.8` consultaba igual (la vigencia con fecha imparseable es fail-open) y **listaba movimientos de otra fecha**. **Corregido**: el gate repregunta con el formato `DD/MM/AAAA` y no consulta hasta tener fecha parseable. Queda abierta la parte de **calendario** que pide el tablero (front). | 🔴 | **Cerrado** (código) · calendario → pregunta 5 |
| H-02 | El botón *"No encuentro la transacción"* sólo existe con **exactamente 3** movimientos (`workflow_actions.py:1538`); con 1-2, la salida `.9.exit` es inaccesible. Verificado en E7. | 🟠 | Abierto — decidir con Fabián (pregunta 6 de la estrategia) |
| H-03 | Fecha en ISO en el label y la confirmación. **Cerrado 13/08**: `DD/MM/AAAA` en ambos. | 🟡 | **Cerrado** |
| H-07 | El aviso de fecha ilegible quedaba **pegado**: reaparecía en cada re-pregunta de fecha (reenganches, bucle multi-tx). **Cerrado 13/08**: se retira al procesar una fecha parseable. | 🟠 | **Cerrado** |
| H-11 | **Reenganche con la misma fecha dejaba la conversación parada en el gate**: el marker de idempotencia del gate `.8` cortaba sin reencaminar, y el cliente se quedaba viendo *"Estoy consultando tus movimientos…"* con un botón Continuar y sin salida. Ahora se reencamina al listado (o a `.8.return`) con los datos ya consultados. **Cerrado 17/08**. | 🔴 | **Cerrado** |
| H-12 | **Fixture incoherente del simulador**: el cliente C lista 3 movimientos pero `operations` solo traía detalle de `TXC01`; elegir el 2.º o el 3.º derivaba a `.10.pqr` como si fuera un fallo del flujo. Completado el fixture con `TXC02` y `TXC03`. **Cerrado 17/08**. | 🟠 | **Cerrado** (dato de prueba) |
| H-14 | El cliente no veía todos sus movimientos (3 de 7). **Corregido 19/08**: el listado muestra hasta **5** y avisa del resto; y si el filtro de importe dejó fuera todo lo del día, se dice en vez de responder "no hay compras". **Queda abierto solo el punto 3**: los abonos siguen excluidos (`moneyFlow=EXPENSE`) y el tablero pide incluirlos — decisión de negocio. | 🔴 | **Cerrado** (1 y 2) |
| H-02 | El botón "No encuentro la transacción" solo existía con exactamente 3 movimientos, por las keys posicionales del YAML. **Corregido 19/08** con el override de keys: aparece siempre. | 🟠 | **Cerrado** |
| H-13 | **Índice de movimiento fuera de rango deriva a formulario**: con 1 movimiento listado, enviar `movimiento_3` (posible desde un canal que mande el índice, no desde botones) acaba en `.10.pqr` en vez de repreguntar. El destino es correcto para un fallo real de detalle, pero no para un índice inválido: son dos causas distintas con el mismo final. | 🟡 | **Abierto** — propuesto separar ambas causas |
| H-10 | `tsec_requested` de la traza de recurrencia reportaba el TSEC **legacy** (`TRX_TICKET_URL`, vacío en el configmap) y salía `False` aunque el granting ticket se pidiera y se usara: un dato de auditoría que engañaba justo donde se audita la llamada al ASO. **Cerrado 14/08**. | 🟡 | **Cerrado** |
| H-09 | **Reanudar por `POST /start` perdía los botones**: el endpoint reanuda la sesión (Arquitectura A) pero serializaba el mensaje siempre como texto plano. Recargar el front en cualquier paso de opciones dejaba la pregunta sin nada que pulsar. Afecta a todos los flujos. **Cerrado 14/08**. | 🔴 | **Cerrado** |
| H-08 | La confirmación mostraba **`*XXXX` literal**: el builder leía `last_four_pan_id` (tabla ADA) y el servicio publica `last_four`. **Cerrado 13/08**. | 🟠 | **Cerrado** |
| H-04 | La recurrencia no consultaba al simulador (`salesforce_issues()` era código muerto). **Corregido en F2**: `TRX_SALESFORCE_SOURCE=aso` → `TrxAsoClient` (simulator/real según `ASO_SOURCE`), con fallback fail-open al mock local. El mount de workaround ya no hace falta. | 🟠 | **Cerrado** |
| H-05 | Recurrencia-bot auto-disparada: **corregido en F0** (`6e16f51`). Si reaparece, es regresión. | 🔴 | **Cerrado** |
| H-06 | Truncados: >5 productos ó >3 movimientos quedan fuera del selector. Con la matriz actual (1 producto/cliente) no es provocable por UI; queda de la verificación de código. | 🟡 | Abierto |

## Descartado por la ejecución (no son fallos)

- **El filtro por fecha en transactions funciona** (E9). La sospecha de "el simulador
  ignora la fecha" aplica a `/operations` (detalle), no al listado.
- El copy de "sin productos" del esqueleto es el del **tablero** ("app BBVA"): el
  conflicto tablero-vs-Excel quedó resuelto en el código a favor del tablero. Anotado
  como decisión tomada, ya no como pregunta.
- La conversación llega a la frontera con Luis exactamente donde el contrato dice:
  confirmación → gate `.12` → pregunta de investigación (E6/E7) o `.12.exit` (E8).

## Reglas para editar

Un caso nuevo = una fila en la tabla + su guion en `suite_esqueleto.py` (acciones
`pick:` / `text:` / `expect:` / `expect_opt:` / `expect_no_opt:`). El guion verifica
**contenido**, no sólo botones — E10 sólo existe porque el `expect` era de contenido.
