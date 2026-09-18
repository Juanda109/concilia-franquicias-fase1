# F3 — Cobertura completa del flujo TXNR

**Fecha:** 21/08/2026 · Tercera fase del `PLAN_EVALUACION_PRE_IMAGENES.md`.

```
PASOS   39/48 renderizados
ARISTAS 65/65 cubiertas (100%)   [10 muertas excluidas del denominador]
SIN PISAR (0)
```

De **45/65 (69 %)** al empezar a **65/65**. Los 9 pasos que no se renderizan son exactamente
los gates que reescriben `current_step`: por eso el denominador real son **65** aristas y no
las 75 declaradas.

---

## 1 · Lo que costó llegar aquí

### 1.1 · La arista fantasma

`2.4.0.1 [Continuar]` no se renderizaba **y tampoco figuraba como muerta**. Dos motivos
encadenados:

1. El gate usa `if step == "2.4.0.1":` con **literal**, y la heurística sólo miraba
   constantes `_TRX_*`.
2. Corregido eso, seguía sin detectarse: las asignaciones a `current_step` están dentro de un
   `if/else` —a 12 espacios, no a 8— y **ambas ramas asignan**, así que el gate es
   incondicional aunque el análisis estático no lo vea.

Se resolvió con un **criterio empírico**, más sólido que leer el código: *si un paso tiene
acción, su destino sí se ha renderizado y él nunca, el gate lo salta siempre.* Exige haber
llegado al destino, así que es evidencia y no suposición.

### 1.2 · Tres aristas sin dato, no sin prueba

`2.4.0.1.5 [Producto 3]`, `[4]` y `[5]`: el selector declara cinco posiciones y **ningún
cliente tenía más de dos productos**. No era un defecto ni un fallo de cobertura — faltaba el
dato. Se sembró el **cliente P** (`1013634973`) con cinco productos, que además ejercita el
selector en su tope.

---

## 2 · Los 24 recorridos dirigidos

`docs/pruebas/capturar_f3.py`, ejecutable **por lotes** (el entorno corta procesos largos).

| Grupo | Recorridos | Qué cubre |
|---|---|---|
| Selector | E4, E14–E16 | Producto 2, 3, 4 y 5 |
| Listado | E5–E8 | Movimiento 2, 3, 4 y 5 |
| Salidas del listado | E9, E10 | `.9.exit` por nueva fecha y por finalizar |
| Sucesos | E11, E20, E21 | `2.4.1`, `2.4.2`, `2.4.3` → formulario |
| Recurrencia | E12 | `2.4.0.pqr_recurrencia` |
| **Fallos de servicio** | E1–E3, E17–E19, E22, E23 | `.4.error`, `.8.error`, `.10.pqr` y los dos bloqueos fallidos |
| Bucle | E13, E24 | `.20.1` → `.3` y el cierre en `.20.2` (28 turnos) |

Los recorridos con fallo **detienen el servicio `trx`** en el turno indicado y lo restauran
después, con `try/finally` para no dejar el entorno roto si algo revienta a mitad.

---

## 3 · Lo que esto confirma

Las rutas que se añadieron para Fabián ya no dependen de una comprobación manual:

| Ruta | Antes | Ahora |
|---|---|---|
| `2.4.0.1.4.error` | verificada a mano una vez | **capturada** (E1, E17) |
| `2.4.0.1.8.error` | verificada a mano una vez | **capturada** (E2, E18) |
| `2.4.0.1.16.1.pqr` | verificada a mano una vez | **capturada** (E22) |
| `2.4.0.1.17.1.pqr` | verificada a mano una vez | **capturada** (E23) |
| `2.4.0.1.20.2` cierre del bucle | verificada a mano una vez | **capturada** (E24) |

---

## 4 · El medidor, ahora

`cobertura_txnr.py` combina tres criterios y **se corrige solo**:

1. **heurística estática** — gates que asignan `current_step` a nivel de bloque;
2. **criterio empírico** — pasos con acción cuyo destino se renderizó y ellos no;
3. **autocorrección** — si una arista marcada como muerta aparece pisada, vuelve al
   denominador y el medidor lo dice.

Y empareja **por etiqueta y, si falla, por posición**, porque el selector y el listado
declaran `Producto 1` / `Movimiento 1` y el cliente ve otra cosa.

> Es la segunda vez que emparejar por texto engaña: la primera dio **4/26** cuando la
> cobertura real era **16/26**. Por eso se lee el `current_step` de OpenSearch.

---

## 5 · Lo que queda para F4 y F5

- **F4** — blindar con verificador automático los tres arreglos de Fabián. La captura
  demuestra que las rutas se recorren; falta que algo **falle** si alguien las rompe.
- **F5** — pasada completa de los cinco verificadores con el stack recién reiniciado.

Y sigue pendiente el riesgo de siempre: el entorno corta los procesos cada 3-4 minutos, y por
eso todo se ejecuta en lotes de dos o tres. **Merece ticket propio**: no es razonable que
medir la cobertura dependa de que aguante.
