# Límites antifraude: evidencia en el código
## Control IT4.6 · Trámite de transacción no reconocida · Agente PQRS

Proyecto PQRS · BBVA Colombia · Rama `feature/PQRSdev` · Corte 15/09/2026

| | |
|---|---|
| Solicitado por | Camilo Andrés Montoya Hernández (Equipo Systems, responsable del control) |
| Elaborado por | Pablo Andrés Jarava Guerra (Inetum) |
| Versión bajo revisión | Probado: agente 1.0.15 · trámite test_v1.0.9. Citas de código: rama `feature/PQRSdev` al 15/09 tras los ajustes (commits f071c97c y 92184daa) |
| Documentos relacionados | Evidencias de pruebas funcionales v1.0 (T04, T05, T06, T12) · Registro de hallazgos |
| Clasificación | Uso interno |

> **Qué es este documento.** El equipo responsable del control IT4.6 pidió la evidencia del código
> donde están aplicadas las reglas de límites antifraude. Este documento localiza cada regla en el
> repositorio, con fichero y línea, muestra el fragmento que la aplica, indica qué pruebas
> automatizadas la cubren y qué evidencia funcional la acompaña. Donde el código y la política
> no coinciden, lo dice.

---

## 1. La política que hay que evidenciar

Texto literal de la columna «Comentarios» del control IT4.6 en la hoja de tareas:

> Monto máximo permitido $500.000 por transacción. Monto mínimo permitido $35.000 por
> transacción. Se le permite hacer un máximo 3 solicitudes por tipología, en un rango de 6 meses,
> apalancada en la política de monto menor que tiene el Banco.

Y el enunciado del control: *«Límites antifraude: reglas y parametrización aprobadas para monto,
acumulado por cliente, frecuencia y temporalidad, con pruebas de superación.»*

De ahí salen cinco reglas a evidenciar: importe mínimo, importe máximo, número de solicitudes,
ventana temporal y acumulado por cliente.

## 2. Resumen

| Regla | Dónde se parametriza | Dónde se aplica | Estado frente a la política |
|---|---|---|---|
| Importe mínimo $35.000 | `TRX_MONTO_MIN` en el ConfigMap del trámite | Filtro de movimientos del servicio del trámite y paso 2.4.0.1.6 del flujo | Coincide |
| Importe máximo $500.000 | `TRX_MONTO_MAX` en el ConfigMap del trámite | Ídem | Coincide |
| Máximo 3 transacciones por solicitud | Paso 2.4.0.1.1 del flujo | Opción «Más de 3» deriva al formulario | Coincide |
| Máximo 3 solicitudes por tipología en 6 meses | `MAX_TRX_BOT_RECURRENCE=3` y `TRX_RECURRENCIA_MESES=6` en los ConfigMaps del agente y del trámite | Contador de entradas del cliente y consulta de casos previos en Salesforce, ambos con el mismo tope y la misma ventana | **Coincide tras el ajuste del 15/09** (sección 8). Pendiente de desplegar |
| Acumulado por cliente | — | — | **No implementado**: la política no fija valor (hallazgo H-16, ya registrado) |

## 3. Importe por transacción: $35.000 a $500.000

### 3.1 Dónde se parametriza

`co_pqrs_back_trx_noreconocida/src/infrastructure/core/config.py`, líneas 324–325. Los valores
se leen del entorno con esos nombres; el valor por defecto coincide con la política.

```
monto_min=_load_float("TRX_MONTO_MIN", 35000.0),
monto_max=_load_float("TRX_MONTO_MAX", 500000.0),
```

Valor desplegado en DEV, `IaC/backend/co_pqrs_back_trx_noreconocida/01-configmap.yaml`, líneas
85–86:

```
TRX_MONTO_MIN=35000
TRX_MONTO_MAX=500000
```

### 3.2 Dónde se aplica

Hay dos capas. La primera es la que impide que el cliente llegue a elegir una compra fuera de
rango; la segunda es la declaración del límite en la conversación.

**Capa 1 · el listado de movimientos solo trae los que están en rango.** Cuando el cliente indica
la fecha, el servicio del trámite consulta los movimientos del día y descarta los que quedan
fuera del rango antes de devolverlos. `co_pqrs_back_trx_noreconocida/src/application/trx/aso_rules.py`,
líneas 220–257:

```
def filtrar_por_rango(movimientos, *, monto_min, monto_max):
    """Aplica el rango de valor elegido por el cliente en 2.4.0.1.6.
    Devuelve (dentro_del_rango, cuantos_quedaron_fuera)."""
    ...
    for mov in movimientos:
        valor = mov.get("valor")
        if monto_min is not None and valor < float(monto_min):
            fuera += 1
            continue
        if monto_max is not None and valor > float(monto_max):
            fuera += 1
            continue
        dentro.append(mov)
    return dentro, fuera
```

Quien lo invoca toma el rango de la configuración del trámite, no de un valor escrito en el
código: `co_pqrs_back_trx_noreconocida/src/infrastructure/entrypoint/api/router/v0/trx_router.py`,
líneas 295–298:

```
flow = load_trx_flow_settings()
monto_min = from_amount if from_amount is not None else flow.monto_min
monto_max = to_amount if to_amount is not None else flow.monto_max
```

El servicio devuelve además cuántos movimientos quedaron fuera, y el agente lo usa para no dar al
cliente el mismo mensaje que a quien no tiene compras ese día.
`co_pqrs_back_agent/src/application/chat/chat_service.py`, líneas 748–756:

```
if not movimientos and (movs or {}).get("fuera_de_rango"):
    ... "Ese día sí tienes movimientos, pero por este canal solo puedo gestionar
        compras entre {monto_min} y {monto_max}. Si la compra que no reconoces
        está fuera de ese rango, nuestro equipo especializado puede ayudarte."
```

**Capa 2 · el flujo declara el límite y deriva si el cliente lo elige fuera.** Antes de pedir
ningún dato, el paso 2.4.0.1.3 declara la regla; en el paso 2.4.0.1.6 el cliente indica el rango y
las dos opciones fuera de él llevan al formulario.
`co_pqrs_back_agent/src/domain/workflow/trx_no_reconocida/trx_no_reconocida.yml`, líneas 121 y
178–197:

```
"2.4.0.1.3": "...desde aquí puedes reportar hasta 3 transacciones de entre $35.000 y $500.000 cada una."

"2.4.0.1.6":
  options:
    - key: "menor_35000"          label: "Menor a $35.000"           next_step: "2.4.0.1.6.pqr"
    - key: "entre_35000_500000"   label: "Entre $35.000 y $500.000"  next_step: "2.4.0.1.7"
    - key: "mayor_500000"         label: "Mayor a $500.000"          next_step: "2.4.0.1.6.pqr"
```

### 3.3 Pruebas automatizadas

| Prueba | Fichero | Qué comprueba |
|---|---|---|
| `test_filtra_por_rango` | `co_pqrs_back_trx_noreconocida/tests/test_application/test_aso_rules.py:122` | El filtro descarta los movimientos fuera del rango y cuenta cuántos quedaron fuera |
| `test_sin_rango_devuelve_todo` | ídem, línea 136 | Sin rango configurado no se descarta nada |
| `test_valor_menor_a_35000_redirige_pqr` | `co_pqrs_back_trx_noreconocida/tests/test_application/test_analysis_service.py:69` | La regla por importe individual rechaza por debajo del mínimo |
| `test_valor_mayor_a_500000_redirige_pqr` | ídem, línea 79 | La regla por importe individual rechaza por encima del máximo |
| `test_valor_en_rango_aprobado` | ídem, línea 74 | Dentro del rango aprueba |

### 3.4 Evidencia funcional

T05a y T05b del informe de evidencias: al elegir «Mayor a $500.000» o «Menor a $35.000», el
asistente deriva al formulario sin consultar movimientos. T01c muestra el listado ya filtrado.

### 3.5 Observaciones

- La regla por importe individual (`evaluar_transaccion_individual`, `analysis_service.py`
  líneas 1247–1309) existe y tiene pruebas, pero **el flujo no la invoca**: el rango se aplica en
  el filtro de movimientos. Hasta el 15/09 escribía los valores 35.000 y 500.000 como literales;
  ahora lee `flow.monto_min` y `flow.monto_max`, los mismos parámetros del filtro, y sus claves de
  resultado pasan a `monto_menor_minimo` y `monto_mayor_maximo` (H-29, corregido).
- El agente contenía un evaluador de respaldo (`_FallbackTrxAnalysisService`) con las
  comparaciones invertidas, que habría rechazado cualquier importe. Nunca se ejecutaba. Se retiró
  el 15/09 junto con el cargador que lo instanciaba, 115 líneas (H-29, corregido).

## 4. Número de transacciones por solicitud: máximo 3

### 4.1 Dónde se aplica

Es la primera pregunta del trámite. La opción «Más de 3» no continúa: lleva a un paso de
derivación al formulario. `trx_no_reconocida.yml`, líneas 84–106:

```
"2.4.0.1.1":
  question: "¿Cuántas transacciones quieres reportar?"
  options:
    - key: "1"         next_step: "2.4.0.1.2"
    - key: "2"         next_step: "2.4.0.1.2"
    - key: "3"         next_step: "2.4.0.1.2"
    - key: "mas_de_3"  next_step: "2.4.0.1.1.pqr"
"2.4.0.1.1.pqr":
  question: "Para validar el reporte de más de 3 compras no reconocidas, necesitamos tener la
             información completa en un solo trámite. Completa el formulario..."
```

El número elegido acota el bucle de transacciones: el trámite recorre una por una hasta llegar
a él y cierra. No hay un camino para reportar una cuarta dentro de la misma solicitud.

### 4.2 Evidencia funcional

T06 del informe de evidencias: al elegir «Más de 3», derivación al formulario sin pedir ningún
dato del cliente. El registro confirma que la conversación no llegó a consultar los productos.

## 5. Frecuencia y temporalidad: máximo 3 solicitudes por tipología en 6 meses

El código tiene dos mecanismos. Hasta el 15/09 ninguno de los dos coincidía con el «máximo 3»:
el primero tenía el parámetro en 20 y el segundo desviaba al primer caso previo. Ambos se
ajustaron ese día para aplicar la política con los mismos dos parámetros, tope y ventana.

### 5.1 Dónde se parametriza

Tope y ventana son dos variables, presentes en la configuración del agente y del trámite con el
mismo valor, porque los dos mecanismos deben decidir igual:

```
MAX_TRX_BOT_RECURRENCE=3      # solicitudes permitidas por tipología en la ventana
TRX_RECURRENCIA_MESES=6       # ventana, en meses
```

`IaC/backend/co_pqrs_back_agent/01-configmap.yaml` líneas 39–40 y
`IaC/backend/co_pqrs_back_trx_noreconocida/01-configmap.yaml` líneas 88–89. Los valores por
defecto en código son los mismos: `chat_service.py` en `_trx_bot_recurrence_hit`, y
`co_pqrs_back_trx_noreconocida/src/infrastructure/core/config.py` líneas 328–329
(`max_bot_recurrence`, `recurrencia_meses`).

### 5.2 Mecanismo 1 · contador de entradas del cliente en el propio asistente

Cada vez que un cliente entra al trámite, el asistente lo anota de forma duradera. Antes de
dejarlo continuar, cuenta cuántas entradas tiene en la ventana y las compara con el tope.
`co_pqrs_back_agent/src/application/chat/chat_service.py`, líneas 2341–2358, función `_trx_bot_recurrence_hit`:

```
meses = int(_trx_env("TRX_RECURRENCIA_MESES", "6"))
count = store.get_bot_recurrence_count(record, months=meses)
max_rec = int(_trx_env("MAX_TRX_BOT_RECURRENCE", "3"))
return count >= max_rec
```

El recuento está en `co_pqrs_back_agent/src/infrastructure/persistence/trx_case_store.py`,
líneas 81–98: entradas del cliente con fecha posterior a «hoy menos la ventana». La comparación es
«entradas previas ≥ tope», así que con 3 el cliente puede hacer tres solicitudes y la cuarta se
desvía.

Pruebas: `co_pqrs_back_agent/tests/test_infrastructure/test_persistence/test_trx_case_store.py`,
líneas 42 y 44: una entrada dentro de la ventana cuenta, una fuera no.

### 5.3 Mecanismo 2 · consulta de casos previos en Salesforce

El servicio del trámite consulta los casos del cliente en Salesforce, cuenta los de esta
tipología dentro de la ventana y desvía al alcanzar el tope.
`co_pqrs_back_trx_noreconocida/src/application/trx/aso_rules.py`, líneas 34–68, función `recurrencia_por_subject`:

```
def recurrencia_por_subject(issues, *, subjects_txnr, now=None, months=6, max_solicitudes=3):
    threshold = reference - timedelta(days=months * 30)
    for issue in issues:
        if not any(s in subject for s in subjects_txnr): continue
        if created >= threshold: recent += 1
    tope = max(1, int(max_solicitudes))
    return {"has_recurrence": recent >= tope, "recent_total": recent, "max_solicitudes": tope, ...}
```

Invocado desde `analysis_service.py` en sus dos puntos de llamada con
`months=flow.recurrencia_meses` y `max_solicitudes=flow.max_bot_recurrence`. La decisión que toma
el agente con ese resultado está en `chat_service.py` líneas 517–548: si hay recurrencia, el paso
pasa a la derivación; si no, continúa.

**Sobre la lectura anterior.** Antes del ajuste este mecanismo desviaba en cuanto había un caso
previo, es decir, aplicaba «no duplicar un caso abierto» y no «hasta 3». Si Systems prefiere
conservar esa protección, basta con fijar `MAX_TRX_BOT_RECURRENCE=1` en el trámite: el
comportamiento queda parametrizado, no decidido en el código (H-28).

Pruebas: `test_aso_rules.py`: un caso reciente cuenta pero no alcanza el tope; tres lo alcanzan;
dos no; con el tope en 1 se desvía al primero. `test_analysis_service.py`: tres casos recientes
derivan, uno solo no. Y en el agente, `test_chat_service.py` líneas 1479 y 1493 y
`test_trx_flow.py` líneas 58 y 62.

### 5.4 Un tercer mecanismo, diario

Aparte, el asistente tiene un tope de interacciones por categoría y día
(`MAX_DAILY_CATEGORY_INTERACTIONS`, `co_pqrs_back_agent/src/infrastructure/core/config.py` línea
341), con 17 pruebas en `tests/test_application/test_category_cap_flow.py`. En DEV vale 1000 para
no estorbar las pruebas. No forma parte de la política citada; se menciona para que el inventario
de límites esté completo.

### 5.5 Evidencia funcional

T12 del informe de evidencias, no concluyente: en DEV la consulta de casos previos leía un listado
fijo que no distingue por cliente. El informe de avance describe los ajustes para repetirla. Tras
desplegar este cambio, la prueba de superación es directa: el cliente de pruebas 98782372 ya
tiene más de tres entradas en la ventana, así que su siguiente entrada debe desviarse.

## 6. Acumulado por cliente

No existe una regla de acumulado por cliente en el código: ni por suma de importes en la
solicitud, ni por suma en el tiempo. La regla por importe individual del servicio del trámite
recibe las transacciones acumuladas «como contexto informativo (no altera la decisión
por-transacción)», según su propio comentario en `analysis_service.py` línea 1251. Es el hallazgo
H-16, ya registrado y asignado a Systems y Fabián, pendiente de la parametrización aprobada.

## 7. Discrepancias encontradas y cómo quedaron

| # | Discrepancia | Qué hace falta | Quién |
|---|---|---|---|
| 1 | El tope de solicitudes en 6 meses valía 20 en DEV; la política dice 3 | **Corregido el 15/09**: `MAX_TRX_BOT_RECURRENCE=3` en los ConfigMaps del agente y del trámite, y 3 por defecto en el código (H-27) | Desplegar: reinicio del agente y del trámite |
| 2 | La consulta a Salesforce desviaba al primer caso previo en 6 meses; la política permite hasta 3 | **Corregido el 15/09**: la consulta cuenta los casos de la tipología en la ventana y desvía al alcanzar el tope, con el mismo parámetro que el contador del asistente. Con el parámetro en 1 se recupera el comportamiento anterior, si Systems prefiere no duplicar casos (H-28) | Systems confirma el valor; desplegar la imagen del trámite |
| 3 | El acumulado por cliente no está implementado | Sin cambio: la política no fija ningún valor. Definir el tope (por solicitud, por día o por ventana) y su valor (H-16) | Systems y Fabián definen; equipo técnico implementa |
| 4 | Código muerto con la regla de importe mal escrita | **Corregido el 15/09**: retirado el evaluador de respaldo del agente; la regla individual del servicio lee `TRX_MONTO_MIN/MAX` (H-29) | Desplegar |

## 8. Ajustes realizados el 15/09

Todos los cambios están en la rama `feature/PQRSllmops`, con sus pruebas. Ninguno cambia el
comportamiento frente al cliente salvo en lo que la política exige: a partir de la cuarta
solicitud en seis meses, el trámite deriva.

| Qué | Dónde | Antes | Después |
|---|---|---|---|
| Tope de solicitudes en la ventana | `IaC/backend/co_pqrs_back_agent/01-configmap.yaml` línea 39 · `IaC/backend/co_pqrs_back_trx_noreconocida/01-configmap.yaml` línea 88 | 20 · 1000 | `MAX_TRX_BOT_RECURRENCE=3` en ambos |
| Ventana temporal como parámetro | Ambos ConfigMaps, líneas 40 y 89 · `config.py` del trámite, campo `recurrencia_meses` · `chat_service.py`, contador | `months=6` escrito a mano en dos sitios | `TRX_RECURRENCIA_MESES=6`, leído en los dos mecanismos |
| Valor por defecto del tope en código | `chat_service.py` `_trx_bot_recurrence_hit` (líneas 2341–2358) · `config.py` del trámite línea 328 | 1 | 3 |
| Consulta a Salesforce con tope contable | `aso_rules.py` `recurrencia_por_subject`, parámetro `max_solicitudes` · `analysis_service.py`, dos puntos de llamada | desvía si hay ≥ 1 caso reciente | desvía si hay ≥ tope casos recientes |
| Regla individual de importe | `analysis_service.py` `evaluar_transaccion_individual` | literales 35000 y 500000 | `flow.monto_min` y `flow.monto_max`; claves `monto_menor_minimo` / `monto_mayor_maximo` |
| Evaluador de respaldo del agente | `chat_service.py` (bloque anterior a `_env_const`) | comparaciones invertidas, nunca ejecutado | retirado (115 líneas) |

Pruebas: en el servicio del trámite, 108 de 109 en verde (la restante falla solo por un `.env`
local de la máquina de desarrollo, que apunta al fichero de simulación «sin recurrencia»; pasa sin
él). Nuevas: tres casos recientes desvían, dos no, uno no, y el tope en 1 recupera el comportamiento
anterior. En el agente, las pruebas de recurrencia, flujo, contador y tope diario en verde.

**Para que surta efecto en DEV** hacen falta una imagen nueva del agente y otra del trámite (los
cambios de código) y el reinicio de ambos (los ConfigMaps). El cambio de tope por sí solo, sin
nueva imagen, ya limita a 3 el contador del asistente con el reinicio.

Las reglas 1 y 2 de la política —importe mínimo y máximo— están parametrizadas, aplicadas en el
camino real y probadas. Las de frecuencia y acumulado necesitan las decisiones de la tabla.
