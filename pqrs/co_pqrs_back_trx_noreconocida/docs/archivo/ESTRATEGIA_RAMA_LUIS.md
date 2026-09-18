# Estrategia — ¿corregir la rama de Luis o rehacer el merge?

**Fecha:** 19/08/2026 · **Rama analizada:** `feature/lufmaldotrxno` @ `b5ecb9d`
**Contra:** `feature/trx-esqueleto` @ `cddd4d7` · **Medido en local**, no estimado.

> **Respuesta corta: corregir en sitio. No deshacer el merge.**
> El merge conservó mi tramo íntegro; lo que está roto son **cuatro costuras** —dos ya
> arregladas hoy en ~20 líneas—. Deshacerlo tiraría 26 commits suyos de trabajo real y
> devolvería exactamente los mismos conflictos. Lo único que ningún merge resuelve es una
> **decisión de diseño** que hay que tomar con Luis, y que se explica en §4.

---

## 1 · Qué se midió (evidencia, no impresión)

### 1.1 Topología: el merge fue limpio

```
b5ecb9d  PQRS-0000 prueba deploy
26567a0  Merge 'origin/feature/trx-esqueleto' into feature/lufmaldotrxno   <-- aquí
2f19484  PQRS-0000 fix ASO            }
252a10e  PQRS-0000 fix lectura variable } sus 4 commits, ANTERIORES al merge
4007a34  PQRS-0000 asos               }
9adac6d  PQRS-0000 cambios labels y pruebas }
cddd4d7  PQRS-0000 plan de convergencia   <-- mi punta, base común
```

| Medida | Resultado |
|---|---|
| Commits míos **ausentes** de su rama | **0** |
| Commits suyos no en la mía | 26 |
| ¿Merge real o copia manual? | **merge real** (`26567a0`, dos padres) |

**Luis dice la verdad: sí bajó mi rama, y entera.**

### 1.2 ¿Sobrevivió mi código? Sí, byte a byte

Doce marcadores de mi tramo, contados en ambos árboles:

| Marcador | mía | suya |
|---|---|---|
| `_TRX_MAX_MOVIMIENTOS` | 4 | 4 |
| `dynamic_option_keys` | 2 | 2 |
| `_trx_resolver_pan_de_productos` | 2 | 2 |
| `option_keys_override` | 5 | 5 |
| `fuera_de_rango` (H-14) | 4 | 4 |
| `last_four_origen` | 3 | 3 |
| `_trx_bot_recurrence_hit` | 2 | 2 |
| `_trx_trace_step` | 20 | 20 |
| `dynamic_labels` | 5 | 5 |
| `movimiento_4` / `movimiento_5` | 1 / 1 | 1 / 1 |
| `_local_contingency_enabled` | **0** | **9** ← lo suyo |

**No hay nada que rescatar.** El único elemento nuevo es su bandera, y es justo el hilo del
que cuelgan tres de los cuatro fallos.

### 1.3 Los verificadores sobre su rama

| Verificador | Resultado |
|---|---|
| Suite esqueleto (17) | **12 OK · 5 fallan** |
| Contrato (25) | falla en la frontera |
| Mensajes (61) | OK hasta el listado; falla ahí |

**Los tres fallan en el mismo punto y por la misma causa**: no hay movimientos. Todo lo
anterior —selector de productos, `*0060` real, formatos, reprompt de fecha, ausencia de
crudos en pantalla— **pasa**. Es un fallo de un solo punto, no una degradación general.

---

## 2 · Los cuatro defectos

### D1 · La bandera `LOCAL_CONTINGENCY_MODE` no está definida en ningún sitio
Ni en `compose*.yml`, ni en `.env`, ni en `IaC/`. Comprobado también en caliente: el log del
agente imprime `LOCAL_CONTINGENCY_MODE=None`. **La ruta que Luis protegió con ella es código
muerto en local y lo sería en OKD.**

### D2 · El simulador exige lo que el servicio no manda  ← *causa del síntoma reportado*
El merge cambió el simulador ASO (8050):

```python
-  customer_id: str = Query(..., alias="customer.id"),
-  product_type: str = Query("CARDS", alias="contracts.productType"),
+  customer_id: str = Query("", alias="customer.id"),
+  contract_id: str = Query(..., alias="contracts.id"),      # OBLIGATORIO
```

Pero el servicio sólo manda `contracts.id` **si la bandera está activa**. Con la bandera
apagada —el caso real— manda `contracts.productType` y el simulador responde **422**:

```
GET /financial-overview/...?customer.id=1013634960&contracts.productType=CARDS  -> 422
{"detail":[{"loc":["query","contracts.id"],"msg":"Field required"}]}
```

Sin financial-overview no hay `card_id`, sin `card_id` no hay movimientos. **Esto le pasa a
todos los clientes.** El lado del simulador quedó *sin* proteger por la bandera; el del
servicio, protegido. Es la incoherencia central.

### D3 · `obtener_card_id` pide un argumento que nadie pasa — *independiente de la bandera*
```
TypeError: obtener_card_id() missing 1 required keyword-only argument: 'contract_id'
  chat_service.py:1100 en _trx_resolver_pan_de_productos
```
La firma quedó con `contract_id` obligatorio; los **dos** llamadores del agente lo omiten.
Revienta el gate de productos con el mensaje genérico *"Tuvimos un inconveniente"*.
No depende de ninguna bandera: es una rotura incondicional.

### D4 · Vuelve la recurrencia-bot que ya se había corregido
```python
contingency = _local_contingency_enabled()
if not contingency:
    await _trx_record_milestone_async(conversation, "entered_op4")   # ANTES de leerlo
...
if not has_recurrence and await _trx_bot_recurrence_hit(conversation):
```
Con la bandera sin definir se restaura el orden que `6e16f51` arregló: el hito se escribe
antes de leer el contador, `count=1 >= MAX(1)`, y **todo cliente se desvía a PQR en su
primera entrada**. Mi comentario explicando por qué debía ir después sigue en el fichero,
tres líneas más abajo de código que hace lo contrario — señal de conflicto resuelto a mano
sin ejecutar nada.

### Cómo se encadenan
D4 desviaba a todos a PQR **antes** de llegar al gate de productos, así que **enmascaraba a
D3**; y D3 reventaba antes de la llamada al FO, **enmascarando a D2**. Se arreglan en ese
orden o no se ven.

---

## 3 · Estado a día de hoy

| Defecto | Estado | Coste |
|---|---|---|
| D4 orden del hito | **arreglado y verificado** | 8 líneas |
| D3 firma `obtener_card_id` | **arreglado y verificado** | 12 líneas |
| D2 simulador vs servicio | **arreglado y verificado** | 10 líneas |
| D5 precedencia de `last_four` invertida | **arreglado** (latente, ver §8) | 1 línea |
| D1 bandera indefinida | diagnosticado | 1 línea, pero ver §4 |
| D6 la bandera se lee distinto en cada servicio | diagnosticado (§8) | 3 líneas |

Con D4, D3 y D2 puestos, **el tramo completo funciona de punta a punta** en su rama.
Recorrido real del cliente J (`1013634967`), el que tiene divergencia deliberada entre ADA
(termina en 9999) y financial-overview (PAN termina en 4321):

```
selector      -> Tarjeta de Credito *4321          (viene de financial-overview)
fecha         -> Encontré estas transacciones...
listado       -> 3 movimientos + "No encuentro..."
confirmación  -> • Producto terminado en ••••4321  (NO el 9999 de ADA)
```

---

## 4 · Lo que ningún merge arregla: qué identificador manda

Activar la bandera **no basta**. Medido sobre el fixture del cliente C:

| Origen | Identificador |
|---|---|
| ADA / Postgres (`contract_id` de productos activos) | `00131003201300060` |
| financial-overview, contrato LIC (`id`) | `00130067000200940060` |
| financial-overview, contrato PAN (`id`) | `4912680517940060` |
| financial-overview, `number` de ambos | `0060` |

**Son tres espacios de identificadores distintos.** La búsqueda por `contracts.id` que Luis
introduce presupone que el `contract_id` de ADA es el `id` del contrato en FO, y **no lo
es**. Por eso devuelve `{"contracts":[]}` incluso preguntando "bien". El emparejamiento por
`number` (últimos 4) que hay hoy funciona con los dos.

Esto no es un descuido suyo: es exactamente la divergencia que el **cliente J** (commit
`2d7b19e`) se creó para hacer visible. Con el fixture de Nicolás (`1010223694`) los ids sí
podían coincidir, y de ahí la impresión de que funcionaba.

**Decisión que hay que tomar (Luis + Nicolás, y confirmar con Fabián):**

- **(a) Mantener el emparejamiento por `number`/últimos-4** — funciona con los fixtures de
  hoy, es lo que está verificado con 61 comprobaciones. *Mi recomendación para desbloquear
  ya.*
- **(b) Pasar a `contracts.id`** — probablemente más correcto contra el ASO real, pero
  exige saber **de qué campo de ADA sale ese id**, y hoy no sale de `contract_id`. Es
  pregunta para Nicolás.
- **(c) Las dos, con respaldo** — buscar por `contracts.id` y caer a `number` si no hay
  resultado. Más código, pero no bloquea y deja el camino abierto a (b).

Hasta que se decida, el simulador debe **volver a aceptar las dos formas** (`contracts.id`
opcional, `contracts.productType` con valor por defecto). Eso solo ya resuelve D2 sin
prejuzgar la decisión.

---

## 5 · Por qué corregir y no rehacer

| | Corregir en sitio | Deshacer y rehacer el merge |
|---|---|---|
| Trabajo mío que se recupera | ninguno: **ya está entero** | ninguno |
| Trabajo suyo en riesgo | ninguno | **26 commits** que habría que rehacer |
| Los 4 defectos | 2 hechos, 2 acotados | **reaparecen**: no vienen del merge, vienen de dos diseños distintos del mismo dato |
| Decisión de §4 | igual de necesaria | igual de necesaria |
| Coste | **~½ jornada** | 2–3 jornadas, y con el mismo final |
| Relación con Luis | se le entrega un arreglo revisable | se le deshace su rama |

El argumento decisivo: **el merge no perdió información**. Los conflictos se resolvieron
conservando ambos lados; lo que falló es que nadie ejecutó el flujo después. Un merge nuevo,
por cuidadoso que sea, se topa con el mismo choque de diseño de §4 — porque el problema no
está en cómo se unieron los ficheros, sino en que **hay dos respuestas distintas a "qué
identificador identifica una tarjeta"**.

---

## 6 · Plan

### P1 · Entregar a Luis lo ya arreglado (hoy, 30 min)
Rama `fix/merge-trx-costuras` desde su punta, con D3 y D4 y un mensaje que explique el
encadenamiento. **No se toca `feature/lufmaldotrxno`**: él revisa y mergea.

### P2 · Desbloquear el listado (½ día, tras acordar con Luis)
Simulador: `contracts.id` opcional y `contracts.productType` con defecto → resuelve D2 sin
prejuzgar §4. Con eso los tres verificadores deberían volver a verde sobre su rama; ese es
el criterio de aceptación, no la impresión de que "ya funciona".

### P3 · Cerrar la bandera (1 h)
Una de dos, según lo que decida Luis:
- si la contingencia se queda: **declararla** en `compose` y en `IaC/`, con su valor por
  entorno, y documentar qué cambia;
- si no: **retirarla** y dejar una sola ruta.

Lo que no puede quedarse es una bandera que nadie define y que cambia el comportamiento en
producción.

### P4 · Regresión conjunta (2 h)
Los 3 verificadores + los 25 casos U sobre la rama fusionada, y las filas de
`Merged_Flux.xlsx` actualizadas. Es la primera vez que el tramo completo (mío + el de Luis)
se mediría junto.

### P5 · Prevención (1 h)
Los verificadores se ejecutan **como parte del merge**, no después. Los cuatro defectos
habrían salido en la primera pasada: la suite tarda menos de tres minutos.

---

## 7 · Qué decirle a Luis

1. Su merge está bien hecho: mi rama entró entera y mi código está intacto.
2. Hay cuatro costuras rotas, encadenadas: se enmascaran unas a otras y por eso "no se
   mostraban los movimientos". Dos ya van arregladas en una rama para que las revise.
3. La tercera es que el simulador exige `contracts.id` y el servicio sólo lo manda con una
   bandera que **no está definida en ningún entorno**.
4. Debajo hay una decisión real, no un bug: **por qué campo se busca la tarjeta en
   financial-overview**. Su `contracts.id` no casa con el `contract_id` de ADA — son
   identificadores distintos. Conviene resolverlo con Nicolás antes de tocar más código.
5. Propuesta: nadie deshace nada; se arregla en su rama y se pasan los tres verificadores
   antes de dar el tramo por cerrado.

---

## 8 · Double check milimétrico del merge (19/08, tarde)

Mi primera comprobación contaba **apariciones** de marcadores. Contar no es comparar: dos
funciones pueden tener el mismo nombre y hacer cosas distintas. Esta segunda pasada compara
contenido y aísla, con precisión, qué decidió un humano.

### 8.1 · El método: qué habría hecho git solo

```bash
git merge-tree --write-tree cddd4d7 2f19484     # el merge automático
git diff <ese-árbol> 26567a0                    # lo que el humano cambió encima
```

Git no pudo resolver **8 ficheros**. Y el resultado importante:

> **Fuera de esos 8 ficheros, el commit de Luis es idéntico, byte a byte, al merge
> automático.** No hay ningún cambio introducido "de contrabando" en el merge.

Toda la revisión se reduce, por tanto, a 8 decisiones. Aquí están las 8:

| Fichero | Resolución | Veredicto |
|---|---|---|
| `.gitignore` | conserva mi regla `~$*` | ✅ correcta |
| `IaC/.../agent/03-deployment.yaml` | su etiqueta `test_v3` | ✅ correcta |
| `IaC/.../trx_aso_simulator/01-deployment.yaml` | su etiqueta `test_v3` | ✅ correcta |
| `IaC/.../trx_noreconocida/03-deployment.yaml` | su etiqueta `test_v3` | ✅ correcta |
| `trx/.../core/config.py` | mi lado (sin respaldo `127.0.0.1`) | ✅ correcta |
| `trx/tests/test_aso_rules.py` | conserva **las dos** aserciones | ❌ **test imposible** (§9) |
| `agent/.../chat_service.py` | 3 conflictos | ⚠️ **2 mal (D4, D3)** |
| `agent/.../workflow_actions.py` | 1 conflicto grande | ⚠️ **1 latente (D5)** |

**`IaC` no cruzó entornos**: mis tres etiquetas de prueba (`test_pablov1`, `v2`) pasaron a
`test_v3` de forma coherente en los tres servicios, mismo registro y mismo proyecto.

### 8.2 · El origen exacto de D3 (lo que no se veía antes)

En el tercer conflicto de `chat_service.py`, **su lado sí pasaba `contract_id`**:

```python
<<<<<<< cddd4d7   (mío)         >>>>>>> 2f19484   (suyo)
card_id = ...cache del gate .4  card = await obtener_card_id(
if not card_id:                     ...
    card = await obtener_card_id(   contract_id=str(product.get("contract_id") or ""),
        customer_id=user_id,        last_four=_trx_last_four(product),
        last_four=...)          )
```

Eligió **mi lado** —correctamente, porque el mío reutiliza el PAN ya resuelto y ahorra una
llamada— pero con ello se quedó sin el `contract_id` que **su nueva firma exige**. No es
descuido: es la trampa clásica del merge, quedarse con el llamador de uno y la firma del
otro. Mi arreglo hace justo la reconciliación que faltaba: mi caché **y** su argumento.

### 8.3 · D5 — la precedencia de `last_four`, invertida

Su helper `_get_selected_trx_last4` centraliza lógica que yo tenía en línea. Bien hecho,
salvo el orden:

```python
mío:  product.get("last_four")        or product.get("last_four_pan_id")
suyo: product.get("last_four_pan_id") or product.get("last_four")
```

`last_four` es la clave que publica el servicio y, tras el gate `.4`, la que lleva los
últimos 4 del **PAN de financial-overview** — la fuente que Fabián pidió explícitamente.
`last_four_pan_id` es el nombre de la columna en ADA.

**Hoy no se manifiesta**, y hay que decirlo con precisión: el payload persistido no trae la
clave `last_four_pan_id` (comprobado en OpenSearch: `last_four=4321`,
`last_four_pan_id=None`), así que cae al valor bueno. Pero `_normalize_trx_products`
**sí escribe ambas claves** a propósito, de modo que basta con que otro camino guarde el
producto normalizado para que el cliente vea los dígitos de ADA en la confirmación. Es
literalmente H-08 otra vez, esperando. Corregido: una línea.

### 8.4 · D6 — la bandera se lee de dos maneras distintas

```python
agente        (chat_service.py)  raw = _env_const("LOCAL_CONTINGENCY_MODE")   # .env + entorno
servicio trx  (aso_client.py)    raw = os.getenv("LOCAL_CONTINGENCY_MODE")    # sólo entorno
servicio trx  (trx_router.py)    raw = os.getenv("LOCAL_CONTINGENCY_MODE")    # sólo entorno
```

> **CORRECCIÓN (20/08).** Escribí aquí, y lo repetí en el PR #78, que el servicio «no ve el
> `.env`» y que definir la bandera dejaría *media contingencia*. **Es falso.** El
> `config.py` del servicio llama a `_load_dotenv("/app/.env", override=False)` al importarse,
> así que vuelca el fichero a `os.environ` y `os.getenv` sí lo ve. Y en OKD **los dos**
> servicios reciben su configmap montado exactamente en `/app/.env` (`subPath: .env`), con
> `WORKDIR=/app`, de modo que el `".env"` relativo del agente resuelve al mismo sitio.
>
> Lo que queda es una **inconsistencia de estilo**, no un peligro: dos mecanismos distintos
> para leer lo mismo, y `os.getenv` directo va contra la convención del repo (`CLAUDE.md`:
> la configuración pasa por `load_env_constants()`). Conviene unificarlo, pero **no bloquea
> nada** y no hay riesgo de contingencia parcial.

Esto importa **antes** de tocar la bandera en P3: si se decide activarla, hay que unificar
primero cómo se lee, o el arreglo será parcial y difícil de diagnosticar.

### 8.5 · Cosas que parecían defectos y NO lo son

Las anoto porque descartarlas costó tiempo y evita que se vuelvan a levantar:

- **`_fecha_ddmmaaaa` aplicado dos veces** seguidas en la confirmación. Es **idempotente**
  (sólo transforma cadenas ISO `AAAA-MM-DD`; cualquier otra la devuelve tal cual), así que
  es redundancia inocua, no un bug.
- **`/movimientos` exige `customer_id`** — es un endpoint distinto de `/movimientos-aso`,
  que es el que usa el agente. No hay contrato roto.
- **`extraer_card_id` y `parse_movimientos`**, las dos funciones del servicio de las que
  depende mi tramo: **idénticas** byte a byte entre las dos ramas.
- **Los cambios de `aso_rules`** (ECI, `observations`, `customer_address`) son de la lógica
  de clasificación, es decir **del tramo de Luis**. No tocan el camino del dato de mi mitad.

### 8.6 · Higiene menor, para que él decida

No lo he tocado — es su código y son cambios de estilo, no de corrección:

- `_get_selected_trx_product` calcula `products = json.loads(raw)...` **dos veces
  seguidas**, idéntico. Código muerto.
- Quedan trazas `TXR LAST4 DEBUG` / `TXR PRODUCT DEBUG` en nivel `info`/`warning` que se
  emiten en **cada** confirmación. Fabián pidió logs por paso, así que no sobran del todo,
  pero conviene bajarlas a `debug` o darles el formato del resto.
- Varios comentarios en castellano que explicaban **el porqué** (la divergencia ASO-real en
  `descProvision`, el desajuste de nombres de H-08) se sustituyeron por comentarios en
  inglés que describen **el qué**. El comportamiento no cambia, pero se pierde la razón —
  y es justo esa razón la que evita que el fallo vuelva. Sugerencia, no exigencia.

### 8.7 · Conclusión del double check

El merge de Luis es, en lo estructural, **bueno**: 8 decisiones, 5 correctas, 1 inocua, y
las 2 malas concentradas en un solo fichero. No hay pérdida de información ni cambios
espurios. **Se confirma la recomendación de §5: corregir en sitio.** Lo que sostiene esa
conclusión no es que "parezca poco", sino que ya está medido — el tramo completo se recorre
de punta a punta en su rama con los arreglos puestos.


---

## 9 · Lo que salió al revisar antes de abrir el PR

### 9.1 · Corrección: la resolución de `test_aso_rules.py` NO era inocua

En §8.1 la di por buena ("misma aserción, sólo movida"). Al ejecutar las pruebas apareció
que la resolución conservó **los dos lados dentro del mismo test**:

```python
def test_01576905_pqr(self) -> None:
    r = self._resolve("01576905", "9461", "TXR201")
    self.assertEqual(r["card_id"], "4916555117389461")
    self.assertEqual(r["clasif"]["resultado"], "devolucion")   # mi lado
    self.assertEqual(r["clasif"]["resultado"], "pqr")          # su lado
```

Dos aserciones contradictorias: **el test no puede pasar nunca**. Hoy devuelve
`devolucion`, así que falla en la segunda.

**No lo he tocado**, y es deliberado: el valor correcto depende de la lógica de
clasificación (ECI / `observations`) que Luis reescribió, y eso es su tramo. Puede ser que
sus reglas nuevas deban dar `pqr` —como dice el nombre del test— y entonces hay una
regresión real en la clasificación; o que el esperado haya cambiado a `devolucion` y el
nombre esté obsoleto. **Sólo él puede decidirlo**, y borrar una de las dos líneas sin
saberlo sería tapar el aviso en vez de leerlo.

### 9.2 · Estado de las pruebas unitarias (medido en las tres ramas)

| | agente | servicio trx |
|---|---|---|
| `feature/lufmaldotrxno` (b5ecb9d) | 345 pasan · **10 fallan** · 2 errores | 40 pasan · 1 falla (§9.1) |
| `feature/trx-esqueleto` (cddd4d7) | 345 pasan · **10 fallan** · 2 errores | — |
| `fix/merge-trx-costuras` | 345 pasan · **10 fallan** · 2 errores | 40 pasan · 1 falla (§9.1) |

**Los 10 fallos del agente son idénticos en las tres ramas**: no los introduce el merge ni
este PR. Son previos del repositorio. Que nadie los hubiera visto encaja con que el agente
**no declara `pytest` como dependencia** (hay que invocarlo con `uv run --with pytest`), así
que su suite no se ejecuta de forma habitual. Merece su propio ticket, aparte de esto.

### 9.3 · Intermitencia de la suite E2E, y qué se puede afirmar

Cinco pasadas de `suite_esqueleto` sobre esta rama: **17/17 en tres**, 16/17 en una y 15/17
en otra. Los fallos degradados se dan en el **turno de ruteo por LLM** (`opciones=[]` al
elegir el suceso), que ocurre **antes** de cualquier gate del flujo TXNR.

Lo que sí está medido:
- ese turno, aislado y repetido 8 veces, salió **8/8 correcto** (0,6–2,7 s);
- el paso que falla **no toca ninguna línea que este PR modifique**;
- las pasadas degradadas fueron las inmediatamente posteriores a un
  `reset_cliente.sh --todos`, lo que apunta a latencia de refresco de OpenSearch tras el
  borrado masivo.

Lo que **no** puedo afirmar: no he conseguido cuantificarlo en la rama pre-merge (cada
pasada son ~5 min y el intento se pasó del tiempo disponible; la única pasada completada dio
17/17). Así que lo dejo dicho como lo que es —**intermitencia ambiental muy probable, no
demostrada al 100%**— en vez de darlo por cerrado. Si a alguien le sale un 16/17 con
`opciones=[]`, es esto y se repite la pasada.

### 9.4 · Comprobaciones previas al PR

| Comprobación | Resultado |
|---|---|
| Los 6 ficheros compilan | ✅ |
| CRLF intacto (`chat_service`, `workflow_actions` 100% CRLF) | ✅ |
| La rama mergea en `feature/lufmaldotrxno` sin conflictos | ✅ |
| El simulador atiende **las dos** formas del FO | ✅ (por contrato devuelve sus 2 contratos) |
| Stack en frío: contrato / mensajes | ✅ OK · 61/61 |
| Ficheros ajenos colados en los commits | ✅ ninguno |
