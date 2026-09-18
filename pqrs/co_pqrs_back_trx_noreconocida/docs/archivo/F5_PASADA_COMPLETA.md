# F5 — Pasada completa antes de construir las imágenes

**Fecha:** 21/08/2026 · **Rama:** `fix/merge-trx-costuras`
Última fase del `PLAN_EVALUACION_PRE_IMAGENES.md` antes de construir `test_v5`.

---

## 1 · Resultado

| Verificador | Resultado |
|---|---|
| `suite_esqueleto` | **17/17** |
| `verificar_mensajes` | **61/61**, sin avisos |
| `verificar_contrato` | **OK** |
| `verificar_tramo_luis · bloqueo` | **11/11** |
| `verificar_tramo_luis · desenlaces` | **39/39**, sin avisos |
| `verificar_tramo_luis · errores` | **8/8** |
| `verificar_tramo_luis · bloqueo_repetido` | **5/5** |
| `verificar_tramo_luis · bucle` | **4/4** |
| Unitarias del servicio | **42/42** |
| **Cobertura de aristas** | **65/65 (100 %)** |

Todo con el stack recién reiniciado, y **la suite salió 17/17 a la primera** — cosa que no
ocurría desde ayer.

---

## 2 · Contra los seis criterios de aceptación del plan

| # | Criterio | Estado |
|---|---|---|
| 1 | Toda arista alcanzable pisada o justificada | ✅ 65/65, con 10 muertas documentadas |
| 2 | Los clientes recorridos hasta donde les corresponde | ✅ los 19 clasificados en F1 |
| 3 | Los verificadores en verde | ✅ nueve de nueve |
| 4 | Sin afirmaciones falsas con el ASO caído | ✅ comprobado explícitamente (sección `errores`) |
| 5 | Trazabilidad de desenlaces y errores | ✅ 23 trazas, 14 operaciones, `error_type` en las rutas de fallo |
| 6 | **Dos pasadas seguidas dan el mismo resultado** | ⚠️ ver §4 |

---

## 3 · Un fallo mío que el verificador cazó

La sección de desenlaces avisó de **palabras sin tilde en `2.4.0.1.19.pqr`**, un texto que yo
había dado por corregido el 20/08 y así lo escribí en el commit.

**No lo estaba.** Mi reemplazo buscaba el `question:` en una línea y el YAML lo tiene en
bloque (`question: |`), así que no casó — y no lo verifiqué después. El aviso llevaba razón
desde el primer momento.

Corregido de verdad y confirmado: **39/39, cero avisos**.

Merece quedar escrito por dos motivos. El primero, que el commit del 20/08 afirma algo que no
era cierto. El segundo, y más útil: **el mecanismo de avisos funcionó exactamente para lo que
se diseñó** — señalar una divergencia de forma sin romper la prueba, y sobrevivir hasta que
alguien la mirase.

---

## 4 · El criterio 6 sigue sin cumplirse, y no por el código

«Dos pasadas seguidas dan el mismo resultado» es el único criterio que no puedo firmar. A lo
largo de estos dos días, la suite ha fallado en **cinco pasadas**, **cada vez en un caso
distinto**, y cada uno de esos casos ha salido verde en otra:

| Pasada | Resultado | Caso |
|---|---|---|
| 1ª | 16/1 | R3 · feedback |
| 2ª | **17/0** | — |
| 3ª | cortada | I · transactions vacío |
| 4ª | 16/1 | A · recurrencia |
| 5ª | 16/1 | R2 · rango mayor |
| **hoy** | **17/0** | — |

Síntomas siempre de infraestructura: `ReadTimeout` de OpenSearch, *polling agotado (60 s)*,
opciones vacías en el turno de ruteo, y procesos de fondo que mueren cada 3-4 minutos.

**Descartado que sea el código**, con medidas y no con impresiones: el camino sospechoso
responde en menos de un segundo punto a punto, y el caso del ruteo sale **5/5 en aislamiento**.

**Recomendación:** ticket propio para el entorno local. Se puede construir las imágenes con lo
medido hoy, pero **no se puede certificar reproducibilidad** sobre un entorno que corta
procesos. Y eso hay que decirlo antes, no después.

---

## 5 · Listo para F6 (construir)

Con una condición y dos avisos:

- **Condición:** las etiquetas están **desparejas** — `co_pqrs_back_agent:test_v5`,
  `co_pqrs_back_trx_aso_simulator:test_v5` y `co_pqrs_back_trx_noreconocida:test_v6`. Hay que
  decidir si se igualan antes de publicar.
- **Aviso 1:** el simulador se construye con **`Dockerfile`**, no `Containerfile`. Un script
  que asuma lo segundo falla en él.
- **Aviso 2:** hay que reconstruir **las tres**; las que están en el registro no llevan nada
  de lo hecho estos dos días.


---

## 6 · Pasada FINAL del 21/08 — con todo el double check dentro

Repetida entera tras los arreglos C-1…C-4 y A-1, A-2, A-3, A-5, A-6, con el stack recién
reiniciado. **Nueve de nueve, todos a la primera:**

| # | Verificador | Resultado |
|---|---|---|
| 1 | Unitarias del servicio | **42/42** |
| 2 | `suite_esqueleto` | **17/17** |
| 3 | `verificar_mensajes` | **61/61** |
| 4 | `verificar_contrato` | **OK** |
| 5 | tramo Luis · bloqueo | **11/11** |
| 6 | tramo Luis · desenlaces | **39/39**, sin avisos |
| 7 | tramo Luis · errores (fail-closed) | **8/8** |
| 8 | tramo Luis · bloqueo_repetido | **5/5** |
| 9 | tramo Luis · bucle | **4/4** |

Una corrección de verificador por el camino: la comprobación de la viñeta buscaba la palabra
literal «producto», y tras C-2 ahí va el **tipo real** del payload. Se cambió por una
comprobación **contra la fuente** (el tipo publicado aparece en pantalla), que es más fuerte
que la anterior y coherente con la filosofía del verificador.

**Sobre el criterio 6 (reproducibilidad):** esta pasada completa salió limpia de una vez —
la primera vez en tres días que ocurre. No lo cuento como criterio cumplido (una pasada no
es «dos consecutivas»), pero sí como señal de que la inestabilidad era del entorno y de que
la pauta de trabajo (stack recién reiniciado + secciones por lotes) la esquiva.

**Con esto el `PLAN_EVALUACION_PRE_IMAGENES.md` queda cumplido en sus fases F1–F5, más el
double check D1–D5 completo. Listo para F6 (construir las imágenes), con la única condición
ya conocida: decidir las etiquetas (agente y simulador en `test_v5`, servicio trx en
`test_v6` por el push de Luis).**
