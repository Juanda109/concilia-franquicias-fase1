# F2 — Medidor de cobertura y línea base

**Fecha:** 20/08/2026 · Segunda fase del `PLAN_EVALUACION_PRE_IMAGENES.md`.
**Herramienta:** `docs/pruebas/cobertura_txnr.py`

---

## 1 · La línea base, medida

```
PASOS   32/48 renderizados
ARISTAS 45/66 cubiertas (68%)   [9 muertas excluidas del denominador]
```

Hasta hoy la cobertura se expresaba en **casos** («17 casos OK»), que no dice qué caminos
quedan sin pisar. Ahora hay un número y, sobre todo, **una lista de 21 aristas concretas**
que es el plan de trabajo de F3.

---

## 2 · Dos trampas que el medidor evita, ambas sufridas

### 2.1 · El denominador declarado es falso

**9 aristas están en el YAML pero no se pintan nunca.** Su paso lleva una acción que reescribe
`current_step` y devuelve, así que el botón no llega a existir:

```
2.4.0.1.3   2.4.0.1.4   2.4.0.1.8    2.4.0.1.10   2.4.0.1.12
2.4.0.1.16.1   2.4.0.1.17.1   2.4.0.1.19   2.4.0.1.20.0
```

Contarlas hacía que el 100 % fuera inalcanzable por construcción. Se excluyen del
denominador: **66, no 75**.

La detección es heurística —analiza el bloque del gate en `chat_service.py`— y por eso **se
corrige sola**: si una arista marcada como muerta aparece pisada en alguna captura, el
medidor la devuelve al denominador y lo dice. En esta pasada ocurrió con una.

### 2.2 · Emparejar por texto no vale

El selector de productos y el listado de movimientos declaran en el YAML `Producto 1`,
`Movimiento 1`… y el cliente ve `Tarjeta de Credito *0060` o
`COMPRA FALABELLA — $120.000 — 06/08/2026`. Emparejar por etiqueta daba **~10 aristas por no
cubiertas para siempre**.

El medidor empareja **por etiqueta y, si falla, por posición**: busca en qué índice estaba el
botón pulsado dentro de las opciones renderizadas. Añadirlo subió la medición de 40 % a 43 %
sobre la misma captura.

> Es la segunda vez que el emparejamiento por texto engaña. La primera dio **4/26** cuando la
> cobertura real era **16/26**. Por eso el medidor lee el `current_step` que queda en
> OpenSearch y no lo deduce del mensaje.

---

## 3 · Lo que falta, clasificado (21 aristas)

### 3.1 · Sólo necesitan un recorrido (11)

| Arista | Con qué cliente |
|---|---|
| `2.4.0.1.5` → Producto **2, 3, 4, 5** | `1010223694`, que tiene 2 productos (TDC + Pasivo) |
| `2.4.0.1.9` → Movimiento **2, 3, 4, 5** | `1013634968`, que tiene 10 movimientos |
| `2.4.0.1.9.exit` → *nueva fecha* y *finalizar* | `1013634960` tras «No encuentro» |
| `2.4.1` → Formulario PQR | ya se llega a `2.4.1`; falta pulsar el botón |

### 3.2 · Necesitan provocar un fallo (7)

`2.4.0.1.4.error`, `2.4.0.1.8.error`, `2.4.0.1.10.pqr`, `2.4.0.1.16.1.pqr`,
`2.4.0.1.17.1.pqr` — se alcanzan **parando el servicio `trx`** en el turno correspondiente,
técnica ya probada con los dos bloqueos.

`2.4.0.pqr_recurrencia` — requiere un cliente con gestión reciente en Salesforce.

### 3.3 · Verificadas a mano pero sin captura (2)

`2.4.0.1.20.2` (mensaje de cierre del bucle) y su salida. Se comprobaron por UI al
implementarlas, pero **ninguna herramienta las cubre**: es justo lo que F4 debe blindar.

### 3.4 · Un caso que merece mirarse (1)

```
2.4.0.1 [Continuar] -> 2.4.0.1.1     (paso NUNCA renderizado)
```

`2.4.0.1` es el paso de la recurrencia. Nunca se ha renderizado en ninguna captura, pero
**tampoco está en la lista de gates incondicionales**. O es una arista muerta que la
heurística no detecta, o hay un camino que nadie ha recorrido. Hay que resolverlo antes de dar
la cobertura por buena.

---

## 4 · Cómo se usa

```bash
# capturar (POR LOTES: el entorno corta los procesos largos)
python3 -u capturar_tramo_pablo.py Q1,Q2,Q3
python3 -u capturar_tramo_luis.py

# medir: suma todas las capturas que encuentre
python3 cobertura_txnr.py
python3 cobertura_txnr.py captura_a.json captura_b.json
```

El medidor no necesita ejecutar nada: analiza capturas. Así que cualquier recorrido nuevo
—venga de donde venga— suma cobertura sin tocar la herramienta.

---

## 5 · Nota sobre el entorno

Los 15 recorridos de mi tramo **no se pudieron capturar de una vez**: el entorno mata los
procesos cada 3-4 minutos. En lotes de tres sí sobreviven, y por eso la herramienta acepta
lotes. Tres recorridos (`Q2`, `Q5`, `Q7`) cayeron en el fallo intermitente del turno de ruteo
y habrá que repetirlos.

Es el mismo problema que viene lastrando toda la jornada, y a estas alturas **merece ticket
propio**: no es razonable que medir la cobertura dependa de que el entorno aguante.
