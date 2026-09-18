# Datos sensibles en las trazas (KYNS IT 3.6 / 3.7)

> Última actualización: **2026-09-09**, rama `feature/PQRSllmops`. Frente 2 del plan de
> cumplimiento IA.

## El hallazgo

El 31/08 se revisaron las trazas E2E que el error handler guarda en MinIO
(`audit-logs/clients/<customer>/...`) y en ellas viajaban **en claro**:

| Dato | De dónde salía | Por qué estaba ahí |
|---|---|---|
| Contraseña del grantingTicket | `co_pqrs_back_trx_noreconocida` → `_mask_password` | flag `ASO_TRACE_PASSWORD_FULL=true` en el ConfigMap de dev |
| TSEC completo (credencial de sesión) | TXNR y doble cobro → `_tsec_debug` | flag `ASO_TRACE_TSEC_FULL=true` (diagnóstico del 25/08 nunca apagado) |
| financial-overview entero: PAN, titular, correo | TXNR `_response_debug` y `co_pqrs_back_data` `commercial_info_client` | `E2E_DEBUG_TRACE=true` volcaba `body_full` sin enmascarar |

Un ConfigMap de diagnóstico que se olvida encendido no puede ser la única barrera. La
remediación tiene tres capas y ninguna depende de un flag.

## Las tres capas

**1. En el emisor no existe la opción de volcar la credencial.**

- La contraseña del granting va **siempre** como `<oculto len=N>`. El flag
  `ASO_TRACE_PASSWORD_FULL` se retiró del código; si alguien lo deja en un ConfigMap no
  tiene efecto.
- El TSEC nunca sale completo. `_tsec_debug` emite longitud, prefijo, sufijo y SHA256, que
  basta para comprobar que el ASO 2 recibió el mismo token que devolvió el grantingTicket.
  El flag `ASO_TRACE_TSEC_FULL` se retiró en TXNR y en doble cobro.
- Con `E2E_DEBUG_TRACE=true` el cuerpo completo de la respuesta se guarda como
  `body_full_masked`: PAN reducido a los últimos 4 y correos ocultos. La cabecera `tsec`
  ya no se copia; `co_pqrs_back_data` solo conserva `content-type`, `date`, `content-length`
  y el id de petición.

**2. En dev los flags de diagnóstico quedan apagados.**
`IaC/backend/co_pqrs_back_trx_noreconocida/01-configmap.yaml` y
`IaC/backend/co_pqrs_back_data/00-configmap.yaml` llevan `E2E_DEBUG_TRACE=false`. Encenderlos
sigue siendo legítimo para depurar, pero lo que se guarda ya está enmascarado.

**3. Última barrera en el error handler, sin flag que la apague.**
`co_pqrs_back_error_handler/src/domain/trace_event/sanitizer.py` se aplica a todo
trace-event y a todo request-log justo antes de escribir en MinIO o en disco:

- **Por clave**: `password`, `tsec`, `authenticationData`, `authorization`, `api_key`,
  `token`, `cookie`, `body_full`… se reemplazan por `<oculto>`. Nombres de personas
  (`holderName`, `customer_name`, `nombre`, `titular`…) se reducen a iniciales.
- **Por valor**: en cualquier texto, un número de 13 a 19 dígitos que empieza como una tarjeta (2 a 6) y pasa
  Luhn (o tiene 16 dígitos y empieza por 4 o 5) se deja en sus últimos 4; los correos se ocultan. Así un PAN escondido en una
  URL, en un mensaje de error o en un JSON serializado tampoco llega al bucket.
- Los identificadores de negocio de primer nivel (`conversation_id`, `customer_id`,
  `trace_id`) no se tocan. Las cédulas (8 a 10 dígitos) quedan fuera del rango, y los números de contrato y de
  producto del banco empiezan por 0 o 1, así que no se tocan aunque pasen Luhn: la traza sigue
  siendo cruzable con el cliente. Medido el 11/09 sobre los fixtures: 12 de 234 contratos quedan
  ocultos (los que empiezan como tarjeta), frente a 159 con la primera versión de la regla; los
  22 PAN de prueba se ocultan con ambas.

## Cómo se demuestra

| Prueba | Dónde | Qué fija |
|---|---|---|
| `test_trace_sanitizer.py` (9) | error handler | PAN con y sin separadores, en URL y en JSON; cédulas y contratos intactos; claves secretas; titular a iniciales; identificadores de primer nivel |
| `test_aso_client_trazas_sin_secretos.py` (4) | TXNR | con los flags viejos encendidos, ni la contraseña, ni el TSEC, ni el PAN salen del emisor |
| `test_aso_debug.py` (reescritos 2) | TXNR | el contrato viejo "valor completo detrás del flag" ya no existe |
| `test_aso_client.py` (reescrito 1) | doble cobro | idem para el TSEC |
| `test_commercial_info_trace_masking.py` (2) | back_data | cuerpo enmascarado y cabeceras seguras |

Resultado del 9/09: error handler 21/21, TXNR 147 en verde (1 rojo preexistente en
recurrencia), doble cobro 54/54, back_data 70 en verde (2 rojos preexistentes en
consultar_service).

## Barrido de lo ya guardado

`co_pqrs_back_error_handler/scripts/scan_sensitive_traces.py` recorre un bucket de MinIO o
una carpeta y cuenta PAN, correos, `tsec_completo`, contraseñas de granting en claro y
`body_full`. Sale con código 1 si hay hallazgos, así que sirve como gate.

```bash
cd co_pqrs_back_error_handler
# inventario de lo histórico (desde un pod con acceso a MinIO o con port-forward)
MINIO_ENDPOINT_URL=http://minio:9000 MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... \
  uv run python scripts/scan_sensitive_traces.py --bucket audit-logs --prefix clients/ --show 20

# evidencia de que las trazas nuevas salen limpias
uv run python scripts/scan_sensitive_traces.py --dir ./output
```

Verificado en local con un objeto sucio sintético (5 tipos detectados) y uno limpio (0).

## Decisión pendiente para Fabián

Los objetos históricos de `audit-logs` en dev contienen credenciales y PAN. Opciones:

1. **Borrar** todo lo anterior al despliegue de esta versión (recomendado: son trazas de
   diagnóstico, no evidencia de negocio).
2. **Reescribir** cada objeto pasando por `sanitize_trace_event` (el script de barrido se
   extiende con `--fix`).

Además, la API key de Azure y la contraseña del granting que aparecían en trazas deberían
rotarse, porque estuvieron persistidas en claro desde el 25/08.

## Qué cambia para el despliegue

Imágenes nuevas de `co_pqrs_back_error_handler`, `co_pqrs_back_trx_noreconocida`,
`co_pqrs_back_data` y `co_pqrs_back_doble_cobro`, más aplicar los dos ConfigMaps. Ningún
cambio de contrato entre servicios.
