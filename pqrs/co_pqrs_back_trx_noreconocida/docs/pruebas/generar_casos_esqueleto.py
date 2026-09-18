"""Genera las filas de prueba del flujo trx (arbol del esqueleto 2.4.0.1.x)
para el documento corporativo 'Feedback Chat Bot - Blue PQRs'.

Cabecera identica a la hoja 'Pruebas Integrales'. Numeracion en el bloque
reservado 100+ para no chocar con las 52 filas existentes. Se genera con
script para poder regenerar cuando cambie el tablero sin arrastrar ediciones.

Salida: CASOS_PRUEBA_TRX_ESQUELETO.xlsx (para pegar) y .md (para revisar).
"""

from __future__ import annotations

import pathlib

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

CABECERA = [
    "NO.",
    "Categoria prueba",
    "Responsable Principal de la prueba",
    "Caso de prueba",
    "Pregunta realizada a Blue",
    "Respuesta esperada por Blue",
    "Respuesta otorgada por Blue PQRs",
    "Estatus de la prueba",
    "ESTADO TÉCNICO DEL CASO DE PRUEBA",
    "Observación",
]

CATEGORIA = "Transacción no reconocida"
RESPONSABLE = "Pablo Jarava"
APROBADA = "Aprobada"
PENDIENTE = "Pendiente"
LISTO = "DISPONIBLE PARA PROBAR"

NOTA_ENTORNO = (
    "Entorno local (13/08/2026): esqueleto de feature/PQRSdev, simulador ASO y "
    "Postgres con la matriz de clientes de CLIENTES_SIMULADOR.md. Fecha con "
    "movimientos: 06/08/2026 (los fixtures son absolutos y envejecen)."
)

# (no, caso, cliente, pregunta, esperada, obtenida, estatus, observacion)
CASOS = [
    (100,
     "Cliente con gestión reciente de la misma tipología (recurrencia Salesforce)",
     "1013634958",
     "No reconozco esta compra → Compra presencial o por internet",
     "Detecta la gestión reciente y deriva al formulario sin más preguntas:\n"
     "\"Encontré una gestión reciente relacionada con una transacción no "
     "reconocida...\" con botón Formulario PQR.",
     "\"Encontré una gestión reciente relacionada con una transacción no "
     "reconocida. Para garantizar la seguridad de tus productos y darte una "
     "solución sin duplicar la solicitud...\" · botón Formulario PQR.",
     APROBADA,
     "Re-verificado en F2 (13/08 tarde): con TRX_SALESFORCE_SOURCE=aso la "
     "recurrencia consulta el ASO de Salesforce vía la costura (simulador en "
     "local), sin el mount de workaround de la mañana. Hallazgo H-04 cerrado."),
    (101,
     "Cliente sin productos válidos para el flujo (card_flag=false)",
     "1013634959",
     "Frase → suceso 4 → 1 transacción → Empezar ahora → Sí, continuar",
     "\"Actualmente no tienes productos activos con nosotros para realizar esta "
     "solicitud. Si deseas revisar el estado de tus productos o movimientos, "
     "puedes ingresar a tu app BBVA. Hasta pronto.\" No muestra productos.",
     "Texto exacto del tablero, con botón Terminar. No mostró ningún producto.",
     APROBADA,
     "El copy es el del tablero (\"app BBVA\"), no el del Excel de comunicaciones "
     "(\"canales de atención\"): el conflicto entre fuentes quedó resuelto en "
     "código a favor del tablero."),
    (102,
     "Reporte de más de 3 transacciones",
     "98787954",
     "Frase → suceso 4 → cantidad \"Más de 3\"",
     "\"Para validar el reporte de más de 3 compras no reconocidas, necesitamos "
     "tener la información completa en un solo trámite...\" con Formulario PQR.",
     "Texto esperado, con botón Formulario PQR.",
     APROBADA, ""),
    (103,
     "Fecha fuera del plazo de la franquicia (MASTERCARD, 120 días)",
     "1013634965",
     "...hasta la fecha → escribir 01/01/2025",
     "\"La fecha que ingresaste supera el plazo permitido por las franquicias de "
     "la tarjeta para reportar compras no reconocidas...\" y cierra. No debe "
     "consultar movimientos.",
     "Texto esperado con botón Terminar. La traza confirma que no se llamó al "
     "ASO de movimientos.",
     APROBADA,
     "Pendiente de negocio: el tablero distingue ámbito (VISA nacional 180 / "
     "interoperable e internacional 120); el código aplica sólo marca. Falta "
     "definir de qué campo sale el ámbito (pregunta a Data)."),
    (104,
     "Fecha dentro de plazo sin movimientos (transactions vacío)",
     "1013634966",
     "...producto → fecha 06/08/2026 (cliente sin transacciones)",
     "\"No encontramos compras registradas en la fecha seleccionada para este "
     "producto.\" con TRES salidas: Elegir otra fecha / Seleccionar otro "
     "producto / Terminar consulta.",
     "Texto y las tres salidas presentes.",
     APROBADA, ""),
    (105,
     "Camino feliz: listado, confirmación y entrega a investigación",
     "1013634960",
     "...producto Tarjeta *0060 → fecha 06/08/2026 → COMPRA FALABELLA → "
     "Sí, continuar con el reporte",
     "Listado con los 3 movimientos del día y la opción \"No encuentro la "
     "transacción en este listado\". Confirmación con los datos de la compra y "
     "dos botones (Sí, continuar / No es necesario, ya reconozco la "
     "transacción). Al confirmar, pasa a la pregunta de investigación.",
     "Listado con 3 movimientos + \"No encuentro...\"; confirmación con ambos "
     "botones; tras confirmar: \"Para continuar con tu proceso debemos iniciar "
     "con la investigación de tu caso...\".",
     APROBADA,
     "La cadena completa usó datos reales de las tres fuentes: productos de "
     "Postgres, card-id por financial-overview y movimientos del simulador. "
     "Tiempos medidos por turno: todos los gates respondieron en menos de 250 "
     "ms contra el simulador local (el camino asincrono del 204/polling no se "
     "activa). Desde la investigación en adelante el flujo es de Luis."),
    (106,
     "Listado con un solo movimiento",
     "1013634961",
     "...producto → fecha 06/08/2026 (cliente con 1 movimiento)",
     "Listado con el movimiento y la opción de no encontrar la transacción.",
     "Listado con el movimiento, PERO sin el botón \"No encuentro la "
     "transacción\": sólo aparece cuando hay exactamente 3 movimientos.",
     APROBADA,
     "HALLAZGO H-02 (abierto): con 1-2 movimientos la salida \"no encuentro mi "
     "transacción\" es inaccesible por botones. Decidir si es deliberado."),
    (107,
     "Movimiento en estado pendiente (TDC)",
     "1013634964",
     "...movimiento pendiente → Sí, continuar con el reporte",
     "\"Esta compra se encuentra actualmente en estado pendiente. Esto significa "
     "que el comercio aún la está procesando y podría liberarla o anularla en "
     "los próximos días sin realizar el cobro...\" y finaliza.",
     "Texto esperado con botón Terminar.",
     APROBADA,
     "El estado pendiente se evalúa sobre el detalle (responseOperati); la regla "
     "de 7 días del cruce MC30 del tablero aún no existe en código (tramo del "
     "otro responsable, contrato en definición)."),
    (108,
     "El listado respeta la fecha indicada",
     "10482895",
     "...producto → fecha 05/08/2026 (día sin movimientos para ese cliente)",
     "\"No encontramos compras registradas en la fecha seleccionada...\" — no "
     "debe listar los movimientos de otro día.",
     "Respondió sin movimientos, con las tres salidas. El filtro por fecha "
     "funciona en el listado.",
     APROBADA, ""),
    (109,
     "Fechas ilegibles: repregunta sin consultar",
     "01576905",
     "En la fecha, escribir seguidas: 99/99/9999, luego \"hola\", luego "
     "06/08/2026",
     "Las dos primeras repreguntan (\"No pude leer esa fecha. Escríbela en "
     "formato DD/MM/AAAA...\") sin romper el turno ni consultar movimientos; "
     "la tercera lista los movimientos del día correcto.",
     "Repreguntó dos veces y con la fecha buena listó los movimientos de "
     "06/08/2026.",
     APROBADA,
     "HALLAZGO H-01, corregido el 13/08: antes la fecha ilegible ni se validaba "
     "ni se usaba — se listaban movimientos de otra fecha y el cliente habría "
     "confirmado una compra de un día que no indicó. El calendario que pide el "
     "tablero es de front y sigue pendiente."),
    (111,
     "Recurrencia vía costura ASO: fallback y aislamiento de fuentes",
     "1013634958 / 1013634960",
     "Con TRX_SALESFORCE_SOURCE=aso: repetir el caso 100 (cliente con gestión) "
     "y el 105 (cliente sin gestión). Con la costura caída: repetir el 105.",
     "Con la costura viva: A recurre y C no, y el simulador registra la "
     "consulta con targetUserId={tipo_doc}-{documento}. Con la costura caída: "
     "el flujo continúa (fail-open, cae al mock local) sin romper el turno. "
     "Con TRX_SALESFORCE_SOURCE=mock: no se toca la red.",
     "A → has_recurrence=true; C → false; el simulador recibió ambas "
     "consultas. Fail-open y aislamiento verificados con pruebas unitarias "
     "(33 pasan en el servicio).",
     APROBADA,
     "Añadido en F2 al cerrar H-04. Para ASO real faltan credenciales "
     "(ASO_SOURCE=real + ASO_REAL_URL + TRX_API_*); el TSEC ya está "
     "implementado."),
    (112,
     "Contrato de la frontera entre tramos (Pablo → Luis)",
     "1013634960",
     "Camino feliz completo hasta \"Sí, continuar con el reporte\" y, sobre la "
     "conversación persistida, ejecutar docs/pruebas/verificar_contrato.py",
     "Las 25 claves del contrato (CONTRATO_FRONTERA.md v1) presentes y bien "
     "formadas: flow_answers (cantidad, producto, fecha, movimiento, "
     "confirmación afirmativa) y captured_data (trx_card_id, trx_vigencia, "
     "trx_index, trx_clasificacion completa, trx_detalle_result, "
     "products_result con origin_flag/last_four/card_brand).",
     "CONTRATO OK: 25/25. El verificador además avisa que trx_products_map no "
     "es fuente (pierde origin_flag) y documenta el hueco de la fecha de "
     "cruce para la regla de 7 días (sin insumo en el detalle; con Data).",
     APROBADA,
     "Añadido en F3. El verificador es parte de la definición de hecho de "
     "ambos tramos: se corre antes de cada push que toque el flujo."),
    (113,
     "Sucesos 1-3 (cambiazo, hurto, datos obtenidos) van directo a formulario",
     "1013634962 / 63 / 64",
     "Tres conversaciones: elegir Cambiazo; Hurto o perdida; Alguien obtuvo mis "
     "datos por llamada, mensaje, correo o enlace",
     "Los tres derivan al formulario sin mas preguntas, con boton Formulario PQR.",
     "Los tres ofrecieron Formulario PQR de inmediato.",
     APROBADA,
     "Anadido en el double-check de cobertura del 13/08: el tramo asignado "
     "incluia estas ramas y no estaban en el documento."),
    (114,
     "Rango de valor fuera de limite (ambos extremos)",
     "1013634963 / 62",
     "Hasta el rango de valor; elegir Menor a $35.000 (una conversacion) y "
     "Mayor a $500.000 (otra)",
     "Ambos derivan al formulario (.6.pqr) con boton Formulario PQR.",
     "Ambos ofrecieron Formulario PQR.",
     APROBADA, ""),
    (115,
     "El cliente reconoce la transaccion en la confirmacion",
     "10482895",
     "Camino feliz hasta la confirmacion; elegir 'No es necesario, ya "
     "reconozco la transaccion'",
     "Cierra por el proceso de feedback (¿Te ha ayudado esta informacion?), "
     "sin radicar nada.",
     "Paso directo al feedback.",
     APROBADA,
     "Es la salida limpia del tramo: el caso confirma que no entra a "
     "investigacion ni deja radicado."),
    (116,
     "Reenganches: 'No encuentro la transaccion' y 'sin movimientos'",
     "1013634960 / 66",
     "En el listado elegir 'No encuentro la transaccion' -> 'Seleccionar una "
     "nueva fecha' -> dia sin movimientos -> 'Elegir otra fecha' -> dia con "
     "movimientos. En cliente sin transacciones: 'Elegir otra fecha' y "
     "'Seleccionar otro producto'",
     "Cada reenganche vuelve al paso correspondiente (fecha o selector de "
     "producto) sin arrastrar estado: la reconsulta con la fecha nueva "
     "funciona y el listado reaparece.",
     "Los reenganches encadenados funcionaron; la vuelta al dia con "
     "movimientos volvio a listar los 3.",
     APROBADA, ""),
    (117,
     "'Finalizar conversacion' en la confirmacion de datos de contacto",
     "01576905",
     "En 'Antes de continuar...' elegir Finalizar conversacion",
     "Cierra por el proceso de feedback sin continuar el flujo.",
     "Paso directo al feedback.",
     APROBADA, ""),
    (118,
     "Contenido de la confirmación de la compra (viñetas del tablero)",
     "1013634960",
     "Camino feliz hasta la confirmación; leer el texto completo",
     "Viñetas con Descripción, Valor, Fecha (DD/MM/AAAA) y Producto terminado "
     "en *[últimos 4 reales], y la pregunta con dos botones.",
     "\"• Descripción: COMPRA FALABELLA CALLE 80 • Valor: $120.000 • Fecha: "
     "06/08/2026 • Producto terminado en *0060\" con ambos botones.",
     APROBADA,
     "HALLAZGO H-08, encontrado y cerrado el 13/08: salía el placeholder "
     "literal *XXXX porque el builder leía la clave last_four_pan_id (tabla "
     "ADA) y el servicio publica last_four. Mismo patrón de desajuste de "
     "claves que el products_map del contrato."),
    (119,
     "El aviso de fecha ilegible no se queda pegado",
     "1013634966",
     "Fecha ilegible → fecha buena → reenganche 'Elegir otra fecha'",
     "La re-pregunta de fecha muestra el texto normal, no \"No pude leer esa "
     "fecha\" de un intento anterior.",
     "Tras el arreglo: el reenganche muestra el prompt normal.",
     APROBADA,
     "HALLAZGO H-07 (era known-issue del PR), cerrado el 13/08: el aviso "
     "quedaba pegado y reaparecía en cada re-pregunta de fecha — reenganches "
     "y bucle multi-transacción — como si el cliente hubiera vuelto a fallar."),
    (120,
     "Validación de recurrencia silenciosa (ajuste 13/08)",
     "1013634960",
     "Frase → Compra presencial o por internet",
     "Pasa DIRECTO a '¿Cuántas transacciones quieres reportar?' sin mostrar "
     "'Estoy validando tu caso...' ni un botón Continuar. En backend la "
     "validación (Salesforce + recurrencia-bot + hito) ejecuta igual: con "
     "recurrencia real (cliente A) el desvío a PQR sigue saliendo de inmediato.",
     "Directo a la cantidad; con el cliente A, desvío a PQR intacto. Un turno "
     "menos en el camino común.",
     APROBADA,
     "Pedido por Fabián. La rama sin recurrencia del gate ahora reescribe el "
     "paso igual que los gates de productos y pendiente."),
    (121,
     "El selector de producto nunca muestra un identificador completo",
     "1013634960",
     "Hasta el selector de producto; revisar el label",
     "Tipo + últimos 4 de la TARJETA (last_four del servicio). Si el dato "
     "falta: '****'. Nunca los últimos 4 del contrato ni un identificador "
     "entero.",
     "'Tarjeta de Credito *0060' desde last_four. El normalizador conserva la "
     "clave y ningún consumidor cae ya a product_id (el contrato completo).",
     APROBADA,
     "Pedido por Fabián. Antes caía a product_id: coincidía con el PAN solo "
     "por el seed — con datos reales de ADA habría mostrado el dato "
     "equivocado. Cuarto caso del desajuste last_four/last_four_pan_id, "
     "cerrado en la raíz (el normalizador)."),
    (122,
     "Trazabilidad: el journey completo se reconstruye desde logs",
     "1013634961",
     "Camino feliz completo; luego: docker logs co-pqrs-back-agent | grep "
     "'TXNR paso'",
     "Una línea INFO por transición con paso origen → destino, la respuesta "
     "enmascarada (claves de opción sí; texto libre reducido a longitud; "
     "jamás PAN/contrato) y el estado. Además el evento viaja al "
     "error_handler → MinIO (audit-logs/traces) donde esté desplegado.",
     "10 líneas 'TXNR paso start → ... → satisfaction_check' reconstruyen el "
     "recorrido completo, incluida la reescritura de los gates.",
     APROBADA,
     "Pedido por Fabián. Emisión en un solo punto (fin de turno), no en 20 "
     "llamadas dispersas."),
    (201,
     "Sucesos 1-3 derivan a formulario y el botón cierra por feedback",
     "1013634962 / 63 / 64",
     "[U-1a · 1013634962] No reconozco esta compra / Me cambiaron la tarjeta (cambiazo) / Formulario PQR // [U-1b · 1013634963] No reconozco esta compra / Hurto o perdida / Formulario PQR // [U-1c · 1013634964] No reconozco esta compra / Alguien obtuvo tus datos por llamada, mensaje, correo o enlace / Formulario PQR",
     "[U-1a · 1013634962] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención // [U-1b · 1013634963] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención // [U-1c · 1013634964] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención",
     "",
     PENDIENTE,
     "Plan de UI U-1 (~8 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'TXNR paso' | grep 2.4.1"),
    (202,
     "Ruteo de las 12 frases de entrada del tablero",
     "varios",
     "Escribir cada una de las 12 frases parametrizadas del tablero y verificar que rutean a la tipologia",
     "Las 12 frases abren el menu de sucesos de transaccion no reconocida",
     "",
     PENDIENTE,
     "NO VALIDABLE EN LOCAL: el router LLM responde 401 y contesta el fallback deterministico, asi que el resultado no es representativo. Validar en DEV con credenciales."),
    (203,
     "Cantidad 2 y 3: aviso de una a la vez y límites completos",
     "10482895",
     "[U-3a · 10482895] No reconozco esta compra / Compra presencial o por internet / 2 / Empezar ahora // [U-3b · 10482895] No reconozco esta compra / Compra presencial o por internet / 3 / Empezar ahora",
     "[U-3a · 10482895] Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza | Botones: Si, continuar · Finalizar conversacion // [U-3b · 10482895] Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza | Botones: Si, continuar · Finalizar conversacion",
     "",
     PENDIENTE,
     "Plan de UI U-3 (~6 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'trx_cantidad'"),
    (204,
     "'Más de 3' deriva y el botón Formulario PQR transiciona",
     "98787954",
     "No reconozco esta compra / Compra presencial o por internet / Mas de 3 / Formulario PQR",
     "Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención",
     "",
     PENDIENTE,
     "Plan de UI U-4 (~3 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.1.pqr'"),
    (205,
     "Sin productos: el botón Terminar cierra por feedback",
     "1013634959",
     "No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Terminar",
     "Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención",
     "",
     PENDIENTE,
     "Plan de UI U-5 (~3 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.4.exit'"),
    (206,
     "Rango fuera de límite en ambos extremos",
     "1013634963 / 62",
     "[U-6a · 1013634963] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0063 / Menor a $35.000 / Formulario PQR // [U-6b · 1013634962] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0062 / Mayor a $500.000 / Formulario PQR",
     "[U-6a · 1013634963] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención // [U-6b · 1013634962] Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención",
     "",
     PENDIENTE,
     "Plan de UI U-6 (~6 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.6.pqr'"),
    (207,
     "Elegir el 2.º movimiento de la lista llega a la confirmación",
     "1013634960",
     "No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0060 / Entre $35.000 y $500.000 / 06/08/2026 / COMPRA MERCADOLIBRE.COM.CO — $89.990 — 06/08/2026",
     "Confirma los datos de la compra seleccionada. • Descripción: COMPRA MERCADOLIBRE.COM.CO • Valor: $89.990 • Fecha: 06/08/2026 • Producto terminado en *0060 ¿Es la transacción que deseas reportar? | Botones: Si, continuar con el reporte · No es necesario, ya reconozco la transaccion",
     "",
     PENDIENTE,
     "Plan de UI U-7 (~5 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'TXNR paso 2.4.0.1.9'"),
    (208,
     "Reenganche con la MISMA fecha vuelve al listado (H-11)",
     "1013634960",
     "No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0060 / Entre $35.000 y $500.000 / 06/08/2026 / No encuentro la transaccion en este listado / Seleccionar una nueva fecha / 06/08/2026",
     "Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces: | Botones: COMPRA FALABELLA CALLE 80 — $120.000 — 06/08/2026 · COMPRA MERCADOLIBRE.COM.CO — $89.990 — 06/08/2026 · COMPRA EXITO SUPERMERCADO — $250.000 — 06/08/2026 · No encuentro la transaccion en este listado",
     "",
     PENDIENTE,
     "Plan de UI U-8 (~6 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'reenganche_cacheado'"),
    (209,
     "Índice de producto inexistente y formatos de fecha alternos",
     "1013634961",
     "[U-9a · 1013634961] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / producto_4 // [U-9b · 1013634961] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0061 / Entre $35.000 y $500.000 / 31/12/2099 // [U-9c · 1013634961] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0061 / Entre $35.000 y $500.000 / 6/8/2026 // [U-9d · 1013634961] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0061 / Entre $35.000 y $500.000 / 2026-08-06",
     "[U-9a · 1013634961] Antes de continuar, selecciona el rango de valor de la transaccion que deseas reportar: | Botones: Menor a $35.000 · Entre $35.000 y $500.000 · Mayor a $500.000 // [U-9b · 1013634961] No encontramos compras registradas en la fecha seleccionada para este producto. | Botones: Elegir otra fecha · Seleccionar otro producto · Terminar consulta // [U-9c · 1013634961] Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces: | Botones: COMPRA AMAZON MKTP — $150.000 — 06/08/2026 // [U-9d · 1013634961] Encontré estas transacciones en la fecha indicada. Selecciona la compra que no reconoces: | Botones: COMPRA AMAZON MKTP — $150.000 — 06/08/2026",
     "",
     PENDIENTE,
     "Plan de UI U-9 (~8 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'vigencia'"),
    (210,
     "'Seleccionar otro producto' vuelve al selector",
     "1013634966",
     "No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0066 / Entre $35.000 y $500.000 / 06/08/2026 / Seleccionar otro producto",
     "Selecciona el producto activo sobre el que deseas revisar las transacciones. - Tarjeta de Credito *0066 Responde con el numero de la opcion que prefieres. | Botones: Tarjeta de Credito *0066",
     "",
     PENDIENTE,
     "Plan de UI U-10 (~4 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.8.return'"),
    (211,
     "MASTERCARD vencida: mensaje de plazo y Terminar",
     "1013634965",
     "No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0065 / Entre $35.000 y $500.000 / 01/01/2025 / Terminar",
     "Cierra por el proceso de feedback. El copy ROTA entre tres variantes: no compares por el texto, ancla a los botones 'Si, me ayudo' / 'No, ver linea de atencion'. | Botones: Sí, me ayudó · No, ver línea de atención",
     "",
     PENDIENTE,
     "Plan de UI U-11 (~4 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'outcome=vencida'"),
    (212,
     "Fronteras exactas de la ventana de contracargo",
     "1013634960 / 65",
     "Fechas a 179, 180, 181 dias (VISA) y 119, 120, 121 (MASTERCARD)",
     "VISA acepta hasta 180 inclusive; MASTERCARD hasta 120 inclusive",
     "",
     PENDIENTE,
     "CUBIERTO POR PRUEBAS UNITARIAS (fecha relativa, no caducan). Por UI no es teclable con fixtures de fecha fija; ver fila 124."),
    (213,
     "Entradas no válidas donde se esperan botones",
     "01576905",
     "[U-13a · 01576905] No reconozco esta compra / Compra presencial o por internet / texto libre que no es opcion // [U-13b · 01576905] No reconozco esta compra / Compra presencial o por internet / 99 // [U-13c · 01576905] No reconozco esta compra / Compra presencial o por internet / cancelar",
     "[U-13a · 01576905] No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar? | Botones: 1 · 2 · 3 · Mas de 3 // [U-13b · 01576905] No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar? | Botones: 1 · 2 · 3 · Mas de 3 // [U-13c · 01576905] No pude identificar una opcion valida para el paso 2.4.0.1.1. Cuantas transacciones quieres reportar? | Botones: 1 · 2 · 3 · Mas de 3",
     "",
     PENDIENTE,
     "Plan de UI U-13 (~5 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'No pude identificar'"),
    (214,
     "Repetir la misma opción dos veces",
     "1013634964",
     "No reconozco esta compra / Compra presencial o por internet / 1 / 1",
     "Antes de empezar, ten en cuenta que desde aqui puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una. Al continuar, confirmas que tus datos de contacto y direccion estan actualiza | Botones: Si, continuar · Finalizar conversacion",
     "",
     PENDIENTE,
     "Plan de UI U-14 (~3 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'TXNR paso'"),
    (215,
     "Recurrencia-bot en la segunda entrada del dia",
     "1013634960",
     "Entrar dos veces por la opcion 4 el mismo dia sin resetear",
     "La segunda entrada desvia a formulario con fuente=bot",
     "",
     PENDIENTE,
     "PARCIAL: la rama simple se observa en U-17; el doble hit con Salesforce requiere montaje. Ver H-05 (cerrado) en el protocolo."),
    (216,
     "Índice de movimiento fuera de rango (H-13, abierto)",
     "1013634961",
     "No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *0061 / Entre $35.000 y $500.000 / 06/08/2026 / movimiento_3",
     "Con la informacion disponible no podemos resolver esta solicitud en este canal. Por favor registra tu solicitud en el formulario. | Botones: Formulario PQR",
     "",
     PENDIENTE,
     "Plan de UI U-16 (~4 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep '2.4.0.1.10'"),
    (217,
     "Reabrir la conversación a mitad de flujo conserva el paso",
     "1013634962",
     "No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar",
     "Selecciona el producto activo sobre el que deseas revisar las transacciones. - Tarjeta de Credito *0062 Responde con el numero de la opcion que prefieres. | Botones: Tarjeta de Credito *0062",
     "",
     PENDIENTE,
     "Plan de UI U-17 (~3 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'Resuming existing session'"),
    (218,
     "Precedencia de Salesforce sobre la recurrencia-bot",
     "1013634958",
     "Cliente con gestion en Salesforce Y entrada previa del bot",
     "Prevalece Salesforce y la traza lo refleja en source",
     "",
     PENDIENTE,
     "NO VALIDABLE POR UI: exige provocar ambos a la vez. La distincion ya viaja en la traza (campo source_used)."),
    (219,
     "Fecha con espacios y fecha larguísima",
     "01576905",
     "[U-19a · 01576905] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *9461 / Entre $35.000 y $500.000 /     // [U-19b · 01576905] No reconozco esta compra / Compra presencial o por internet / 1 / Empezar ahora / Si, continuar / Tarjeta de Credito *9461 / Entre $35.000 y $500.000 / xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
     "[U-19a · 01576905]  // [U-19b · 01576905] No pude leer esa fecha. Escribela en formato DD/MM/AAAA, por ejemplo 06/08/2026. Consulta la fecha en tu extracto o en los movimientos de tu App BBVA.",
     "",
     PENDIENTE,
     "Plan de UI U-19 (~4 min). Pasos y respuesta esperada VERIFICADOS contra el stack el 18/08: son los que funcionan, no una suposicion. Diagnostico si falla: docker logs co-pqrs-back-agent | grep 'fecha_ilegible'"),
    (220,
     "[STACK] Caso de resiliencia con servicios caidos o mal configurados",
     "segun el caso",
     "Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias",
     "El flujo degrada sin romper el turno y el mensaje al cliente es comprensible",
     "",
     PENDIENTE,
     "Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar."),
    (221,
     "[STACK] Caso de resiliencia con servicios caidos o mal configurados",
     "segun el caso",
     "Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias",
     "El flujo degrada sin romper el turno y el mensaje al cliente es comprensible",
     "",
     PENDIENTE,
     "Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar."),
    (222,
     "[STACK] Caso de resiliencia con servicios caidos o mal configurados",
     "segun el caso",
     "Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias",
     "El flujo degrada sin romper el turno y el mensaje al cliente es comprensible",
     "",
     PENDIENTE,
     "Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar."),
    (223,
     "[STACK] Caso de resiliencia con servicios caidos o mal configurados",
     "segun el caso",
     "Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias",
     "El flujo degrada sin romper el turno y el mensaje al cliente es comprensible",
     "",
     PENDIENTE,
     "Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar."),
    (224,
     "[STACK] Caso de resiliencia con servicios caidos o mal configurados",
     "segun el caso",
     "Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias",
     "El flujo degrada sin romper el turno y el mensaje al cliente es comprensible",
     "",
     PENDIENTE,
     "Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar."),
    (225,
     "[STACK] Caso de resiliencia con servicios caidos o mal configurados",
     "segun el caso",
     "Ver GUIA_SESION_PRUEBAS.md bloque 4: para el simulador / back_trx / variables vacias",
     "El flujo degrada sin romper el turno y el mensaje al cliente es comprensible",
     "",
     PENDIENTE,
     "Requiere manipular el stack y restaurarlo entre casos. Ejecutar al final de la sesion o delegar."),
    (123,
     "Reanudar la conversación (POST /start) conserva los botones del paso",
     "98787954",
     "Llegar a un paso con botones (p. ej. 'Más de 3' → Formulario PQR) y "
     "recargar el front o pulsar 'Iniciar conversación (/start)'",
     "El bot vuelve a mostrar la pregunta CON sus botones (input_type=choice y "
     "las opciones del paso). El saludo inicial sigue sin botones.",
     "Tras el arreglo: input_type=choice y ['Formulario PQR'] al reanudar; "
     "saludo inicial input_type=text con options vacías.",
     APROBADA,
     "HALLAZGO H-09, encontrado en la pasada de UI del 14/08 y corregido el "
     "mismo día: POST /start es idempotente y REANUDA la sesión (Arquitectura "
     "A), pero serializaba siempre el mensaje como texto plano sin opciones — "
     "quien recargaba el front en cualquier paso de botones se quedaba viendo "
     "la pregunta sin nada que pulsar. Afecta a TODOS los flujos del bot, no "
     "solo a trx. Cambio aditivo de contrato: StartMessageContent admite "
     "options (vacías en el saludo)."),
    (124,
     "Ventana de contracargo: fronteras exactas por marca",
     "1013634960 (VISA) / 1013634965 (MASTERCARD)",
     "Con VISA probar 179, 180 y 181 días de antigüedad; con MASTERCARD 119, "
     "120 y 121. Además, la banda diferencial: misma fecha (150 días) con "
     "VISA y con MASTERCARD.",
     "VISA acepta hasta 180 días inclusive y rechaza en 181. MASTERCARD acepta "
     "hasta 120 inclusive y rechaza en 121. A 150 días VISA continúa y "
     "MASTERCARD muestra el mensaje del plazo de las franquicias.",
     "Verificado con pruebas de fecha relativa (no caducan): 179/180 pasan, "
     "181 vence; 119/120 pasan, 121 vence; banda 150 discrimina.",
     APROBADA,
     "Regla confirmada por negocio el 14/08: SOLO marca, sin ámbito — cierra "
     "la duda del tablero (nacional/interoperable/internacional). Plazos "
     "parametrizables (VIGENCIA_VISA_DIAS / VIGENCIA_MASTER_DIAS). PENDIENTE: "
     "qué plazo aplica a lo que no es VISA ni MASTER (AMEX, Diners, marca "
     "vacía); hoy reciben 180, el más permisivo."),
    (125,
     "Exactitud de los mensajes dinámicos (procedencia, formato, degradación)",
     "1013634960",
     "Recorrer el camino feliz ejecutando docs/pruebas/verificar_mensajes.py, "
     "que compara cada dato mostrado contra su fuente en el payload",
     "En los 4 puntos con datos del cliente (selector, reprompt de fecha, "
     "listado y confirmación): cada valor sale de la clave correcta, las "
     "fechas van en DD/MM/AAAA, los importes formateados, el producto con sus "
     "últimos 4 reales, y nunca aparece un crudo (XXXX, None, contrato "
     "completo).",
     "61 comprobaciones OK. Degradación fijada aparte con pruebas: sin "
     "last_four el selector muestra **** y jamás el contrato.",
     APROBADA,
     "Pedido por Fabián el 14/08. El verificador compara contra la FUENTE del "
     "dato, no contra un literal: un cambio de copy autorizado no rompe la "
     "prueba, pero un dato leído de la clave equivocada sí — que es el fallo "
     "que se escapó tres veces (H-03, H-07, H-08)."),
    (126,
     "Los ultimos 4 salen del PAN de financial-overview, no del contrato",
     "1013634967",
     "Recorrido normal hasta el selector de producto y despues hasta la "
     "confirmacion, con el cliente J (divergencia deliberada: ADA y el "
     "contrato terminan en 9999; el PAN de financial-overview en 4321)",
     "Selector y confirmacion muestran **4321** -- los ultimos 4 del PAN. Si "
     "mostraran 9999 estarian leyendo de ADA o del contrato, que es el defecto "
     "reportado por negocio.",
     "Selector: 'Tarjeta de Credito *4321'. Confirmacion: 'Producto terminado "
     "en *4321'.",
     APROBADA,
     "Cliente creado el 18/08 para que la verificacion sea inequivoca: en el "
     "resto de la matriz ADA y el PAN coinciden por diseno de los fixtures, asi "
     "que un fallo pasaria desapercibido. Semilla en "
     "dev/postgres/03-seed-cliente-j.sql y fixtures del simulador para el PAN "
     "4912680517944321."),
    (110,
     "Formato del label del movimiento",
     "01576905",
     "(sobre el listado del caso anterior)",
     "El tablero pide \"[Descripción] — $[valor] [DD/MM/AAAA]\".",
     "Tras el arreglo del 13/08 (tarde): \"COMPRA FALABELLA CALLE 80 — $120.000 "
     "— 06/08/2026\" — descripcion, valor y fecha en DD/MM/AAAA, como pide el "
     "tablero.",
     APROBADA,
     "HALLAZGO H-03, cerrado el 13/08: la fecha salia en ISO. Corregido en el "
     "label del listado y en la confirmacion."),
]


def construir() -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Casos TRX esqueleto"
    fill = PatternFill("solid", fgColor="1F3864")
    ws.append(CABECERA)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for no, caso, cliente, pregunta, esperada, obtenida, estatus, obs in CASOS:
        obs_full = f"user_id {cliente}. {obs}".strip()
        ws.append([no, CATEGORIA, RESPONSABLE, caso, pregunta, esperada,
                   obtenida, estatus, LISTO, obs_full])
    nota = ws.max_row + 2
    ws.cell(row=nota, column=1, value="NOTA")
    ws.cell(row=nota, column=4, value=NOTA_ENTORNO)
    anchos = {"A": 7, "B": 24, "C": 18, "D": 40, "E": 42, "F": 58,
              "G": 52, "H": 12, "I": 24, "J": 55}
    for col, w in anchos.items():
        ws.column_dimensions[col].width = w
    for fila in ws.iter_rows(min_row=2):
        for c in fila:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(CABECERA))}{len(CASOS) + 1}"
    return wb


def markdown() -> str:
    filas = [
        "# Casos de prueba — flujo trx sobre el esqueleto (para el documento corporativo)",
        "",
        NOTA_ENTORNO,
        "",
        "Bloques reservados 100-122 (ejecutados) y 200-225 (plan de UI, pendientes de pasada manual). Pegar como filas nuevas al final de "
        "**Pruebas Integrales**, sin tocar las existentes.",
        "",
    ]
    for no, caso, cliente, pregunta, esperada, obtenida, estatus, obs in CASOS:
        filas += [f"## {no} · {caso}", "",
                  f"**Cliente:** `{cliente}` · **Estatus:** {estatus}", "",
                  "**Pregunta:**", "```", pregunta, "```", "",
                  "**Esperada:**", "```", esperada, "```", "",
                  "**Obtenida (13/08):**", "```", obtenida or "(sin ejecutar)", "```", ""]
        if obs:
            filas += [f"**Observación.** {obs}", ""]
        filas += ["---", ""]
    return "\n".join(filas)


if __name__ == "__main__":
    aqui = pathlib.Path(__file__).parent
    construir().save(aqui / "CASOS_PRUEBA_TRX_ESQUELETO.xlsx")
    (aqui / "CASOS_PRUEBA_TRX_ESQUELETO.md").write_text(markdown(), encoding="utf-8")
    print(f"{len(CASOS)} casos -> CASOS_PRUEBA_TRX_ESQUELETO.xlsx / .md")
