# Datos de prueba de Doble Cobro

Fixtures generados por [`scripts/gen_doble_cobro_fixtures.py`](../scripts/gen_doble_cobro_fixtures.py).

Este archivo describe **qué hay en los datos**. Para saber qué escribir en el
front y qué debe responder el bot en cada camino, mira
[`co_pqrs_back_doble_cobro/docs/PRUEBAS_DOBLE_COBRO.md`](../../co_pqrs_back_doble_cobro/docs/PRUEBAS_DOBLE_COBRO.md).

Las reglas del flujo se evalúan contra **la fecha de hoy** (días hábiles de
conciliación, ventana de 6 meses, vigencia de franquicia), así que las fechas
caducan solas. Cuando dejen de servir, regenera:

```bash
cd co_pqrs_back_trx_aso_simulator
python scripts/gen_doble_cobro_fixtures.py
```

> Las fechas de las tablas corresponden a la generación del **2026-09-08**. El
> script las recalcula y las imprime al ejecutarse.

## Clientes

| Cliente | Productos | Para qué |
|---|---|---|
| `13083558` | Ahorro Libretón •2384, CUENTA META •3755, Visa Débito •4818 | El principal: casi todos los caminos |
| `13083559` | Mastercard Débito •7799 | Vigencia de franquicia MASTER (120 días) |
| `13083560` | ninguno | `3.4.0.1.pqr` — «no pude consultar tus productos» |

`13083558` **no** sirve para probar «sin productos»: su tarjeta débito aparece
en la familia de ahorro y en la de corriente, así que siempre devuelve algo.
Tampoco sirve para MASTER: la marca se deduce del primer dígito del PAN (4 =
VISA, 5 y 2 = MASTER) y la suya empieza por 4.

El cliente principal **no tiene cuenta corriente**: elegir «Cuenta corriente»
devuelve solo la Visa Débito, que es lo correcto.

## Escenarios por fecha — cuenta Ahorro Libretón (`13083558`)

| Fecha | Hábiles | Qué prueba | Resultado |
|---|---|---|---|
| 03/09/2026 | 3 | Aún en conciliación | `3.4.0.3.pendiente` — «…de **7** días hábiles» |
| 28/08/2026 | 7 | Mínimo justo | Avanza a pedir el monto |
| 21/08/2026 | 12 | Camino feliz | Selector con transacciones |
| 10/08/2026 | 20 | Casos límite del detector | Ver tabla siguiente |
| 31/07/2026 | 25 | Paginación | 8 cobros sobrantes → 2 páginas |
| 09/01/2026 | — | Fuera de los 6 meses | `3.4.0.3.pqr` |

Los **7 días hábiles aplican por igual** a cuentas de ahorro, corrientes y
tarjetas débito. El 28/08 es el mínimo justo: un día hábil menos y devuelve
«aún en conciliación».

### 21/08/2026 — camino feliz

| Monto | Resultado |
|---|---|
| `145000` | **1 grupo ×3** (SUPERMERCADO LA 14): dos cargos a las 10:15 y 10:19 más un tercero a las 14:30 → **2 reportables**. Al agrupar por día completo, la separación de 4 h no lo excluye |
| `88000` | 1 grupo ×2 (EDS PRIMAX CALLE 80) → 1 reportable |
| `146500` | El mismo grupo de `145000`: la tolerancia de búsqueda es ±2000 |
| `210000` | 0 grupos → `3.4.0.6.pqr` (cargo único) |

### 10/08/2026 — límites del detector

| Monto | Qué hay en los datos | Resultado |
|---|---|---|
| `24500` | 3 cargos del mismo comercio en 8 min | **1 grupo ×3** → 2 reportables |
| `47000` | Mismo comercio y monto, separados **3 horas** | **1 grupo ×2** — la hora no interviene |
| `76000` | Mismo comercio, montos 76.000 y 76.500 | 0 grupos — entran como candidatos pero el monto debe ser idéntico |
| `15000` | Mismo monto y minuto, **comercios distintos** | 0 grupos — falla por comercio |
| `57000` | Cargo único (LIBRERIA NACIONAL) | 0 grupos |

### 31/07/2026 — paginación

| Monto | Qué hay en los datos | Resultado |
|---|---|---|
| `34000` | 8 parejas del **mismo monto** en 8 comercios distintos | 8 grupos ×2 → **8 reportables**: página 1 con 6 + «Ver más movimientos», página 2 con 2 |

Mismo monto en las ocho a propósito: una sola búsqueda tiene que devolverlas
todas, y la tolerancia de ±2000 dejaría fuera a la mitad si cada pareja valiera
algo distinto. Comercios distintos también a propósito: al agrupar la clave es
comercio + monto + fecha, así que salen 8 grupos de 2 y no un único grupo de 16.

## Otros productos de `13083558`

| Producto | Fecha | Monto | Resultado |
|---|---|---|---|
| CUENTA META •3755 | 21/08/2026 | `99000` | 1 grupo ×2 (SEGUROS BOLIVAR) |
| Visa Débito •4818 | 28/08/2026 | `62000` | Frontera de 7 hábiles, igual que las cuentas |
| Visa Débito •4818 | 21/08/2026 | `189000` | 1 grupo ×2 (MERCADO LIBRE CO) |
| Visa Débito •4818 | 11/03/2026 | `450000` | Supera los 180 días de VISA → `3.4.0.3.pqr` |

La fecha de franquicia VISA cae en una ventana estrecha (180 días de vigencia
contra ~182 del plazo general de 6 meses) y puede no contener ningún día hábil
según el mes. Cuando eso pasa el script **omite el escenario** en vez de generar
una fecha que afirmaría lo contrario, y lo avisa al ejecutarse.

## Cliente `13083559` — Mastercard

| Fecha | Monto | Resultado |
|---|---|---|
| 21/08/2026 | `75000` | 1 grupo ×2 (TIENDA ONLINE MASTER) → llega al selector |
| 10/04/2026 | `890000` | Supera los **120 días** de MASTER → `3.4.0.3.pqr` |

La segunda fecha está dentro de los 180 días de VISA y dentro de los 6 meses:
es la única casuística que demuestra que el plazo depende de la marca.

## Cliente `79294815` — volumen

Espeja la estructura de `13083558` y **copia sus movimientos**, así que los casos
conocidos responden igual. Lo que añade es volumen: días con más de 100
movimientos, que `13083558` no tiene en ninguna fecha.

| Contrato | Producto | Movimientos |
|---|---|---|
| `00130766000200079294` | Ahorro •9294 | 169, de los cuales **130 el 20/08/2026** |
| `00130766000200079481` | **Corriente •9481** | **150, todos el 25/08/2026** |
| `4912684136574815` | Visa Débito •4815 | 92 |

`00130766000200079481` es la **primera cuenta corriente del simulador**: hasta
ahora la familia `CHECKING` no tenía ningún dato y ese camino no se podía probar.

### Qué probar

| Producto | Fecha | Monto | Resultado |
|---|---|---|---|
| Ahorro •9294 | 20/08/2026 | `7000` | 14 en rango → pareja CAFE ANDINO + trío MINISO |
| Ahorro •9294 | 20/08/2026 | `8500` | 17 en rango → los mismos dos grupos |
| Corriente •9481 | 25/08/2026 | `187500` | 2 en rango → pareja ALMACEN EXITO CHAPINERO |

Los dos primeros dan **exactamente el mismo resultado que `13083558`** con esa
fecha y ese monto, aunque el día haya pasado de 18 movimientos a 130: el relleno
usa importes por encima de 12.000, fuera del alcance de la tolerancia de
búsqueda (±2000) de los casos copiados. El volumen no los contamina.

### Lo que este cliente NO prueba

**La paginación del ASO.** El endpoint `GET /cards/v2/operations` del simulador
acepta `pageSize` y `paginationKey` y no los usa: devuelve el día entero en una
sola respuesta. Por eso los tres ficheros declaran `totalPages: 1` con
`pageSize` igual al total — es lo único coherente con lo que el simulador hace.

Declarar más de una página **sin que el simulador trocee** haría que el cliente
pidiera la página 2, recibiera la misma respuesta y acumulara cada movimiento
dos veces: 300 movimientos de un día de 150, y una pareja falsa por cada
transacción del día.

Lo que sí ejercita es el volumen en el servicio `:8006`: parsear y filtrar 150
movimientos en vez de 18.

```bash
cd co_pqrs_back_doble_cobro
python scripts/gen_cliente_79294815.py
```

## Sobre el TSEC

El simulador expone `POST /TechArchitecture/co/grantingTicket/V02` y devuelve un
`SIMULATED-TSEC-TOKEN` en la cabecera, pero **sus endpoints no validan el
header `tsec`**: responden 200 con un token válido, uno inventado o ninguno.
Que el flujo funcione contra este simulador no dice nada sobre si el TSEC sirve
contra el ASO real.
