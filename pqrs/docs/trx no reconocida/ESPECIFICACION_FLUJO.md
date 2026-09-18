# TXNR (Transacción No Reconocida) — Especificación del flujo

> **Estado: fotografía del flujo tal como está HOY (2026-08-25), rama `feature/PQRSdev`.**
> Este documento describe lo implementado, no lo deseado. Se deja así a propósito
> para poder comparar cuando el flujo se modifique.
>
> **Los mensajes salen de DOS fuentes**, y hay que mirar las dos:
> 1. El YAML del flujo (`trx_no_reconocida.yml`) → sección 6.
> 2. **Código** (`workflow_actions.py`, `chat_service.py`) para los mensajes que
>    dependen de datos del cliente → sección 7.
>
> Ambas secciones se **generan** desde las fuentes, no se transcriben. La versión
> anterior de este documento solo leía el YAML y por eso 10 pasos aparecían sin
> texto, entre ellos los de confirmación de bloqueo de tarjeta.

---

## 1. Arquitectura

Tres piezas colaboran en cada turno:

| Pieza | Responsabilidad |
|---|---|
| `co_pqrs_back_agent` | Conduce la conversación: enruta, renderiza los nodos del YAML y ejecuta los *gates* automáticos que deciden el paso siguiente. |
| `co_pqrs_back_trx_noreconocida` | Consulta Postgres (productos) y el ASO (movimientos, detalle, bloqueos). No conoce la conversación. |
| `co_pqrs_back_trx_tantia_export` | CronJob que consolida los abonos automáticos del día en el CSV para el RPA de Tantia. |

El agente **nunca** consulta Postgres ni el ASO directamente: siempre pasa por
`co_pqrs_back_trx_noreconocida` (variable `TRX_SERVICE_URL`).

### Dónde vive la lógica

El YAML define **qué se le muestra** al cliente. El **código** decide a qué nodo
ir cuando la decisión depende de datos externos. Esa división es importante para
entender el flujo:

- Nodo con `options[].next_step` → la transición está **en el YAML**.
- Nodo con `action` → el agente llama al back y **el código elige** el destino.

La función que concentra esa lógica es `_prefetch_trx_data_if_needed`
(`chat_service.py`), que hoy ocupa ~950 líneas y contiene **12 gates**.

> El árbol tiene **53 nodos**. Creció respecto a versiones anteriores del
> documento (49) al incorporarse el subflujo de **notificación a la App BBVA**
> para autorizar los bloqueos (commit `0c50f49`).

---

## 2. Portón de despliegue (canario)

**Antes de cualquier nodo del flujo** se evalúa el portón:

```python
if step.startswith("2.4.0.1") and not _trx_flow_allowed(conversation):
    conversation.current_step = "2.4.0.4.pqr"   # formulario PQR
    return
```

| Variable | Efecto |
|---|---|
| `TRX_FLOW_ENABLED=false` | El flujo está **cerrado**: las 4 opciones del menú caen al formulario PQR, igual que antes de existir el flujo. |
| `TRX_FLOW_ENABLED=true` | Abierto a todos los clientes. |
| `TRX_CANARY_TOKEN` | Quien escriba ese token en el chat desbloquea el flujo **solo para su conversación**. |

El permiso es **por conversación**: al abrir un chat nuevo hay que volver a
escribir el token. El interceptor del token corre **antes** del guardrail de
entrada, para que no lo bloquee.

Estado actual: `false` en producción (entra cerrado), `true` en dev.

---

## 3. Menú de entrada (`2.4.0`)

Cuatro causales. Solo una entra al flujo completo:

| Opción | Destino | Nota |
|---|---|---|
| `cambiazo` | `2.4.1` | Rama propia, fuera de este documento |
| `hurto_o_perdida` | `2.4.2` | Ídem |
| `ingenieria_social` | `2.4.3` | Ídem |
| `compra_presencial_o_internet` | **`2.4.0.1`** | **Flujo TXNR completo** |

---

## 4. Los 12 gates automáticos

Estos son los puntos donde el **código**, no el YAML, decide el siguiente paso.
Es el esqueleto real del flujo:

| # | Gate (paso) | Qué consulta | Destinos posibles |
|---|---|---|---|
| 1 | `2.4.0.1` | Recurrencia del bot y de Salesforce | `2.4.0.1.1` (sigue) · `2.4.0.pqr_recurrencia` (demasiadas veces) |
| 2 | `2.4.0.1.4` | Productos vigentes en Postgres | `2.4.0.1.5` (hay productos) · `2.4.0.1.4.exit` (no tiene) · `2.4.0.1.4.error` (falla de infraestructura) |
| 3 | `2.4.0.1.8` | ASO: `financial-overview` + `transactions` | `2.4.0.1.9` (hay movimientos) · `2.4.0.1.8.return` (sin movimientos) · `2.4.0.1.8.error` |
| 4 | `2.4.0.1.10` | ASO: `operations` (detalle) | `2.4.0.1.11` (confirmar) · `2.4.0.1.10.pqr` |
| 5 | `2.4.0.1.12` | Compra con TDC pendiente | `2.4.0.1.13` · `2.4.0.1.12.exit` |
| 6 | `2.4.0.1.15` | Pregunta de bloqueo (semántica) | `2.4.0.1.16` temporal · `2.4.0.1.17` definitivo |
| 7 | `2.4.0.1.16.1` | ASO: **notificación** a la App (temporal) | `2.4.0.1.16.2` (autorizado) · `2.4.0.1.16.1.denied` |
| 8 | `2.4.0.1.17.1` | ASO: **notificación** a la App (definitivo) | `2.4.0.1.17.2` (autorizado) · `2.4.0.1.17.1.denied` |
| 9 | `2.4.0.1.19` | Validaciones (presencial / reversado) | `2.4.0.1.19.1` · `2.4.0.1.19.2` · `2.4.0.1.19.pqr` |
| 10 | `2.4.0.1.20` | **Devolución automática** | Registra el caso y acumula la transacción para el CSV |
| 11 | `2.4.0.1.20.0` | Cierre del bucle | `2.4.0.1.20.1` (otra transacción) · `2.4.0.1.20.2` (fin) |
| 12 | `2.4.0.1.20.1` | Bucle "una a la vez" | Reinicia los campos por transacción |

### Selección de bloqueo: es semántica, no posicional
La elección entre bloqueo temporal y permanente se resuelve por el **texto** de la
respuesta (`definitivamente` → permanente, `temporalmente` → temporal), no por el
orden de los botones. Cambiar el orden en el YAML no rompe el ruteo.

### Vigencia por franquicia
En `2.4.0.1.7` se compara la fecha de la transacción contra la vigencia de la
franquicia: `VIGENCIA_VISA_DIAS=180`, `VIGENCIA_MASTER_DIAS=120`. Fuera de rango
va a `2.4.0.1.7.exit`.

---

## 5. Bucle "una transacción a la vez"

El cliente declara en `2.4.0.1.1` cuántas transacciones quiere reportar (1, 2, 3 o
más de 3). El flujo procesa **una por una** y vuelve al inicio del ciclo:

```
2.4.0.1.5 (producto) → … → 2.4.0.1.20 (devolución) → 2.4.0.1.20.0 (¿otra?)
        ↑                                                      │
        └──────────────────  2.4.0.1.20.1  ←───────────────────┘
```

Al reiniciar, `_trx_reset_per_tx_state` limpia los datos de la transacción
anterior. Dos detalles que se aprendieron por error y quedaron documentados en el
código:

1. La limpieza de los prompts dinámicos se hace **por prefijo**, no con una lista
   de claves. Con la lista, mensajes de una transacción se filtraban a la
   siguiente (aparecía "tu tarjeta ya quedó bloqueada" con la tarjeta anterior).
2. `_TRX_BLOQUEADOS_KEY` **no** se limpia: el bloqueo es de la *tarjeta*, no de la
   transacción. Si se borrara, el flujo ofrecería bloquear un producto ya
   bloqueado.

### Acumulación para el CSV de Tantia
En `2.4.0.1.20`, además de registrar el hito, la transacción se **acumula** en
`trx_case_state.tantia_items` (una entrada por transacción, con huella
`statementId|movementId` para no duplicar). Sin esa lista sería imposible emitir
una fila de CSV por transacción, porque el reset borra el detalle.

---

## 6. Árbol completo de nodos (generado desde el YAML)

> 53 nodos. `(lo decide el código)` significa que la transición la resuelve uno de
> los gates de la sección 4. Los nodos marcados **mensaje dinámico** tienen su
> texto en la sección 7, no aquí.

### `2.4.0`
**guarda en**: `evento_trx_no_reconocida` · **entrada**: `choice`

```text
Antes de iniciar el proceso de análisis, confírmame por favor si fuiste víctima de alguno de estos sucesos:
```
| opción | etiqueta | va a |
|---|---|---|
| `cambiazo` | Me cambiaron la tarjeta (cambiazo) | `2.4.1` |
| `hurto_o_perdida` | Hurto o pérdida | `2.4.2` |
| `ingenieria_social` | Alguien obtuvo tus datos bancarios por llamada, mensaje, correo o enlace | `2.4.3` |
| `compra_presencial_o_internet` | Hiciste una compra presencial o por internet | `2.4.0.1` |

### `2.4.0.1`
**action**: `consultar_recurrencia_salesforce` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

```text
Gracias. Estoy validando tu caso para continuar con el análisis.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.1` |

### `2.4.0.1.1`
**guarda en**: `trx_cantidad` · **entrada**: `choice`

```text
¿Cuántas transacciones quieres reportar?
```
| opción | etiqueta | va a |
|---|---|---|
| `1` | 1 | `2.4.0.1.2` |
| `2` | 2 | `2.4.0.1.2` |
| `3` | 3 | `2.4.0.1.2` |
| `mas_de_3` | Más de 3 | `2.4.0.1.1.pqr` |

### `2.4.0.1.1.pqr`
**entrada**: `choice`

```text
Para validar el reporte de más de 3 compras no reconocidas, necesitamos tener la información completa en un solo trámite. Completa el formulario a continuación y analizaremos cada movimiento a fondo.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.0.1.2`
**entrada**: `choice`

```text
Revisaremos una transacción a la vez para darte el detalle de cada caso. Al terminar la primera, continuaremos de inmediato con la siguiente.
```
| opción | etiqueta | va a |
|---|---|---|
| `empezar` | Empezar ahora | `2.4.0.1.3` |

### `2.4.0.1.3`
**entrada**: `choice`

```text
Antes de empezar, ten en cuenta que desde aquí puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una.

Al continuar, confirmas que tus datos de contacto y dirección están actualizados para el envío de tu tarjeta si se requiere. ¿Quieres continuar?
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Sí, continuar | `2.4.0.1.4` |
| `finalizar` | Finalizar conversacion | `satisfaction_check` |

### `2.4.0.1.4`
**action**: `verificar_productos_trx` · **entrada**: `choice`

```text
Estoy validando tus productos activos.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.5` |

### `2.4.0.1.4.error`
**entrada**: `choice`

```text
En este momento no podemos consultar tus productos por un inconveniente técnico de nuestro lado.

Para que tu caso quede registrado y nuestro equipo lo revise, por favor radica tu solicitud en el siguiente formulario.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.0.1.4.exit`
**entrada**: `choice`

```text
Actualmente no tienes productos activos con nosotros para realizar esta solicitud.

Si deseas revisar el estado de tus productos o movimientos, puedes ingresar a tu app BBVA. Hasta pronto.
```
| opción | etiqueta | va a |
|---|---|---|
| `terminar` | Terminar | `satisfaction_check` |

### `2.4.0.1.5`
**action**: `mostrar_productos_activos_trx` · **guarda en**: `producto_trx_no_reconocida` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

```text
Selecciona la cuenta o tarjeta en la que aparece la compra que no reconoces:
```
| opción | etiqueta | va a |
|---|---|---|
| `producto_1` | Producto 1 | `2.4.0.1.6` |
| `producto_2` | Producto 2 | `2.4.0.1.6` |
| `producto_3` | Producto 3 | `2.4.0.1.6` |
| `producto_4` | Producto 4 | `2.4.0.1.6` |
| `producto_5` | Producto 5 | `2.4.0.1.6` |

### `2.4.0.1.6`
**guarda en**: `trx_rango_valor` · **entrada**: `choice`

```text
Antes de continuar, selecciona el rango de valor de la transacción que deseas reportar:
```
| opción | etiqueta | va a |
|---|---|---|
| `menor_35000` | Menor a $35.000 | `2.4.0.1.6.pqr` |
| `entre_35000_500000` | Entre $35.000 y $500.000 | `2.4.0.1.7` |
| `mayor_500000` | Mayor a $500.000 | `2.4.0.1.6.pqr` |

### `2.4.0.1.6.pqr`
**entrada**: `choice`

```text
Para validar el reporte de estas compras no reconocidas, necesitamos la validación de nuestro equipo especializado. Completa el formulario a continuación y analizaremos cada movimiento a fondo.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.0.1.7`
**guarda en**: `trx_fecha` · **entrada**: `text` · **siguiente**: `2.4.0.1.8` · **mensaje dinámico** (ver §7)

```text
Escribe la fecha en la que se realizó la compra no reconocida usando el formato DD/MM/AAAA.

Consulta la fecha en tu extracto o en los movimientos de tu App BBVA y verifica que sea una transacción sin estado pendiente para poder validarla desde este canal.
```

### `2.4.0.1.7.exit`
**entrada**: `choice`

```text
La fecha que ingresaste supera el plazo permitido por las franquicias de la tarjeta para reportar compras no reconocidas, por lo que no podemos procesar tu solicitud.

Te sugerimos contactar directamente al comercio donde se realizó la compra para solicitar el detalle o la devolución del cobro. Hasta pronto.
```
| opción | etiqueta | va a |
|---|---|---|
| `terminar` | Terminar | `satisfaction_check` |

### `2.4.0.1.8`
**action**: `consultar_movimientos_trx` · **entrada**: `choice`

```text
Estoy consultando tus movimientos en la fecha indicada.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.9` |

### `2.4.0.1.8.error`
**entrada**: `choice`

```text
En este momento no podemos consultar los movimientos de tu producto por un inconveniente técnico de nuestro lado.

No queremos darte información incompleta sobre tus compras. Para que tu caso quede registrado y nuestro equipo lo revise, por favor radica tu solicitud en el siguiente formulario.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.0.1.8.return`
**entrada**: `choice` · **mensaje dinámico** (ver §7)

```text
No encontramos compras registradas en la fecha seleccionada para este producto.
```
| opción | etiqueta | va a |
|---|---|---|
| `otra_fecha` | Elegir otra fecha | `2.4.0.1.7` |
| `otro_producto` | Seleccionar otro producto | `2.4.0.1.5` |
| `terminar` | Terminar consulta | `satisfaction_check` |

### `2.4.0.1.9`
**action**: `mostrar_movimientos_trx` · **guarda en**: `trx_movimiento_seleccionado` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

```text
Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:
```
| opción | etiqueta | va a |
|---|---|---|
| `movimiento_1` | Movimiento 1 | `2.4.0.1.10` |
| `movimiento_2` | Movimiento 2 | `2.4.0.1.10` |
| `movimiento_3` | Movimiento 3 | `2.4.0.1.10` |
| `movimiento_4` | Movimiento 4 | `2.4.0.1.10` |
| `movimiento_5` | Movimiento 5 | `2.4.0.1.10` |
| `no_encuentro` | No encuentro la transacción en este listado. | `2.4.0.1.9.exit` |

### `2.4.0.1.9.exit`
**entrada**: `choice`

```text
Para continuar, puedes elegir otra fecha. Por favor valida que la transacción no esté pendiente en tus movimientos en la App BBVA.
```
| opción | etiqueta | va a |
|---|---|---|
| `nueva_fecha` | Seleccionar una nueva fecha | `2.4.0.1.7` |
| `finalizar` | No, finalizar la conversacion | `satisfaction_check` |

### `2.4.0.1.10`
**action**: `consultar_detalle_trx` · **entrada**: `choice`

```text
Estoy consultando el detalle de la compra seleccionada.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.11` |

### `2.4.0.1.10.pqr`
**entrada**: `choice`

```text
Con la información disponible no podemos resolver esta solicitud en este canal. Por favor registra tu solicitud en el formulario.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.0.1.11`
**action**: `confirmar_movimiento_trx` · **guarda en**: `trx_confirmacion_movimiento` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

```text
Confirma los datos de la compra seleccionada. ¿Es la transacción que deseas reportar?
```
| opción | etiqueta | va a |
|---|---|---|
| `si_reportar` | Sí, continuar con el reporte | `2.4.0.1.12` |
| `ya_reconozco` | No es necesario, ya reconozco la transacción | `satisfaction_check` |

### `2.4.0.1.12`
**action**: `validar_pendiente_trx` · **entrada**: `choice`

```text
Estoy validando el estado de la compra.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.13` |

### `2.4.0.1.12.exit`
**entrada**: `choice`

```text
Esta compra se encuentra actualmente en estado pendiente. Esto significa que el comercio aún la está procesando y podría liberarla o anularla en los próximos días sin realizar el cobro.

Si la compra se confirma en tus movimientos definitivos y continúas sin reconocerla, podrás ingresar de nuevo a este chat para realizar tu reporte. Que tengas un buen día.
```
| opción | etiqueta | va a |
|---|---|---|
| `terminar` | Terminar | `satisfaction_check` |

### `2.4.0.1.13`
**entrada**: `choice`

```text
Para continuar con tu proceso debemos iniciar con la investigación de tu caso, ¿quieres continuar con este proceso?
```
| opción | etiqueta | va a |
|---|---|---|
| `si_investigar` | Sí, continuar con la investigación | `2.4.0.1.15` |
| `no_finalizar` | No, finalizar la conversación | `satisfaction_check` |

### `2.4.0.1.15`
**entrada**: `choice`

```text
Para continuar con este proceso es necesario bloquear definitivamente tu tarjeta, ¿quieres continuar con este bloqueo?
```
| opción | etiqueta | va a |
|---|---|---|
| `definitivamente` | Sí, bloquear definitivamente | `2.4.0.1.17` |
| `temporalmente` | No, bloquear temporalmente | `2.4.0.1.16` |

### `2.4.0.1.16`
**entrada**: `choice`

```text
Apagaremos temporalmente tu tarjeta para protegerla. Podrás volver a encenderla desde tus canales digitales.

Al elegir esta opción, la revisión automática de la transacción finalizará. Si luego confirmas que no reconoces la compra, podrás volver a ingresar para hacer tu reporte. ¿Quieres continuar?
```
| opción | etiqueta | va a |
|---|---|---|
| `si_apagar` | Sí, apagar temporalmente | `2.4.0.1.16.1` |
| `no_finalizar` | No, finalizar conversación | `satisfaction_check` |

### `2.4.0.1.16.1`
**action**: `enviar_notificacion_bloqueo_temporal_trx` · **entrada**: `choice`

```text
Listo. Enviamos una notificación a tu App BBVA para confirmar este bloqueo. Revísala y regresa aquí para continuar.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.16.2` |

### `2.4.0.1.16.1.denied`
**entrada**: `choice`

```text
No pudimos validar tu autorización para continuar con el bloqueo de tu producto.

Siempre que lo necesites, estoy aquí para apoyarte con tus productos BBVA. Hasta pronto.
```
| opción | etiqueta | va a |
|---|---|---|
| `terminar` | Terminar | `satisfaction_check` |

### `2.4.0.1.16.2`
**action**: `bloqueo_temporal_trx` · **entrada**: `choice`

```text
Estoy apagando temporalmente tu tarjeta.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.16.3` |

### `2.4.0.1.16.2.pqr`
**entrada**: `choice`

```text
No hemos podido completar el bloqueo temporal. Por favor realiza el siguiente formulario PQR.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.0.1.16.3`
**action**: `mostrar_bloqueo_temporal_trx` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

> Sin texto en el YAML: el mensaje se construye en código. Ver §7.

| opción | etiqueta | va a |
|---|---|---|
| `terminar` | Terminar | `satisfaction_check` |

### `2.4.0.1.17`
**entrada**: `choice`

```text
Al continuar, tu tarjeta actual quedará bloqueada definitivamente. Solicitaremos una nueva tarjeta, sin costo. ¿Quieres continuar?
```
| opción | etiqueta | va a |
|---|---|---|
| `si_bloquear` | Sí, bloquear y continuar | `2.4.0.1.17.1` |
| `no_finalizar` | No, finalizar conversación | `satisfaction_check` |

### `2.4.0.1.17.1`
**action**: `enviar_notificacion_bloqueo_permanente_trx` · **entrada**: `choice`

```text
Listo. Enviamos una notificación a tu App BBVA para confirmar este bloqueo. Revísala y regresa aquí para continuar.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.17.2` |

### `2.4.0.1.17.1.denied`
**entrada**: `choice`

```text
No pudimos validar tu autorización para continuar con el bloqueo de tu producto.

Siempre que lo necesites, estoy aquí para apoyarte con tus productos BBVA. Hasta pronto.
```
| opción | etiqueta | va a |
|---|---|---|
| `terminar` | Terminar | `satisfaction_check` |

### `2.4.0.1.17.2`
**action**: `bloqueo_permanente_trx` · **entrada**: `choice`

```text
Estoy bloqueando definitivamente tu tarjeta y solicitando la nueva.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.17.3` |

### `2.4.0.1.17.2.pqr`
**entrada**: `choice`

```text
No hemos podido completar el bloqueo permanente. Por favor realiza el siguiente formulario PQR.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.0.1.17.3`
**action**: `mostrar_bloqueo_definitivo_trx` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

> Sin texto en el YAML: el mensaje se construye en código. Ver §7.

| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.18` |

### `2.4.0.1.18`
**entrada**: `choice` · **mensaje dinámico** (ver §7)

```text
Ahora revisaremos la información de la transacción para determinar cómo podemos gestionar tu solicitud.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.19` |

### `2.4.0.1.19`
**action**: `validar_investigacion_trx` · **entrada**: `choice`

```text
Estoy analizando la transacción.
```
| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.20` |

### `2.4.0.1.19.1`
**action**: `mostrar_trx_no_reconocida` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

> Sin texto en el YAML: el mensaje se construye en código. Ver §7.

| opción | etiqueta | va a |
|---|---|---|
| `terminar` | Finalizar conversación | `2.4.0.1.20.0` |

### `2.4.0.1.19.2`
**action**: `mostrar_trx_reversada` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

> Sin texto en el YAML: el mensaje se construye en código. Ver §7.

| opción | etiqueta | va a |
|---|---|---|
| `ver_movimientos` | Ver paso a paso para consultar movimientos | `2.4.0.1.19.2.guia` |
| `finalizar` | Finalizar | `2.4.0.1.20.0` |

### `2.4.0.1.19.2.guia`
**entrada**: `choice`

```text
Puedes consultar tus movimientos desde la BBVA net siguiendo estos pasos:

1. Ingresa a bbva.com.co y haz clic en "Acceso". Inicia sesion con tu documento de identidad y contrasena de la Net.
2. Ubica en el menú principal la opción de "Descarga tus certificados".
3. Dentro de esta sección, selecciona la opción titulada "Otros certificados".
4. En la lista de documentos disponibles, haz clic sobre la opción específica de "Paz y Salvo".
5. Elige el tipo de producto que necesitas certificar, ya sea tu tarjeta de crédito o tus préstamos.
6. Confirma el número del producto específico y haz clic en descargar para obtener tu documento PDF.
```
| opción | etiqueta | va a |
|---|---|---|
| `finalizar` | Finalizar | `2.4.0.1.20.0` |

### `2.4.0.1.19.pqr`
**entrada**: `choice`

```text
Con la información disponible no podemos resolver esta solicitud en este canal. Tu caso necesita una revisión por parte de nuestro equipo especializado.

Por favor registra tu solicitud en este enlace y nosotros nos encargaremos de analizarlo.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `2.4.0.1.20.0` |

### `2.4.0.1.20`
**action**: `registrar_devolucion_trx` · **entrada**: `choice` · **mensaje dinámico** (ver §7)

> Sin texto en el YAML: el mensaje se construye en código. Ver §7.

| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.20.0` |

### `2.4.0.1.20.0`
**action**: `cierre_bucle_trx` · **entrada**: `choice`

> Nodo sin mensaje: es un *gate* que decide y salta sin hablarle al cliente.

| opción | etiqueta | va a |
|---|---|---|
| `continuar` | Continuar | `2.4.0.1.20.1` |

### `2.4.0.1.20.1`
**entrada**: `choice`

```text
¿Deseas reportar la siguiente transacción?
```
| opción | etiqueta | va a |
|---|---|---|
| `si_siguiente` | Sí, reportar la siguiente | `2.4.0.1.3` |
| `no_finalizar` | No, finalizar | `satisfaction_check` |

### `2.4.0.1.20.2`
**entrada**: `choice`

```text
Ya reportaste todas las transacciones no reconocidas que nos indicaste.
```
| opción | etiqueta | va a |
|---|---|---|
| `terminar` | Terminar | `satisfaction_check` |

### `2.4.0.4.pqr`
**entrada**: `choice`

```text
Por las caracteristicas de lo ocurrido, necesitamos que nuestro equipo de especialistas revise tu caso detalladamente. Por favor registra tu solicitud en el formulario.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.0.pqr_recurrencia`
**entrada**: `choice`

```text
Encontré una gestión reciente relacionada con una transacción no reconocida. Para garantizar la seguridad de tus productos y darte una solución sin duplicar la solicitud, es necesario que un equipo especializado revise tu caso. Completa el siguiente formulario para registrar la reclamación.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.1`
**entrada**: `choice`

```text
Por las características de lo ocurrido, tu caso requiere una revisión a fondo por parte de nuestro equipo especializado. Por favor completa el siguiente formulario.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.2`
**entrada**: `choice`

```text
Por las características de lo ocurrido, necesitamos que nuestro equipo de especialistas revise tu caso detalladamente. Por favor registra tu solicitud en este enlace y nosotros nos encargaremos de analizarlo.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

### `2.4.3`
**entrada**: `choice`

```text
Por las características de lo ocurrido, necesitamos que nuestro equipo de especialistas revise tu caso detalladamente. Por favor registra tu solicitud en este enlace y nosotros nos encargaremos de analizarlo.
```
| opción | etiqueta | va a |
|---|---|---|
| `pqr` | Formulario PQR | `satisfaction_check` |

---

## 7. Mensajes construidos en código

Estos pasos NO tienen su texto en el YAML: el mensaje se arma en código porque
depende de datos del cliente. Los marcadores `{...}` se sustituyen en ejecución.

### `2.4.0.1.7`

*variante 1 de 2* · `chat_service.py:760`

```text
Esa fecha todavia no ha ocurrido. Indicame la fecha en la que ya se realizo la compra, en formato DD/MM/AAAA.
```

*variante 2 de 2* · `chat_service.py:765`

```text
No pude leer esa fecha. Escribela en formato DD/MM/AAAA, por ejemplo 06/08/2026. Consulta la fecha en tu extracto o en los movimientos de tu App BBVA.
```

### `2.4.0.1.8.return`

*mensaje* · `chat_service.py:826`

```text
Ese día sí tienes movimientos, pero por este canal solo puedo gestionar compras entre {_trx_pesos((movs or {}).get('monto_min'))} y {_trx_pesos((movs or {}).get('monto_max'))}. Si la compra que no reconoces está fuera de ese rango, nuestro equipo especializado puede ayudarte.monto_minmonto_max
```

### `2.4.0.1.9`

*mensaje* · `workflow_actions.py:1719`

```text
Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces:
```

### `2.4.0.1.11`

*variante 1 de 2* · `workflow_actions.py:1786`

```text
Confirma los datos de la compra seleccionada.

• {desc}
• Valor: {valor}
• Fecha: {fecha}
```

*variante 2 de 2* · `workflow_actions.py:1748`

```text
Confirma los datos de la compra seleccionada. ¿Es la transacción que deseas reportar?
```

### `2.4.0.1.16.3`

*variante 1 de 2* · `workflow_actions.py:1962`

```text
Listo. Tu tarjeta terminada en •{last4} quedó apagada temporalmente.

Podrás volver a encenderla desde tus canales digitales.
```

*variante 2 de 2* · `workflow_actions.py:1968`

```text
Listo. Tu tarjeta quedó apagada temporalmente.

Podrás volver a encenderla desde tus canales digitales.
```

### `2.4.0.1.17.3`

*variante 1 de 2* · `workflow_actions.py:2116`

```text
Confirmamos que tu tarjeta terminada en •{last4} quedó cancelada por seguridad.

Tu nueva tarjeta ya está en camino.

Te la enviaremos a la dirección {direccion} en un lapso de {dias} días hábiles.
```

*variante 2 de 2* · `workflow_actions.py:2124`

```text
Confirmamos que tu tarjeta quedó cancelada por seguridad.

Tu nueva tarjeta ya está en camino.

Te la enviaremos a {direccion} en un lapso de {dias} días hábiles.
```

### `2.4.0.1.18`

*mensaje* · `chat_service.py:1128`

```text
Tu producto ya quedó bloqueado en el reporte anterior, así que seguimos con la revisión de esta transacción.Tu tarjeta terminada en •{ultimos} ya quedó bloqueada en el reporte anterior, así que seguimos con la revisión de esta transacción.
```

### `2.4.0.1.19.1`

*variante 1 de 2* · `workflow_actions.py:2008`

```text
Revisamos la investigación de la transacción {desc} por {valor}.

Tras analizar los registros del caso, identificamos que la transacción se realizó de forma presencial con la lectura física del chip de tu tarjeta y la digitación de tu clave secreta en el datáfono del establecimiento.

Conforme al marco del Régimen de Protección al Consumidor Financiero, cuando una operación cumple con la totalidad de los mecanismos de autenticación presenciales y los sistemas del banco no presentan fallas operativas, la compra se valida como autorizada.

Por esta razón, no es posible realizar la devolución del dinero.
```

*variante 2 de 2* · `workflow_actions.py:1987`

```text
Tras analizar los registros del caso, no fue posible identificar la información de la transacción seleccionada.
```

### `2.4.0.1.19.2`

*variante 1 de 2* · `workflow_actions.py:2083`

```text
Te confirmamos que la compra por {valor} ya fue devuelta a tu {product_name}.

Detalle del reembolso:

{detalle_lines}

Puedes consultar tus movimientos para confirmar que el valor ya se encuentra reflejado.
```

*variante 2 de 2* · `workflow_actions.py:2049`

```text
Te confirmamos que la compra seleccionada ya fue devuelta a tu {product_name}.
```

### `2.4.0.1.20`

*mensaje* · `chat_service.py:1067`

```text
Validamos la información de tu solicitud y tu caso aplica para la devolución automática.

Gestionaremos el abono de tu dinero y te enviaremos la confirmación a tu correo electrónico en un máximo de {dias_dev} días hábiles. No necesitas realizar ningún trámite adicional.
```


---

## 8. Estado y persistencia

| Dónde | Qué guarda | Vida |
|---|---|---|
| `conversation.captured_data["trx_case_state"]` | Estado en vuelo: producto, fecha, movimiento, detalle, validaciones, `tantia_items` | La conversación |
| Índice `conversations-*` | Se persiste cada turno | Según la política del índice |
| Índice `trx-no-reconocida-cases` | Registro durable por cliente: hitos, entradas, `trx_case_state_snapshot` | **Sin TTL** |

El índice durable **no lo crea nadie explícitamente**: lo crea el agente al
escribir el primer documento (`upsert`). Mientras ningún cliente llegue a la
devolución automática, el índice no existe — y eso es normal, no un error.

### Recurrencia
Dos fuentes, ambas por cliente:
- **Bot**: cuántas veces entró al flujo (`MAX_TRX_BOT_RECURRENCE=20`), leída del índice durable.
- **Salesforce**: casos previos reales, vía ASO.

Si el ASO de recurrencia falla, se responde `error` y **nunca** "no hay
recurrencia": asumir que no hay casos previos sería peor que no responder.

---

## 9. Guardrail anti-mock

Con `TRX_PRODUCTS_SOURCE=postgres` existía un fallback silencioso que mostraba
tarjetas de ejemplo (`4979`, `4567`) a clientes reales. Hoy:

- `_load_products_from_postgres` devuelve `(rows, error)` y distingue "el cliente
  no tiene productos" de "falló la infraestructura".
- Un fallo de base devuelve `status="error"`, no una lista vacía.
- `TRX_ALLOW_MOCKS` es el interruptor global: **`false` en producción y QA**.

---

## 10. Lo que NO está implementado

Para que quede explícito y no se asuma:

- Las ramas `2.4.1`, `2.4.2` y `2.4.3` (cambiazo, hurto/pérdida, ingeniería
  social) no forman parte de este flujo.
- El flujo no cachea el TSEC del ASO: se solicita en cada operación.
- El corte del CSV de Tantia es a las 16:00. Los abonos posteriores se recuperan
  en la corrida del siguiente día hábil (ventana de 4 días), así que no se pierden;
  ver [`CSV_TANTIA.md`](./CSV_TANTIA.md).
