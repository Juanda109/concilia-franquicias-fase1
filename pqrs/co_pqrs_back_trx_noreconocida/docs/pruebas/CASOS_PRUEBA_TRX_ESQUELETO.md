# Casos de prueba — flujo trx sobre el esqueleto (para el documento corporativo)

Entorno local (13/08/2026): esqueleto de feature/PQRSdev, simulador ASO y Postgres con la matriz de clientes de CLIENTES_SIMULADOR.md. Fecha con movimientos: 06/08/2026 (los fixtures son absolutos y envejecen).

Bloques reservados 100-122 (ejecutados) y 200-225 (plan de UI, pendientes de pasada manual). Pegar como filas nuevas al final de **Pruebas Integrales**, sin tocar las existentes.

## 100 · Cliente con gestión reciente de la misma tipología (recurrencia Salesforce)

**Cliente:** `1013634958` · **Estatus:** Aprobada

**Pregunta:**
```
No reconozco esta compra → Compra presencial o por internet
```

**Esperada:**
```
Detecta la gestión reciente y deriva al formulario sin más preguntas:
"Encontré una gestión reciente relacionada con una transacción no reconocida..." con botón Formulario PQR.
```

**Obtenida (13/08):**
```
"Encontré una gestión reciente relacionada con una transacción no reconocida. Para garantizar la seguridad de tus productos y darte una solución sin duplicar la solicitud..." · botón Formulario PQR.
```

**Observación.** Re-verificado en F2 (13/08 tarde): con TRX_SALESFORCE_SOURCE=aso la recurrencia consulta el ASO de Salesforce vía la costura (simulador en local), sin el mount de workaround de la mañana. Hallazgo H-04 cerrado.

---

## 101 · Cliente sin productos válidos para el flujo (card_flag=false)

**Cliente:** `1013634959` · **Estatus:** Aprobada

**Pregunta:**
```
Frase → suceso 4 → 1 transacción → Empezar ahora → Sí, continuar
```

**Esperada:**
```
"Actualmente no tienes productos activos con nosotros para realizar esta solicitud. Si deseas revisar el estado de tus productos o movimientos, puedes ingresar a tu app BBVA. Hasta pronto." No muestra productos.
```

**Obtenida (13/08):**
```
Texto exacto del tablero, con botón Terminar. No mostró ningún producto.
```

**Observación.** El copy es el del tablero ("app BBVA"), no el del Excel de comunicaciones ("canales de atención"): el conflicto entre fuentes quedó resuelto en código a favor del tablero.

---

## 102 · Reporte de más de 3 transacciones

**Cliente:** `98787954` · **Estatus:** Aprobada

**Pregunta:**
```
Frase → suceso 4 → cantidad "Más de 3"
```

**Esperada:**
```
"Para validar el reporte de más de 3 compras no reconocidas, necesitamos tener la información completa en un solo trámite..." con Formulario PQR.
```

**Obtenida (13/08):**
```
Texto esperado, con botón Formulario PQR.
```

---

## 103 · Fecha fuera del plazo de la franquicia (MASTERCARD, 120 días)

**Cliente:** `1013634965` · **Estatus:** Aprobada

**Pregunta:**
```
...hasta la fecha → escribir 01/01/2025
```

**Esperada:**
```
"La fecha que ingresaste supera el plazo permitido por las franquicias de la tarjeta para reportar compras no reconocidas..." y cierra. No debe consultar movimientos.
```

**Obtenida (13/08):**
```
Texto esperado con botón Terminar. La traza confirma que no se llamó al ASO de movimientos.
```

**Observación.** Pendiente de negocio: el tablero distingue ámbito (VISA nacional 180 / interoperable e internacional 120); el código aplica sólo marca. Falta definir de qué campo sale el ámbito (pregunta a Data).

---

## 104 · Fecha dentro de plazo sin movimientos (transactions vacío)

**Cliente:** `1013634966` · **Estatus:** Aprobada

**Pregunta:**
```
...producto → fecha 06/08/2026 (cliente sin transacciones)
```

**Esperada:**
```
"No encontramos compras registradas en la fecha seleccionada para este producto." con TRES salidas: Elegir otra fecha / Seleccionar otro producto / Terminar consulta.
```

**Obtenida (13/08):**
```
Texto y las tres salidas presentes.
```

---

## 105 · Camino feliz: listado, confirmación y entrega a investigación

**Cliente:** `1013634960` · **Estatus:** Aprobada

**Pregunta:**
```
...producto Tarjeta *0060 → fecha 06/08/2026 → COMPRA FALABELLA → Sí, continuar con el reporte
```

**Esperada:**
```
Listado con los 3 movimientos del día y la opción "No encuentro la transacción en este listado". Confirmación con los datos de la compra y dos botones (Sí, continuar / No es necesario, ya reconozco la transacción). Al confirmar, pasa a la pregunta de investigación.
```

**Obtenida (13/08):**
```
Listado con 3 movimientos + "No encuentro..."; confirmación con ambos botones; tras confirmar: "Para continuar con tu proceso debemos iniciar con la investigación de tu caso...".
```

**Observación.** La cadena completa usó datos reales de las tres fuentes: productos de Postgres, card-id por financial-overview y movimientos del simulador. Tiempos medidos por turno: todos los gates respondieron en menos de 250 ms contra el simulador local (el camino asincrono del 204/polling no se activa). Desde la investigación en adelante el flujo es de Luis.

---

## 106 · Listado con un solo movimiento

**Cliente:** `1013634961` · **Estatus:** Aprobada

**Pregunta:**
```
...producto → fecha 06/08/2026 (cliente con 1 movimiento)
```

**Esperada:**
```
Listado con el movimiento y la opción de no encontrar la transacción.
```

**Obtenida (13/08):**
```
Listado con el movimiento, PERO sin el botón "No encuentro la transacción": sólo aparece cuando hay exactamente 3 movimientos.
```

**Observación.** HALLAZGO H-02 (abierto): con 1-2 movimientos la salida "no encuentro mi transacción" es inaccesible por botones. Decidir si es deliberado.

---

## 107 · Movimiento en estado pendiente (TDC)

**Cliente:** `1013634964` · **Estatus:** Aprobada

**Pregunta:**
```
...movimiento pendiente → Sí, continuar con el reporte
```

**Esperada:**
```
"Esta compra se encuentra actualmente en estado pendiente. Esto significa que el comercio aún la está procesando y podría liberarla o anularla en los próximos días sin realizar el cobro..." y finaliza.
```

**Obtenida (13/08):**
```
Texto esperado con botón Terminar.
```

**Observación.** El estado pendiente se evalúa sobre el detalle (responseOperati); la regla de 7 días del cruce MC30 del tablero aún no existe en código (tramo del otro responsable, contrato en definición).

---

## 108 · El listado respeta la fecha indicada

**Cliente:** `10482895` · **Estatus:** Aprobada

**Pregunta:**
```
...producto → fecha 05/08/2026 (día sin movimientos para ese cliente)
```

**Esperada:**
```
"No encontramos compras registradas en la fecha seleccionada..." — no debe listar los movimientos de otro día.
```

**Obtenida (13/08):**
```
Respondió sin movimientos, con las tres salidas. El filtro por fecha funciona en el listado.
```

---

## 109 · Fechas ilegibles: repregunta sin consultar

**Cliente:** `01576905` · **Estatus:** Aprobada

**Pregunta:**
```
En la fecha, escribir seguidas: 99/99/9999, luego "hola", luego 06/08/2026
```

**Esperada:**
```
Las dos primeras repreguntan ("No pude leer esa fecha. Escríbela en formato DD/MM/AAAA...") sin romper el turno ni consultar movimientos; la tercera lista los movimientos del día correcto.
```

**Obtenida (13/08):**
```
Repreguntó dos veces y con la fecha buena listó los movimientos de 06/08/2026.
```

**Observación.** HALLAZGO H-01, corregido el 13/08: antes la fecha ilegible ni se validaba ni se usaba — se listaban movimientos de otra fecha y el cliente habría confirmado una compra de un día que no indicó. El calendario que pide el tablero es de front y sigue pendiente.

---

## 111 · Recurrencia vía costura ASO: fallback y aislamiento de fuentes

**Cliente:** `1013634958 / 1013634960` · **Estatus:** Aprobada

**Pregunta:**
```
Con TRX_SALESFORCE_SOURCE=aso: repetir el caso 100 (cliente con gestión) y el 105 (cliente sin gestión). Con la costura caída: repetir el 105.
```

**Esperada:**
```
Con la costura viva: A recurre y C no, y el simulador registra la consulta con targetUserId={tipo_doc}-{documento}. Con la costura caída: el flujo continúa (fail-open, cae al mock local) sin romper el turno. Con TRX_SALESFORCE_SOURCE=mock: no se toca la red.
```

**Obtenida (13/08):**
```
A → has_recurrence=true; C → false; el simulador recibió ambas consultas. Fail-open y aislamiento verificados con pruebas unitarias (33 pasan en el servicio).
```

**Observación.** Añadido en F2 al cerrar H-04. Para ASO real faltan credenciales (ASO_SOURCE=real + ASO_REAL_URL + TRX_API_*); el TSEC ya está implementado.

---

## 112 · Contrato de la frontera entre tramos (Pablo → Luis)

**Cliente:** `1013634960` · **Estatus:** Aprobada

**Pregunta:**
```
Camino feliz completo hasta "Sí, continuar con el reporte" y, sobre la conversación persistida, ejecutar docs/pruebas/verificar_contrato.py
```

**Esperada:**
```
Las 25 claves del contrato (CONTRATO_FRONTERA.md v1) presentes y bien formadas: flow_answers (cantidad, producto, fecha, movimiento, confirmación afirmativa) y captured_data (trx_card_id, trx_vigencia, trx_index, trx_clasificacion completa, trx_detalle_result, products_result con origin_flag/last_four/card_brand).
```

**Obtenida (13/08):**
```
CONTRATO OK: 25/25. El verificador además avisa que trx_products_map no es fuente (pierde origin_flag) y documenta el hueco de la fecha de cruce para la regla de 7 días (sin insumo en el detalle; con Data).
```

**Observación.** Añadido en F3. El verificador es parte de la definición de hecho de ambos tramos: se corre antes de cada push que toque el flujo.

---

## 113 · Sucesos 1-3 (cambiazo, hurto, datos obtenidos) van directo a formulario

**Cliente:** `1013634962 / 63 / 64` · **Estatus:** Aprobada

**Pregunta:**
```
Tres conversaciones: elegir Cambiazo; Hurto o perdida; Alguien obtuvo mis datos por llamada, mensaje, correo o enlace
```

**Esperada:**
```
Los tres derivan al formulario sin mas preguntas, con boton Formulario PQR.
```

**Obtenida (13/08):**
```
Los tres ofrecieron Formulario PQR de inmediato.
```

**Observación.** Anadido en el double-check de cobertura del 13/08: el tramo asignado incluia estas ramas y no estaban en el documento.

---

## 114 · Rango de valor fuera de limite (ambos extremos)

**Cliente:** `1013634963 / 62` · **Estatus:** Aprobada

**Pregunta:**
```
Hasta el rango de valor; elegir Menor a $35.000 (una conversacion) y Mayor a $500.000 (otra)
```

**Esperada:**
```
Ambos derivan al formulario (.6.pqr) con boton Formulario PQR.
```

**Obtenida (13/08):**
```
Ambos ofrecieron Formulario PQR.
```

---

## 115 · El cliente reconoce la transaccion en la confirmacion

**Cliente:** `10482895` · **Estatus:** Aprobada

**Pregunta:**
```
Camino feliz hasta la confirmacion; elegir 'No es necesario, ya reconozco la transaccion'
```

**Esperada:**
```
Cierra por el proceso de feedback (¿Te ha ayudado esta informacion?), sin radicar nada.
```

**Obtenida (13/08):**
```
Paso directo al feedback.
```

**Observación.** Es la salida limpia del tramo: el caso confirma que no entra a investigacion ni deja radicado.

---

## 116 · Reenganches: 'No encuentro la transaccion' y 'sin movimientos'

**Cliente:** `1013634960 / 66` · **Estatus:** Aprobada

**Pregunta:**
```
En el listado elegir 'No encuentro la transaccion' -> 'Seleccionar una nueva fecha' -> dia sin movimientos -> 'Elegir otra fecha' -> dia con movimientos. En cliente sin transacciones: 'Elegir otra fecha' y 'Seleccionar otro producto'
```

**Esperada:**
```
Cada reenganche vuelve al paso correspondiente (fecha o selector de producto) sin arrastrar estado: la reconsulta con la fecha nueva funciona y el listado reaparece.
```

**Obtenida (13/08):**
```
Los reenganches encadenados funcionaron; la vuelta al dia con movimientos volvio a listar los 3.
```

---

## 117 · 'Finalizar conversacion' en la confirmacion de datos de contacto

**Cliente:** `01576905` · **Estatus:** Aprobada

**Pregunta:**
```
En 'Antes de continuar...' elegir Finalizar conversacion
```

**Esperada:**
```
Cierra por el proceso de feedback sin continuar el flujo.
```

**Obtenida (13/08):**
```
Paso directo al feedback.
```

---

## 118 · Contenido de la confirmación de la compra (viñetas del tablero)

**Cliente:** `1013634960` · **Estatus:** Aprobada

**Pregunta:**
```
Camino feliz hasta la confirmación; leer el texto completo
```

**Esperada:**
```
Viñetas con Descripción, Valor, Fecha (DD/MM/AAAA) y Producto terminado en *[últimos 4 reales], y la pregunta con dos botones.
```

**Obtenida (13/08):**
```
"• Descripción: COMPRA FALABELLA CALLE 80 • Valor: $120.000 • Fecha: 06/08/2026 • Producto terminado en *0060" con ambos botones.
```

**Observación.** HALLAZGO H-08, encontrado y cerrado el 13/08: salía el placeholder literal *XXXX porque el builder leía la clave last_four_pan_id (tabla ADA) y el servicio publica last_four. Mismo patrón de desajuste de claves que el products_map del contrato.

---

## 119 · El aviso de fecha ilegible no se queda pegado

**Cliente:** `1013634966` · **Estatus:** Aprobada

**Pregunta:**
```
Fecha ilegible → fecha buena → reenganche 'Elegir otra fecha'
```

**Esperada:**
```
La re-pregunta de fecha muestra el texto normal, no "No pude leer esa fecha" de un intento anterior.
```

**Obtenida (13/08):**
```
Tras el arreglo: el reenganche muestra el prompt normal.
```

**Observación.** HALLAZGO H-07 (era known-issue del PR), cerrado el 13/08: el aviso quedaba pegado y reaparecía en cada re-pregunta de fecha — reenganches y bucle multi-transacción — como si el cliente hubiera vuelto a fallar.

---

## 120 · Validación de recurrencia silenciosa (ajuste 13/08)

**Cliente:** `1013634960` · **Estatus:** Aprobada

**Pregunta:**
```
Frase → Compra presencial o por internet
```

**Esperada:**
```
Pasa DIRECTO a '¿Cuántas transacciones quieres reportar?' sin mostrar 'Estoy validando tu caso...' ni un botón Continuar. En backend la validación (Salesforce + recurrencia-bot + hito) ejecuta igual: con recurrencia real (cliente A) el desvío a PQR sigue saliendo de inmediato.
```

**Obtenida (13/08):**
```
Directo a la cantidad; con el cliente A, desvío a PQR intacto. Un turno menos en el camino común.
```

**Observación.** Pedido por Fabián. La rama sin recurrencia del gate ahora reescribe el paso igual que los gates de productos y pendiente.

---

## 121 · El selector de producto nunca muestra un identificador completo

**Cliente:** `1013634960` · **Estatus:** Aprobada

**Pregunta:**
```
Hasta el selector de producto; revisar el label
```

**Esperada:**
```
Tipo + últimos 4 de la TARJETA (last_four del servicio). Si el dato falta: '****'. Nunca los últimos 4 del contrato ni un identificador entero.
```

**Obtenida (13/08):**
```
'Tarjeta de Credito *0060' desde last_four. El normalizador conserva la clave y ningún consumidor cae ya a product_id (el contrato completo).
```

**Observación.** Pedido por Fabián. Antes caía a product_id: coincidía con el PAN solo por el seed — con datos reales de ADA habría mostrado el dato equivocado. Cuarto caso del desajuste last_four/last_four_pan_id, cerrado en la raíz (el normalizador).

---

## 122 · Trazabilidad: el journey completo se reconstruye desde logs

**Cliente:** `1013634961` · **Estatus:** Aprobada

**Pregunta:**
```
Camino feliz completo; luego: docker logs co-pqrs-back-agent | grep 'TXNR paso'
```

**Esperada:**
```
Una línea INFO por transición con paso origen → destino, la respuesta enmascarada (claves de opción sí; texto libre reducido a longitud; jamás PAN/contrato) y el estado. Además el evento viaja al error_handler → MinIO (audit-logs/traces) donde esté desplegado.
```

**Obtenida (13/08):**
```
10 líneas 'TXNR paso start → ... → satisfaction_check' reconstruyen el recorrido completo, incluida la reescritura de los gates.
```

**Observación.** Pedido por Fabián. Emisión en un solo punto (fin de turno), no en 20 llamadas dispersas.

---

## 201 · Sucesos 1-3 derivan a formulario y el botón cierra por feedback

**Cliente:** `1013634962 / 63 / 64` · **Estatus:** Pendiente

**Pregunta:**
```
[U-1a · 1013634962] No reconozco esta compra / Me cambiaron la tarjeta (cambiazo) / Formulario PQR // [U-1b · 1013634963] No reconozco esta compra / Hurto o perdida / Formulario PQR // [U-1c · 1013634964] No reconozco esta compra / Alguien obtuvo mis datos por llamada, mensaje, correo o enlace / Formulario PQR
```

**Esperada:**
```
[U-1a · 1013634962] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención // [U-1b · 1013634963] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención // [U-1c · 1013634964] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-1 (~8 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'TXNR paso' | grep 2.4.1

---

## 202 · Ruteo de las 12 frases de entrada del tablero

**Cliente:** `varios` · **Estatus:** Pendiente

**Pregunta:**
```
Escribir cada una de las 12 frases parametrizadas del tablero y verificar que rutean a la tipologia
```

**Esperada:**
```
Las 12 frases abren el menu de sucesos de transaccion no reconocida
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** NO VALIDABLE EN LOCAL: el router LLM responde 401 y contesta el fallback deterministico, asi que el resultado no es representativo. Validar en DEV con credenciales.

---

## 203 · Cantidad 2 y 3: aviso de una a la vez y límites completos

**Cliente:** `10482895` · **Estatus:** Pendiente

**Pregunta:**
```
[U-3a · 10482895] No reconozco esta compra / Compra presencial o por internet / 2 / Empezar ahora // [U-3b · 10482895] No reconozco esta compra / Compra presencial o por internet / 3 / Empezar ahora
```

**Esperada:**
```
[U-3a · 10482895] Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza | Botones: Si, continuar · Finalizar conversacion // [U-3b · 10482895] Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza | Botones: Si, continuar · Finalizar conversacion
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-3 (~6 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'trx_cantidad'

---

## 204 · 'Más de 3' deriva y el botón Formulario PQR transiciona

**Cliente:** `98787954` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / Mas de 3 / Formulario PQR
```

**Esperada:**
```
Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-4 (~3 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.1.pqr'

---

## 205 · Sin productos: el botón Terminar cierra por feedback

**Cliente:** `1013634959` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Terminar
```

**Esperada:**
```
Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-5 (~3 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.4.exit'

---

## 206 · Rango fuera de límite en ambos extremos

**Cliente:** `1013634963 / 62` · **Estatus:** Pendiente

**Pregunta:**
```
[U-6a · 1013634963] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0063 / Menor a $35.000 / Formulario PQR // [U-6b · 1013634962] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0062 / Mayor a $500.000 / Formulario PQR
```

**Esperada:**
```
[U-6a · 1013634963] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención // [U-6b · 1013634962] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-6 (~6 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.6.pqr'

---

## 207 · Elegir el 2.º movimiento de la lista llega a la confirmación

**Cliente:** `1013634960` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0060 / Entre $35.000 y $500.000 / 06/08/2026 / COMPRA MERCADOLIBRE.COM.CO — $89.990 — 06/08/2026
```

**Esperada:**
```
Confirma los datos de la compra seleccionada. • Descripción: COMPRA MERCADOLIBRE.COM.CO • Valor: $89.990 • Fecha: 06/08/2026 • Producto terminado en *0060 ¿Es la transacción que deseas reportar? | Botones: Si, continuar con el reporte · No es necesario, ya reconozco la transaccion
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-7 (~5 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'TXNR paso 2.4.0.1.9'

---

## 208 · Reenganche con la MISMA fecha vuelve al listado (H-11)

**Cliente:** `1013634960` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0060 / Entre $35.000 y $500.000 / 06/08/2026 / No encuentro la transaccion en este listado / Seleccionar una nueva fecha / 06/08/2026
```

**Esperada:**
```
Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces: | Botones: COMPRA FALABELLA CALLE 80 — $120.000 — 06/08/2026 · COMPRA MERCADOLIBRE.COM.CO — $89.990 — 06/08/2026 · COMPRA EXITO SUPERMERCADO — $250.000 — 06/08/2026 · No encuentro la transaccion en este listado
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-8 (~6 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'reenganche_cacheado'

---

## 209 · Índice de producto inexistente y formatos de fecha alternos

**Cliente:** `1013634961` · **Estatus:** Pendiente

**Pregunta:**
```
[U-9a · 1013634961] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / producto_4 // [U-9b · 1013634961] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0061 / Entre $35.000 y $500.000 / 31/12/2099 // [U-9c · 1013634961] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0061 / Entre $35.000 y $500.000 / 6/8/2026 // [U-9d · 1013634961] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0061 / Entre $35.000 y $500.000 / 2026-08-06
```

**Esperada:**
```
[U-9a · 1013634961] Antes de continuar, selecciona el rango de valor de la transaccion que deseas reportar: | Botones: Menor a $35.000 · Entre $35.000 y $500.000 · Mayor a $500.000 // [U-9b · 1013634961] No encontramos compras registradas en la fecha seleccionada para este producto. | Botones: Elegir otra fecha · Seleccionar otro producto · Terminar consulta // [U-9c · 1013634961] Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces: | Botones: COMPRA AMAZON MKTP — $150.000 — 06/08/2026 // [U-9d · 1013634961] Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces: | Botones: COMPRA AMAZON MKTP — $150.000 — 06/08/2026
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-9 (~8 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'vigencia'

---

## 210 · 'Seleccionar otro producto' vuelve al selector

**Cliente:** `1013634966` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0066 / Entre $35.000 y $500.000 / 06/08/2026 / Seleccionar otro producto
```

**Esperada:**
```
Selecciona el producto activo sobre el que deseas revisar las transacciones. - Tarjeta de Credito *0066 Responde con el numero de la opcion que prefieres. | Botones: Tarjeta de Credito *0066
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-10 (~4 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.8.return'

---

## 211 · MASTERCARD vencida: mensaje de plazo y Terminar

**Cliente:** `1013634965` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0065 / Entre $35.000 y $500.000 / 01/01/2025 / Terminar
```

**Esperada:**
```
Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-11 (~4 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'outcome=vencida'

---

## 212 · Fronteras exactas de la ventana de contracargo

**Cliente:** `1013634960 / 65` · **Estatus:** Pendiente

**Pregunta:**
```
Fechas a 179, 180, 181 dias (VISA) y 119, 120, 121 (MASTERCARD)
```

**Esperada:**
```
VISA acepta hasta 180 inclusive; MASTERCARD hasta 120 inclusive
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** CUBIERTO POR PRUEBAS UNITARIAS (fecha relativa, no caducan). Por UI no es teclable con fixtures de fecha fija; ver fila 124.

---

## 213 · Entradas no válidas donde se esperan botones

**Cliente:** `01576905` · **Estatus:** Pendiente

**Pregunta:**
```
[U-13a · 01576905] No reconozco esta compra / Compra presencial o por internet / texto libre que no es opcion // [U-13b · 01576905] No reconozco esta compra / Compra presencial o por internet / 99 // [U-13c · 01576905] No reconozco esta compra / Compra presencial o por internet / cancelar
```

**Esperada:**
```
[U-13a · 01576905] No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar? | Botones: 1 · 2 · 3 · Mas de 3 // [U-13b · 01576905] No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar? | Botones: 1 · 2 · 3 · Mas de 3 // [U-13c · 01576905] No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar? | Botones: 1 · 2 · 3 · Mas de 3
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-13 (~5 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'No pude identificar'

---

## 214 · Repetir la misma opción dos veces

**Cliente:** `1013634964` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / 1 / 1
```

**Esperada:**
```
Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza | Botones: Si, continuar · Finalizar conversacion
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-14 (~3 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'TXNR paso'

---

## 215 · Recurrencia-bot en la segunda entrada del dia

**Cliente:** `1013634960` · **Estatus:** Pendiente

**Pregunta:**
```
Entrar dos veces por la opcion 4 el mismo dia sin resetear
```

**Esperada:**
```
La segunda entrada desvia a formulario con fuente=bot
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** PARCIAL: la rama simple se observa en U-17; el doble hit con Salesforce requiere montaje. Ver H-05 (cerrado) en el protocolo.

---

## 216 · Índice de movimiento fuera de rango (H-13, abierto)

**Cliente:** `1013634961` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0061 / Entre $35.000 y $500.000 / 06/08/2026 / movimiento_3
```

**Esperada:**
```
Con la informacion disponible no podemos resolver esta solicitud en este canal. Por favor registra tu solicitud en el formulario. | Botones: Formulario PQR
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-16 (~4 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.10'

---

## 217 · Reabrir la conversación a mitad de flujo conserva el paso

**Cliente:** `1013634962` · **Estatus:** Pendiente

**Pregunta:**
```
No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar
```

**Esperada:**
```
Selecciona el producto activo sobre el que deseas revisar las transacciones. - Tarjeta de Credito *0062 Responde con el numero de la opcion que prefieres. | Botones: Tarjeta de Credito *0062
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-17 (~3 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'Resuming existing session'

---

## 218 · Precedencia de Salesforce sobre la recurrencia-bot

**Cliente:** `1013634958` · **Estatus:** Pendiente

**Pregunta:**
```
Cliente con gestion en Salesforce Y entrada previa del bot
```

**Esperada:**
```
Prevalece Salesforce y la traza lo refleja en source
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** NO VALIDABLE POR UI: exige provocar ambos a la vez. La distincion ya viaja en la traza (campo source_used).

---

## 219 · Fecha con espacios y fecha larguísima

**Cliente:** `01576905` · **Estatus:** Pendiente

**Pregunta:**
```
[U-19a · 01576905] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *9461 / Entre $35.000 y $500.000 /     // [U-19b · 01576905] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *9461 / Entre $35.000 y $500.000 / xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Esperada:**
```
[U-19a · 01576905]  // [U-19b · 01576905] No pude leer esa fecha. Escribela en formato DD/MM/AAAA, por ejemplo 06/08/2026. Consulta la fecha en tu extracto o en los movimientos de tu App BBVA.
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Plan de UI U-19 (~4 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'fecha_ilegible'

---

## 220 · [STACK] Caso de resiliencia con servicios caidos o mal configurados

**Cliente:** `segun el caso` · **Estatus:** Pendiente

**Pregunta:**
```
Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias
```

**Esperada:**
```
El flujo degrada sin romper el turno y el mensaje al cliente es comprensible
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar.

---

## 221 · [STACK] Caso de resiliencia con servicios caidos o mal configurados

**Cliente:** `segun el caso` · **Estatus:** Pendiente

**Pregunta:**
```
Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias
```

**Esperada:**
```
El flujo degrada sin romper el turno y el mensaje al cliente es comprensible
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar.

---

## 222 · [STACK] Caso de resiliencia con servicios caidos o mal configurados

**Cliente:** `segun el caso` · **Estatus:** Pendiente

**Pregunta:**
```
Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias
```

**Esperada:**
```
El flujo degrada sin romper el turno y el mensaje al cliente es comprensible
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar.

---

## 223 · [STACK] Caso de resiliencia con servicios caidos o mal configurados

**Cliente:** `segun el caso` · **Estatus:** Pendiente

**Pregunta:**
```
Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias
```

**Esperada:**
```
El flujo degrada sin romper el turno y el mensaje al cliente es comprensible
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar.

---

## 224 · [STACK] Caso de resiliencia con servicios caidos o mal configurados

**Cliente:** `segun el caso` · **Estatus:** Pendiente

**Pregunta:**
```
Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias
```

**Esperada:**
```
El flujo degrada sin romper el turno y el mensaje al cliente es comprensible
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar.

---

## 225 · [STACK] Caso de resiliencia con servicios caidos o mal configurados

**Cliente:** `segun el caso` · **Estatus:** Pendiente

**Pregunta:**
```
Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias
```

**Esperada:**
```
El flujo degrada sin romper el turno y el mensaje al cliente es comprensible
```

**Obtenida (13/08):**
```
(sin ejecutar)
```

**Observación.** Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar.

---

## 123 · Reanudar la conversación (POST /start) conserva los botones del paso

**Cliente:** `98787954` · **Estatus:** Aprobada

**Pregunta:**
```
Llegar a un paso con botones (p. ej. 'Más de 3' → Formulario PQR) y recargar el front o pulsar 'Iniciar conversación (/start)'
```

**Esperada:**
```
El bot vuelve a mostrar la pregunta CON sus botones (input_type=choice y las opciones del paso). El saludo inicial sigue sin botones.
```

**Obtenida (13/08):**
```
Tras el arreglo: input_type=choice y ['Formulario PQR'] al reanudar; saludo inicial input_type=text con options vacías.
```

**Observación.** HALLAZGO H-09, encontrado en la pasada de UI del 14/08 y corregido el mismo día: POST /start es idempotente y REANUDA la sesión (Arquitectura A), pero serializaba siempre el mensaje como texto plano sin opciones — quien recargaba el front en cualquier paso de botones se quedaba viendo la pregunta sin nada que pulsar. Afecta a TODOS los flujos del bot, no solo a trx. Cambio aditivo de contrato: StartMessageContent admite options (vacías en el saludo).

---

## 124 · Ventana de contracargo: fronteras exactas por marca

**Cliente:** `1013634960 (VISA) / 1013634965 (MASTERCARD)` · **Estatus:** Aprobada

**Pregunta:**
```
Con VISA probar 179, 180 y 181 días de antigüedad; con MASTERCARD 119, 120 y 121. Además, la banda diferencial: misma fecha (150 días) con VISA y con MASTERCARD.
```

**Esperada:**
```
VISA acepta hasta 180 días inclusive y rechaza en 181. MASTERCARD acepta hasta 120 inclusive y rechaza en 121. A 150 días VISA continúa y MASTERCARD muestra el mensaje del plazo de las franquicias.
```

**Obtenida (13/08):**
```
Verificado con pruebas de fecha relativa (no caducan): 179/180 pasan, 181 vence; 119/120 pasan, 121 vence; banda 150 discrimina.
```

**Observación.** Regla confirmada por negocio el 14/08: SOLO marca, sin ámbito — cierra la duda del tablero (nacional/interoperable/internacional). Plazos parametrizables (VIGENCIA_VISA_DIAS / VIGENCIA_MASTER_DIAS). PENDIENTE: qué plazo aplica a lo que no es VISA ni MASTER (AMEX, Diners, marca vacía); hoy reciben 180, el más permisivo.

---

## 125 · Exactitud de los mensajes dinámicos (procedencia, formato, degradación)

**Cliente:** `1013634960` · **Estatus:** Aprobada

**Pregunta:**
```
Recorrer el camino feliz ejecutando docs/pruebas/verificar_mensajes.py, que compara cada dato mostrado contra su fuente en el payload
```

**Esperada:**
```
En los 4 puntos con datos del cliente (selector, reprompt de fecha, listado y confirmación): cada valor sale de la clave correcta, las fechas van en DD/MM/AAAA, los importes formateados, el producto con sus últimos 4 reales, y nunca aparece un crudo (XXXX, None, contrato completo).
```

**Obtenida (13/08):**
```
61 comprobaciones OK. Degradación fijada aparte con pruebas: sin last_four el selector muestra **** y jamás el contrato.
```

**Observación.** Pedido por Fabián el 14/08. El verificador compara contra la FUENTE del dato, no contra un literal: un cambio de copy autorizado no rompe la prueba, pero un dato leído de la clave equivocada sí — que es el fallo que se escapó tres veces (H-03, H-07, H-08).

---

## 126 · Los ultimos 4 salen del PAN de financial-overview, no del contrato

**Cliente:** `1013634967` · **Estatus:** Aprobada

**Pregunta:**
```
Recorrido normal hasta el selector de producto y despues hasta la confirmacion, con el cliente J (divergencia deliberada: ADA y el contrato terminan en 9999; el PAN de financial-overview en 4321)
```

**Esperada:**
```
Selector y confirmacion muestran **4321** -- los ultimos 4 del PAN. Si mostraran 9999 estarian leyendo de ADA o del contrato, que es el defecto reportado por negocio.
```

**Obtenida (13/08):**
```
Selector: 'Tarjeta de Credito *4321'. Confirmacion: 'Producto terminado en *4321'.
```

**Observación.** Cliente creado el 18/08 para que la verificacion sea inequivoca: en el resto de la matriz ADA y el PAN coinciden por diseno de los fixtures, asi que un fallo pasaria desapercibido. Semilla en dev/postgres/03-seed-cliente-j.sql y fixtures del simulador para el PAN 4912680517944321.

---

## 110 · Formato del label del movimiento

**Cliente:** `01576905` · **Estatus:** Aprobada

**Pregunta:**
```
(sobre el listado del caso anterior)
```

**Esperada:**
```
El tablero pide "[Descripción] — $[valor] [DD/MM/AAAA]".
```

**Obtenida (13/08):**
```
Tras el arreglo del 13/08 (tarde): "COMPRA FALABELLA CALLE 80 — $120.000 — 06/08/2026" — descripcion, valor y fecha en DD/MM/AAAA, como pide el tablero.
```

**Observación.** HALLAZGO H-03, cerrado el 13/08: la fecha salia en ISO. Corregido en el label del listado y en la confirmacion.

---
