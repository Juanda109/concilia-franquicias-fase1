# Estrategia — cubrir todas las ramas del tramo de Luis y contrastarlas con el tablero

**Fecha:** 20/08/2026 · **Objetivo:** que ninguna rama del tramo de Luis quede sin recorrer,
que cada una se contraste contra el tablero, y que sus 26 filas del Excel queden rellenas
con evidencia real y no con suposiciones.

> **El método ya ha demostrado que funciona**: aplicarlo a *un solo recuadro* del tablero
> —la regla ECI— ha destapado dos defectos y ha resuelto de paso el test contradictorio que
> arrastrábamos desde el merge (§4). Esto es lo que se busca escalar a las 26 transiciones.

---

## 1 · Qué hay que cubrir, contado

El tramo de Luis (de `2.4.0.1.12` en adelante):

| | |
|---|---|
| Pasos | **20** |
| Transiciones (aristas) | **26** |
| Acciones Python | **9** — `validar_pendiente_trx`, `bloqueo_temporal_trx`, `mostrar_bloqueo_temporal_trx`, `bloqueo_permanente_trx`, `mostrar_bloqueo_definitivo_trx`, `validar_investigacion_trx`, `mostrar_trx_no_reconocida`, `mostrar_trx_reversada`, `registrar_devolucion_trx` |
| Desenlaces de la investigación | **4** — `presencial`, `reversado`, `pqr`, `devolucion` |

**Siete pasos no tienen botón que lleve a ellos**: se alcanzan sólo por redirección desde
código (`2.4.0.1.12.exit`, `…16.1.pqr`, `…17.1.pqr`, `…19.1`, `…19.2`, `…19.2.guia`,
`…19.pqr`). Son precisamente los desenlaces y los caminos de error — los que más importan y
los que un recorrido "feliz" nunca toca.

## 2 · Qué está cubierto hoy, de verdad

De sus **26 filas** en `Merged_Flux.xlsx`: **25 sin estatus** y 1 marcada *"Falllida"*.
De mis recorridos de ayer sólo salieron 2 de los 4 desenlaces.

### El mapa de alcanzabilidad (medido sobre los fixtures, no estimado)

| Desenlace | Operaciones | Cliente por el que se llega | ¿Por UI? |
|---|---|---|---|
| `pqr` | 21 | `1013634960` (TXC01, eci=5) | ✅ |
| `devolucion` | 4 | `10482895` (TXR101, eci=7), `1013634961` (TXD01, eci=1) | ✅ |
| `presencial` | 1 (TXH01, eci=9) | **ninguno** | ❌ |
| `reversado` | 1 (TXI01, obs `01 REVER`) | **ninguno** | ❌ |

**Dos de los cuatro desenlaces de Luis no se pueden provocar por la UI.** Sus fixtures viven
en PAN `…940067` y `…940068`, que **no aparecen en ningún `financial-overview`** y **no
tienen fichero de `transactions`**. Es decir: ningún cliente resuelve a esas tarjetas, y aun
resolviendo no habría movimientos que listar. Hoy sólo existen para la prueba unitaria.

## 3 · El método: contrastar recuadro a recuadro contra el tablero

Para cada uno de los 20 pasos, tres columnas enfrentadas:

| Tablero (captura del 13/08) | YAML / acción | Comportamiento real |
|---|---|---|
| texto y botones que pinta el PO | lo que declara el flujo | lo que devuelve el bot |

Y por cada **regla de negocio** que el tablero enuncia en sus recuadros grises, una
comprobación explícita contra el código. Es exactamente lo que ha destapado §4.

## 4 · Lo que ya ha salido aplicándolo a UN recuadro

El tablero dice, literalmente:

> *"Serán contracargables según ECI: Contracargo (responsabilidad del comercio): **0,1,2,3,7**"*
> *"Si el campo ECI está sin información se debe activar el formulario para radicación"*

### 4.1 · El `0` falta — y es el cliente quien lo paga

```python
eci_allowed = {"1", "2", "3", "7"}          # falta el "0"
...
elif (eci == "") or (eci not in eci_allowed):
    resultado = "pqr"
else:
    resultado = "devolucion"
```

Una transacción con **ECI 0** es contracargable según el tablero —responsabilidad del
comercio, al cliente se le devuelve el dinero— y el código la manda al **formulario de PQR**.

**Por qué nadie lo ha visto**: no existe **ni un solo fixture con `eci = "0"`**. Es el mismo
patrón que el cliente J: un defecto invisible porque ningún dato lo ejercita.

### 4.2 · El conjunto configurable es **código muerto**, y eso es peor

```
IaC/…/01-configmap.yaml   ECI_CHARGEBACK_SET=0,1,2,3,7      <- correcto, el del tablero
config.py                 eci_chargeback_set=eci_set        <- lo parsea
trx_router.py:271         eci_chargeback_set=flow.eci_…     <- lo PASA a la funcion
aso_rules.py:138          eci_chargeback_set: frozenset…    <- lo RECIBE
aso_rules.py:150          eci_allowed = {"1","2","3","7"}   <- y usa este, no aquel
```

El parámetro llega hasta dentro y **se descarta**. Consecuencia: **tocar
`ECI_CHARGEBACK_SET` en el configmap no hace absolutamente nada**. Quien intente ajustar la
regla en QA o PRD verá que no pasa nada y no sabrá por qué.

**Arreglo**: usar el parámetro que ya llega. Una línea.

### 4.3 · De paso, se resuelve `test_01576905_pqr`

La duda que quedó abierta en el PR #78 —¿`devolucion` o `pqr`?— tiene respuesta:

| | Lógica vieja | Lógica nueva | Tablero |
|---|---|---|---|
| ECI contracargable | → `pqr` | → `devolucion` | **responsabilidad del comercio ⇒ se devuelve** |

La lógica anterior estaba **invertida** y Luis la corrigió bien. El cliente `01576905` tiene
`eci = "1"`, así que el resultado correcto es **`devolucion`**. La aserción `pqr` y el propio
nombre del test son residuo de la regla vieja: **hay que quedarse con `devolucion` y
renombrar el test**, no al revés.

## 5 · Los tres huecos de datos que hay que cerrar

Sin esto, parte del tramo no es probable por UI:

| # | Hueco | Qué crear |
|---|---|---|
| H-1 | ningún fixture con `eci = "0"` | operación ECI-0 en un cliente nuevo → debe dar **devolución** |
| H-2 | `presencial` inalcanzable | `financial-overview` + `transactions` para el PAN `…940067` |
| H-3 | `reversado` inalcanzable | ídem para `…940068` |

Son tres ficheros de fixture y una entrada de FO por cada uno. Es el mismo trabajo que se
hizo con los clientes J/K/L, y por la misma razón: **hacer visible lo que hoy no lo es**.

## 6 · Plan por fases

### F1 · Cerrar los huecos de datos (2 h)
Crear los fixtures de H-1, H-2 y H-3 y comprobar que cada desenlace se alcanza por UI.
Sin esto, F2 no puede cubrir más del 50 % de los desenlaces.

### F2 · Recorrer las 26 transiciones y capturar lo real (½ jornada)
Un recorrido por transición, guardando el **texto literal** que devuelve el bot y el
`captured_data` en cada desenlace. Igual que se hizo con mi tramo: se compara contra la
**fuente del dato**, no contra un literal, para que un cambio de copy autorizado no dé un
falso fallo.

### F3 · Contraste con el tablero, recuadro a recuadro (3 h)
Las 17 capturas contra los 20 pasos. Se anota: **coincide** / **difiere** / **no está en el
tablero** / **el tablero lo pide y no está**. Los recuadros grises (reglas de negocio) se
contrastan contra el código, que es lo que ha producido §4.

### F4 · Rellenar las 26 filas del Excel (2 h)
Columnas `F` (esperado, del tablero), `G` (obtenido, literal capturado en F2), `H` (estatus),
`I` (estado técnico), `K`/`L` (observación técnica y comentarios). Los hallazgos nuevos
entran como filas propias, y el protocolo se actualiza.

### F5 · Verificador automático del tramo de Luis (3 h)
El hermano de `verificar_mensajes.py` para su mitad: los cuatro desenlaces, los dos bloqueos
y el bucle de 2ª/3ª transacción, comparando contra la fuente. Así su tramo deja de depender
de que alguien se acuerde de probarlo.

**Total ≈ 1,5 jornadas**, y F1 es requisito de todo lo demás.

## 7 · Lo que se le propone a Luis

1. `eci_allowed` debe ser el `eci_chargeback_set` que ya recibe — hoy el configmap es inerte.
2. Falta el **`0`** frente al tablero: hoy una compra contracargable acaba en formulario.
3. `test_01576905_pqr`: quedarse con **`devolucion`** y renombrar; su corrección de la
   inversión fue acertada.
4. Sus fixtures de `presencial` y `reversado` no son alcanzables por UI: faltan la entrada de
   `financial-overview` y el fichero de `transactions`.

---

## 8 · Segunda pasada: contraste contra la analítica

Decidido hacer **dos pasadas**: primero *diseño contra comportamiento* (§3, el tablero) y
después *comportamiento contra lo que queda registrado*. La segunda responde a una pregunta
distinta y que hoy nadie ha comprobado: **¿el tramo de Luis deja rastro medible?** Si un paso
no emite nada, en producción no se puede saber cuántos clientes llegaron ahí ni dónde
abandonan.

### 8.1 · Hay dos canales, no uno

| Canal | Ruta | Qué lleva | ¿Cubre el tramo de Luis? |
|---|---|---|---|
| **Métricas** | agente → RabbitMQ `pqr.events` → Logstash → `pqr-metrics-*`, `pqr-conversations-*` | 6 eventos: `conversation.started`, `.turn`, `.trace`, `.closed`, `.cap_reached`, `.error` | por agregación de `.turn` (llevan el paso) |
| **Journey** | `_trx_trace_step` → MinIO `audit-logs/clients` | operación + desenlace por gate | **sí**: `bloqueo_temporal`, `bloqueo_permanente`, `devolucion`, `registrada`, `loop`, `siguiente_disponible` |

Buena noticia: su tramo **sí está instrumentado** en el canal de journey. Lo que falta es
comprobar que lo emitido coincide con lo ocurrido, en las 26 transiciones.

### 8.2 · Limitación local, y cómo se sortea

En local **la primera pasada de analítica no es observable**: `RABBITMQ_ENABLED=false`, sin
Logstash ni índices `pqr-*`. Así que la segunda pasada se parte en dos:

- **8.2.a — estática, en local (2 h).** Por cada transición, comprobar en el código qué evento
  y qué campos se emiten, y contrastarlos contra el diccionario de métricas
  (`docs/METRICAS_CAMPOS_Y_VISUALIZACIONES.md`). Detecta pasos mudos y campos que el panel
  espera y nadie rellena. **Se puede hacer ya.**
- **8.2.b — en vivo, sobre DEV (2 h).** Tras desplegar `test_v5`, recorrer los desenlaces y
  comprobar en OpenSearch Dashboards que aparecen con los valores correctos. **Requiere el
  despliegue**, así que va después.

### 8.3 · Qué se considera hallazgo aquí

- un paso que **no emite nada** (invisible en los paneles);
- un campo del diccionario de métricas que **ningún evento rellena**;
- un `outcome` que **no distingue** dos desenlaces distintos (p. ej. si `devolucion` y `pqr`
  quedaran indistinguibles, no se podría medir la tasa de resolución automática);
- un evento que se emite **en el paso equivocado**.

## 9 · Dónde se registran los resultados

Sobre **`Merged_Flux.xlsx`**, hoja *Pruebas Integrales*, en las **26 filas de Luis** que ya
existen (25 sin estatus + 1 *"Falllida"*). Columnas a rellenar:

| Col | Contenido |
|---|---|
| `F` | respuesta esperada — **del tablero**, literal |
| `G` | respuesta obtenida — **capturada** en la ejecución, literal |
| `H` | estatus (Aprobada / Fallida / Pendiente) |
| `I` | estado técnico |
| `K` | observación técnica (cliente, paso, fixture usado) |
| `L` | comentarios de ejecución |

Los hallazgos nuevos entran como **filas propias**, no sobrescriben las suyas. No se toca
ninguna fila de las 52 mías ya aprobadas.

## 10 · Plan consolidado

| Fase | Trabajo | Dep. | Est. |
|---|---|---|---|
| F1 | Cerrar huecos de datos (ECI-0, `presencial`, `reversado`) | — | 2 h |
| F2 | Recorrer las 26 transiciones y capturar literales | F1 | ½ jornada |
| F3 | **Pasada 1**: contraste contra el tablero, recuadro a recuadro | F2 | 3 h |
| F4 | **Pasada 2a**: contraste estático contra el diccionario de métricas | F2 | 2 h |
| F5 | Rellenar las 26 filas de `Merged_Flux.xlsx` | F3, F4 | 2 h |
| F6 | Verificador automático del tramo de Luis | F2 | 3 h |
| F7 | **Pasada 2b**: analítica en vivo sobre DEV | despliegue `test_v5` | 2 h |

**≈ 2 jornadas**, de las cuales F7 depende de que las imágenes estén desplegadas.
