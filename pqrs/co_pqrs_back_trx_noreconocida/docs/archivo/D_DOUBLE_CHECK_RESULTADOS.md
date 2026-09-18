# Double check del flujo — resultados consolidados (D1–D5)

**Fecha:** 21/08/2026 · Ejecutado con **tres agentes en paralelo** (contraste con tablero,
barridos de coherencia, revisión adversaria) más el diff contra baseline en secuencia.

> **Balance final (21/08): 4 defectos de copy corregidos, y de los 6 hallazgos serios de la
> revisión adversaria, CINCO corregidos y verificados (A-1, A-2, A-3, A-5, A-6) y UNO
> planteado a PO (A-4, punto 1 de decisiones).** El diff contra la baseline salió limpio: los 3 cambios que
> muestra son los esperados.

---

## 1 · D1 — diff contra la baseline

37 pasos idénticos, **3 distintos y los 3 esperados**: la viñeta única en `.16.2`, los `**`
retirados en `.19.2` y las tildes de `.19.pqr`. **Cero sorpresas.**

Matiz de método: el diff estaba contaminado por capturas viejas (E13/E24, anteriores a las
correcciones de máscara). E13 re-capturada; la técnica queda anotada — *el diff sólo vale si
las capturas son del mismo código*.

## 2 · Corregido hoy (verificado en vivo)

| # | Defecto | Origen |
|---|---|---|
| C-1 | El aviso «ya quedó bloqueada» usaba `••••` — **fallo mío**: lo escribí antes de la decisión de viñeta única y no lo migré | D4 |
| C-2 | La confirmación imprimía la palabra literal «Producto»; el tablero pide el **tipo** — ahora: `Tarjeta de Credito terminado en *0070` | D3 |
| C-3 | El override dinámico pisaba la etiqueta **tildada** del YAML con `transaccion` sin tilde; y la cabecera del bucle igual | D4 |
| C-4 | El respaldo `"****"` tras el asterisco de máscara produciría `*****` (latente) | D4 |

## 3 · D5 — revisión adversaria: lo serio que queda

Trece hallazgos; los seis que hay que corregir, por daño:

| # | Hallazgo | Consecuencia |
|---|---|---|
| **A-1** | El fail-closed **no cubre los fallos detrás de back_trx**: si Postgres/ADA o el ASO caen pero back_trx responde 200 con `not_found`, el cliente recibe las **frases falsas** que `.4.error`/`.8.error` debían impedir (hallazgos 1 y 5) | la petición central de Fabián, incumplida en el modo de fallo más probable |
| **A-2** | La re-ruta de idempotencia del `.8` manda a `.8.return` **cuando el estado previo fue `.8.error`** (hallazgo 4) | «no encontramos compras» tras un fallo técnico; y la compra que se confirma de un día para otro es irreportable |
| **A-3** | Los gates de bloqueo son los únicos **sin marcador de idempotencia** (hallazgo 8) | reintento tras un error de turno ⇒ **segunda reexpedición de tarjeta real** |
| **A-4** | `.20.0` no recibe las salidas tempranas (`.12.exit`, `.16.2`, `.10.pqr`…) (hallazgo 9) | quien declaró 2-3 y su primera queda pendiente **pierde las demás** — la interferencia I-3 prevista en la estrategia, confirmada |
| **A-5** | Dos `dynamic_prompt` no se limpian (`.8.return` fuera-de-rango y `.18` ya-bloqueada) (hallazgos 6-7) | mensajes de la transacción anterior, con la **tarjeta equivocada** en el peor caso |
| **A-6** | La llave del registro de bloqueos **no es estable entre ramas de fetch** (hallazgo 10) | la misma tarjeta con dos llaves ⇒ segundo bloqueo real |

Menores del mismo informe: franquicia vacía → 180 días (ya en decisiones); `trx_customer_address`
no se limpia en el reset; `.20.0` con las URLs sin configurar deja pantalla repetida.

**Bien defendido** (verificado por el mismo agente): el corte por fecha ilegible, la exclusión
deliberada de `trx_productos_bloqueados` del reset, el orden del hito de recurrencia, y todos
los `json.loads` de `captured_data`.

## 4 · D4 — coherencia: lo que queda tras C-1/C-3/C-4

- **Markdown**: limpio en TXNR (la única evidencia era histórica, ya corregida).
- **Frases prohibidas**: cada una vive en un único sitio y se rinde en su paso. Dos matices
  anotados (un mensaje 203 semánticamente equivalente, y la doble redacción por diseño del
  `.8.return`).
- **Tildes**: ✅ **resuelto el 21/08** — Fabián aprobó tildar el YAML completo. Se
  corrigieron **37 líneas** de texto al cliente (las 12 detectadas más el resto que salió al
  barrer: `confirmame`, `victima`, `Encontre`, `menu`, `especifica`, `prestamos`, el `¿` que
  faltaba en la confirmación…), en dos pasadas con revisión del diff completo y barrido
  residual en cero. Los condicionales (`Si deseas…`) y demostrativos (`esta solicitud`) se
  dejaron sin tilde a propósito, que es lo correcto. Regresión en verde.

## 5 · D3 — contraste con el tablero (tramo de Pablo): decisiones de PO

Del contraste completo (30 ítems): **la mayoría coincide literal**. Lo que difiere y no es
corregible sin PO:

| Ítem | Tablero | Bot |
|---|---|---|
| Copy del selector `.5` | «Selecciona la cuenta o tarjeta en la que aparece la compra…» | otro texto + coletilla «Responde con el numero…» |
| Tope del listado `.9` | *«son todos los movimientos, inclusive los abonos»* | tope 5 + aviso (H-14, ya en decisiones) |
| Calendario en `.7` | *«muestra calendario»* | entrada de texto libre |
| Colas de `2.4.2`/`2.4.3` | «…en este enlace y nosotros nos encargaremos de analizarlo» | «…en el formulario» |
| Opciones 3-4 del suceso | «tus datos bancarios» / «Hiciste una compra» | «mis datos» / «Compra» |
| `.4.error`/`.8.error`/`.10.pqr` | no existen en el tablero | robustez añadida — **copy sin aprobar por PO** |

## 6 · Orden de corrección propuesto

1. **A-1 y A-2** — devuelven el fail-closed a donde Fabián lo pidió (el servicio debe
   distinguir «no hay» de «no pude», y el agente propagarlo; la re-ruta debe recordar el error).
2. **A-3 y A-6** — evitan la doble reexpedición de tarjeta, que es daño real al cliente.
3. **A-4** — decisión + código: ¿las salidas tempranas ofrecen continuar con las restantes?
4. **A-5** — limpieza de los dos prompts en el reset.
5. Tildes del YAML si se aprueba, y los copys de PO cuando Fabián los zanje.


---

## 7 · Cierre (21/08, tarde)

| Hallazgo | Estado |
|---|---|
| A-1 fail-closed detrás de back_trx | ✅ corregido: el servicio distingue error de vacío en los tres puntos y el agente lo consume. Verificado con ASO caído y con Postgres caído |
| A-2 idempotencia del `.8` memoriza el error | ✅ corregido: el fallo no se memoriza y el marcador lleva el día. Verificado sobre el estado |
| A-3 doble reexpedición por reintento | ✅ corregido: candado durable `bloqueo_ejecutado:...`. Verificado con revert real: un solo POST |
| A-6 llave inestable del registro | ✅ corregido: manda `contract_id`. `bloqueo_repetido` 5/5 |
| A-5 prompts dinámicos sin limpiar | ✅ corregido: barrido por prefijo (11 claves, no 4). Verificado: 8 antes → 0 después |
| A-4 salidas tempranas y el bucle | 📋 planteado a PO (decisiones, punto 1) |

Pasada final tras todos los arreglos: **nueve de nueve verificadores en verde, a la primera**
(ver `F5_PASADA_COMPLETA.md` §6).
