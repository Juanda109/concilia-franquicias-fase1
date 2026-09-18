# Estrategia — double check del flujo completo

**Fecha:** 21/08/2026 · **Rama:** `fix/merge-trx-costuras` @ `593ddcb`
**Motivo:** en dos días han entrado **35 commits** que tocan **9 ficheros de flujo**
(+420/−76), añaden **4 pasos** y cambian **11 textos**. Cada cambio se verificó por separado;
**ninguno se ha verificado junto a los demás**.

---

## 1 · El riesgo real no es cada cambio, es su interacción

Los verificadores están todos en verde, y eso es cierto pero incompleto: **prueban lo que
sabíamos que había que probar**. Lo que no cubren es la interferencia entre cambios que se
hicieron en momentos distintos, cada uno con su propia prueba.

He identificado **seis parejas concretas** que pueden interferir. No son hipótesis genéricas:
cada una toca el mismo dato o el mismo paso desde dos sitios.

| # | Pareja | Por qué puede romper |
|---|---|---|
| I-1 | **fail-closed `.4`** × **captura de la dirección** | la dirección se lee tras `_trx_fetch_products`, en el mismo gate que ahora puede derivar a `.4.error`. ¿Se ejecuta sobre un payload vacío sin reventar? |
| I-2 | **retirada del mock** × **fail-closed `.4`** | ahora hay **dos vacíos distintos**: «Postgres no tiene» → `.4.exit` y «el servicio no contestó» → `.4.error`. Si se confunden, el cliente recibe el mensaje equivocado |
| I-3 | **bucle tras cualquier desenlace** × **salidas tempranas** | los 4 desenlaces van a `.20.0`, pero `.12.exit`, `.7.exit`, `.9.exit` y `.6.pqr` siguen yendo a satisfacción. **Quien declaró 2 y su primera queda pendiente, ¿pierde la segunda?** Es el mismo hueco que Fabián señaló |
| I-4 | **salto del bloqueo `.15`** × **cliente con varios productos** | el registro es **por producto**. Si la 2ª transacción usa otra tarjeta, el bloqueo **debe** volver a ofrecerse. Nunca se ha probado: hasta hoy ningún cliente tenía 2 productos usables |
| I-5 | **regla de pendiente por `observations`** × **clasificación ECI** | `observations` alimenta ahora **dos** reglas (pendiente y reversado). Un texto que contenga «pendiente» y empiece por `01` cumpliría ambas |
| I-6 | **filtro `contracts.id`** × **resolución por `number`** | la petición filtra por contrato y la respuesta se recorre por últimos 4. Si el ASO devolviera **sólo** el contrato filtrado, ¿sigue casando? |

---

## 2 · La baseline que ya existe y nadie ha usado

Durante F2 y F3 se guardaron **17 ficheros de captura** con el **texto literal** de cada paso
y los botones. Se generaron para medir cobertura, pero sirven para algo más valioso:

> **Volver a capturar hoy y comparar contra ellos. El diff debería contener EXACTAMENTE los
> cambios que hicimos a propósito. Cualquier otra diferencia es una sorpresa.**

Es la técnica más barata y la que más puede destapar: no hay que decidir qué comprobar, la
comparación lo hace sola. Y detecta lo que ningún verificador mira — un texto que cambió sin
que nadie lo pidiera.

**Cambios esperados en ese diff** (si aparece algo más, es hallazgo):

- `••••XXXX` → `•XXXX` en los dos mensajes de bloqueo;
- `••••XXXX` → `*XXXX` en la confirmación;
- `No, ya reconozco…` → `No es necesario, ya reconozco la transacción`;
- desaparición de los `**` en el reembolso;
- tildes en `2.4.0.1.19.pqr`;
- la dirección real en la reexpedición;
- `¿Deseas reportar la siguiente transacción?` con signo y tilde.

---

## 3 · El contraste con el tablero está a medias

F3 contrastó **el tramo de Luis** (22 pasos) contra las capturas del tablero: 7 coincidencias
literales y 6 hallazgos. **Mi tramo (26 pasos) nunca se ha contrastado así**, y es donde más
textos han cambiado estos días.

Hay que hacerlo con el mismo método: recuadro del tablero contra literal capturado, anotando
*coincide / difiere / no está en el tablero / el tablero lo pide y falta*.

---

## 4 · Barridos de coherencia (automatizables, baratos)

Cuatro reglas que ahora deben cumplirse **en todo el flujo**, no sólo donde se corrigieron:

| Regla | Cómo se comprueba |
|---|---|
| **Ningún Markdown** | ningún mensaje contiene `**` ni `__` |
| **Máscaras coherentes** | `*XXXX` en la confirmación, `•XXXX` en bloqueos, y **ningún `••••`** |
| **Tildes** | ninguna palabra de una lista corta (`informacion`, `revision`, `transaccion`, `devolucion`, `direccion`) aparece sin tilde en texto al cliente |
| **Sin afirmaciones falsas** | con el ASO caído, ninguna de las frases prohibidas en ningún paso |

Se hacen sobre las capturas, sin ejecutar nada, y se pueden dejar como comprobación
permanente.

---

## 5 · Revisión adversaria de los gates

`chat_service.py` se ha llevado **259 líneas** de cambio. Conviene una lectura hecha con la
pregunta contraria a la habitual: no *«¿hace lo que quiero?»* sino **«¿en qué caso hace lo que
no quiero?»**. Los seis gates que cambiaron:

`.4` (fail-closed + dirección) · `.8` (fail-closed) · `.15` (salto de bloqueo) ·
`.20.0` (nuevo) · `.20.1` (cierre condicional) · `.16.1`/`.17.1` (registro de bloqueo)

Preguntas concretas por gate: ¿qué pasa si el dato llega vacío? ¿si el cliente vuelve por un
reenganche? ¿si la conversación se retoma al día siguiente? ¿si el mismo gate se ejecuta dos
veces?

---

## 6 · Plan

| Fase | Trabajo | Est. |
|---|---|---|
| **D1** | Re-capturar y **diff contra la baseline** (§2). Clasificar cada diferencia en *esperada* / *sorpresa* | 1,5 h |
| **D2** | Probar las **seis interferencias** de §1, una por una, con recorrido dirigido | 2 h |
| **D3** | Contraste del **tramo de Pablo** contra el tablero (§3) | 2 h |
| **D4** | **Barridos de coherencia** (§4), y dejarlos como comprobación permanente | 1 h |
| **D5** | Lectura adversaria de los seis gates (§5) | 1,5 h |
| **D6** | Corregir lo que aparezca y repasar la pasada completa | 2 h |

**≈ 1,5 jornadas.** D1 y D2 son las que más probabilidad tienen de encontrar algo: la primera
porque compara contra un estado real anterior, la segunda porque ataca justo lo que nadie ha
probado.

---

## 7 · Qué se considera «pasado»

- **Cero sorpresas** en el diff de D1, o cada una explicada y corregida.
- **Las seis interferencias** probadas, con su recorrido guardado como captura.
- **El tramo de Pablo contrastado** contra el tablero, con sus hallazgos anotados.
- **Los cuatro barridos** en verde y ejecutables de nuevo por cualquiera.
- La pasada completa de F5 **repetida** tras los cambios que surjan.

---

## 8 · Lo que este double check NO va a resolver

- **La inestabilidad del entorno.** Seguirá cortando procesos; se trabaja en lotes y se repite
  en aislamiento lo que falle. Sigue mereciendo ticket propio.
- **La integración con ASO real.** Todo esto se mide contra el simulador.
- **Las decisiones abiertas** de `DECISIONES_PENDIENTES_TXNR.md`: las dos máscaras, los valores
  de QA/PRD, el respaldo de ruteo. No son defectos.
