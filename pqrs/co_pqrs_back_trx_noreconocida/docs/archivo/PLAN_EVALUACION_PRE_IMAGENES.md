# Plan de evaluación previo a construir las imágenes

**Fecha:** 20/08/2026 · **Rama:** `fix/merge-trx-costuras` @ `062c24c`
**Objetivo:** recorrer **todos los caminos** del flujo TXNR con **todos los clientes**,
corregir lo que aparezca, y sólo entonces construir `test_v5`.

---

## 1 · Por qué este plan, y por qué ahora

Las imágenes que se van a construir llevan dentro cambios grandes y recientes: la reparación
del merge, los tres requisitos de Fabián, el filtro de financial-overview y nueve decisiones
de negocio aplicadas hoy. **Nada de eso ha pasado nunca por una pasada completa** — se ha ido
verificando por partes.

Además, hasta ahora se ha medido lo que *creíamos* que había que medir. Este plan parte de
haber contado el universo entero, que es más grande de lo que sugerían las suites.

---

## 2 · El universo, contado

| | |
|---|---|
| Pasos del flujo | **48** — 26 de mi tramo, 22 del de Luis |
| Aristas (transiciones) | **75** — 47 mías, 28 de Luis |
| Pasos con acción Python | **17** |
| Gates que reescriben el paso | **12** |
| Clientes en Postgres | **18** |
| Fixtures del simulador | 17 financial-overview · 16 transactions · 15 operations |

**Los fixtures no cubren a los 18 clientes**, y en parte es deliberado (hay clientes creados
para probar «sin productos» o «fecha fuera de plazo», que no deben llegar al ASO). Pero
**parte del desajuste no está justificado y hay que resolverlo**: es el punto §4.1.

### Aristas muertas: un aviso sobre cómo se mide

Cuatro aristas del tramo de Luis están **declaradas en el YAML pero no se pintan nunca**:
`2.4.0.1.12`, `.16.1`, `.17.1` y `.19` llevan una acción que reescribe `current_step` y
devuelve, así que su botón `Continuar` no llega a existir. Está medido empíricamente en F2.

**No sé cuántas hay equivalentes en mi tramo**, y es lo primero que hay que averiguar: sin ese
dato, cualquier porcentaje de cobertura es falso — el denominador está mal. Un 100 % sobre 75
aristas es inalcanzable por construcción.

---

## 3 · Lo que ya está cubierto, y con qué

| Herramienta | Qué cubre | Estado |
|---|---|---|
| `suite_esqueleto.py` | 17 casos del tramo mío, extremo a extremo | 17/17 |
| `verificar_mensajes.py` | 61 comprobaciones de los 4 mensajes con datos del cliente | 61/61 |
| `verificar_contrato.py` | el contrato de la frontera `.11 → .12` | OK |
| `verificar_tramo_luis.py` | los 4 desenlaces, los 2 bloqueos y el bucle | bloqueo 11/11 · 4 desenlaces OK |
| `capturar_tramo_luis.py` | 13 recorridos → 22 de 26 aristas de Luis | capturado |
| Unitarias del servicio | reglas ASO, clasificación, vigencia | 42/42 |

**Lo que ninguna cubre**: los tres arreglos de Fabián de hoy (fail-closed, cierre del bucle,
bloqueo único) y el filtro nuevo de financial-overview. Se verificaron a mano, una vez.

---

## 4 · Los huecos que hay que cerrar

### 4.1 · Clientes sin datos completos

18 clientes en Postgres, 15 con fixture de `operations`. Hay que clasificar **uno por uno**:

- **deliberado** — el cliente existe para probar una salida temprana (sin productos, fecha
  fuera de plazo, recurrencia) y no debe llegar al ASO;
- **hueco** — el cliente debería completar el flujo y no puede.

Los del segundo grupo se completan. Sin esto, «todos los usuarios» es una frase vacía.

### 4.2 · Sin medidor de cobertura por arista

Hoy no existe forma de responder *«¿qué aristas no ha pisado nadie?»* para el flujo completo.
`capturar_tramo_luis.py` lo hace para las 28 de Luis; falta lo mismo para las 47 mías y una
vista conjunta.

### 4.3 · Los cambios de hoy no tienen prueba automática

Fail-closed, cierre del bucle y bloqueo único están verificados a mano. Si alguien los rompe
mañana, **nada avisa**.

---

## 5 · El instrumento: un medidor de cobertura

Antes de correr nada, construir `cobertura_txnr.py`, que:

1. **lee el YAML** y construye el grafo: 48 pasos, 75 aristas;
2. **marca las aristas muertas** — las de gates que redirigen incondicionalmente — para que el
   denominador sea el real y no el declarado;
3. **recorre** los clientes y los caminos, registrando el `current_step` real de OpenSearch en
   cada turno (la técnica que ya usa `capturar_tramo_luis.py`, y que corrigió una medición mía
   que daba 4/26 cuando era 16/26);
4. **emite** la lista de aristas no pisadas, con qué cliente habría que pisarlas.

Ese listado es el plan de pruebas de verdad; lo demás es ejecutarlo.

---

## 6 · Fases

### F1 · Inventario de clientes (1 h)
Clasificar los 18 en «deliberado» o «hueco», y completar los fixtures de los segundos.
**Entregable:** tabla cliente → qué prueba → hasta dónde llega → por qué.

### F2 · Medidor de cobertura (2 h)
`cobertura_txnr.py` según §5. **Entregable:** el denominador real y la lista de aristas sin
pisar.

### F3 · Recorrer lo que falte (½ jornada)
Diseñar un recorrido por cada arista no cubierta y ejecutarlo. Lo que aparezca **se corrige en
el momento**, no se anota para después.

### F4 · Blindar los cambios de hoy (3 h)
Las tres secciones que quedaron pendientes en `verificar_tramo_luis.py`:
`errores` (ASO caído → `.4.error` / `.8.error`, sin frases falsas), `bucle_cierre` y
`bloqueo_repetido`.

### F5 · Pasada completa y limpia (2 h)
Los cinco verificadores seguidos, con el stack recién reiniciado. **Criterio de aceptación en
§7.**

### F6 · Construir las imágenes (1 h)
Las tres con `test_v5`, y comprobar que arrancan y responden. Recordar que el simulador usa
**`Dockerfile`** y no `Containerfile`.

**Total ≈ 1,5 jornadas.** F1 y F2 son requisito de todo lo demás.

---

## 7 · Criterio de aceptación — qué significa «sin errores»

No basta con «pasó». Para dar la evaluación por buena:

| # | Criterio |
|---|---|
| 1 | **Cobertura**: toda arista alcanzable pisada al menos una vez, o justificada por escrito |
| 2 | **Clientes**: los 18 recorridos hasta donde les corresponde, sin quedarse a medias por falta de fixture |
| 3 | **Verificadores**: suite 17/17 · mensajes 61/61 · contrato OK · tramo de Luis completo · unitarias 42/42 |
| 4 | **Sin afirmaciones falsas**: con el ASO caído, en ningún punto aparece «no tienes productos» ni «no encontramos compras» |
| 5 | **Trazabilidad**: todo desenlace y todo error deja traza con `outcome`, y los errores con `error_type` |
| 6 | **Reproducible**: dos pasadas seguidas dan el mismo resultado |

El criterio 6 es el que más va a costar, por lo que explico en §9.

---

## 8 · Qué hacer con lo que aparezca

Distinguir **tres** cosas, porque hoy se están mezclando:

| Tipo | Qué es | Qué se hace |
|---|---|---|
| **Defecto** | el código hace algo distinto de lo acordado | se corrige y se añade prueba |
| **Hueco de datos** | el código está bien, falta el fixture | se completa el fixture |
| **Decisión** | no está acordado qué debe pasar | va a `DECISIONES_PENDIENTES_TXNR.md`, no se inventa |

Los tres se ven igual desde fuera —«esto falla»— y tratarlos igual es lo que hace perder
tiempo. Hoy mismo reporté como defecto lo que era un hueco de fixture (la viñeta «Monto
devuelto»), y Fabián tuvo que corregirme.

---

## 9 · El riesgo real: el entorno, no el código

Esta tarde la suite ha fallado en **tres pasadas de cuatro**, cada vez en un **caso distinto**,
y cada uno de esos casos ha salido verde en otra pasada:

| Pasada | Resultado | Caso |
|---|---|---|
| 1ª | 16/1 | R3 · feedback |
| 2ª | **17/0** | — |
| 3ª | cortada | I · transactions vacío |
| 4ª | 16/1 | A · recurrencia |

Síntomas: `ReadTimeout` de OpenSearch, *polling agotado (60 s)*, opciones vacías en el turno de
ruteo. Comprobado que **no es el código**: el camino sospechoso responde en menos de un
segundo medido punto a punto, y el caso del ruteo sale 5/5 en aislamiento.

**Mitigaciones para este plan:**

- **reiniciar el agente antes de cada pasada** — lo desatasca de forma consistente;
- **ejecutar por secciones**, no en cadena: los procesos largos se mueren;
- **repetir en aislamiento** cualquier fallo antes de investigarlo, para no perseguir fantasmas;
- **registrar qué caso falló en cada pasada**: si siempre falla el mismo, es código; si cambia,
  es entorno. Esa tabla es la que ha permitido descartarlo hoy.

Si tras las mitigaciones la inestabilidad persiste, merece ticket propio: **no se puede
certificar un release sobre un entorno que no es reproducible**.

---

## 10 · Lo que este plan NO cubre

- **El tramo de backoffice** (fila NO=23, RPA Tantia): no es verificable por conversación.
- **La integración con ASO real**: DEV apunta al simulador. Cuando se vuelva a `real` hay que
  repetir la evaluación, y antes resolver la pregunta a Nicolás sobre el filtro `contracts.id`.
- **Los 19 flujos ajenos al TXNR**: el barrido de ruteo se hizo y dio 14/20 por el respaldo
  local; con el LLM real en DEV el resultado será otro. Va aparte.
