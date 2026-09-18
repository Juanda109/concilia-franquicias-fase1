# Evaluación de `fix/merge-trx-costuras` como rama de imágenes

**Fecha:** 20/08/2026 · La rama pasa de *"arreglo para que Luis revise"* a **rama desde la que
se construyen las imágenes con el trabajo de los dos**. El listón cambia, así que esta
evaluación cubre lo que hasta ahora no se había mirado: el tramo de Luis, los flujos ajenos
al TXNR, la construcción real de las imágenes y la coherencia de `IaC`.

> **Veredicto: se puede construir.** Todo lo verificable está en verde y la única condición
> previa que quedaba **la resolvió Luis mientras se escribía esto** (§3): su commit
> *"deploy mocks"* devuelve DEV al simulador, que es justo el entorno contra el que se ha
> validado todo. Quedan cuatro decisiones abiertas (§7), ninguna bloqueante.

---

## 1 · Flujo TXNR completo, extremo a extremo (por primera vez)

Hasta hoy sólo se había medido **mi** mitad (hasta `2.4.0.1.11`). Recorrido el flujo entero,
incluida la de Luis:

```
ruteo -> suceso -> cantidad -> intro -> productos (*0060) -> rango -> fecha
      -> listado (3 movs) -> confirmación (••••0060)          [frontera .11]
      -> investigación -> bloqueo definitivo -> tarjeta cancelada
      -> análisis -> resultado -> satisfacción -> cierre       [tramo de Luis]
```

**Las dos salidas de la clasificación funcionan y coinciden con las unitarias:**

| Cliente | Esperado (unitaria) | Obtenido por UI |
|---|---|---|
| `10482895` | `devolucion` | *"tu caso aplica para la devolución automática"* ✅ |
| `1013634960` | — | derivación a PQR (según su fixture) ✅ |

**Caminos alternativos del tramo de Luis, los tres correctos:**

| Camino | Resultado |
|---|---|
| "No, ya reconozco la transacción" | sale a satisfacción ✅ |
| "No, finalizar" en investigación | sale a satisfacción ✅ |
| **Bloqueo temporal** (en vez de definitivo) | *"tu tarjeta ••••0063 quedó apagada temporalmente"* → cierre ✅ |

**Un defecto encontrado y corregido**: el mensaje de tarjeta cancelada decía *"Te la
enviaremos a la dirección **la dirección** registrada en nuestros sistemas"*. La cadena de
respaldo ya incluía "la dirección" y la plantilla la repetía. **No era un caso raro**: el
`customer_address` llega vacío en los fixtures, así que salía en **todas** las ejecuciones.

## 2 · Regresión de los otros 19 flujos

La imagen del agente sirve **20 flujos**, no sólo el TXNR, y mis cambios viven en ficheros
compartidos. Barridos los 20 con su frase de ejemplo del catálogo:

**14 rutean bien · 6 caen en `trx_no_reconocida`** — de forma **determinista**, 6/6 en dos
rondas. Investigado hasta el fondo:

```
Strands routing FAILED (LLM not consumed), using local fallback
reason=AuthenticationError: 401 - invalid subscription key
```

**No es un defecto del producto.** El `.env` local declara la clave del LLM como *dummy a
propósito* para que las pruebas sean deterministas; las 133 rutas del día cayeron al
**respaldo local por palabras clave**. En DEV/OKD la clave real viene de secreto y rutea el
LLM. Los ficheros de ruteo (`general.yml`, `routing_prompt.yml`) son **idénticos** en las
tres ramas, así que el merge no tocó nada de esto.

**Pero deja una observación que conviene subir**: si el LLM falla en producción (caída,
clave rotada), el respaldo manda **6 de 20 intenciones canónicas al TXNR** — un flujo pesado,
con límites diarios y con pasos que **bloquean la tarjeta del cliente**. Ese modo de fallo
merece revisarse aparte de este merge.

**Consecuencia honesta para esta evaluación**: no he podido validar el ruteo real por LLM en
local. Lo que sí queda validado es todo lo posterior al ruteo, que es YAML determinista más
los gates en Python.

## 3 · La condición previa: DEV ya no usa el simulador

`IaC` de DEV cambió en el merge (cambios de Luis, deliberados):

| Variable | Mi rama | Rama de release |
|---|---|---|
| `ASO_SOURCE` | `simulator` | **`real`** |
| `TRX_SALESFORCE_SOURCE` | `mock` | **`real`** |
| `TRX_TICKET_URL` | vacío | granting ticket real |
| `ASO_SALESFORCE_BASE_URL` | — | `dev-arqaso…` (nuevo) |
| `ASO_OPERATIONS_BASE_URL` | — | `aso-dev-co…` (nuevo, host distinto) |
| `MAX_DAILY_SESSIONS` | 3 | **1000** |
| `MAX_DAILY_CATEGORY_INTERACTIONS` | 3 | **1000** |
| `DIAS_HABILES_DEVOLUCION` | 10 | 40 |

DEV pasa de entorno simulado a **integración contra los servicios reales de BBVA**. Eso es
razonable para probar de verdad, y explica muchos de sus cambios. Pero tiene una
consecuencia que hay que decir claramente:

> **Todo lo que he validado hoy corre contra el simulador. En DEV no se usará.**

Y ahí está la pregunta abierta. El arreglo D2 hizo que el **simulador** vuelva a aceptar
`customer.id + contracts.productType`. Pero si Luis endureció el simulador para **imitar al
ASO real** —que es la explicación más plausible—, entonces en DEV el servicio, con la
bandera apagada, seguirá mandando `contracts.productType` y **el ASO real podría rechazarlo
igual que lo hacía el simulador**. Con el agravante de §4 de `ESTRATEGIA_RAMA_LUIS.md`: el
`contract_id` de ADA **no es** el `id` del contrato en financial-overview, así que mandar
`contracts.id` tampoco resolvería por sí solo.

### RESUELTO — Luis devolvió DEV al simulador

Mientras se redactaba esta evaluación, Luis subió tres commits a la rama
(`f692d8f`, `b9c84cf`, `49973d7 "deploy mocks"`) que **revierten precisamente eso**:

```
TRX_SALESFORCE_SOURCE=real  ->  mock
ASO_SOURCE=real             ->  simulator
```

y sube las etiquetas a `co_pqrs_back_agent:test_v4`,
`co_pqrs_back_trx_aso_simulator:test_v4` y `co_pqrs_back_trx_noreconocida:test_v5`.

**Con esto, DEV vuelve a usar el simulador, que es exactamente el entorno contra el que se
ha validado todo lo anterior.** El arreglo D2 es el camino operativo en DEV, y la pregunta
de abajo deja de bloquear: pasa a ser deuda a resolver **antes** de apuntar a ASO real, no
antes de construir.

(Nota: las etiquetas quedan desparejas —`test_v4` para agente y simulador, `test_v5` para el
servicio trx—. Si es intencionado, perfecto; si no, conviene igualarlas antes de publicar.)

**La pregunta, aplazada pero no resuelta**, para cuando se vuelva a `ASO_SOURCE=real`:

> ¿Endureciste el simulador porque el **ASO real** exige `contracts.id`? Si es que sí,
> ¿con qué valor lo llamas, dado que el `contract_id` de ADA no casa con el `id` del FO?

- Si la respuesta es **"sí, el real lo exige"** → hay que resolver el identificador **antes**
  de construir, o DEV se quedará sin movimientos igual que pasaba en local.
- Si es **"no, fue por otro motivo"** → se puede construir ya; el arreglo D2 es correcto en
  ambos entornos.

## 4 · Construcción de las imágenes

| Imagen | Receta | Construye | Arranca |
|---|---|---|---|
| `co_pqrs_back_agent` | `Containerfile` | ✅ 433 MB | ✅ `/docs` 200 |
| `co_pqrs_back_trx_noreconocida` | `Containerfile` | ✅ 264 MB | — |
| `co_pqrs_back_trx_aso_simulator` | **`Dockerfile`** | ✅ 263 MB | ✅ `/docs` 200 |

Ojo con el simulador: es el único de los tres que usa **`Dockerfile`** y no `Containerfile`.
Un script de construcción que asuma `-f Containerfile` para los tres **falla en él**.

Y el arreglo D2 viaja dentro de la imagen, comprobado sobre el contenedor construido:

```
FO por customer.id  -> 200      (la forma que manda el servicio con la bandera apagada)
FO por contracts.id -> 200      (la busqueda por contrato de Luis, intacta)
```

**Hallazgo del arranque**: el log de la imagen del agente dice

```
INFO: Started reloader process [1] using StatReload
```

El `Containerfile` del agente lleva **`--reload` en el `CMD`**. Es una bandera de desarrollo:
levanta un proceso vigilante extra, consume más memoria y **reinicia el servidor ante
cualquier cambio de fichero** — y en OKD el configmap va montado como fichero dentro del
contenedor. El servicio trx **no** la lleva. Es previo a este merge, así que no lo he tocado,
pero conviene decidirlo antes de dar estas imágenes por buenas.

## 5 · Estado de las pruebas

| | Resultado |
|---|---|
| `suite_esqueleto` | **17/17** |
| `verificar_contrato` | **OK** |
| `verificar_mensajes` | **61/61** |
| Unitarias agente | 345 pasan · 10 fallan (**idénticas en las tres ramas**, previas) |
| Unitarias servicio trx | 40 pasan · **1 falla**: `test_01576905_pqr`, con dos aserciones contradictorias del merge |

## 6 · Corrección de algo que publiqué

En `ESTRATEGIA_RAMA_LUIS.md` §8.4 y en el PR #78 escribí que el servicio trx «no ve el
`.env`» y que definir `LOCAL_CONTINGENCY_MODE` dejaría *media contingencia*. **Es falso**, y
lo he corregido: el `config.py` del servicio hace `_load_dotenv("/app/.env")` al importarse,
y en OKD **los dos** servicios reciben su configmap montado justo ahí (`subPath: .env`,
`WORKDIR=/app`). Queda una inconsistencia de estilo, no un peligro.

También conviene matizar **D4**: con `MAX_TRX_BOT_RECURRENCE=20` en el agente de DEV, el
error de orden **no se dispararía** allí (haría falta la entrada nº 20). Era un fallo real y
había que corregirlo, pero **no es lo que habría roto DEV**; lo que rompía en local era el
`MAX=1` de pruebas.

## 7 · Antes de construir

| | Acción | Quién |
|---|---|---|
| 🟠 | Pregunta del identificador de §3 — aplazada al volver a ASO real | Luis (+ Nicolás) |
| 🟠 | Decidir `test_01576905_pqr`: ¿`devolucion` o `pqr`? | Luis |
| 🟠 | Decidir si `--reload` se queda en la imagen del agente | equipo |
| 🟡 | Confirmar copys: `••••0060` y `"No, ya reconozco"` | Fabián / PO |
| 🟡 | Recordar que `MAX_DAILY_*=1000` no puede pasar a QA/PRD | equipo |
| 🟢 | El respaldo de ruteo manda 6/20 intenciones al TXNR: ticket aparte | equipo |
