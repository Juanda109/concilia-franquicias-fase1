# Plan — merge de `fix/merge-trx-costuras` a `feature/PQRSdev`

**Fecha:** 21/08/2026 · **Autorizado por:** Fabián
**Estado de partida, medido** (no estimado):

| Dato | Valor |
|---|---|
| Commits nuestros pendientes de llevar | **17** (desde `13e3ef8`) |
| Commits de dev que no tenemos | **23** (ruteo `PQRS-0001`, imágenes base, merges) |
| Base común | `13e3ef8` — dev **ya absorbió** nuestra rama hasta el 20/08 (`1309e4a`) |
| Conflictos del ensayo (`git merge-tree`) | **2 ficheros**: `chat_service.py` y `analysis_service.py` |
| Dato clave | dev **normalizó `chat_service.py` a LF**; el nuestro sigue CRLF → el diff textual es de 11k líneas, pero el semántico nuestro son **~191** |
| Imágenes en dev | versionadas `1.0.1` (el esquema `test_vN` queda atrás) |
| PR #78 | abierto contra `feature/lufmaldotrxno`, **obsoleta** — dev ya la absorbió |

### Qué llevan nuestros 17 commits (lo que dev aún NO tiene, verificado con sondas)

| En dev | Nuestro, pendiente |
|---|---|
| ✅ `4.error`/`8.error` (fail-closed v1) | A-1: fail-closed **detrás** de back_trx (error ≠ vacío en servicio y agente) |
| ✅ `fuente_real` (mock retirado) | A-2: el fallo no se memoriza + marcador con día |
| ✅ `cierre_bucle_trx` (gate .20.0) | **A-3: candado durable anti doble-reexpedición** (`bloqueo_ejecutado` = 0 en dev) |
| ✅ tests alineados al fail-closed | A-5 barrido de dinámicos · A-6 llave estable · copy del tablero · YAML tildado · dirección real · cierre sólo 2-3 · docs/Excel/herramientas |

---

## Principio rector

**Dev no se toca hasta que la integración esté verificada en local.** Es la lección del
merge de Luis: los conflictos se resolvieron sin ejecutar nada y salieron cuatro defectos
encadenados. Esta vez la batería existe (9 verificadores, medidor de cobertura, diff contra
baseline) y se corre **antes** del PR, no después.

---

## Fases

### F1 · Rama de integración y resolución (½ jornada)

```bash
git checkout -b integracion/costuras-a-dev origin/feature/PQRSdev
git merge --no-commit fix/merge-trx-costuras
```

**Resolución de los 2 conflictos, con receta por fichero:**

- **`chat_service.py`** — el conflicto es de **formato** (LF vs CRLF), no de lógica. Receta:
  quedarse con la base de **dev (LF)** y **portar nuestros ~191 cambios semánticos** como
  parche re-terminado a LF:
  ```bash
  git diff 13e3ef8..fix/merge-trx-costuras -- co_pqrs_back_agent/src/application/chat/chat_service.py \
    | sed 's/\r$//' > /tmp/costuras_chat.patch
  git checkout origin/feature/PQRSdev -- co_pqrs_back_agent/src/application/chat/chat_service.py
  git apply --3way /tmp/costuras_chat.patch
  ```
  Los hunks que no apliquen limpios se portan a mano — están identificados uno a uno
  (A-1, A-2, A-3, A-5, A-6, dirección, cierre 2-3, tilde del bucle).
- **`analysis_service.py`** — conflicto real pero pequeño (nuestros 18 vs sus 232). Su lado
  trae «productos sólo desde back_trx conservando `customer_address`»; el nuestro, el
  `None` ante excepción de Postgres y `fuente_real` en las tres publicaciones. **Ambos se
  quieren**: se reconcilian a mano.

**Regla nueva a partir de aquí: LF.** Dev ya normalizó; mantener CRLF en nuestra rama sólo
genera este mismo conflicto en cada merge futuro. La integración adopta LF y se anota.

### F2 · La batería completa sobre la integración (½ jornada)

Exactamente la de `F5_PASADA_COMPLETA.md`, sin recortes:

1. Unitarias del servicio (42) — **ojo**: dev alineó tests al fail-closed; pueden haber
   añadido casos que también deben pasar.
2. Suite 17 · mensajes 60 · contrato · tramo de Luis (5 secciones).
3. `cobertura_txnr.py` — el YAML pudo cambiar en dev (ruteo/porton TXNR): re-medir el grafo.
4. **Re-captura + `diff_capturas.py` contra la baseline**: el diff debe contener sólo lo
   esperado. Es la red que detecta lo que los verificadores no miran.
5. **Barrido de ruteo**: dev metió `PQRS-0001` (captación tolerante, desambiguación,
   portón/token TXNR) que **nunca se ha cruzado con nuestro trabajo**. Repetir el barrido de
   las 20 intenciones y los recorridos de entrada al TXNR — es el área con más probabilidad
   de sorpresa, porque el portón nuevo decide **quién entra** a nuestro flujo.

Lo que aparezca se corrige **en la rama de integración**, con su prueba.

### F3 · PR a `feature/PQRSdev` (1 h)

- Push de `integracion/costuras-a-dev` y **PR por API** (como el #78), con el resumen de
  qué entra y la evidencia de F2.
- `feature/PQRSdev` tiene reglas de rama (allowlist de autor + firmas): si el merge del PR
  las tropieza, **lo ejecuta Fabián o Luis con sus credenciales** — el PR queda listo para
  su botón. No se fuerza nada.
- **Cerrar el PR #78** con nota: la rama destino quedó obsoleta; el contenido viaja a dev
  por este PR nuevo.

### F4 · Post-merge (con Luis)

- **Imágenes desde dev**, con su esquema `1.0.x` (el capítulo `test_vN` se cierra). Recordar:
  el simulador se construye con `Dockerfile`, y hay que reconstruir **las tres**.
- Smoke en DEV desplegado: los tres recorridos canónicos (devolución, PQR, error de servicio)
  y el barrido de ruteo **con el LLM real** — lo que en local nunca pudimos medir.
- Revisar los valores del configmap de dev contra la pregunta 3 de decisiones (los `1000`).

### F5 · Higiene de ramas (30 min)

| Rama | Acción |
|---|---|
| `fix/merge-trx-costuras` | se congela tras el merge (histórico) |
| `feature/lufmaldotrxno` | obsoleta — confirmar con Luis y borrar |
| `feature/trx-esqueleto` | absorbida hace días — confirmar y borrar |
| `pruebas-rama-luis` (local) | borrar |

---

## Riesgos, por probabilidad

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | **El portón/token TXNR de `PQRS-0001` cambia quién entra al flujo** y ningún verificador nuestro lo cubre | el barrido de ruteo de F2.5 + leer el diff de `905ba36` antes de resolver |
| 2 | El parche de `chat_service` no aplica limpio sobre LF | los 191 cambios están identificados por hallazgo; portarlos a mano es tedioso pero acotado |
| 3 | dev cambió comportamiento que nuestras capturas dan por bueno | el diff contra baseline (F2.4) lo destapa por diseño |
| 4 | El entorno local corta procesos (T-2) | por lotes, stack reiniciado, repetir en aislamiento lo que falle |
| 5 | Las reglas de rama bloquean el merge | el PR queda listo y lo ejecuta quien tiene firma |

## Criterio de aceptación

El mismo de la pasada final, sobre la **integración**: unitarias · suite · mensajes ·
contrato · tramo de Luis completo · cobertura re-medida · diff de baseline sin sorpresas ·
barrido de ruteo explicado. **Nada verde a medias entra en dev.**

---

## Resultado de F1–F2 (21/08, tarde)

**F1** — merge resuelto en `fix/integracion-costuras-dev` (el prefijo `integracion/` lo
rechazan las reglas del repo). `chat_service` en LF con los ~191 cambios portados y ocho
sondas verificadas; `analysis_service` con el diseño de dev (superconjunto). Las 8 pruebas
que el merge rompía eran tests de dev codificando el comportamiento pre-decisiones:
alineadas, y de propina cazaron el crudo `XXXX` en la etiqueta degradada. **Agente
10/407 (la línea base exacta de dev +1), servicio 49/49.**

**F2** — la batería entera sobre la integración:

| Paso | Resultado |
|---|---|
| Portón canary: cerrado / token / abierto | ✅ los tres modos, con captura del cerrado |
| Barrido de ruteo | ✅ mismo patrón local conocido (respaldo por clave dummy), sin regresión |
| Suite | ✅ 17/17 |
| Mensajes · contrato | ✅ 60/60 · OK |
| Tramo de Luis (5 secciones) | ✅ 11/11 · 39/39 · 8/8 · 5/5 · 4/4, cero avisos |
| Cobertura re-medida (YAML de la integración, 49 pasos) | ✅ **66/66 (100 %)** |

**Y el hallazgo que justificó todo el método**: Fabián vio en los logs de DEV que el
financial-overview salía **sin el filtro por contrato**. Reproducido en local con los
access-logs: en el `trx_client` del **agente** sobrevivía la última rama de
`LOCAL_CONTINGENCY_MODE`, que descartaba el `contract_id` que los llamadores sí pasan.
Corregido y verificado con las URLs reales (`contracts.id=00131003201300060`, ceros
conservados — la columna es `text` y toda la cadena envuelve en `str()`). DEV tiene ese
mismo defecto: **le llega el arreglo con este PR.**

Riesgo nº 1 del plan (el portón de PQRS-0001), cubierto y con captura. Listo para F3.
