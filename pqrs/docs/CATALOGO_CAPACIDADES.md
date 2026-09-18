# Catálogo de capacidades del agente PQRS

> Generado por `co_pqrs_back_agent/scripts/build_capability_catalog.py` a partir de
> `general.yml`, los YAML de cada flujo y `chat_service.py`. No editar a mano: el test
> `test_catalogo_capacidades.py` falla si este fichero no coincide con lo generado.

Evidencia del control **KYNS IT 4** (restricción de autonomía): el LLM solo elige la ruta,
valida texto libre y clasifica opciones. Toda acción con efecto está en la *allowlist* de
abajo, la ejecuta código determinista y solo se alcanza tras las puertas que se listan.

## 1. Qué decide el modelo y qué no

| Punto | Lo decide el LLM | Lo decide código |
|---|---|---|
| Ruteo inicial | `is_match`, `workflow`, `confidence` | umbral de confianza, confirmación en `low`, aclaración determinista, formulario como último recurso |
| Texto libre en un paso (fecha, monto) | extrae y normaliza | la fecha se reparsea con `_trx_parse_date`; futura o ilegible se repregunta |
| Opción de un paso `choice` | clasifica el texto contra las opciones | el `next_step` lo fija el YAML |
| Cierre de guía rápida | redacta solo si `LLM_CLOSURE_ENABLED=true` (apagado por defecto) | el texto aprobado del YAML |
| Cualquier acción con efecto | **nunca** | gates de `chat_service` / hooks, con fail-closed |

## 2. Rutas a las que puede enrutar

| Grupo | Opción | Workflow | Categoría de tope diario |
|---|---|---|---|
| hazlo_tu_mismo | certificado_de_cuenta | `certificado_de_cuenta` | general |
| hazlo_tu_mismo | consulta_de_movimientos | `consulta_de_movimientos` | general |
| hazlo_tu_mismo | certificado_tributario | `certificado_tributario` | general |
| hazlo_tu_mismo | extractos_bancarios | `extractos_bancarios` | general |
| hazlo_tu_mismo | paz_y_salvo | `paz_y_salvo` | general |
| hazlo_tu_mismo | solicitud_de_documentos_leasing | `solicitud_de_documentos_leasing` | general |
| hazlo_tu_mismo | certificado_de_deuda | `certificado_de_deuda` | general |
| hazlo_tu_mismo | certificados_fondos_de_inversion | `certificados_fondos_de_inversion` | general |
| guia_rapida | impuesto_4x1000 | `impuesto_4x1000` | general |
| guia_rapida | puntos_y_promociones | `puntos_y_promociones` | general |
| guia_rapida | cuota_de_manejo | `cuota_de_manejo` | general |
| guia_rapida | limites_transaccionales | `limites_transaccionales` | general |
| guia_rapida | faq_cuenta_embargada | `faq_cuenta_embargada` | general |
| pqrs | centrales_de_riesgo | `centrales_de_riesgo` | centrales |
| preguntas_frecuentes | faq_plazos_reporte_negativo | `faq_plazos_reporte_negativo` | general |
| preguntas_frecuentes | faq_definicion_tipos_reporte | `faq_definicion_tipos_reporte` | general |
| preguntas_frecuentes | faq_notificacion_previa_reporte | `faq_notificacion_previa_reporte` | general |
| preguntas_frecuentes | faq_frecuencia_actualizacion_centrales | `faq_frecuencia_actualizacion_centrales` | general |
| preguntas_frecuentes | faq_solicitud_actualizacion_tras_pago | `faq_solicitud_actualizacion_tras_pago` | general |
| trx_no_reconocida | trx_no_reconocida | `trx_no_reconocida` | trx_no_reconocida |
| doble_cobro | doble_cobro | `doble_cobro` | doble_cobro |

## 3. Allowlist de acciones

Clases de efecto:

- **lectura**: Lectura de datos. Sin efecto sobre el cliente ni sus productos.
- **presentacion**: Construye el mensaje que se muestra. Sin efecto.
- **validacion**: Regla determinista que decide el siguiente paso. Sin efecto.
- **derivacion**: Cambia de flujo. Sin efecto.
- **escritura_caso**: Escribe la ficha del caso en OpenSearch. No mueve dinero: el abono lo ejecuta el RPA de Tantia fuera del agente.
- **accion_producto**: Acción sobre un producto del cliente (POST al ASO vía back_trx). Exige autorización del cliente en la App.

| Acción | Clase | Dónde se resuelve | Servicio | Declarada en | Nota |
|---|---|---|---|---|---|
| `bloqueo_permanente_trx` | accion_producto | chat_service._prefetch_trx_data_if_needed (gate por paso) | back_trx /bloqueo (ASO) | trx_no_reconocida:2.4.0.1.17.2 | gate 2.4.0.1.17.2; antes 2.4.0.1.17.1 pide autorización en la App; candado durable contra reejecución |
| `bloqueo_temporal_trx` | accion_producto | chat_service._prefetch_trx_data_if_needed (gate por paso) | back_trx /bloqueo (ASO) | trx_no_reconocida:2.4.0.1.16.2 | gate 2.4.0.1.16.2; antes 2.4.0.1.16.1 pide autorización en la App; candado durable contra reejecución |
| `build_satisfaction_check_message` | presentacion | workflow_actions.py (if-chain) | - | shared:satisfaction_check, shared:satisfaction_check_faq |  |
| `build_satisfaction_no_message` | presentacion | workflow_actions.py (if-chain) | - | shared:satisfaction_no |  |
| `build_satisfaction_si_message` | presentacion | workflow_actions.py (if-chain) | - | shared:satisfaction_si |  |
| `cierre_bucle_trx` | validacion | chat_service._prefetch_trx_data_if_needed (gate por paso) | - | trx_no_reconocida:2.4.0.1.20.0 | gate 2.4.0.1.20.0: otra transacción o fin |
| `confirmar_movimiento_trx` | presentacion | workflow_actions.py (if-chain) | - | trx_no_reconocida:2.4.0.1.11 | el cliente confirma que NO reconoce ese movimiento |
| `consultar_centrales_producto_seleccionado` | lectura | workflow_actions.py (if-chain) | back_data | centrales_de_riesgo:1.4.1.1.1.1 |  |
| `consultar_detalle_trx` | lectura | chat_service._prefetch_trx_data_if_needed (gate por paso) | back_trx /detalle (ASO operations) | trx_no_reconocida:2.4.0.1.10 | gate 2.4.0.1.10 |
| `consultar_estado_doble_cobro` | lectura | workflows/doble_cobro_hook.py (prefetch por paso) | OpenSearch trx-no-reconocida-cases | doble_cobro:3.4.0.8 |  |
| `consultar_movimientos_trx` | lectura | chat_service._prefetch_trx_data_if_needed (gate por paso) | back_trx /movimientos-aso (ASO financial-overview + transactions) | trx_no_reconocida:2.4.0.1.8 | gate 2.4.0.1.8, vigencia por franquicia |
| `consultar_notificacion_producto_seleccionado` | lectura | workflow_actions.py (if-chain) | back_data | centrales_de_riesgo:1.4.1.3.1 |  |
| `consultar_productos_cliente` | lectura | workflow_actions.py (if-chain) | back_data | centrales_de_riesgo:1.4.1.1, centrales_de_riesgo:1.4.1.3.0 | productos del cliente para el selector |
| `consultar_productos_consulta_sin_permiso` | lectura | workflow_actions.py (if-chain) | back_data | centrales_de_riesgo:1.4.1.2 |  |
| `consultar_recurrencia_salesforce` | lectura | chat_service._prefetch_trx_data_if_needed (gate por paso) | back_trx /validar-recurrencia | trx_no_reconocida:2.4.0.1 | gate 2.4.0.1: recurrencia Salesforce y del bot |
| `consultar_todos_productos_centrales` | lectura | workflow_actions.py (if-chain) | back_data | centrales_de_riesgo:1.4.1.0 |  |
| `consultar_todos_productos_centrales_sin_notificacion` | lectura | workflow_actions.py (if-chain) | back_data | centrales_de_riesgo:1.4.1.3 |  |
| `goto_centrales_de_riesgo` | derivacion | workflow_actions.py (if-chain) | - | shared:faq_no_goto_centrales |  |
| `goto_extractos_bancarios` | derivacion | workflow_actions.py (if-chain) | - | centrales_de_riesgo:1.4.1.3.4 |  |
| `mostrar_bloqueo_definitivo_trx` | presentacion | workflow_actions.py (if-chain) | - | trx_no_reconocida:2.4.0.1.17.3 |  |
| `mostrar_bloqueo_temporal_trx` | presentacion | workflow_actions.py (if-chain) | - | trx_no_reconocida:2.4.0.1.16.3 |  |
| `mostrar_grupos_doble_cobro` | lectura | workflows/doble_cobro_hook.py (prefetch por paso) | back_doble_cobro /grupos-duplicados (ASO) | doble_cobro:3.4.0.6 | paginado, selección múltiple |
| `mostrar_movimientos_trx` | presentacion | workflow_actions.py (if-chain) | - | trx_no_reconocida:2.4.0.1.9 |  |
| `mostrar_productos_activos_dc` | lectura | actions/doble_cobro.py (registro) | back_doble_cobro /productos-activos | doble_cobro:3.4.0.1 |  |
| `mostrar_productos_activos_trx` | lectura | workflow_actions.py (if-chain) | - | trx_no_reconocida:2.4.0.1.5 | selector dinámico con lo ya leído |
| `mostrar_trx_no_reconocida` | presentacion | workflow_actions.py (if-chain) | - | trx_no_reconocida:2.4.0.1.19.1 |  |
| `mostrar_trx_reversada` | presentacion | workflow_actions.py (if-chain) | - | trx_no_reconocida:2.4.0.1.19.2 |  |
| `registrar_caso_doble_cobro` | escritura_caso | workflows/doble_cobro_hook.py (prefetch por paso) | OpenSearch trx-no-reconocida-cases | doble_cobro:3.4.0.7 | solo grupos con 2+ cargos iguales; reemplaza el reporte previo equivalente |
| `registrar_devolucion_trx` | escritura_caso | workflow_actions.py (if-chain) + chat_service._prefetch_trx_data_if_needed (gate por paso) | OpenSearch trx-no-reconocida-cases | trx_no_reconocida:2.4.0.1.20 | hito `devolucion` y fila para el CSV de Tantia; idempotente por huella statementId|movementId |
| `validar_investigacion_trx` | validacion | chat_service._prefetch_trx_data_if_needed (gate por paso) | - | trx_no_reconocida:2.4.0.1.19 | gate 2.4.0.1.19: presencial / reversada / procede |
| `validar_pendiente_trx` | validacion | chat_service._prefetch_trx_data_if_needed (gate por paso) | - | trx_no_reconocida:2.4.0.1.12 | gate 2.4.0.1.12: compra con TDC pendiente |
| `validar_recurrencia_doble_cobro` | validacion | workflows/doble_cobro_hook.py (prefetch por paso) | OpenSearch trx-no-reconocida-cases | doble_cobro:3.4.0.5 | reportes previos del cliente |
| `validar_vigencia_doble_cobro` | validacion | workflows/doble_cobro_hook.py (prefetch por paso) | back_doble_cobro /validar-vigencia | doble_cobro:3.4.0.3 | 7 días hábiles de conciliación |
| `verificar_productos_trx` | lectura | chat_service._prefetch_trx_data_if_needed (gate por paso) | back_trx /productos-activos | trx_no_reconocida:2.4.0.1.4 | gate 2.4.0.1.4 |

34 acciones, 4 con efecto (`escritura_caso`, `accion_producto`). Ninguna sin clasificar.

## 4. Puertas obligatorias antes de cada acción con efecto

Se calculan todos los caminos simples del YAML desde el inicio del flujo hasta el paso de la
acción. *Pasos por los que pasan todos* es la intersección; las puertas esperadas deben estar
dentro. El código añade salidas (fail-closed, formulario), nunca atajos: no existe ninguna
asignación directa de `current_step` a un paso con efecto.

### `registrar_devolucion_trx` (trx_no_reconocida, paso 2.4.0.1.20)

- Caminos desde el inicio: 1 (el más corto, 23 pasos).
- Pasos por los que pasan todos: 2.4.0, 2.4.0.1, 2.4.0.1.1, 2.4.0.1.10, 2.4.0.1.11, 2.4.0.1.12, 2.4.0.1.13, 2.4.0.1.15, 2.4.0.1.17, 2.4.0.1.17.1, 2.4.0.1.17.2, 2.4.0.1.17.3, 2.4.0.1.18, 2.4.0.1.19, 2.4.0.1.2, 2.4.0.1.3, 2.4.0.1.4, 2.4.0.1.5, 2.4.0.1.6, 2.4.0.1.7, 2.4.0.1.8, 2.4.0.1.9
- Puertas esperadas:
  - ✓ `2.4.0.1.3`: el cliente confirma datos de contacto y el tope de 3 transacciones de $35.000 a $500.000
  - ✓ `2.4.0.1.6`: rango de valor: fuera de $35.000-$500.000 va al formulario
  - ✓ `2.4.0.1.11`: el cliente confirma que NO reconoce el movimiento
  - ✓ `2.4.0.1.12`: regla: compra con TDC pendiente no procede
  - ✓ `2.4.0.1.13`: el cliente pide investigar
  - ✓ `2.4.0.1.19`: regla: presencial / reversada / procede

### `bloqueo_temporal_trx` (trx_no_reconocida, paso 2.4.0.1.16.2)

- Caminos desde el inicio: 1 (el más corto, 19 pasos).
- Pasos por los que pasan todos: 2.4.0, 2.4.0.1, 2.4.0.1.1, 2.4.0.1.10, 2.4.0.1.11, 2.4.0.1.12, 2.4.0.1.13, 2.4.0.1.15, 2.4.0.1.16, 2.4.0.1.16.1, 2.4.0.1.2, 2.4.0.1.3, 2.4.0.1.4, 2.4.0.1.5, 2.4.0.1.6, 2.4.0.1.7, 2.4.0.1.8, 2.4.0.1.9
- Puertas esperadas:
  - ✓ `2.4.0.1.11`: el cliente confirma que NO reconoce el movimiento
  - ✓ `2.4.0.1.15`: el cliente elige el tipo de bloqueo
  - ✓ `2.4.0.1.16`: el cliente confirma apagar la tarjeta
  - ✓ `2.4.0.1.16.1`: autorización del cliente en la App (subida de nivel)

### `bloqueo_permanente_trx` (trx_no_reconocida, paso 2.4.0.1.17.2)

- Caminos desde el inicio: 1 (el más corto, 19 pasos).
- Pasos por los que pasan todos: 2.4.0, 2.4.0.1, 2.4.0.1.1, 2.4.0.1.10, 2.4.0.1.11, 2.4.0.1.12, 2.4.0.1.13, 2.4.0.1.15, 2.4.0.1.17, 2.4.0.1.17.1, 2.4.0.1.2, 2.4.0.1.3, 2.4.0.1.4, 2.4.0.1.5, 2.4.0.1.6, 2.4.0.1.7, 2.4.0.1.8, 2.4.0.1.9
- Puertas esperadas:
  - ✓ `2.4.0.1.11`: el cliente confirma que NO reconoce el movimiento
  - ✓ `2.4.0.1.15`: el cliente elige el tipo de bloqueo
  - ✓ `2.4.0.1.17`: el cliente confirma el bloqueo definitivo
  - ✓ `2.4.0.1.17.1`: autorización del cliente en la App (subida de nivel)

### `registrar_caso_doble_cobro` (doble_cobro, paso 3.4.0.7)

- Caminos desde el inicio: 1 (el más corto, 8 pasos).
- Pasos por los que pasan todos: 3.4.0, 3.4.0.1, 3.4.0.2, 3.4.0.3, 3.4.0.4, 3.4.0.5, 3.4.0.6
- Puertas esperadas:
  - ✓ `3.4.0.3`: regla: vigencia de la fecha (conciliación de 7 días hábiles)
  - ✓ `3.4.0.5`: regla: reportes previos equivalentes
  - ✓ `3.4.0.6`: el cliente selecciona los cobros y pulsa reportar

Saltos directos del código a pasos con efecto: **ninguno**.

## 5. Parámetros que leen los gates

| Variable | Valor por defecto en código |
|---|---|
| `DIAS_HABILES_DEVOLUCION` | `10` |
| `LLM_CLOSURE_ENABLED` | `false` |
| `MAX_TRX_BOT_RECURRENCE` | `1` |
| `VIGENCIA_MASTER_DIAS` | `120` |
| `VIGENCIA_VISA_DIAS` | `180` |

Topes y portones en `.env.example` del agente:

| Variable | Valor de ejemplo |
|---|---|
| `MAX_DAILY_SESSIONS` | `3` |
| `MAX_DAILY_CATEGORY_INTERACTIONS` | `100` |
| `TRX_FLOW_ENABLED` | `true` |
| `MAX_TRX_BOT_RECURRENCE` | `1000` |

Los topes del flujo TXNR que vienen del propio YAML: hasta 3 transacciones por trámite y
valores entre $35.000 y $500.000 (paso 2.4.0.1.6); fuera de eso, formulario PQR.
