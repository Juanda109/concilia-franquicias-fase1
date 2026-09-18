# F3 — Contraste recuadro a recuadro: tablero contra el tramo de Luis

**Fecha:** 20/08/2026 · **Fuentes:** capturas del tablero (13/08, `.claude/Roadmap_Pieces`)
contra `literales_tramo_luis.json` (capturado en F2, comportamiento real).

## 1 · Resumen

| Veredicto | Pasos |
|---|---|
| ✅ Coincide literal con el tablero | **7** |
| ⚠️ Coincide en fondo, difiere en forma | **4** |
| ❌ Falta contenido que el tablero pide | **1** |
| ❌ Regla de negocio del tablero no implementada | **1** |
| ➖ El tablero no lo especifica | 3 |

**Lo bueno primero**: los textos largos y jurídicamente delicados están **calcados**. El de
`presencial` (`.19.1`), que cita el Régimen de Protección al Consumidor Financiero, coincide
**palabra por palabra** con el tablero. Igual el de compra pendiente (`.12.exit`).

## 2 · Coincidencias exactas (7)

| Paso | Comprobado |
|---|---|
| `2.4.0.1.12.exit` | texto de compra pendiente, íntegro |
| `2.4.0.1.13` | pregunta + los dos botones |
| `2.4.0.1.15` | pregunta + «Sí, bloquear **definitivamente**» / «No, bloquear **temporalmente**» |
| `2.4.0.1.16` | apagado temporal, con la advertencia de que la revisión finaliza |
| `2.4.0.1.17` | «Al continuar, tu tarjeta actual quedará bloqueada definitivamente…» |
| `2.4.0.1.19.1` | **presencial**, párrafo completo del Régimen de Protección al Consumidor |
| `2.4.0.1.20` | devolución automática, con los días hábiles parametrizados |

## 3 · Hallazgos

### F3-01 · `2.4.0.1.19.2` — falta la viñeta del **monto devuelto** ❌

El tablero pide **dos** líneas de detalle:

```
Detalle del reembolso:
* Transacción:    $[valor] el [DD/MM/AAAA]
* Monto devuelto: $[valor] el [DD/MM/AAAA del reverso]      <- NO SE ENTREGA
```

Lo que entrega el bot:

```
**Detalle del reembolso:** • Transacción: $99.000 el 06/08/2026
```

Falta **«Monto devuelto»** por completo. Y es, con diferencia, el dato que más le importa al
cliente en ese punto: *cuánto* se le devolvió y *cuándo*. El importe del reverso puede no
coincidir con el de la compra (reversos parciales), así que no es redundante con la primera
línea.

### F3-02 · `2.4.0.1.19.2` — Markdown crudo en pantalla ⚠️

Los `**` viajan **literales**: el cliente lee `**Detalle del reembolso:**`. El tablero lo
pinta en negrita y **ningún otro mensaje del flujo usa Markdown**, así que o el front lo
interpreta —y habría que confirmarlo— o hay que quitar los asteriscos.

### F3-03 · La regla de los **7 días** no está implementada ❌

El tablero es explícito en dos sitios:

> rombo: **«¿Movimiento pendiente en tarjeta de crédito?»**
> arista: **«No, o ya superó los 7 días la compra con TC»** → sigue a investigación
> nota: *«Conexión con sistema para verificar transacciones en estado pendiente (hasta 7 días
> para el cruce) Tx MC30»*

El código:

```python
pendiente_tdc = (origin_flag == "TDC") and (response_cf == "pendiente")
```

**No hay ninguna comprobación de días.** Consecuencia: una compra que lleve pendiente **más
de 7 días** sigue desviando al cliente a la salida `.12.exit` («vuelve más adelante»), cuando
el tablero dice que a partir de ese plazo **debe entrar a investigación**. El cliente queda
en un bucle: vuelve, sigue pendiente, se le vuelve a despedir.

Esto enlaza con el `[HUECO]` que el verificador de contrato ya venía avisando: **el detalle
no trae fecha de cruce/contabilización**; `dateOper` es la fecha de la operación, no la del
cruce. Es decir, **hoy la regla no es implementable con el dato disponible** — hace falta
pedirle a Nicolás el campo, o confirmar cuál de los que ya llegan sirve.

### F3-04 · `2.4.0.1.19.pqr` — sin tildes ⚠️

| | |
|---|---|
| Tablero | «Con la **información** disponible… necesita una **revisión**…» |
| Bot | «Con la **informacion** disponible… necesita una **revision**…» |

Llama la atención porque el resto de su tramo **sí** está acentuado (`investigación`,
`¿quieres continuar…?`). Es el único mensaje suyo que se quedó sin tildes.

### F3-05 · `2.4.0.1.20.1` — sin signo de apertura ni tildes ⚠️

| | |
|---|---|
| Tablero | rombo «¿Desea reportar otra tx?» |
| Bot | «Deseas reportar la siguiente transaccion?» |

Debería ser **«¿Deseas reportar la siguiente transacción?»**.

### F3-06 · `2.4.0.1.12.exit` cierra con botón, el tablero con final directo ➖

El tablero dibuja un terminal rojo («Finaliza interacción con el agente»); el bot ofrece
`['Terminar']` y pasa por satisfacción. Como el propio tablero indica que la salida lleva los
mensajes de feedback, **lo doy por conforme**; se anota por trazabilidad.

## 4 · Lo que el tablero no especifica (3)

`2.4.0.1.16.2`, `2.4.0.1.17.2` y `2.4.0.1.18` tienen texto en el tablero, pero sin botones
dibujados; el bot añade `Continuar` / `Terminar` para poder avanzar. Razonable y no se
considera divergencia.

## 5 · Para Luis, ordenado por lo que afecta al cliente

| | Hallazgo | Coste |
|---|---|---|
| 🔴 | **F3-03** regla de 7 días ausente: el pendiente desvía siempre | necesita dato de Data |
| 🔴 | **F3-01** falta la viñeta «Monto devuelto» del reembolso | media |
| 🟠 | **F3-02** `**` literales en pantalla | 1 línea |
| 🟡 | **F3-04**, **F3-05** tildes y signos de apertura | 2 líneas |


---

## 6 · Evolución de los hallazgos (actualizado 21/08)

Este documento es la foto del 20/08. Tres hallazgos evolucionaron después y conviene leerlos
con su corrección:

- **F3-01 (falta «Monto devuelto») — NO era defecto de código.** El código sí construye la
  viñeta, condicionada a `dateReverse`; era mi fixture el que no traía el campo. Añadido, la
  viñeta sale. Y Fabián confirmó que el reverso es siempre por el total, así que copiar el
  importe es correcto.
- **F3-02 (Markdown) y F3-04/F3-05 (tildes y signos)** — corregidos y verificados; el front
  no interpreta Markdown (confirmado por Fabián).
- **F3-03 (regla de los 7 días) — RESUELTO sin código.** Fabián aclaró que el estado
  *pendiente* ya encierra la ventana de 7 días: pasado el cruce, el ASO deja de marcarla y el
  cliente entra a investigación solo. La señal además es `observations`, no
  `responseOperati` (corregido en código y en `ESPECIFICACION_FLUJO.md`).
