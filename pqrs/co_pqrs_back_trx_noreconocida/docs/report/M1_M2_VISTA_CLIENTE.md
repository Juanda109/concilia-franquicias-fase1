# Evidencia M1/M2 — lo que ve el cliente en Descripción · Valor · Fecha

**Fecha:** 27/08/2026 · **Rama:** `fix/descripcion-comercio-listado`
**Data:** el movimiento REAL capturado en dev (tarjeta de pruebas `…9784`, 14/04/2026),
reproducido en el stack local byte a byte (fixture = la respuesta literal de dev).

## El problema (M1 — evidencia del estado actual)

El ASO real entrega `descProvision: "ACEPTADA"` (un **estado**) y
`placeOperation: "ASCR"` (un **código**). El nombre del comercio viaja dentro de
`observations`, 5º bloque: `EDS COMBUS LLANOS`. Con el mapeo desplegado, el cliente ve:

```
Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:
  ▶ ACEPTADA — $96.930 14/04/2026          ← un ESTADO como descripción
  ▶ No encuentro la transacción en este listado.

Confirma los datos de la compra seleccionada.
  • ACEPTADA                                ← ídem en la confirmación
  • Valor: $96.930
  • Fecha: 14/04/2026
  • Visa Clásica terminado en *9784
```

## El arreglo (M2 — implementado y verificado)

1. **Servicio** — la descripción sale del **5º bloque de `observations`** (patrón
   garantizado por Jessica); la cascada anterior queda de respaldo para payloads
   sin bloques. 4 tests contra el payload real.
2. **Agente** — la confirmación repite **lo que el cliente vio y pulsó** en el
   listado (antes prefería el `descProvision` del detalle).

```
Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:
  ▶ EDS COMBUS LLANOS — $96.930 14/04/2026   ← el comercio real
  ▶ No encuentro la transacción en este listado.

Confirma los datos de la compra seleccionada.
  • EDS COMBUS LLANOS
  • Valor: $96.930
  • Fecha: 14/04/2026
  • Visa Clásica terminado en *9784
```

*(La fecha ya se mostraba bien: el label la reformatea a DD/MM/AAAA aunque el ASO
la entregue en ISO.)*

## Verificación

- Recorrido E2E por chat en local (listado + confirmación): capturas de arriba, literales.
- `mensajes` 60/60 · tests del servicio 4/4 nuevos (payload real).
- Reproducible por cualquiera: cliente `1013634998` en el stack local.

## Notas para el equipo

1. **El arreglo de Fabián del "servicio equivocado" no está en dev** (la punta sigue
   en `9083c25`) — recordarle empujarlo para poder integrar ambos cambios.
2. **Hueco local nuevo e independiente**: el agente `9083c25` exige la subida de
   nivel y el simulador local no tiene fixtures de `user-status`/`order-chanel`
   por perfil → en local todo bloqueo cae a `.17.1.denied` hasta que se alineen
   esos fixtures (tarea aparte; no afecta a dev).
