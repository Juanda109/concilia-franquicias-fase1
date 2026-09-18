# F2 — Recorrido de las 26 transiciones del tramo de Luis

**Fecha:** 20/08/2026 · **Herramienta:** `docs/pruebas/capturar_tramo_luis.py`
**Datos crudos:** `captura_tramo_luis.json` · **Literales por paso:** `literales_tramo_luis.json`

## 1 · Resultado

| | Antes de F1/F2 | Ahora |
|---|---|---|
| Desenlaces alcanzables por UI | 2 de 4 | **4 de 4** |
| Pasos del tramo alcanzados | 7 de 20 | **16 de 20** |
| Transiciones cubiertas | — | **22 de 26** |
| Filas del Excel con evidencia | 1 de 26 | pendiente de F5 |

**Las 4 transiciones restantes no son cubribles, y no por falta de pruebas** (§3).

## 2 · Los 13 recorridos

| Id | Cliente | Cubre |
|---|---|---|
| P1 | `1013634970` | bloqueo definitivo → devolución → cierre |
| P2 | `1013634961` | **bucle**: reportar la 2ª transacción (`.20.1` → vuelta a `.3`) |
| P2b | `1013634970` | `.20.1` → no reportar la siguiente |
| P3 | `1013634972` | bloqueo **temporal** completo |
| P4 | `1013634962` | salida en `.13` (no inicia investigación) |
| P5 | `1013634963` | salida en `.16` (no apaga la tarjeta) |
| P6 | `1013634960` | salida en `.17` (no bloquea definitivamente) |
| P7 | `1013634971` | desenlace **presencial** (`.19.1`) |
| P8 | `1013634972` | desenlace **reversado** + guía paso a paso (`.19.2`, `.19.2.guia`) |
| P9 | `1013634960` | desenlace **PQR** (`.19.pqr`) |
| P10 | `1013634972` | reversado, salida directa sin guía |
| P11 | `1013634964` | gate `validar_pendiente_trx` → `.12.exit` → Terminar |
| P12/P13 | `1013634970` / `…72` | **bloqueo que falla** → `.17.1.pqr` / `.16.1.pqr` |

P12 y P13 se provocan parando el servicio `trx` en el turno del bloqueo y
restaurándolo después. Texto obtenido, idéntico en ambos salvo la palabra:

> *"No hemos podido completar el bloqueo permanente / temporal. Por favor realiza el
> siguiente formulario PQR."*

## 3 · Las 4 transiciones no cubribles: son declaraciones muertas

```
2.4.0.1.12    --[Continuar]--> 2.4.0.1.13     (accion validar_pendiente_trx)
2.4.0.1.16.1  --[Continuar]--> 2.4.0.1.16.2   (accion bloqueo_temporal_trx)
2.4.0.1.17.1  --[Continuar]--> 2.4.0.1.17.2   (accion bloqueo_permanente_trx)
2.4.0.1.19    --[Continuar]--> 2.4.0.1.20     (accion validar_investigacion_trx)
```

Los cuatro pasos llevan una **acción** que reescribe `current_step` y devuelve, así que el
motor nunca llega a pintar su pregunta ni su botón. El destino **sí se alcanza** (`.13`,
`.16.2`, `.17.2` y `.20` están todos entre los 16 visitados): lo que no existe es el botón.

**Propuesta para Luis**: quitar esas cuatro `options` del YAML o marcarlas con un comentario.
Hoy sugieren una interacción que no puede ocurrir, y hacen que cualquier medida de cobertura
por aristas dé un 85 % que nunca podrá llegar a 100.

## 4 · Lo que corrigió la realidad sobre el papel

Tres recorridos escritos desde el YAML **no sobrevivieron al primer contacto**, y cada
corrección es información:

1. **`2.4.0.1.20.1` sólo existe si se pidieron 2 o 3 transacciones.** Con "1", tras la
   devolución el flujo va directo a satisfacción. Es correcto —no hay siguiente que
   reportar— pero significa que **el bucle sólo se prueba pidiendo 2**.
2. **El cliente `1013634964` tiene una compra pendiente** y se desvía a `.12.exit` antes de
   la investigación. El gate `validar_pendiente_trx` funciona; era el recorrido el que
   asumía que no.
3. **Del `.20` al `.20.1` hacen falta tres "Continuar"**, no dos: `.17.2 → .18 → .20 → .20.1`.

## 5 · Dos defectos de copy encontrados

### 5.1 · Markdown crudo en pantalla (`2.4.0.1.19.2`)

```
Te confirmamos que la compra por $99.000 ya fue devuelta a tu Tarjeta de Credito.
**Detalle del reembolso:**  • Transacción: $99.000 el 06/08/2026
```

Los `**` van **literales** en el texto. El tablero pinta *Detalle del reembolso* en negrita,
así que la intención es clara, pero el bot entrega asteriscos. Si el front no interpreta
Markdown —y el resto del flujo no lo usa— el cliente ve `**Detalle del reembolso:**`.

### 5.2 · `2.4.0.1.20.1` sin signos ni tildes

```
Deseas reportar la siguiente transaccion?
```

Debería ser **«¿Deseas reportar la siguiente transacción?»**. Llama la atención porque Luis
sí acentuó el resto de su tramo (`investigación`, `¿quieres continuar…?`): éste se quedó
atrás.

## 6 · Literales capturados

Los 16 pasos alcanzados quedan con su **texto literal y sus botones** en
`literales_tramo_luis.json`. Ése es el material que alimenta:

- **F3** — contraste recuadro a recuadro contra el tablero;
- **F5** — columnas `F` (esperado, del tablero) y `G` (obtenido, literal) del Excel.


> **Actualización 21/08:** los dos defectos de copy de §5 quedaron corregidos y verificados
> (el front no interpreta Markdown — confirmado por Fabián — y `.20.1` lleva ya signo y
> tilde). Las cuatro `options` muertas de §3 pasaron a ser **diez** al medir el flujo
> completo; están excluidas del denominador del medidor (`cobertura_txnr.py`).
