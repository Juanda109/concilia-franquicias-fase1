# Guía de Pruebas de Flujos — Agente PQRs

Esta guía indica, para **cada camino mapeado en los YAML** del agente y para las
funcionalidades de `co_pqrs_back_data`, **qué `customer_id` usar**, **qué decirle al
agente** y **la respuesta esperada**.

> Fuente de datos verificada: tabla `ada_info_detail` (Postgres), cargada desde
> `pqrs_ada_data_20260601_part_1.parquet`, cruzada con los JSON mockeados de centrales
> `co_pqrs_back_data/data/commercial_info_{personal_id}.json`. Los `customer_id` de la
> Parte B fueron verificados ejecutando la lógica real de
> `co_pqrs_back_data/src/application/customer/consultar_service.py` sobre esos datos.

---

## 0. Cómo probar (mínimo)

El flujo real es:

```
POST /start  { "user_id": "<customer_id>" }          -> crea conversation_id = <customer_id>_<yyyymmdd>
POST /chat   { "conversation_id": "...", "content": "<frase>" }
```

- El `customer_id` se extrae del **prefijo** del `conversation_id`
  (`_extract_customer_id` en `chat_service.py`). La comparación **ignora ceros a la
  izquierda** (`04167712` ≡ `4167712`).
- El **primer** `POST /chat` con la frase libre dispara el router (LLM + `general.yml`),
  que **auto-inicia** el workflow identificado (no pide confirmación).
- **Parte A (informativos):** el `customer_id` es indiferente; puedes usar cualquiera
  válido, p. ej. `04167712`.
- **Parte B (Centrales de Riesgo):** el `customer_id` **sí importa** porque determina el
  `id_msg` que `co_pqrs_back_data` escribe en OpenSearch (`client-control-table`) y que
  el agente luego lee. Usa el `customer_id` indicado en cada caso.

Mecanismo Centrales: agente → fire-and-forget a `co_pqrs_back_data`
(`/consultar`, `/centrales_no_autorizo`, `/notificacion_centrales`) → back_data escribe
en OpenSearch → el agente hace polling y renderiza el mensaje de `responses.yml`.

---

## Parte A — Workflows informativos (17 caminos)

Estos workflows **no dependen del `customer_id`**. La "frase para el agente" está tomada
de los `examples` de `general.yml` (diseñados para rutear con alta confianza). La
respuesta esperada es el **texto del paso `1`/`respuesta`** del YAML del workflow.

Tras mostrar la información, el paso ofrece **`Continuar`** (responde `1` o `Continuar`),
que lleva a la verificación de satisfacción:
- `satisfaction_check` (hazlo_tu_mismo, guia_rapida) o `satisfaction_check_faq`
  (preguntas_frecuentes): pregunta *"¿Te ha ayudado esta información?"*.
  - Responder **`1` / "Sí"** → mensaje de despedida y cierre.
  - Responder **`2` / "No"** → línea de atención `601 401 0000` (o, en FAQ, te conecta
    al flujo de Centrales de Riesgo).

`customer_id` sugerido para toda la Parte A: **`04167712`**.

### A.1 Grupo `hazlo_tu_mismo` (8)

| # | Workflow | Frase para el agente | Respuesta esperada (resumen del YAML) |
|---|----------|----------------------|----------------------------------------|
| 1 | `certificado_de_cuenta` | "¿Cómo descargo una certificación de mi cuenta?" | Pasos para descargar el certificado de cuenta desde App BBVA (Más → Ver certificados) y BBVA Net (Descarga tus certificados → Certificado de cuenta). |
| 2 | `consulta_de_movimientos` | "¿Dónde veo lo que gasté ayer?" | Pasos para consultar movimientos en App (Buscar movimientos, filtros) y BBVA Net (descarga Excel/PDF). |
| 3 | `certificado_tributario` | "¿Dónde bajo mis certificados para la declaración de renta?" | Pasos App (Opera → Certificados tributarios → Enviar a mi correo) y BBVA Net (Otros certificados → Tributarios). |
| 4 | `extractos_bancarios` | "Necesito descargar el extracto de mi cuenta" | Pasos App (Más → Ver extractos, últimos 24 meses) y BBVA Net (Extractos). Para +24 meses: `601 4010000`. |
| 5 | `paz_y_salvo` | "Ya pagué todo, ¿dónde saco mi paz y salvo?" | Pasos en BBVA Net (Descarga tus certificados → Otros certificados → Paz y Salvo). |
| 6 | `solicitud_de_documentos_leasing` | "Necesito un certificado de mi operación de leasing" | Correo `postventaleasingcolombia@bbva.com`, lunes a viernes 8:00 a.m.–6:00 p.m. |
| 7 | `certificado_de_deuda` | "Necesito el certificado de deuda para llevarme mi cuenta a otro banco" | Formulario en bbva.com.co (Certificado de deuda); un asesor llama para gestionar la entrega. |
| 8 | `certificados_fondos_de_inversion` | "¿Dónde bajo el extracto de mi fondo de inversión?" | Pasos App (Inversiones → Ver detalles y extractos). Contraseña = número de identificación. Correo `sugerencias.reclamos.fiduciaria@bbva.com`. |

### A.2 Grupo `guia_rapida` (4)

| # | Workflow | Frase para el agente | Respuesta esperada (resumen del YAML) |
|---|----------|----------------------|----------------------------------------|
| 9 | `impuesto_4x1000` | "¿Qué es ese cobro de GMF que me sale en el extracto?" | Explica el GMF (4x1.000): qué es, 0,4%, el banco solo recauda. Enlace al blog. Línea `601 4010000`. |
| 10 | `puntos_y_promociones` | "¿Dónde veo mis puntos BBVA?" | Pasos en BBVA Net → Experiencias BBVA (movimientos de puntos, simulador, promociones). Línea `601 4010000`. |
| 11 | `cuota_de_manejo` | "¿Por qué me están cobrando cuota de manejo?" | Tabla de teléfonos de atención por ciudad para asesoría personalizada. |
| 12 | `limites_transaccionales` | "No me deja transferir tanta plata" | Pasos App (Configuración → Límites operacionales, editar con Token). Notas de seguridad y Net Cash corporativo. |

> Nota: en `guia_rapida` el mensaje de cierre lo redacta el LLM (closure amigable),
> por lo que el texto exacto puede variar respecto al YAML, pero el contenido informativo
> es el del paso `1`.

### A.3 Grupo `preguntas_frecuentes` (5)

| # | Workflow | Frase para el agente | Respuesta esperada (resumen del YAML) |
|---|----------|----------------------|----------------------------------------|
| 13 | `faq_plazos_reporte_negativo` | "Ya pagué mi deuda, ¿cuándo me borran de Datacrédito?" | Permanencia: mora <2 años = doble del tiempo en mora; mora ≥2 años = hasta 4 años. La info positiva permanece. |
| 14 | `faq_definicion_tipos_reporte` | "¿Qué significa estar reportado?" | Explica reporte positivo (pagos a tiempo) vs negativo (retrasos/deudas). |
| 15 | `faq_notificacion_previa_reporte` | "¿Me tienen que avisar antes de reportarme?" | Ley 1266 (Habeas Data): aviso previo con ≥20 días, normalmente en el extracto. |
| 16 | `faq_frecuencia_actualizacion_centrales` | "Ya pagué hace dos días y sigo apareciendo reportado" | El reporte a centrales es **una vez al mes**; depende de la fecha de corte. |
| 17 | `faq_solicitud_actualizacion_tras_pago` | "¿Tengo que mandar el recibo de pago a algún lado para que me quiten el reporte?" | No requiere trámite; BBVA reporta automáticamente cada mes en el siguiente ciclo. |

> En las FAQ, responder **`2` / "No"** en la verificación lleva al flujo de
> **Centrales de Riesgo** (`satisfaction_check_faq` → `goto_centrales_de_riesgo`,
> paso `1.4.1`).

---

## Parte B — Centrales de Riesgo (data-driven)

### B.0 Entrada y ramas

Workflow `centrales_de_riesgo`, paso inicial `1.4.1` (con `smart_route`). Frase de
entrada general, p. ej.: **"No reconozco un reporte en centrales de riesgo"** o
**"Mi cuenta aparece embargada"**.

El paso `1.4.1` presenta 3 opciones (el `smart_route` puede saltar directo a una según
tu frase; si no, muestra el menú y eliges `1`/`2`/`3`):

| Opción | Texto | Rama (next_step) | Endpoint back_data |
|--------|-------|------------------|--------------------|
| `1` | "No estoy de acuerdo con mi reporte en centrales de Riesgo" | `1.4.1.0` | `/consultar` |
| `2` | "Consultaron mi información en centrales de riesgo sin mi autorización" | `1.4.1.2` | `/centrales_no_autorizo` |
| `3` | "Tengo un reporte negativo en centrales de riesgo y no recibí notificación" | `1.4.1.3` | `/notificacion_centrales` |

En `1.4.1.0`, si **todos** los productos están al día (`id_msg=1`) el agente responde de
inmediato con el mensaje agregado (`id_msg=2`) y cierra. Si hay hallazgos, muestra la
**lista de productos** (solo los productos con novedad), eliges el número del producto
(`1`, `2`, …) y el agente renderiza el mensaje del `id_msg` correspondiente.

Tras cada respuesta de negocio, el flujo pasa a `satisfaction_check`
(`1` = me ayudó / cierre; `2` = línea `601 401 0000`).

---

### B.1 Rama 1 — "No estoy de acuerdo" (`1.4.1.0` → `/consultar`)

El selector `1.4.1` también ofrece rutas independientes dentro de
`centrales_de_riesgo` para **Embargos/desembargos** y **Venta o cesión de
cartera**. Ambas usan la misma consulta `/consultar`, pero solo muestran
productos con los hallazgos propios de la ruta. En Embargos, primero se
muestran únicamente los embargos vigentes (`id_msg` 12). Si existen
desembargos registrados (`id_msg` 11), el agente pregunta si el cliente desea
consultarlos y solo los lista tras elegir **Sí, consultar**. Si solo existen
desembargos, informa primero que no hay embargos vigentes y ofrece esa misma
consulta opcional. Si los productos pasivos no tienen embargo (`id_msg` 1),
muestra su tipo y los últimos cuatro dígitos del contrato antes de continuar.
Venta de cartera muestra `id_msg` 3 o 19. Si no hay
coincidencias, la ruta finaliza con su mensaje específico.

Secuencia común:
1. `POST /start` con el `customer_id` indicado.
2. `POST /chat`: **"No reconozco un reporte en centrales de riesgo"** (o elige opción `1`).
3. El agente consulta `/consultar`. Si hay novedad, muestra la lista de productos →
   responde con el **número** del producto.
4. El agente muestra el mensaje del `id_msg`.

| Escenario | `id_msg` | `customer_id` | Qué decir / pasos | Respuesta esperada (`responses.yml`) |
|-----------|----------|---------------|-------------------|--------------------------------------|
| Todo al día (agregado) | **2** | `04167712` | Opción `1` "No estoy de acuerdo". (No pide producto.) | Msg 2: *"¡Buenas noticias! He terminado la revisión y no tienes reportes negativos en las centrales de riesgo asociados a ninguno de tus productos…"* |
| Mora (reporte negativo) | **4** | `07667553` | Opción `1` → selecciona el producto **`*1843`** | Msg 4: *"Validé tu caso y encontré que tienes un reporte negativo asociado a tu producto [{tipo_producto} / número terminado en 1843], generado por {tipo}…"* (variables: `key_id_last=1843`, `tipo=activo_mora`). |
| Cuenta pasiva sin embargo | **9** | `01214447` | Opción `1` → selecciona el producto **`*2536`** | Msg 9: *"Revisé tu caso y encontré que tu cuenta no presenta bloqueos y la información reportada coincide con tu estado actual en el banco: Estado de tu cuenta: Status Actualizado, sin embargo"*. |
| Cartera vendida | **19** | `00203498` | Opción `1` → selecciona el producto **`*2320`** | Msg 19: *"Revisé tu caso y encontré que tu {tipo} terminado en 2320 fue vendido a BANCA INVERSIONES COMPRA CART. SAS. Esta operación se realizó siguiendo la normativa vigente…"*. |
| Cartera castigada (pasado) | **20** | `06848639` | Opción `1` → selecciona el producto **`*1629`** | Msg 20: *"Validé tu caso y encontré el motivo del reporte… cartera castigada por impago. Tiempo de permanencia… contado desde {Fecha inicio mora}"* (Fecha inicio mora `2023-05-25`). |
| Cartera castigada (vigente) | **21** | `03128991` | Opción `1` → selecciona el producto **`*2304`** | Msg 21: *"Validé tu caso y encontré el motivo del reporte… cartera castigada por impago. Tiempo de permanencia de {Meses en mora} meses…"* (Meses en mora ≈ `15`). |

Alternativas con el mismo resultado:
- `id_msg 4`: también `03128991`, `07851843`.
- `id_msg 19`: también `07854192`, `08123456`, `06234567`, `05445678`.
- `id_msg 20`: también `07851843`.

---

### B.2 Rama 2 — "Consultaron sin autorización" (`1.4.1.2` → `/centrales_no_autorizo`)

Secuencia:
1. `POST /start` con el `customer_id`.
2. `POST /chat`: **"Consultaron mi información en centrales de riesgo sin mi autorización"**
   (o elige opción `2`).
3. El agente responde directamente (no pide producto).

| Escenario | `id_msg` | `customer_id` | Respuesta esperada (`responses.yml`) |
|-----------|----------|---------------|--------------------------------------|
| Tiene producto **ACTIVO** (consulta autorizada / "huella") | **14** | `01227510` | Msg 14: *"{detalle_consulta_autorizada} … es solo una 'huella' de consulta necesaria para el proceso y no es un reporte negativo. Tu historial crediticio sigue intacto."* |
| **Sin** producto activo (escalamiento a PQRS) | **15** | `01232829` | Msg 15 (variante): *"Tu caso requiere una revisión a fondo… completa el siguiente formulario… [enlace al formulario de PQRS]"* + opción `radicar_pqrs`. |

Alternativas:
- `id_msg 14`: también `06848639`, `07667553`, `03128991`, `07851843`, `00203498`.
- `id_msg 15`: también `04167712`, `07136263`, `07679301`, `07732016`, `03218596`.

---

### B.3 Rama 3 — "Reporte negativo sin notificación" (`1.4.1.3` → `/notificacion_centrales`)

Secuencia:
1. `POST /start` con el `customer_id`.
2. `POST /chat`: **"Tengo un reporte negativo en centrales de riesgo y no recibí notificación"**
   (o elige opción `3`).
3. El agente responde directamente (no pide producto).

| Escenario | `id_msg` | `customer_id` | Respuesta esperada (`responses.yml`) |
|-----------|----------|---------------|--------------------------------------|
| Sin reporte en centrales | **18** | `01227510` | Msg 18: *"¡Buenas noticias! He terminado la validación y no tienes reportes negativos en las centrales de riesgo asociados a tu {tipo} terminado en {key_id_last}…"* |
| Adelanto de nómina / sin extracto disponible (escalamiento) | **17** | `09889012` | Msg 17 (variante): *"Tu caso requiere una revisión a fondo… [enlace al formulario de PQRS]"* + opción `radicar_pqrs`. |

Alternativas:
- `id_msg 17`: también `10990123`, `11001234`.

> **`id_msg 16`** (notificación entregada por extracto, con fecha y correo anonimizado)
> requiere la API ASO real para descargar el extracto. En el entorno mock/offline ese
> camino degrada a `id_msg 17`, por lo que **no es reproducible** sin ASO.

---

## Apéndice 1 — Cobertura de `id_msg` (responses.yml)

| `id_msg` | Escenario | ¿Reproducible con la data actual? | Notas |
|----------|-----------|-----------------------------------|-------|
| 1 | Producto al día | ✅ (interno) | A nivel de producto; el agregado se muestra como msg 2. |
| 2 | Todos los productos al día | ✅ | `04167712`. |
| 3 | Cartera vendida con datos del nuevo acreedor | ❌ TODO | `tenemos_info=False` hardcodeado en `consultar_service.py`. |
| 4 | Reporte negativo por mora | ✅ | `07667553`. |
| 5 | Reporte negativo (motivo genérico) | ❌ | No producido por back_data. |
| 6 | Castigo solo en centrales | ❌ | No hay pareja "solo centrales" en la data. |
| 7 | (placeholder "validar") | ❌ | Mensaje incompleto en YAML. |
| 8 | Productos sin bloqueo (lista) | ❌ | No producido por back_data. |
| 9 | Cuenta pasiva sin embargo | ✅ | `01214447`. |
| 10 | Embargo levantado | ❌ | No producido por back_data. |
| 11 | Embargo levantado (variante) | ❌ | No producido por back_data. |
| 12 | Embargo vigente (BBVA + centrales) | ❌ | Requiere `origin_flag=PASIVE` + `blocking_type∈{P,E,5}` + obligación `ACEMB/INEMB` BBVA que cruce por `key_id`; no existe esa combinación en la data actual. |
| 13 | Embargo solo en centrales | ❌ | Requiere `ACEMB/INEMB` sin bloqueo BBVA; no existe en la data. |
| 14 | Consulta autorizada ("huella") | ✅ | `01227510` (rama 2). |
| 15 | Consulta sin permiso → PQRS | ✅ | `01232829` (rama 2). |
| 16 | Notificación por extracto | ⚠️ Requiere ASO | Degrada a 17 sin la API ASO real. |
| 17 | Adelanto nómina / sin extracto → PQRS | ✅ | `09889012` (rama 3). |
| 18 | Sin reporte en centrales | ✅ | `01227510` (rama 3). |
| 19 | Cartera vendida (sin datos del acreedor) | ✅ | `00203498`. |
| 20 | Cartera castigada (pasado) | ✅ | `06848639`. |
| 21 | Cartera castigada (vigente) | ✅ | `03128991`. |
| 22 | Mora solo en centrales | ❌ | No hay pareja "solo centrales" en la data. |
| 99 | Hallazgo solo en BBVA (mora/castigo/embargo) | ❌ Sin mensaje | `consultar_service.py` lo emite (TODO) pero `responses.yml` no tiene texto → fallback de error. Aparece, p. ej., en `06848639` (segundo producto). |

Resumen reproducible end-to-end hoy: **1/2, 4, 9, 14, 15, 17, 18, 19, 20, 21**.

---

## Apéndice 2 — Verificación directa de `co_pqrs_back_data` (opcional)

Para validar el back_data de forma aislada (sin el agente), llama los endpoints
directamente; el resultado se persiste en OpenSearch (`client-control-table`) y la
estructura relevante es `hallazgos.validaciones[].hallazgos[].id_msg`.

```bash
# Carga datos de productos + centrales (rama "No estoy de acuerdo")
curl -X POST "<BACK_DATA_URL>/consultar?customer_id=07667553&workflow=centrales_de_riesgo"

# Consulta sin autorización
curl -X POST "<BACK_DATA_URL>/centrales_no_autorizo?customer_id=01227510&workflow=centrales_de_riesgo"

# Reporte sin notificación
curl -X POST "<BACK_DATA_URL>/notificacion_centrales?customer_id=09889012&workflow=centrales_de_riesgo"
```

`id_msg` esperado por `customer_id` (verificado contra la lógica real):

| Endpoint | `customer_id` | `id_msg` esperado |
|----------|---------------|-------------------|
| `/consultar` | `04167712` | todos `1` (agregado → 2) |
| `/consultar` | `07667553` | `4` (key_id `1843`) + `1` (key_id `1900`) |
| `/consultar` | `01214447` | `9` |
| `/consultar` | `00203498` | `19` |
| `/consultar` | `06848639` | `20` + `99` |
| `/consultar` | `03128991` | `21` + `4` |
| `/centrales_no_autorizo` | `01227510` | `14` |
| `/centrales_no_autorizo` | `01232829` | `15` |
| `/notificacion_centrales` | `09889012` | `17` |
| `/notificacion_centrales` | `01227510` | `18` |

> Nota: el `GET /consultar?customer_id=...` documentado en el README devuelve la misma
> estructura de forma síncrona, útil para inspección rápida.
