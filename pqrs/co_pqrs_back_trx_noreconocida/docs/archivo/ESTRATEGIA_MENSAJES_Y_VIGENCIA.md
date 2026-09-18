# Estrategia — exactitud de los mensajes dinámicos y regla de vigencia

**Fecha:** 14/08/2026 · Responde a las dos peticiones de Fabián: (A) verificar que **todos**
los mensajes dinámicos del tramo son exactos, y (B) fijar **VISA 180 / MASTER 120**.

---

## Parte B — la vigencia (se responde primero: ya está y cierra una decisión abierta)

### Lo que hay hoy en código

```python
if "MASTER" in (card_brand or "").upper():
    limite = VIGENCIA_MASTER_DIAS   # 120
else:
    limite = VIGENCIA_VISA_DIAS     # 180
return dias > limite
```

**Es exactamente lo que Fabián pide**, y además parametrizado por entorno
(`VIGENCIA_VISA_DIAS` / `VIGENCIA_MASTER_DIAS`) en el agente y en el servicio, así que un
cambio de plazo no toca código.

**Esto cierra una decisión que llevaba abierta desde el 11/08**: el tablero distinguía
VISA nacional 180 / interoperable 120 / internacional 120, y no sabíamos de qué campo
salía el ámbito. Fabián zanja: **sólo marca**. Se cierra el punto 3 de
`DECISIONES_NEGOCIO.md` y desaparece la pregunta a Data sobre el ámbito.

### El hueco que la regla deja abierto (medido, no teórico)

`else` significa **180 días para todo lo que no diga MASTER**. Comprobado:

| `card_brand` | 150 días | 190 días |
|---|---|---|
| `VISA` | pasa | vence |
| `MASTERCARD` / `MASTER` | **vence** | vence |
| `AMEX`, `DINERS` | pasa | vence |
| `""`, `None` | pasa | vence |
| `Cuenta de Ahorros` | pasa | vence |

Es decir: **un producto sin marca reconocida recibe el plazo más largo**. Hoy no se nota
porque los 12 clientes de la matriz son VISA o MASTERCARD, pero con cartera real (AMEX,
Diners, o un `card_brand` vacío por un dato incompleto de ADA) el bot aceptaría
reclamaciones fuera de plazo.

**Pregunta concreta para Fabián** (no bloquea, pero conviene resolverla antes de OKD):
lo que no es VISA ni MASTER, ¿qué plazo tiene? Tres opciones razonables:
- **(a) 120 días** — el más conservador: por defecto el plazo corto.
- **(b) 180 días** — lo de hoy: por defecto el largo.
- **(c) sin plazo** — si son productos sin franquicia (cuentas), como se decidió en su día
  para el pasivo.

Mi recomendación: **(a)**, y que las cuentas/pasivo se traten aparte por `origin_flag`,
no por marca — el dato ya viaja en el contrato.

### Verificación que se añade (cierra la laguna de pruebas)

Las fronteras exactas **nunca se han probado**. Casos nuevos, medibles con fecha relativa
para que no caduquen:

| Caso | Marca | Antigüedad | Esperado |
|---|---|---|---|
| V-1 | VISA | 179 días | pasa |
| V-2 | VISA | **180 exactos** | pasa (`>` es estricto) |
| V-3 | VISA | 181 días | vence |
| V-4 | MASTERCARD | 119 días | pasa |
| V-5 | MASTERCARD | **120 exactos** | pasa |
| V-6 | MASTERCARD | 121 días | vence |
| V-7 | banda 120–180 (150 días) | VISA pasa · MASTER vence | el caso que enseña la diferencia |
| V-8 | marca desconocida / vacía | 150 días | **según decida Fabián** |

Los V-1..V-7 se fijan como prueba unitaria (deterministas, sin red) **y** un E2E por UI
para la banda diferencial. El V-8 queda pendiente de la decisión.

---

## Parte A — exactitud de los mensajes dinámicos

### Inventario cerrado (4 puntos, 6 claves)

Todo lo que el cliente ve **con datos suyos dentro** en mi tramo:

| Paso | Clave | Qué compone | Fuente del dato |
|---|---|---|---|
| `2.4.0.1.5` | `dynamic_prompt` + `dynamic_option_labels` | selector de productos: tipo + últimos 4 | `trx_products_result[].last_four`, `commercial_product_desc` |
| `2.4.0.1.7` | `dynamic_prompt` | reprompt de fecha ilegible | — (texto fijo condicional) |
| `2.4.0.1.9` | `dynamic_prompt` + `dynamic_option_labels` | listado: descripción — valor — fecha | `trx_movimientos_result[]` |
| `2.4.0.1.11` | `dynamic_prompt` | confirmación: viñetas con descripción, valor, fecha, producto | movimiento elegido + producto |

### Por qué esta área merece la pregunta de Fabián

**De los 10 hallazgos de la semana, 3 salieron justo aquí** — y ninguno lo detectaba la
suite de botones:

- **H-03**: la fecha salía en ISO (`2026-08-06`) donde el tablero pide `DD/MM/AAAA`.
- **H-07**: el reprompt de fecha se quedaba pegado y reaparecía cuando no tocaba.
- **H-08**: la confirmación mostraba **`*XXXX` literal** en vez de los últimos 4 reales.

El patrón común: **el mensaje se construye leyendo una clave que no es la que el servicio
publica** (`last_four_pan_id` vs `last_four`), y como el texto "se ve razonable", pasa.

### Las cuatro dimensiones a verificar por mensaje

Para cada uno de los 4 puntos, y por cada campo que muestra:

1. **Procedencia** — el valor sale de la clave correcta del payload, no de una parecida
   ni de un identificador de repuesto (la trampa de H-08).
2. **Formato** — el que pide el tablero: fechas `DD/MM/AAAA`, importes `$120.000`,
   producto `*0060` (nunca completo), viñetas donde el tablero las pinta.
3. **Degradación** — con el dato **ausente o vacío**: nunca un placeholder crudo
   (`XXXX`, `None`, `""`), nunca un identificador entero, nunca una cadena rota.
4. **Ciclo de vida** — el mensaje **se limpia** cuando deja de aplicar (la trampa de
   H-07): tras un reenganche, tras cambiar de producto o fecha, y en la 2ª/3ª
   transacción del bucle.

### Cómo se verifica: comparación contra la fuente, no contra un texto fijo

Un verificador nuevo, `verificar_mensajes.py`, hermano de `verificar_contrato.py`:

- recorre el camino feliz y, **en cada uno de los 4 puntos**, lee a la vez lo **renderizado**
  (por HTTP) y el **payload de origen** (de `captured_data`);
- comprueba que cada campo mostrado **coincide con su fuente** y respeta el formato;
- fuerza la degradación con un payload sin `last_four` / sin `descripcion` / sin fecha, y
  comprueba que no se cuela ningún crudo;
- comprueba el ciclo de vida repitiendo fecha y producto tras un reenganche.

**La ventaja de comparar contra la fuente y no contra un literal:** un cambio de copy
autorizado no rompe la prueba, pero un dato que se muestra de la clave equivocada sí. Es
justo el fallo que se nos escapó tres veces.

### Verificación cruzada contra el tablero (lo que ningún script puede juzgar)

Los formatos y las viñetas se contrastan **a ojo** contra las capturas del 13/08, una vez,
y el resultado se congela como literal esperado en el protocolo. Eso lo hace un humano —
va en la pasada de UI, no en el verificador.

---

## Plan de ejecución

| # | Trabajo | Estimación |
|---|---|---|
| 1 | Pruebas unitarias de vigencia V-1..V-7 (fronteras exactas, fecha relativa) | 30 min |
| 2 | `verificar_mensajes.py`: procedencia + formato en los 4 puntos | 1,5 h |
| 3 | Degradación: payloads incompletos en los 4 puntos | 45 min |
| 4 | Ciclo de vida: reenganches y 2ª transacción del bucle | 45 min |
| 5 | Cotejo visual contra el tablero + congelar literales en el protocolo | 30 min |
| 6 | Filas nuevas en el Excel y en el documento único; cerrar decisión 3 | 30 min |

**Total ≈ medio día.** Nada bloquea: V-8 (marca desconocida) queda parametrizado y se
ajusta con una línea cuando Fabián decida.

## Qué responder a Fabián ahora

1. **Vigencia**: ya es VISA 180 / MASTER 120, parametrizado por entorno; su confirmación
   **cierra** la duda del ámbito que veníamos arrastrando. Falta que decida el plazo de lo
   que no es ni VISA ni MASTER — hoy recibe 180 por defecto.
2. **Mensajes dinámicos**: son 4 puntos con datos del cliente. **No están verificados de
   forma sistemática**: los hemos ido corrigiendo a golpes (3 de los 10 hallazgos de la
   semana salieron ahí). Esta estrategia los cubre en cuatro dimensiones —procedencia,
   formato, degradación y ciclo de vida— con un verificador que compara contra la fuente,
   no contra el texto.
