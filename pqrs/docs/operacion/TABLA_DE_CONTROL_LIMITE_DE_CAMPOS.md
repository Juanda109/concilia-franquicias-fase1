# La tabla de control se queda sin campos

Incidente del 1 al 3 de septiembre de 2026. Se documenta porque **el mecanismo
que lo causó se repite en cualquier índice que use fechas como nombre de campo**,
y porque el diagnóstico se equivocó dos veces antes de acertar.

---

## 1. Qué veía el cliente

```
usuario: "Tengo un reporte en centrales y no sé por qué"
  ...15 segundos de espera...
bot:     "En este momento no puedo validar el estado de tus productos
          en las centrales de riesgo."
```

El servicio de fondo funcionaba. El dato existía. El agente no lo encontraba.

Los 15 segundos son el presupuesto de sondeo: `BACK_DATA_MAX_POLL_ATTEMPTS=60`
por `BACK_DATA_POLL_INTERVAL_SECONDS=0.25`. Cuando veas ese tiempo exacto,
sospecha del sondeo, no de la latencia.

## 2. La causa

El índice `client-control-table` **agotó su límite de 1000 campos** y OpenSearch
empezó a rechazar toda escritura:

```json
400 illegal_argument_exception: "Limit of total fields [1000] has been exceeded"
```

Se llenó porque la tabla usa **fechas como nombre de campo**:

```
daily_categories.<YYYYMMDD>.<categoria>.count          ← una rama nueva CADA DÍA
monthly.<YYYY-MM>.workflows.<wf>.back_data_run_id      ← una rama nueva CADA MES
```

OpenSearch registra en el esquema del índice cada ruta distinta que ve. Con
`dynamic: true`, ese contador solo sube. Desde junio hasta septiembre, con unas
pocas categorías en uso, se pasó de los 1000.

### La cadena completa

```
1. El agente intenta crear monthly.2026-09.*   → 400 → SE LO TRAGA (except)
2. back_data escribe en monthly.2026-07 y .08  → esas rutas ya existían → OK
3. El agente lee monthly.2026-09               → vacío
4. Sondea 60 veces / 15 s                      → timeout
5. Cliente: "no puedo validar el estado de tus productos"
```

**El desajuste de meses era un síntoma, no la causa.** El buzón de septiembre no
existía porque el agente no podía crearlo.

### Por qué apareció el 1 de septiembre

Porque el cambio de mes natural obliga a crear rutas nuevas. Mientras cliente y
bot estuvieron dentro del mismo mes, las rutas ya estaban registradas y nadie
notó que el índice estaba al borde.

---

## 3. Cómo diagnosticarlo la próxima vez

Todo lo que hace falta está ahora en las trazas. Estos tres eventos, en orden:

| Traza | Qué mirar |
|---|---|
| `update_client_control_data` `outcome=error` | `response_summary.body` — el motivo real del rechazo |
| `control_table_write` `outcome=error` | igual, pero para las escrituras del **agente** |
| `back_data_control_table` `outcome=timeout` | `response_summary` — qué meses hay y en cuál quedó el sobre |

El diagnóstico del timeout se ve así, y fue lo que cerró el caso:

```json
{
  "mes_actual": "2026-09",
  "meses_en_el_registro":  ["2026-07", "2026-08"],
  "meses_con_el_workflow": ["2026-07", "2026-08"],
  "envelopes": {
    "2026-08": { "status": "ok", "run_id": "ea7a0601",
                 "updated_at": "2026-09-02T14:32:44" }
  }
}
```

Un dato escrito **hoy** que aparece en el buzón de **julio**: ahí está el fallo,
sin necesidad de entrar a OpenSearch.

### Comprobación directa, si tienes acceso

```bash
POD=$(oc get pods -n <ns> -l app=opensearch -o name | head -1)
PASS=$(oc get secret opensearch-secret -n <ns> \
        -o jsonpath='{.data.OPENSEARCH_INITIAL_ADMIN_PASSWORD}' | base64 -d)

oc exec -n <ns> $POD -- curl -sk -u "admin:$PASS" \
  "https://localhost:9200/client-control-table/_settings?flat_settings=true" \
  | tr ',' '\n' | grep -i total_fields
```

Si no devuelve nada, el índice está en el límite de 1000 por defecto.

---

## 4. Cómo arreglarlo

### Índice que ya existe: el desplegable de mantenimiento

```bash
oc create job saneo-$(date +%m%d-%H%M) \
  --from=cronjob/co-pqrs-back-control-table-maintenance -n <ns>

oc logs -n <ns> job/saneo-<sufijo> -f
```

Vive en `IaC/backend/co_pqrs_back_control_table_maintenance/`, es un CronJob
**suspendido** (se lanza a demanda, no por horario) y hace dos cosas:

1. `PUT _mapping` con `dynamic: false` en `daily_categories`, `monthly`, `daily`
   y `workflows` → esas ramas dejan de añadir campos al esquema.
2. `PUT _settings` con `total_fields.limit: 3000` → hueco para los ~1000 ya
   registrados, que no se pueden desregistrar sin reindexar.

**El orden importa.** Solo el paso 2 funciona unos meses y el problema vuelve.
Solo el paso 1 no desbloquea, porque el techo ya está tocado.

No borra documentos, no reindexa y **no reinicia OpenSearch**: son operaciones
en caliente sobre la API. Es idempotente: relanzarlo no hace daño. Y termina en
`exit 1` si alguna petición no es reconocida, para que no haya que deducir nada
de un log en silencio.

> Hay que ejecutarlo **en cada ambiente**. Dev y producción tienen índices
> distintos, cada uno con sus propios campos acumulados.

### Índice nuevo: el template ya lo cubre

`IaC/BD/opensearch/11-configmap-index-templates.yaml` declara las cuatro ramas
con `dynamic: false` y el techo en 3000, así que un índice creado desde cero nace
inmune. Es un ConfigMap: aplicarlo no reinicia nada.

### Lo que NO hay que hacer

El job de bootstrap tiene una variable `FORCE_REINDEX`. En `true` **borra y
recrea el índice**, y con él los contadores de control de todos los clientes
(sesiones por día, topes por categoría, avisos de flujo repetido).

Es un hook `PostSync` de ArgoCD: dejarla en `true` haría que **cualquier
sincronización futura** volviera a borrar la tabla. Si alguna vez hace falta,
devuélvela a `false` en el mismo rato, no al día siguiente.

Además, con el índice vacío la escritura de back_data depende de que el agente
haya creado antes el documento del cliente, y ya vimos que esa escritura puede
fallar. El saneamiento no destructivo evita todo eso.

---

## 5. Guardas automáticas

```
co_pqrs_back_agent/tests/test_infrastructure/
    test_control_table_schema_guards.py     9 tests
    test_control_table_month_bucket.py     23 tests
```

Fallan si:

- alguna de las cuatro ramas por fecha pierde su `dynamic: false`;
- el template baja el techo de campos por debajo de 2000;
- desaparece el desplegable de saneo o deja de estar suspendido;
- se reintroduce el `scripted_upsert` en el script painless de back_data;
- la traza del error pierde el cuerpo de la respuesta;
- **aparece un quinto punto que se trague el fallo de escritura sin trazarlo** —
  ese test cuenta los puntos cableados, así que no depende de que nos acordemos.

---

## 6. Los tres errores de diagnóstico, y qué los causó

Se documentan porque el patrón es más útil que el detalle.

### Error 1 · Concluir por estructura en vez de medir

Leyendo el código se dedujo que el desajuste de meses no podía ocurrir en
producción, porque el agente registra la interacción al entrar al flujo y eso
debería crear el buzón del mes actual. La deducción era correcta **salvo que esa
escritura estaba fallando en silencio**, que es justo lo que no se veía.

### Error 2 · Atribuir por coincidencia temporal

Cuando apareció el 400, coincidía con un despliegue, así que se revirtió el
cambio más sospechoso de ese despliegue (`scripted_upsert`). Era inocente. El
400 venía del límite de campos, y lo que lo disparaba era escribir en un mes
nuevo.

**El mensaje del error lo decía**, pero la traza no llevaba el cuerpo de la
respuesta. Ese fue el arreglo que permitió acertar al día siguiente.

### Error 3 · Probar contra una imitación

El `scripted_upsert` pasó todos los tests porque simulaban OpenSearch en
memoria. Una imitación siempre responde lo que se espera; la base de datos real
rechazó la instrucción. Es como probar una llave contra la foto de la cerradura.

> **Regla que queda:** un cambio en el script painless o en el mapping no se
> puede validar solo con tests en memoria. Hay que probarlo contra un OpenSearch
> de la misma versión que producción, o no se ha probado.

---

## 7. Lo que hizo la diferencia

De todo lo que se cambió, la pieza que resolvió el caso no fue un arreglo: fue
**enriquecer la traza del timeout con el estado del registro**.

Antes decía:

```json
{ "attempts": 60 }
```

Después decía en qué meses estaba el dato y cuál se estaba consultando. Con eso,
el primer caso posterior al despliegue dio la respuesta que dos días de lectura
de código no habían dado.

Cuando un fallo sea difícil de diagnosticar, la primera pregunta útil casi nunca
es "¿qué está mal?" sino **"¿por qué no puedo verlo?"**.
