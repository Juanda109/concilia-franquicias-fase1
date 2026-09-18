# Subida de nivel: autorización push previa al bloqueo de tarjeta

Este documento describe cómo funciona la subida de nivel del flujo de
transacción no reconocida (TXNR): desde que el cliente elige bloquear su
tarjeta hasta que el bloqueo queda ejecutado. Cubre el contrato con el ASO,
lo que hace cada servicio (agente y `co_pqrs_back_trx_noreconocida`), la
configuración por ambiente, las trazas para diagnosticar y cómo probarlo con
el simulador.

> **Última validación:** 14/09/2026 en dev contra el simulador ASO (agente
> `1.0.15`, trx `1.0.9_qa`, simulador `1.0.11`). Casos y evidencia en
> [`pruebas/CASOS_PRUEBA_TRX_ESQUELETO.md`](pruebas/CASOS_PRUEBA_TRX_ESQUELETO.md),
> bloque 300.

## Resumen

1. El cliente elige el bloqueo (definitivo `2.4.0.1.17` o temporal `2.4.0.1.16`).
2. El agente obtiene la identidad de la tarjeta con **una sola consulta a
   Postgres** (`/v1/trx/identity-by-card`).
3. trx ejecuta la ceremonia contra el ASO: TSEC, dispositivo activo, primer
   `POST` (tipo de autenticación) y segundo `POST`, que **envía la notificación
   push**.
4. El cliente autoriza en su App y pulsa **Continuar** en el chat. El agente
   consulta el estado del reto **una vez por pulsación**.
5. Con el reto aceptado se ejecuta el bloqueo: el definitivo con un tercer
   `POST` (cancelación y reexpedición), el temporal con un `PATCH` de apagado.

> **Nota:** los códigos `403` y `401` de los pasos 2 y 3 son respuestas
> esperadas del protocolo de autenticación; no son fallos técnicos.

## Servicios y endpoints internos

| Paso del flujo | Agente llama a | trx hace |
| --- | --- | --- |
| `2.4.0.1.16.1` / `2.4.0.1.17.1` | `GET /v1/trx/identity-by-card?customer_id&last_four&origin_flag=TDC` | Consulta `ada_info_detail` y devuelve `account_id` y `personal_id` |
| `2.4.0.1.16.1` / `2.4.0.1.17.1` | `POST /v1/trx/subida-nivel?card_id&personal_id&last_four&account_last_four` | Pasos 0 a 3 contra el ASO |
| `2.4.0.1.16.2` / `2.4.0.1.17.2` | `GET /v1/trx/subida-nivel/estado?challenge` | Paso 4 contra el ASO (una consulta) |
| `2.4.0.1.16.2` / `2.4.0.1.17.2` | `POST /v1/trx/bloqueo?card_id&tipo&challenge&authentication_state&device_id&profile_id&account_last_four` | Paso 5 (definitivo) o `PATCH` (temporal) |

## Variables del flujo

| Variable | Origen | Descripción |
| --- | --- | --- |
| `customer_id` | Conversación (`user_id`) | Llave del cliente en `ada_info_detail`. |
| `personal_id` | `ada_info_detail.personal_id` | Cédula; en ADA viene rellenada con ceros a 15 dígitos (p. ej. `000000003017449`). |
| `profileId` | trx | `CC` + `personal_id` rellenado con ceros a 15 dígitos. |
| `accountId` | `ada_info_detail.account_id` | Cuenta asociada; solo viajan sus últimos 4 (`product=cuenta-XXXX`). |
| `deviceId` | Paso 1 | Primer dispositivo con soft token `ACTIVE`. |
| `tsec` | Paso 0 | Token de sesión del grantingTicket. |
| `authenticationtype` | Paso 2 | Tipo de autenticación, `241`. |
| `authenticationChallenge` | Paso 3 | Identificador del reto; se consulta en el paso 4. |
| `authenticationstate` | Paso 3 | Estado del reto; se envía en el paso 5. |

## Origen del `accountId`: una sola consulta a Postgres

El `account_id` sale **solo** de la consulta que hace `/identity-by-card`:

```sql
SELECT account_id, personal_id FROM ada_info_detail
WHERE customer_id = %s AND origin_flag = %s AND last_four_pan_id = %s
LIMIT 1
```

El agente calcula los últimos 4 y los envía a `/subida-nivel` como
`account_last_four`. **trx no vuelve a consultar Postgres**: si
`account_last_four` no llega o no son 4 dígitos, responde
`{"status": "error", "etapa": "account_id"}` **sin llamar al ASO**.

> **Por qué (14/09/2026).** Desde el 28/08 `/subida-nivel` hacía una segunda
> consulta pasando la cédula como `customer_id`. Con los datos de prueba no se
> notaba porque en ellos `customer_id` y `personal_id` son iguales; con clientes
> reales (`customer_id` ≠ `personal_id`) no encontraba la fila y la subida de
> nivel terminaba en `2.4.0.1.17.1.denied` sin enviar el push (QA `13083558`,
> dev `98782372`). Corregido en `59868b9`.

Si la fila de ADA no tiene `account_id`, el agente no llama a `/subida-nivel`
(log `TXNR SUBIDA NIVEL 05 NO SE EJECUTA faltantes=account_last_four`) y el
cliente no puede bloquear, ni temporal ni definitivamente.

## Paso 0: obtener el TSEC

**Método:** `POST`
**Ruta:** `{base}/TechArchitecture/co/grantingTicket/V02` (o `TRX_TICKET_URL` si está definida)

```json
{
  "authentication": {
    "userID": "{{TRX_API_USER_ID}}",
    "consumerID": "{{TRX_API_CONSUMER_ID}}",
    "authenticationType": "04",
    "authenticationData": [
      {"idAuthenticationData": "password", "authenticationData": ["{{TRX_API_PASSWORD}}"]}
    ]
  },
  "backendUserRequest": {"userId": "", "accessCode": "", "dialogId": ""}
}
```

El TSEC se lee del header `tsec`; si no viene, se toma el cuerpo de la respuesta.
Cada endpoint de trx pide su propio TSEC (ver *Pendientes de confirmar*).

## Paso 1: validar el dispositivo del cliente

**Método:** `GET`
**Ruta:** `{challenge_base}/security/v0/user-status?profileId={profileId}`

Para la cédula `3017449` el valor es `CC000000003017449`.

### Validaciones

1. La respuesta debe traer al menos un dispositivo en `data`.
2. Se toma el **primer dispositivo cuyo** `device.softToken.status.id` sea
   `ACTIVE` (no necesariamente `data[0]`).
3. Sin dispositivo activo la respuesta es `status: sin_dispositivo`
   (`etapa: user_status`) y el agente lleva a `.denied`.

### Respuesta de ejemplo

```json
{
  "data": [
    {
      "device": {
        "id": "BB-04-CG0400002ELZ",
        "name": "SOFTWARE_AMAZON",
        "softToken": {"id": "BB-04-CG0400002ELZ", "status": {"id": "ACTIVE"}}
      }
    }
  ]
}
```

## Paso 2: obtener el tipo de autenticación

**Método:** `POST`
**Ruta:** `{challenge_base}/cards/v2/operations`
**Headers:** `tsec`, `Content-Type: application/json`

**Respuesta esperada:** `403 Forbidden` con el header `authenticationtype: 241`.
`403` es el código HTTP y `241` el tipo de autenticación. Si el tipo no es el
esperado (`ASO_CHALLENGE_AUTH_TYPE`), trx responde `etapa: challenge_iniciar` y
no envía el push.

## Paso 3: enviar la notificación push

**Método:** `POST`
**Ruta:** `{challenge_base}/cards/v2/operations`

### Headers enviados hoy

| Header | Valor |
| --- | --- |
| `tsec` | Token de sesión |
| `Content-Type` | `application/json` |
| `authenticationtype` | `241` |
| `authenticationdata` | Ver estructura |

> **Pendiente de confirmar con el ASO real:** la documentación inicial marcaba
> `authenticationstate` como header obligatorio de esta petición, pero la
> respuesta del paso 2 no lo entrega. El código **no lo envía** y el simulador
> lo acepta (validado el 14/09), pero el simulador se construyó igual que el
> código, así que eso no confirma el contrato real.

### Estructura de `authenticationdata`

```text
deviceId={deviceId},profileId={profileId},channel=12000035,operation=NMONETARY,smc=SMGG20210970,amount=,product=cuenta-{ultimos_4_accountId},description=bloqueo y reexpedicion
```

Los valores fijos salen de configuración (`ASO_CHALLENGE_CHANNEL`,
`ASO_CHALLENGE_OPERATION`, `ASO_CHALLENGE_SMC`, `ASO_CHALLENGE_DESCRIPTION`).

### Cuerpo de la petición (pasos 2, 3 y 5)

```json
{
  "card": {
    "cardId": "{{PAN}}",
    "cardInformation": {
      "reason": "Fraude",
      "requestDate": "YYYY-MM-DD",
      "requestHour": "HH:MM",
      "description": "Cliente reporta transaccion no reconocida bot PQRs",
      "retentionName": "Titular"
    }
  }
}
```

`description` es un texto fijo del bot; no se envía el relato del cliente.

### Respuesta esperada

**Código:** `401 Unauthorized` con los headers `authenticationChallenge` y
`authenticationstate`. trx devuelve ambos al agente, que los guarda con un plazo
de **3 minutos**.

> **Limpieza del challenge:** el servicio puede devolver el reto con `;;` (o
> `::`) al final, por ejemplo `9b84c586-f5c7-47a4-8576-3a35f8627532;;`. Se quitan
> antes de usarlo en el paso 4.

## Paso 4: consultar el estado de la autorización

**Método:** `GET`
**Ruta:** `{challenge_base}/security/v0/order-chanel/{authenticationChallenge_limpio}`

> El endpoint conserva `order-chanel` tal como lo define el servicio.

```json
{"data": {"status": {"id": "pending"}}}
```

### Cómo lo usa el flujo

- **No hay sondeo automático.** El agente consulta el estado **una vez cada vez
  que el cliente pulsa "Continuar"** en `2.4.0.1.17.2` (o `16.2`).
- Mientras el cliente no pulse Continuar, no pasa nada: no se bloquea aunque
  haya aprobado en la App.

| `data.status.id` | El agente | Siguiente paso |
| --- | --- | --- |
| `accepted` / `approved` | Ejecuta el bloqueo | `2.4.0.1.17.3` (o `16.3`) |
| `pending` y dentro de 3 min | Vuelve al paso del push **sin reenviarlo** | Mismo mensaje con botón Continuar |
| `pending` y más de 3 min desde el push | Da el reto por vencido | `2.4.0.1.17.1.denied` |
| `rejected` / `denied` | No bloquea | `2.4.0.1.17.1.denied` |
| `expired` / `timeout` | No bloquea | `2.4.0.1.17.1.denied` |
| Error técnico (sin TSEC, ASO caído) | No bloquea | `2.4.0.1.17.1.denied` |

Los 3 minutos cuentan desde el primer push y no se reinician. El plazo local
solo aplica mientras el estado sea `pending`: si el ASO ya responde `accepted`,
el bloqueo se ejecuta aunque el cliente pulse Continuar más tarde.

## Paso 5: bloqueo definitivo (tercera llamada)

Solo para el bloqueo **definitivo**, cuando el estado es `accepted`.

**Método:** `POST`
**Ruta:** `{challenge_base}/cards/v2/operations`

| Header | Valor | Origen |
| --- | --- | --- |
| `tsec` | Token de sesión | Paso 0 |
| `Content-Type` | `application/json` | — |
| `authenticationtype` | `241` | Paso 2 |
| `authenticationstate` | Valor recibido | Respuesta del paso 3 |
| `authenticationdata` | Misma cadena del paso 3 | — |

`authenticationstate` va **solo como header**; no se agregan `authenticationstate`,
`operationId` ni `correlationToken` dentro de `authenticationdata`. El cuerpo es
el mismo del paso 3.

**Respuesta:** `2xx` = bloqueo y reexpedición ejecutados (el simulador responde
`201`); `400` = el cliente no autorizó.

Si falta alguno de `challenge`, `authentication_state`, `device_id` o
`profile_id`, trx **no llama al ASO** y responde `falta la autorizacion`.

## Bloqueo temporal

El bloqueo temporal **nunca** ejecuta el paso 5 (cancelaría la tarjeta). Tras
el `accepted` se apaga la tarjeta con:

**Método:** `PATCH`
**Ruta:** `{base}/cards/v1/cards/{card_id}/activations`

```json
{"root": [{"id": "ON_OFF", "isActive": false, "additionalInformation1": null, "additionalInformation2": 0, "additionalInformation3": null, "additionalInformation4": null}]}
```

El bloqueo temporal también pasa por la subida de nivel (pasos 0 a 4).

## Candado contra doble bloqueo

Tras un bloqueo exitoso se registra el hito
`bloqueo_ejecutado:{tipo}:{conversation_id}:{producto}` en el índice durable
`trx-no-reconocida-cases`. Si el turno se reintenta en la **misma conversación**
(el `conversation_id` es `{customer_id}_{yyyymmdd}`), el bloqueo no se vuelve a
enviar al ASO. Para repetir un bloqueo definitivo real el mismo día hay que
borrar el caso del cliente en ese índice.

## Módulo de autorización

La subida de nivel **no usa** `co_pqrs_authorization`. Con
`AUTHORIZATION_SERVICE_URL` vacía o ausente (dev desde `8a6ca4b`, QA y PRD) el
agente consulta el estado directamente en `/v1/trx/subida-nivel/estado`.

## Configuración y destino por ambiente

Resolución en `TrxAsoClient`:

- **Consultas** (`grantingTicket`, `user-status` y demás ASO): `ASO_BASE_URL` si
  está definida; si no, `ASO_REAL_URL` con `ASO_SOURCE=real`; en cualquier otro
  caso, `ASO_SIMULATOR_URL`.
- **Reto** (pasos 1 a 5): `ASO_CHALLENGE_BASE_URL` **solo** con `ASO_SOURCE=real`;
  si no, la misma base de las consultas.

| Ambiente | `ASO_SOURCE` | Consultas | Reto | Push real |
| --- | --- | --- | --- | --- |
| Dev | `simulator` | `co-pqrs-back-trx-aso-simulator:8050` | Simulador (aunque `ASO_CHALLENGE_BASE_URL` apunte a nextgen) | No |
| QA | `real` | `aus-arqaso.work.co.nextgen.igrupobbva:8050` (`ASO_BASE_URL`) | La misma | Sí |
| PRD | `real` | `arqaso.live.co.nextgen.igrupobbva:8000` | La misma (sin `ASO_CHALLENGE_BASE_URL`) | Sí |

## Trazas para diagnosticar

Todas llegan al error handler (`ERROR_HANDLER_SERVICE_URL`) y quedan en MinIO,
bucket `audit-logs`, ruta
`clients/customer={customer_id}/dt={fecha}/conversation={conversation_id}/`.

| Evento | Servicio | Qué muestra |
| --- | --- | --- |
| `trx.identity_by_card` | Agente | Resultado de la única consulta a Postgres |
| `trx.subida_nivel` | Agente | `status`, `etapa`, `account_last_four` enviado, `authentication_state`, `profile_id` |
| `tsec`, `user_status`, `challenge_iniciar`, `challenge_enviar_push`, `order_channel_status`, `challenge_confirmar` | trx | Petición y respuesta de cada llamada al ASO (URL, headers permitidos, huella del TSEC, status) |
| `subida_nivel.<etapa>` | trx | Etapas que fallan, `tsec` y el push |
| `subida_nivel.ceremonia` | trx | Resumen: `secuencia`, `murio_en` y en `extra_context` la URL real de consultas y reto (`consultas_url`, `challenge_url`, `challenge_va_al`) |
| `trx.subida_nivel_estado` | Agente | `pending` / `accepted` / `rejected` / `expired` |
| `bloqueo_permanente` / `bloqueo_temporal` | Agente | `autorizacion_vencido`, `autorizacion_rechazado`, `ok` |
| `trx_case.bloqueo_ejecutado:…` | Agente | Hito del candado |

La ceremonia solo anota las etapas que fallan, `tsec` y el push; `user_status` y
el paso 4 exitosos se ven en los eventos del ASO y del agente.

## Probar con el simulador (dev)

El simulador guarda el reto en memoria y usa un identificador fijo por tarjeta:
`sim-{ultimos_4_PAN}-challenge`. Desde la terminal del pod
`co-pqrs-back-trx-aso-simulator`:

Consultar el estado:

```bash
python -c "import urllib.request as u; print(u.urlopen('http://localhost:8050/security/v0/order-chanel/sim-2274-challenge').read().decode())"
```

Aprobar (cambiar `approve` por `reject` o `expire` para los otros caminos):

```bash
python -c "import urllib.request as u; print(u.urlopen(u.Request('http://localhost:8050/security/v0/order-chanel/sim-2274-challenge/approve', data=b'', method='POST')).read().decode())"
```

Orden de la prueba: llegar a "Listo. Enviamos una notificación…", aprobar en el
simulador y pulsar **Continuar** antes de 3 minutos. Un push nuevo sobrescribe el
reto anterior y lo deja otra vez en `pending`. El simulador marca "sin
dispositivo" cuando el `profileId` termina en `0000`.

## Pendientes de confirmar con el ASO real

1. **`authenticationstate` en el paso 3:** confirmar si el push lo requiere.
2. **TSEC entre pasos:** cada endpoint pide un grantingTicket nuevo, así que el
   push, la consulta del estado y la confirmación usan tokens distintos. Confirmar
   que el reto no queda atado al token que lo creó (el simulador siempre devuelve
   el mismo token y no lo valida).
3. **`product=cuenta-XXXX`:** confirmar qué espera el ASO para tarjeta de crédito
   y qué hacer cuando ADA no trae `account_id`.
4. **`description` del paso 5:** confirmar si el texto fijo es aceptable.

## Datos de referencia (pruebas manuales iniciales)

| Paso | Código esperado | Tiempo observado | Tamaño aproximado |
| --- | --- | --- | --- |
| 1. Validación de dispositivo | `200` | 711 ms | 5.47 KB |
| 2. Tipo de autenticación | `403` | 135 ms | 5.61 KB |
| 3. Notificación push | `401` | 320 ms | 7.26 KB |
| 4. Estado de autorización | `200` | 624 ms | 5.47 KB |
| 5. Bloqueo y reexpedición | `2xx` | Pendiente de medir en ASO real | Pendiente |

Valores orientativos; no deben usarse como timeouts de producción sin validación
adicional.

> **Seguridad:** no registrar números completos de tarjeta, cédulas ni cuentas en
> logs, documentación o capturas. Los ejemplos de este documento usan datos de
> prueba.
