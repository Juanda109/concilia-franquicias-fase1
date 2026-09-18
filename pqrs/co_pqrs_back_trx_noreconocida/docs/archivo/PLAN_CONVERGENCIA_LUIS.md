# Plan de convergencia con `feature/lufmaldotrxno`

**Fecha:** 19/08/2026 · Ensayo de merge hecho **en seco** (sin tocar ninguna rama).
Luis avisa que su rama **no está lista**; esto es la preparación para cuando lo esté.

---

## 1 · La foto

| | |
|---|---|
| Punto común | `1b34f9c` — 13/08 |
| Commits suyos | 15 |
| Commits míos | 58 |
| Ficheros tocados por ambos | **11** |
| **Conflictos reales** (ensayo) | **8 ficheros** |

Los otros 3 comunes se auto-resuelven.

---

## 2 · Los 8 conflictos, por dificultad

### Triviales — decisión de una línea (5 ficheros)

| Fichero | Qué pasa |
|---|---|
| `.gitignore` | él añade 1 línea, yo 4 → **se quedan todas** |
| `IaC/…/co_pqrs_back_agent/03-deployment.yaml` | ambos cambiamos el **tag de imagen** |
| `IaC/…/co_pqrs_back_trx_aso_simulator/01-deployment.yaml` | ídem |
| `IaC/…/co_pqrs_back_trx_noreconocida/03-deployment.yaml` | ídem |
| `co_pqrs_back_trx_noreconocida/…/core/config.py` | 1 línea cada uno |

Los tags de imagen los decide **quien despliega** (Fabián), no nosotros: se toma el más
reciente y se avisa.

### Media — mismo fichero, zonas distintas (2)

| Fichero | Yo | Él |
|---|---|---|
| `chat_service.py` | +261/−7 · gates `.1`, `.4`, `.8`, `.10`, turno, PAN | +50/−5 · `_trx_fetch_products`, polling de back_data |
| `test_aso_rules.py` | +189 (caché, recurrencia ASO) | +14/−9 |

**Coincidimos en `_prefetch_trx_data_if_needed` y `_trx_fetch_products`** — la función que
ya identificamos como punto de colisión en el contrato de frontera. Ahí hay que leer, no
elegir un lado.

### 🔴 La difícil — `workflow_actions.py`

| | |
|---|---|
| Yo | +89/−14 (selector de productos y movimientos, `descProvision`, formato de fecha) |
| **Él** | **+331/−43** — es el grueso de su tramo (bloqueos, investigación, devolución) |

Es el fichero donde más ha trabajado él y donde yo he tocado la presentación. **Este es el
que hay que resolver a cuatro ojos**, no en solitario.

---

## 3 · Cómo lo haría, y por qué

### El orden importa: primero él a `PQRSdev`, luego yo

Mi PR #75 lleva **58 commits** y está listo; el suyo aún no. Dos caminos:

- **(a) Fusionar el mío primero.** Cuando Luis termine, encuentra `PQRSdev` con mis
  cambios y resuelve él los conflictos en su rama — con la ventaja de que **verá el
  contrato de frontera ya implementado** y podrá ajustarse a él.
- **(b) Converger las dos ramas antes** y fusionar juntas.

**Recomiendo (a)**, por tres razones: mi rama está verificada y sin conflictos con
`PQRSdev`; retrasarla no aporta nada; y a él le conviene partir de un contrato existente
en vez de negociarlo mientras programa.

Si Fabián prefiere (b), la convergencia se hace en una rama de integración temporal
—nunca directamente sobre las nuestras— y se resuelve `workflow_actions.py` juntos.

### Antes de cualquier merge: correr mis tres verificadores

`suite_esqueleto.py` (17), `verificar_contrato.py` (25) y `verificar_mensajes.py` (61) son
la red que dice si la convergencia rompió el tramo. **Sirven igual tras el merge**, y son
la forma más rápida de saber si algo se perdió por el camino.

---

## 4 · Lo que conviene decirle a Luis ahora

Tres cosas que le ahorran trabajo si las sabe **antes** de terminar:

1. **El contrato de frontera está implementado y verificado.** `docs/CONTRATO_FRONTERA.md`
   dice qué claves recibe en `2.4.0.1.12` y `verificar_contrato.py` lo comprueba. Si su
   código lee otras claves, mejor saberlo ahora.
2. **Cambié cosas que le afectan**: `last_four` ahora viene del PAN de financial-overview
   (no de ADA), el selector de movimientos admite 5 opciones con override de keys, y hay
   caché de `operations` por `(card_id, fecha)` — si él vuelve a pedir el detalle, ya no
   cuesta llamada.
3. **`workflow_actions.py` es nuestro punto de choque.** Cuanto antes acordemos quién toca
   qué bloque, menos duele. Lo propuse en el contrato: dispatch por dueño, o bloques
   comentados.

---

## 5 · Riesgos

| Riesgo | Mitigación |
|---|---|
| Resolver `workflow_actions.py` en solitario y romper su lógica | resolución a cuatro ojos, o esperar a que él fusione sobre lo mío |
| Perder mis arreglos transversales al resolver `chat_service.py` | los verificadores lo detectan; además cada arreglo tiene prueba propia |
| Pelearnos por los tags de imagen de IaC | no son nuestros: los fija quien despliega |
| Que su rama avance mientras converge | repetir el ensayo en seco antes de la resolución definitiva |

**El ensayo se repite con un comando** y no toca nada:

```bash
git merge-tree --write-tree --name-only HEAD origin/feature/lufmaldotrxno
```
