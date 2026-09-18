# Documento de Entendimiento del Flujo

## Flujo analizado
No estoy de acuerdo con mi reporte en centrales de riesgo.
Enfoque especifico: productos del pasivo.

## Objetivo
Este documento resume el flujo en dos vistas:
- Vista funcional: que pasa para el usuario y que resultado recibe.
- Vista tecnica: que componentes, clases, metodos, campos e id_msg intervienen.

Tambien incluye una mini guia para preparar pruebas funcionales.

---

## 1. Vista funcional del flujo

### 1.1 Entrada al flujo
1. El cliente llega al flujo de Centrales de Riesgo.
2. Selecciona la opcion: No estoy de acuerdo con mi reporte en centrales de riesgo.
3. El sistema inicia una consulta de estado de productos y, si detecta novedades, muestra una lista de productos para seleccionar.

### 1.2 Que evalua el negocio para productos del pasivo
Para cada producto de pasivo, el sistema cruza informacion de dos fuentes:
- Estado interno BBVA (tabla de identidad/detalle de producto).
- Hallazgos de centrales (respuesta de commercial info).

Con ese cruce decide el escenario:
1. Embargo en BBVA y en centrales.
2. Embargo solo en centrales.
3. Sin embargo (estado actualizado, sin novedad de embargo).
4. Embargo solo en BBVA (caso tecnico marcado como pendiente de confirmacion funcional).

### 1.3 Mensaje que ve el cliente segun escenario (id_msg)
- id_msg 12: embargo vigente con detalle de entidad y oficio.
- id_msg 13: requiere revision/PQRS (embargo reportado solo en centrales).
- id_msg 9: estado actualizado, sin embargo.
- id_msg 99: caso de discrepancia BBVA vs centrales sin mensaje funcional final definido en catalogo.

### 1.4 Comportamiento de cierre
- Si todos los productos quedan sin hallazgos negativos, se informa estado positivo general (sin reporte negativo) y el flujo pasa a satisfaccion.
- Si existen hallazgos, el cliente selecciona producto y recibe respuesta especifica por id_msg.
- Si hay error de consulta/polling, se responde con mensaje de contingencia para evitar informacion falsa.

### 1.5 Resumen funcional corto
- El flujo no responde solo por texto libre: decide por reglas.
- La regla principal en pasivo es el estado de embargo cruzado BBVA vs centrales.
- El resultado final visible al cliente depende del id_msg calculado.

---

## 2. Vista tecnica del flujo

### 2.1 Componentes principales

#### co_pqrs_back_agent
- Orquesta conversacion, workflow y render de respuesta final.
- Dispara consulta a back_data y consume resultado desde control table.

#### co_pqrs_back_data
- Ejecuta logica de cruce de datos.
- Calcula hallazgos con id_msg.
- Persiste envelope (status/run_id/data/error) en OpenSearch para que agent lo recupere.

### 2.2 Secuencia tecnica end-to-end
1. El workflow entra a paso 1.4.1 (centrales_de_riesgo).
2. Al elegir reporte_no_reconocido_o_incorrecto, avanza a 1.4.1.0.
3. chat_service hace prefetch a /consultar en back_data con run_id.
4. back_data procesa en background y guarda resultado por workflow en control table.
5. agent hace polling y solo acepta resultado fresco (run_id coincidente).
6. workflow_actions procesa hallazgos:
   - si todo ok, mensaje general.
   - si hay hallazgos, construye selector dinamico (1.4.1.1).
7. usuario elige producto y se ejecuta 1.4.1.1.1.1.
8. se toma el hallazgo principal del producto, se resuelve id_msg y se renderiza template de responses.yml.

### 2.3 Archivos y metodos clave

#### Definicion del flujo
- src/domain/workflow/pqrs/centrales_de_riesgo/centrales_de_riesgo.yml
  - start_step 1.4.1
  - save_as tipo_inconveniente_centrales_de_riesgo
  - paso 1.4.1.0 action consultar_todos_productos_centrales
  - paso 1.4.1.1 save_as producto_centrales_de_riesgo
  - paso 1.4.1.1.1.1 action consultar_centrales_producto_seleccionado

#### Orquestacion agent
- src/application/chat/chat_service.py
  - _prefetch_back_data_if_needed(...)
  - _load_back_data_from_control_table(...)
  - _apply_current_step_action_if_needed(...)
  - process_chat_message(...)

#### Acciones de workflow en agent
- src/application/chat/workflow_actions.py
  - execute_workflow_action(...)
  - _load_all_products_central_risk(...)
  - _load_selected_product_central_risk(...)
  - _resolve_centrales_variables(...)
  - _load_centrales_response(...)
  - _build_product_from_back_data_entry(...)
  - _override_product_prompt_from_back_data(...)

#### API y logica de back_data
- src/infrastructure/entrypoint/api/router/v0/consultar_router.py
  - POST /consultar
- src/application/customer/consultar_service.py
  - read_json_centrales(...)
  - build_data_from_customer_df_and_centrales(...)
  - process_consultar_customer_request(...)

#### Persistencia envelope
- src/infrastructure/persistence/opensearch_client.py
  - update_client_control_data(...)
- (agent) src/infrastructure/persistence/control_table_store.py
  - get_workflow_back_data_envelope(...)
  - clear_workflow_back_data(...)

### 2.4 Campos tecnicos relevantes y origen

#### Entrada de usuario/workflow (agent)
- flow_answers.tipo_inconveniente_centrales_de_riesgo
- flow_answers.producto_centrales_de_riesgo

#### Campos internos agent (captured_data)
- back_data_run_id
- back_data_status
- back_data_result
- centrales_riesgo_back_data_map
- dynamic_option_labels_1.4.1.1
- centrales_riesgo_form_option

#### Datos de origen en back_data
Origen BBVA (tabla detalle/identidad):
- origin_flag
- blocking_type
- key_id
- contract_status_type_desc
- seizure_issuing_court_name
- court_order_id
- court_order_entry_date

Origen commercial info (centrales):
- obligations[].financialInstitutionInformation.name (filtro BBVA)
- obligations[].classificationStatus.id (ej. ACEMB, INEMB)

### 2.5 id_msg involucrados (foco pasivo)

#### id_msg de negocio pasivo
- 12: embargo en BBVA y centrales.
- 13: embargo solo en centrales.
- 9: sin embargo en ambos.
- 99: embargo solo BBVA (pendiente de definicion funcional final).

#### id_msg de control del mismo camino
- 1: producto sin hallazgos.
- 2: todos los productos revisados sin reporte negativo.

### 2.6 Reglas de decision pasivo en back_data
En build_data_from_customer_df_and_centrales(...), cuando origin_flag == PASIVE:
1. blocking_type en {P,E,5} y pasivo en centrales -> id_msg 12.
2. pasivo en centrales pero no blocking interno -> id_msg 13.
3. sin pasivo en centrales y sin blocking interno -> id_msg 9.
4. blocking interno sin pasivo en centrales -> id_msg 99.

### 2.7 Catalogo de mensajes
Las respuestas finales por id_msg se toman de:
- src/domain/workflow/pqrs/centrales_de_riesgo/responses.yml

---

## 3. Guia rapida para pruebas del flujo

### 3.1 Preparacion
1. Tener datos de cliente con productos PASIVE en la fuente configurada.
2. Verificar que exista correspondencia por key_id entre fuente BBVA y hallazgos de centrales.
3. Confirmar que back_data escribe envelope en control table para workflow centrales_de_riesgo.

### 3.2 Casos minimos a probar
1. Caso id_msg 12 (embargo en ambos).
   - Esperado: mensaje de embargo vigente con detalles de entidad/oficio.
2. Caso id_msg 13 (solo centrales).
   - Esperado: mensaje de escalamiento/PQRS.
3. Caso id_msg 9 (sin embargo).
   - Esperado: mensaje de estado actualizado sin embargo.
4. Caso id_msg 99 (solo BBVA).
   - Esperado tecnico: id_msg generado; validar comportamiento fallback en agent.
5. Caso all-ok (solo id_msg 1 por producto).
   - Esperado: mensaje global equivalente a id_msg 2 en paso de revision total.

### 3.3 Validaciones tecnicas recomendadas
- Verificar que run_id del trigger y run_id del envelope coincidan.
- Verificar que si status != ok no se use back_data_result viejo.
- Verificar que dynamic_option_labels_1.4.1.1 tenga la misma cantidad de productos hallados.
- Verificar que la opcion seleccionada producto_N apunte al hallazgo correcto.

---

## 4. Notas y riesgos
- El id_msg 99 aparece en reglas tecnicas pero no tiene mensaje dedicado en el catalogo responses.yml.
- Hay caminos legacy/fallback en workflow_actions para escenarios donde no se logra despacho directo por id_msg.
- Si falla back_data o polling, el flujo responde con contingencia para evitar falsos positivos.

---

## 5. Referencias internas recomendadas
- docs/casos_prueba_centrales_riesgo.csv
- docs/casos_pendientes_mapeo.csv
- tests/test_application/test_consultar_service.py
- tests/test_application/test_product_options.py
