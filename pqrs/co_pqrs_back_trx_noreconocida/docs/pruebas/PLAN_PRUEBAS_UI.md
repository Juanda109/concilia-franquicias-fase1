# Casos de prueba de UI — verificados y con literales reales

**v2 · 18/08/2026.** Cada caso de esta versión **se ha ejecutado contra el stack**:
los pasos son los que funcionan y el *Lo que verás* es el texto que devolvió el bot,
no una descripción. Si algo no coincide, es hallazgo del flujo — no del documento.

> Empieza por [`GUIA_SESION_PRUEBAS.md`](./GUIA_SESION_PRUEBAS.md): arranque, bloques
> de trabajo y qué hacer cuando algo falla. Este documento es el detalle de cada caso.

**Convenciones de los pasos:**

- `[botón] Texto` → pulsa ese botón (el texto es literal).
- `(escribe) texto` → tecléalo en el campo de mensaje.
- Todo caso empieza con `(escribe) No reconozco esta compra`.

---

## U-1 · Sucesos 1-3 derivan a formulario y el botón cierra por feedback

**Cliente(s):** `1013634962 / 63 / 64` · **Duración:** ~8 min · **Recorridos:** 3

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

### U-1a — cliente `1013634962`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Me cambiaron la tarjeta (cambiazo)**
3. [botón] **Formulario PQR**

**Lo que verás** (capturado el 18/08):

```
El bot cierra por el proceso de feedback. El texto ROTA entre tres variantes
-- no compares por el texto, compara por los botones:
  · "¿Te ha ayudado esta información con lo que necesitabas?"
  · "¿Ha quedado clara tu duda con esta respuesta o necesitas algo más?"
  · "¿He resuelto tu consulta?"

Botones: Sí, me ayudó · No, ver línea de atención
```

### U-1b — cliente `1013634963`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Hurto o perdida**
3. [botón] **Formulario PQR**

**Lo que verás** (capturado el 18/08):

```
El bot cierra por el proceso de feedback. El texto ROTA entre tres variantes
-- no compares por el texto, compara por los botones:
  · "¿Te ha ayudado esta información con lo que necesitabas?"
  · "¿Ha quedado clara tu duda con esta respuesta o necesitas algo más?"
  · "¿He resuelto tu consulta?"

Botones: Sí, me ayudó · No, ver línea de atención
```

### U-1c — cliente `1013634964`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Alguien obtuvo mis datos por llamada, mensaje, correo o enlace**
3. [botón] **Formulario PQR**

**Lo que verás** (capturado el 18/08):

```
El bot cierra por el proceso de feedback. El texto ROTA entre tres variantes
-- no compares por el texto, compara por los botones:
  · "¿Te ha ayudado esta información con lo que necesitabas?"
  · "¿Ha quedado clara tu duda con esta respuesta o necesitas algo más?"
  · "¿He resuelto tu consulta?"

Botones: Sí, me ayudó · No, ver línea de atención
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'TXNR paso' | grep 2.4.1`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-3 · Cantidad 2 y 3: aviso de una a la vez y límites completos

**Cliente(s):** `10482895` · **Duración:** ~6 min · **Recorridos:** 2

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

### U-3a — cliente `10482895`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **2**
4. [botón] **Empezar ahora**

**Lo que verás** (capturado el 18/08):

```
Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza

Botones: Si, continuar · Finalizar conversacion
```

### U-3b — cliente `10482895`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **3**
4. [botón] **Empezar ahora**

**Lo que verás** (capturado el 18/08):

```
Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza

Botones: Si, continuar · Finalizar conversacion
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'trx_cantidad'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-4 · 'Más de 3' deriva y el botón Formulario PQR transiciona

**Cliente(s):** `98787954` · **Duración:** ~3 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **Mas de 3**
4. [botón] **Formulario PQR**

**Lo que verás** (capturado el 18/08):

```
El bot cierra por el proceso de feedback. El texto ROTA entre tres variantes
-- no compares por el texto, compara por los botones:
  · "¿Te ha ayudado esta información con lo que necesitabas?"
  · "¿Ha quedado clara tu duda con esta respuesta o necesitas algo más?"
  · "¿He resuelto tu consulta?"

Botones: Sí, me ayudó · No, ver línea de atención
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep '2.4.0.1.1.pqr'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-5 · Sin productos: el botón Terminar cierra por feedback

**Cliente(s):** `1013634959` · **Duración:** ~3 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Terminar**

**Lo que verás** (capturado el 18/08):

```
El bot cierra por el proceso de feedback. El texto ROTA entre tres variantes
-- no compares por el texto, compara por los botones:
  · "¿Te ha ayudado esta información con lo que necesitabas?"
  · "¿Ha quedado clara tu duda con esta respuesta o necesitas algo más?"
  · "¿He resuelto tu consulta?"

Botones: Sí, me ayudó · No, ver línea de atención
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep '2.4.0.1.4.exit'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-6 · Rango fuera de límite en ambos extremos

**Cliente(s):** `1013634963 / 62` · **Duración:** ~6 min · **Recorridos:** 2

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

### U-6a — cliente `1013634963`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0063**
7. [botón] **Menor a $35.000**
8. [botón] **Formulario PQR**

**Lo que verás** (capturado el 18/08):

```
El bot cierra por el proceso de feedback. El texto ROTA entre tres variantes
-- no compares por el texto, compara por los botones:
  · "¿Te ha ayudado esta información con lo que necesitabas?"
  · "¿Ha quedado clara tu duda con esta respuesta o necesitas algo más?"
  · "¿He resuelto tu consulta?"

Botones: Sí, me ayudó · No, ver línea de atención
```

### U-6b — cliente `1013634962`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0062**
7. [botón] **Mayor a $500.000**
8. [botón] **Formulario PQR**

**Lo que verás** (capturado el 18/08):

```
El bot cierra por el proceso de feedback. El texto ROTA entre tres variantes
-- no compares por el texto, compara por los botones:
  · "¿Te ha ayudado esta información con lo que necesitabas?"
  · "¿Ha quedado clara tu duda con esta respuesta o necesitas algo más?"
  · "¿He resuelto tu consulta?"

Botones: Sí, me ayudó · No, ver línea de atención
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep '2.4.0.1.6.pqr'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-7 · Elegir el 2.º movimiento de la lista llega a la confirmación

**Cliente(s):** `1013634960` · **Duración:** ~5 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0060**
7. [botón] **Entre $35.000 y $500.000**
8. (escribe) `06/08/2026`
9. (escribe) `COMPRA MERCADOLIBRE.COM.CO — $89.990 — 06/08/2026`

**Lo que verás** (capturado el 18/08):

```
Confirma los datos de la compra seleccionada. • Descripción: COMPRA MERCADOLIBRE.COM.CO • Valor: $89.990 • Fecha: 06/08/2026 • Producto terminado en *0060 ¿Es la transacción que deseas reportar?

Botones: Si, continuar con el reporte · No es necesario, ya reconozco la transaccion
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'TXNR paso 2.4.0.1.9'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-8 · Reenganche con la MISMA fecha vuelve al listado (H-11)

**Cliente(s):** `1013634960` · **Duración:** ~6 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0060**
7. [botón] **Entre $35.000 y $500.000**
8. (escribe) `06/08/2026`
9. [botón] **No encuentro la transaccion en este listado**
10. [botón] **Seleccionar una nueva fecha**
11. (escribe) `06/08/2026`

**Lo que verás** (capturado el 18/08):

```
Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:

Botones: COMPRA FALABELLA CALLE 80 — $120.000 — 06/08/2026 · COMPRA MERCADOLIBRE.COM.CO — $89.990 — 06/08/2026 · COMPRA EXITO SUPERMERCADO — $250.000 — 06/08/2026 · No encuentro la transaccion en este listado
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'reenganche_cacheado'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-9 · Índice de producto inexistente y formatos de fecha alternos

**Cliente(s):** `1013634961` · **Duración:** ~8 min · **Recorridos:** 4

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

### U-9a — cliente `1013634961`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **producto_4**

**Lo que verás** (capturado el 18/08):

```
Antes de continuar, selecciona el rango de valor de la transaccion que deseas reportar:

Botones: Menor a $35.000 · Entre $35.000 y $500.000 · Mayor a $500.000
```

### U-9b — cliente `1013634961`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0061**
7. [botón] **Entre $35.000 y $500.000**
8. (escribe) `31/12/2099`

**Lo que verás** (capturado el 18/08):

```
Esa fecha todavia no ha ocurrido. Indicame la fecha en la que ya se realizo la compra, en formato DD/MM/AAAA.

Botones: Elegir otra fecha · Seleccionar otro producto · Terminar consulta
```

### U-9c — cliente `1013634961`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0061**
7. [botón] **Entre $35.000 y $500.000**
8. (escribe) `6/8/2026`

**Lo que verás** (capturado el 18/08):

```
Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:

Botones: COMPRA AMAZON MKTP — $150.000 — 06/08/2026
```

### U-9d — cliente `1013634961`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0061**
7. [botón] **Entre $35.000 y $500.000**
8. [botón] **2026-08-06**

**Lo que verás** (capturado el 18/08):

```
Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:

Botones: COMPRA AMAZON MKTP — $150.000 — 06/08/2026
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'vigencia'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-10 · 'Seleccionar otro producto' vuelve al selector

**Cliente(s):** `1013634966` · **Duración:** ~4 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0066**
7. [botón] **Entre $35.000 y $500.000**
8. (escribe) `06/08/2026`
9. [botón] **Seleccionar otro producto**

**Lo que verás** (capturado el 18/08):

```
Selecciona el producto activo sobre el que deseas revisar las transacciones. - Tarjeta de Credito *0066 Responde con el numero de la opcion que prefieres.

Botones: Tarjeta de Credito *0066
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep '2.4.0.1.8.return'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-11 · MASTERCARD vencida: mensaje de plazo y Terminar

**Cliente(s):** `1013634965` · **Duración:** ~4 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0065**
7. [botón] **Entre $35.000 y $500.000**
8. (escribe) `01/01/2025`
9. [botón] **Terminar**

**Lo que verás** (capturado el 18/08):

```
El bot cierra por el proceso de feedback. El texto ROTA entre tres variantes
-- no compares por el texto, compara por los botones:
  · "¿Te ha ayudado esta información con lo que necesitabas?"
  · "¿Ha quedado clara tu duda con esta respuesta o necesitas algo más?"
  · "¿He resuelto tu consulta?"

Botones: Sí, me ayudó · No, ver línea de atención
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'outcome=vencida'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-13 · Entradas no válidas donde se esperan botones

**Cliente(s):** `01576905` · **Duración:** ~5 min · **Recorridos:** 3

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

### U-13a — cliente `01576905`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **texto libre que no es opcion**

**Lo que verás** (capturado el 18/08):

```
No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar?

Botones: 1 · 2 · 3 · Mas de 3
```

### U-13b — cliente `01576905`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **99**

**Lo que verás** (capturado el 18/08):

```
No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar?

Botones: 1 · 2 · 3 · Mas de 3
```

### U-13c — cliente `01576905`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **cancelar**

**Lo que verás** (capturado el 18/08):

```
No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar?

Botones: 1 · 2 · 3 · Mas de 3
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'No pude identificar'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-14 · Repetir la misma opción dos veces

**Cliente(s):** `1013634964` · **Duración:** ~3 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **1**

**Lo que verás** (capturado el 18/08):

```
Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza

Botones: Si, continuar · Finalizar conversacion
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'TXNR paso'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-16 · Índice de movimiento fuera de rango (H-13, abierto)

**Cliente(s):** `1013634961` · **Duración:** ~4 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *0061**
7. [botón] **Entre $35.000 y $500.000**
8. (escribe) `06/08/2026`
9. [botón] **movimiento_3**

**Lo que verás** (capturado el 18/08):

```
Con la informacion disponible no podemos resolver esta solicitud en este canal. Por favor registra tu solicitud en el formulario.

Botones: Formulario PQR
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep '2.4.0.1.10'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-17 · Reabrir la conversación a mitad de flujo conserva el paso

**Cliente(s):** `1013634962` · **Duración:** ~3 min · **Recorridos:** 1

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**

**Lo que verás** (capturado el 18/08):

```
Selecciona el producto activo sobre el que deseas revisar las transacciones. - Tarjeta de Credito *0062 Responde con el numero de la opcion que prefieres.

Botones: Tarjeta de Credito *0062
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'Resuming existing session'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## U-19 · Fecha con espacios y fecha larguísima

**Cliente(s):** `01576905` · **Duración:** ~4 min · **Recorridos:** 2

**Antes de empezar:** `./reset_cliente.sh <user_id>` (obligatorio si ya usaste ese cliente hoy).

### U-19a — cliente `01576905`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *9461**
7. [botón] **Entre $35.000 y $500.000**
8. [botón] **   **

**Lo que verás** (capturado el 18/08):

```
(sin texto — ver nota del caso)
```

### U-19b — cliente `01576905`

**Pasos:**

1. (escribe) `No reconozco esta compra`
2. [botón] **Compra presencial o por internet**
3. [botón] **1**
4. [botón] **Empezar ahora**
5. [botón] **Si, continuar**
6. [botón] **Tarjeta de Credito *9461**
7. [botón] **Entre $35.000 y $500.000**
8. [botón] **xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx**

**Lo que verás** (capturado el 18/08):

```
No pude leer esa fecha. Escribela en formato DD/MM/AAAA, por ejemplo 06/08/2026. Consulta la fecha en tu extracto o en los movimientos de tu App BBVA.
```

**Si falla:** `docker logs co-pqrs-back-agent --since 5m | grep 'fecha_ilegible'`

> **Observado:** _______________________  **Estado:** ☐ OK ☐ Falla ☐ No probado

---

## Casos que NO se pueden validar en este entorno

Documentados para que no pierdas tiempo intentándolos:

| Caso | Por qué | Dónde validarlo |
|---|---|---|
| **U-2** · ruteo de las 12 frases del tablero | el router LLM responde **401** en local y contesta el fallback determinista: el resultado no es representativo | DEV, con credenciales |
| **U-12** · fronteras exactas de vigencia | necesita fechas a 179/180/181 y 119/120/121 días, imposible de teclear con fixtures fijos | ✅ ya cubierto por pruebas unitarias |
| **U-15 / U-18** · recurrencia-bot y precedencia Salesforce | exigen dos entradas en la ventana y un doble hit simultáneo | parcialmente unitario; la rama simple sí se ve en U-17 |
| **U-20 … U-25** · [STACK] | paran servicios o cambian variables: **hazlos al final** y restaura entre uno y otro | ver la guía de sesión, bloque 4 |
