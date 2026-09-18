# Plan de la noche del 15/09
## Desplegar, correr y capturar lo que falta para el informe de transacción no reconocida

Proyecto PQRS · BBVA Colombia · Entorno DEV

| | |
|---|---|
| Objetivo | Que mañana el informe cubra el máximo de controles con evidencia propia |
| Punto de partida | Rama `feature/PQRSdev` en `7b1259b9`; informe v1.3 con 38 evidencias |
| Lo que se puede hacer esta noche | Construir y subir imágenes, cambiar configuración, lanzar corridas, capturar |
| Lo que no depende de esta noche | Fichas de identidad (Data), Argo (plataforma), umbrales de avisos (Fabián) |

> **El orden importa.** Hay una prueba que solo puede hacerse ANTES de bajar el tope de
> solicitudes a 3 (el diagnóstico del bloqueo con el cliente 98782372, que ya lleva más de tres
> entradas) y otra que solo puede hacerse DESPUÉS (la cuarta solicitud que debe desviarse). Por eso
> el plan va en dos tandas de despliegue.

---

## Tanda 1 · Imágenes nuevas con la configuración de hoy

### 1.1 Construir y subir

| Imagen | Desde | Tag propuesto | Qué trae |
|---|---|---|---|
| `co_pqrs_back_agent` | `7b1259b9` | `1.0.17` | Contador de solicitudes con parámetros; marca `guardrail_blocked` y cabecera en todo turno del banco; dos reglas nuevas de ruteo; sin el evaluador muerto |
| `co_pqrs_back_trx_noreconocida` | `7b1259b9` | `test_v1.0.10` | Consulta a Salesforce con tope contable; regla de importe parametrizada; e incluye lo de Fabián de hoy (`error_type` en rechazos del bloqueo, huella del TSEC) |

El trámite sigue nuestra serie `test_v1.0.x` (la anterior nuestra fue `test_v1.0.9`); la serie
`1.0.x_qa` es la de Diego y Luis y no se toca. El agente sigue en `1.0.x`, saltando el `1.0.16` de
Nicolás. Los manifiestos de dev ya apuntan a estos dos tags. Las imágenes se construyen desde el
mismo commit, que incluye lo de Fabián, Nicolás, Diego y Luis de hoy: no se pierde nada de nadie.

### 1.2 Cambiar la imagen en la consola y reiniciar

Workloads → Deployments → `co-pqrs-back-agent` → YAML → `image:` con el tag nuevo → Save.
Igual para `co-pqrs-back-trx-noreconocida`. Ambos se reinician solos al cambiar la imagen.
Comprobar en Pods que los dos nuevos están en Running y que la hora de arranque es posterior a
la subida.

**No toques todavía `MAX_TRX_BOT_RECURRENCE`.** Sigue en 20 para la prueba 1.3.

### 1.3 Diagnóstico del bloqueo (H-26) · con el trámite nuevo

Front, cliente `98782372`, recorrido completo hasta el bloqueo, igual que T01. Con la imagen de
Fabián, si la autorización vuelve a fallar, la traza del agente traerá `error_type` y el motivo.

- Si esta vez el bloqueo se completa: captura y traza, y H-26 se cierra como «fallo puntual del
  15/09 por la mañana». Además vale como recorrido completo con la versión nueva.
- Si vuelve a fallar: baja la carpeta de trazas; la anotación `subida_nivel_permanente_error`
  ahora dice por qué. Con eso H-26 tiene causa.

Guion: T14 (nuevo, al final del guion de conversaciones).

### 1.4 Corridas con el agente nuevo

Consola → CronJobs → Actions → Instantiate Job, en este orden, esperando a que termine cada una
(el tiempo es el que tardan en el ambiente, no el mío):

| Trabajo | Para qué | Lo que debe cambiar frente al 15/09 por la mañana |
|---|---|---|
| `co-pqrs-benchmark-adversarial` | R-16 definitivo | Los 4 «MISS» de inyección pasan a OK (marca `guardrail_blocked`); los 9 «sin resolver» se resuelven (cabecera en todo turno); el caso 20 de palabras amontonadas debe dar «sin coincidencia» |
| `co-pqrs-benchmark-grounding` | R-17 puntuable | Los 12 «sin resolver» se resuelven; el caso 14 (aclaración) debe llegar a transacción no reconocida |
| `co-pqrs-benchmark-tnr` | Confirmar que las reglas nuevas no rompen nada | 35 o 36 de 36, sin entradas indebidas |

Al terminar cada una: Jobs → el trabajo → Pods → Logs → Download. Los tres registros van a la
entrega, en `04_Registros/banco_de_casos_ruteo_2026-09-15/`.

Si alguno de los CronJobs no aparece, es que los manifiestos de evidencia no se aplicaron
(Argo). Edita el CronJob base `co-pqrs-benchmark` en YAML, añade `MINIO_ENABLED=false` y cambia
`INPUT_JSON` al banco que quieras correr; es lo mismo que hacen los de evidencia.

## Tanda 2 · Configuración de la política de frecuencia

### 2.1 ConfigMaps

Consola → ConfigMaps:

| ConfigMap | Cambiar | Añadir |
|---|---|---|
| `conf-pqr-agent-env` (el del agente) | `MAX_TRX_BOT_RECURRENCE=20` → `3` | `TRX_RECURRENCIA_MESES=6` |
| `conf-pqr-trxnr-env` (el del trámite) | `MAX_TRX_BOT_RECURRENCE=1000` → `3` | `TRX_RECURRENCIA_MESES=6` |

Y en el del trámite, si vas a intentar T12: `TRX_SALESFORCE_SOURCE=aso`. Solo sirve si Data
cargó la ficha de `1013634958`; si no, déjalo en `mock`.

Después: Deployments → Actions → Restart rollout, los dos. El ConfigMap montado no se refresca en
un pod vivo.

### 2.2 La prueba de superación · T13 (nueva)

Front, cliente `98782372`, escribe «Hay una compra en mi tarjeta que yo no hice» y elige
«Hiciste una compra presencial o por internet».

**Debe** desviarse: avisar de que ya existe una gestión reciente y derivar, sin pedir el producto.
Es la cuarta solicitud (o más) en seis meses de ese cliente. En la carpeta de trazas, la
anotación `op4_recurrencia` debe decir `redirect_pqr` con `source=bot`, y `trx_case.recurrence_bot`
debe traer `count` mayor o igual que `max=3`.

Es la evidencia que el control IT4.6 llama «prueba de superación», y cierra H-27 con captura.

### 2.3 T12, solo si Data cargó la ficha

Guion T12 tal como está. Si no hay ficha, no lo intentes: saldrá igual que el 15/09.

## Tanda 3 · Capturas que no dependen de nada

Se pueden hacer en cualquier hueco, mientras corren los trabajos.

| Captura | Dónde | Para qué evidencia |
|---|---|---|
| Objeto de productos con la tarjeta enmascarada | MinIO → `audit-logs` → `clients/customer=98782372/dt=2026-09-14/conversation=98782372_20260914/` → el `..._financial_overview_ok.json` de las 21:22 → abrir → capturar el cuerpo con `****2274` | R-05, prueba visual |
| Los dos objetos del bloqueo en orden | Misma carpeta, `dt=2026-09-15` (UTC) → `232540180617_..._subida_nivel_estado_accepted.json` y `232540234698_..._trx.bloqueo_ok.json` → una captura del listado ordenado y una de cada cuerpo | R-08, prueba visual |
| Conversación archivada | MinIO → `pqr-conversations-history` → `conversations/98782372_20260914/2026/09/14/` → abrir → capturar | Conversación archivada sin datos sensibles |
| Versiones desplegadas | Consola → Deployments → capturar la lista con la columna de imagen, o cada Details | Estado del servicio |
| Configuración del asistente | Consola → ConfigMaps → `conf-pqr-agent-env` → capturar. Difuminar claves y direcciones internas | Estado del servicio |
| Trabajos programados | Consola → CronJobs → capturar la lista completa | Estado del servicio |
| Las corridas de hoy | Consola → Jobs → capturar la lista con los cinco de la mañana y los de la noche | Trazabilidad de las corridas |

Nombra cada captura al guardarla, con el patrón del guion:
`IT3.2-M01_minio_productos_enmascarados_dev_2026-09-15.png`, `IT4.5-M02_minio_bloqueo_en_orden_…`,
`IT3.6-M03_minio_conversacion_archivada_…`, `IT2.2-S01_consola_versiones_…`, `IT2.2-S02_consola_configmap_…`,
`IT2.3-S03_consola_cronjobs_…`, `IT1.6-S04_consola_jobs_…`.

## Tanda 4 · Tableros, si se puede

Los tableros no están instalados. Dos caminos, y esta noche solo el segundo depende de ti:

1. **Que alguien aplique `IaC/elk/opensearch-analytics`** con terminal. El trabajo de importación
   corre solo y los deja en el inquilino Global.
2. **Importarlos a mano.** OSD → arriba a la derecha, menú de usuario → Switch tenants → Global →
   menú lateral → Stack Management → Saved Objects → Import → subir cada uno de los cuatro
   ficheros de `06_Tableros/` de la entrega, con «overwrite» marcado. Después, Dashboards → buscar
   «PQRS».

Con los tableros visibles y las corridas de la noche hechas, capturar cada uno con el rango de
fechas en «últimos 2 días»:

| Tablero | Filtrar por | Evidencias |
|---|---|---|
| PQRS · Benchmark de ruteo | corrida `evidencia_tnr` | T13 (precisión, latencia, tokens), T14 (fallos por tipología), T19 (últimas corridas) |
| PQRS · Adversarial y bypass | las dos corridas adversariales y la de omisión | T16 |
| PQRS · Grounding | la corrida de fidelidad de la noche | T15 |
| PQRS · Canario de ruteo | — | T17 solo si el canario lleva varias ejecuciones; con una, captura igual y se anota como primera |

Si al abrir Discover el índice `pqr-benchmark-runs-*` no existe, los datos no llegaron: sección 3.6
del documento de avance. Esa comprobación merece hacerse antes de importar nada.

## Qué añade cada cosa al informe

| Si esta noche sale… | El informe gana |
|---|---|
| Tanda 1 completa | R-16 y R-17 definitivos; H-30, H-31, H-32 verificados; posible cierre de H-26 |
| Tanda 2 | T13, la prueba de superación de IT4.6; H-27 cerrado con captura |
| Tanda 3 | 7 capturas: MinIO en crudo (3) y estado del servicio (4); IT2.2 e IT1.6 pasan a evidencia completa |
| Tanda 4 | Hasta 9 evidencias de tablero (T13–T19); IT2.3 e IT2.7 avanzan; IT1.3 e IT1.4 con su tablero |

Mañana, con lo que traigas, trato las capturas, leo las trazas y los registros, y actualizo el
informe, el libro de avance y la entrega.
