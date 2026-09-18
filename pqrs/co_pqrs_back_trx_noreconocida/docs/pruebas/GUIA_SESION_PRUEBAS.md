# Guía de sesión — pruebas de UI del flujo trx

**Abre este documento primero.** Te lleva de "el portátil apagado" a "probando", te
organiza la sesión en bloques que puedes cortar, y te dice qué copiarme cuando algo falle.

El detalle de cada caso está en [`PLAN_PRUEBAS_UI.md`](./PLAN_PRUEBAS_UI.md), con los
pasos ya verificados y el texto literal que debe aparecer.

---

## 1 · Arranque (3 comandos)

```bash
# 1. ¿está todo arriba?
for p in 8000 8004 8050; do curl -s localhost:$p/health; echo; done
curl -s -o /dev/null -w "UI %{http_code}\n" localhost:8501

# 2. clientes a cero (hazlo SIEMPRE al empezar una sesión)
cd co_pqrs_back_trx_noreconocida/docs/pruebas && ./reset_cliente.sh --todos

# 3. abre http://localhost:8501
```

Si algún `/health` no responde, dímelo y relanzo el stack — no pierdas tiempo tú.

---

## 2 · Los cuatro bloques

Cada bloque usa clientes que **no colisionan entre sí**: puedes hacerlo entero sin
resetear a mitad. Entre bloques, `./reset_cliente.sh --todos`.

### Bloque 1 · Salidas tempranas (~20 min)
Todo lo que termina antes de pedir producto.

| Caso | Cliente | Qué prueba |
|---|---|---|
| U-1 | 1013634962 / 63 / 64 | los 3 sucesos de fraude → formulario |
| U-4 | 98787954 | "Más de 3" → formulario |
| U-5 | 1013634959 | sin productos vigentes |

### Bloque 2 · Camino feliz y sus desvíos (~25 min)
El corazón de tu tramo.

| Caso | Cliente | Qué prueba |
|---|---|---|
| U-7 | 1013634960 | elegir el 2.º movimiento → confirmación |
| U-8 | 1013634960 *(resetear antes)* | reenganche con la misma fecha (defecto H-11, ya corregido) |
| U-10 | 1013634966 | "Seleccionar otro producto" |
| U-11 | 1013634965 | MASTERCARD vencida |

### Bloque 3 · Entradas raras (~25 min)
Lo que un cliente real hace sin querer.

| Caso | Cliente | Qué prueba |
|---|---|---|
| U-9 | 1013634961 | producto inexistente, fecha futura, formatos alternos |
| U-13 | 01576905 | texto libre y números donde van botones |
| U-14 | 1013634964 | repetir la misma opción |
| U-19 | 01576905 *(resetear antes)* | fecha con espacios y fecha larguísima |
| U-3 | 10482895 | cantidades 2 y 3 |
| U-6 | 1013634963 / 62 | rango fuera de límite |
| U-16 | 1013634961 *(resetear antes)* | índice de movimiento inválido (H-13, **abierto**) |
| U-17 | 1013634962 | reabrir a mitad de flujo |

### Bloque 4 · [STACK] — al final y con cuidado (~30 min)
Paran servicios. **Restaura entre uno y otro** y comprueba salud antes de seguir.
Si prefieres, dímelo y los ejecuto yo: son los que más fácil dejan el entorno raro.

---

## 3 · Mapa cliente → casos (cuándo resetear)

| Cliente | Aparece en | Nota |
|---|---|---|
| `1013634960` | U-7, U-8 | resetea entre ambos |
| `1013634961` | U-9, U-16 | resetea entre ambos |
| `1013634962` | U-1a, U-6b, U-17 | resetea entre cada uno |
| `1013634963` | U-1b, U-6a | resetea entre ambos |
| `1013634964` | U-1c, U-14 | resetea entre ambos |
| `01576905` | U-13, U-19 | resetea entre ambos |
| `1013634959`, `1013634965`, `1013634966`, `98787954`, `10482895` | un caso cada uno | — |

**Regla simple:** si el bot te saluda y sigue a mitad de camino, o te desvía a PQR nada
más elegir el suceso 4, **es que no reseteaste**. No es un fallo del flujo.

---

## 4 · Los destinos esperados por cliente

Consulta esta tabla antes de reportar nada: **el destino lo elige el cliente**, no el
camino que hagas.

| Cliente | Termina en | ¿Es correcto? |
|---|---|---|
| `1013634958` (A) | *"Encontré una gestión reciente…"* + Formulario PQR | ✅ tiene recurrencia sembrada |
| `1013634959` (B) | *"no tienes productos activos… app BBVA"* | ✅ `card_flag=false` a propósito |
| `1013634960` (C) | camino completo: 3 movimientos → confirmación | ✅ el caso feliz |
| `1013634961` (D) | 1 movimiento → confirmación | ✅ |
| `1013634964` (G) | *"Esta compra se encuentra… en estado pendiente"* | ✅ |
| `1013634965` (H) | *"supera el plazo permitido por las franquicias"* con `01/01/2025` | ✅ MASTERCARD, 120 días |
| `1013634966` (I) | *"No encontramos compras registradas"* + 3 salidas | ✅ sin transacciones |
| `1013634967` (J) | camino normal, pero el producto sale como **\*4321** | ✅ divergencia deliberada: ADA dice `9999`, el PAN de financial-overview termina en `4321`. Si ves `*9999`, es un fallo real |

**Fecha con movimientos: `06/08/2026`.** Cualquier otra dará "sin compras" y es correcto.

---

## 5 · Cuando algo falle

Copia **estas cuatro cosas** y me las pasas — con eso lo diagnostico sin volver a
preguntarte nada:

1. **El caso y el cliente** (p. ej. "U-8 con 1013634960").
2. **Captura de pantalla** o el texto literal que viste.
3. **Lo que esperabas**, según el documento.
4. **El journey**:
   ```bash
   docker logs co-pqrs-back-agent --since 10m | grep "TXNR paso"
   ```

Si el bot dice *"Tuvimos un inconveniente"* o se queda pensando mucho, añade:

```bash
docker logs co-pqrs-back-agent --since 5m | grep -iE "error|traceback" | tail -20
docker logs trx-esqueleto      --since 5m | tail -20
```

---

## 6 · Al terminar

Anota en la columna **«Comentarios de ejecución»** del documento único
(`Merged_Flux.xlsx`) lo que observaste — literal, sin filtrar: un texto raro, un botón
inesperado, una espera larga. De ahí salen los análisis y los refactores.

Pásamelo y te devuelvo: qué es hallazgo, qué es corrección del plan y qué propongo
cambiar en el código.

---

## 7 · ¿Se movió la rama base?

Nuestro trabajo vive en `feature/trx-esqueleto`, que salió de `feature/PQRSdev` (la de
Fabián). Si él avanza su rama, conviene traer sus cambios **antes** de que revise el PR:
los conflictos se resuelven mejor aquí, con contexto, que en el merge del PR.

```bash
./estado_rama.sh      # desde docs/pruebas
```

Dice si hay algo que traer, qué trae y qué ficheros tocaríais los dos. Si avanzó:

```bash
git merge origin/feature/PQRSdev
# resolver, correr los tres verificadores y push
```

**Merge, no rebase**: nuestra rama ya está publicada y el rebase reescribiría los commits,
obligando a `push --force` sobre algo que otros pueden tener descargado.
