# Probar en local: productos desde el financial-overview (solo-FO)

**Actualizado:** 24/08/2026 (tarde) · **Rama:** `fix/fo-filtro-contrato-prd`
**Estado:** `fo` es la **fuente por defecto y única** de productos (decisión de Fabián,
solo-FO). Postgres/ADA ya no se consulta — ni para la dirección. La rama `postgres`
existe solo como vía de escape deprecada (avisa por log) hasta su retirada (H5).

> Ya **no hace falta gemelo ni bandera**: el stack normal de local funciona en solo-FO.
> Batería completa verificada así: suite 17/17 · mensajes 60/60 · contrato OK ·
> tramo 67/67 · cobertura 66/66.

---

## 1 · Qué devuelve el servicio

`GET http://localhost:8004/v1/trx/productos-activos?customer_id=1013634960`

```json
{
  "status": "ok",
  "id_message": 202,
  "step": "2.4.0.1.4",
  "detail": "Productos validados con el financial-overview.",
  "data": {
    "products": [
      {
        "card_id": "4912680517940060",
        "last_four": "0060",
        "product_desc": "VISA ORO LM",
        "card_brand": "VISA",
        "agreement_contract": "",
        "tipo": "TARJETA_CREDITO",
        "sub_product_type": "CREDIT_CARD",
        "numero_type": "PAN",
        "estado": "OPERATIVE",
        "bloqueable": true,
        "moneda": "COP"
      }
    ],
    "origin_flag": "FO",
    "source": "fo"
  }
}
```

El **array es `data.products[]`** (contrato **v4**); cada elemento es un *producto*
(una tarjeta que superó el filtro). **`customer_address` ya no viaja** — el FO no trae
dirección; el agente lo lee tolerante y el mensaje de reexpedición usa el copy
genérico. Se reintroducirá cuando exista la fuente real (servicio de la NET).

## 2 · El array campo a campo

| Campo | De dónde sale (JSON del FO) | Ejemplo | Quién lo consume |
|---|---|---|---|
| `card_id` | `contracts[i].id` — el **PAN completo** (renombrado en v4: llamarlo contrato confundía) | `4912680517940060` | movimientos, detalle y bloqueo; clave del candado A-3 |
| `last_four` | `contracts[i].number` (con `numberType.id="PAN"` son los últimos 4) | `0060` | las máscaras: selector `•0060`, confirmación `*0060`, bloqueos |
| `product_desc` | `contracts[i].product.name` | `VISA ORO LM` | la etiqueta del selector `{product_desc} •{last_four}` |
| `agreement_contract` | `contracts[i].detail.agreementContract` — en la práctica solo lo traen las **débito** (en el JSON de Nicolás vino anonimizado como token; el API real entrega un número de 20 dígitos). Se captura tal cual | `""` / token | reserva para los servicios que lo pidan |
| `card_brand` | **primer dígito del PAN** (`4`→VISA, `5`/`2`→MASTER); el nombre es respaldo si el PAN viene enmascarado. El BIN **gana** al nombre si contradicen | `VISA` | la vigencia por franquicia (VISA 180 / MASTER 120) |
| `tipo` | `subProductType.id` mapeado | `TARJETA_CREDITO` | distinción TD/TC del roadmap |
| `sub_product_type` | `subProductType.id` tal cual | `CREDIT_CARD` | ídem |
| `numero_type` | `numberType.id` | `PAN` | trazabilidad |
| `estado` | `status.id` (o `detail.status.id`) | `OPERATIVE` | trazabilidad |
| `bloqueable` | indicador `BLOCKABLE` (si no viene, `true`) | `true` | reserva (bloqueos→bono, Manuel Villamil) |
| `moneda` | `currencies[0].currency` | `COP` | reserva |

## 3 · El filtro — las cuatro reglas en cadena

| # | Regla | Excluye |
|---|---|---|
| 1 | `productType == "CARD"` | cuentas, préstamos, fondos |
| 2 | `subProductType.id ∈ {DEBIT_CARD, CREDIT_CARD}` | otros subtipos |
| 3 | `status.id ∈ {OPERATIVE, ACTIVATED, ACTIVE}` | tarjetas bloqueadas/canceladas |
| 4 | `BLOCKABLE.isActive ≠ false` | tarjetas no bloqueables |

Contra el JSON real de Nicolás (8 contratos → sus 2 tarjetas):
`tests/fixtures/financial_overview_real_nicolas.json`.

## 4 · Cómo probar

### A — endpoint directo

```bash
curl -s "http://localhost:8004/v1/trx/productos-activos?customer_id=1013634960" | python3 -m json.tool
```

Clientes útiles del simulador:

| Cliente | Qué demuestra |
|---|---|
| `1013634960` | 1 tarjeta + 1 cuenta (la cuenta se excluye) |
| `1013634973` | **5 tarjetas** (VISA/VISA/MASTER/VISA/MASTER por BIN) + 2 cuentas |
| `1013634959` | solo cuentas → `not_found` → `.4.exit` honesto |

### B — flujo por chat

`reset_cliente.sh <cliente>` y recorrido normal. El selector muestra el **nombre real**
del producto (`VISA ORO LM •0060`), ya no el genérico «Tarjeta de Crédito».

### C — solo tests

```bash
cd co_pqrs_back_trx_noreconocida && uv run pytest -q     # 81, sin stack
```

## 5 · Comportamiento ante fallos (verificado en pantalla)

| Escenario | Qué hace |
|---|---|
| FO caído en el selector | `.4.error` — «no podemos consultar tus productos… inconveniente técnico de nuestro lado» + Formulario PQR. **Nunca** «no tienes productos» |
| FO caído en movimientos | `.8.error` — «no queremos darte información incompleta» |
| FO sin tarjetas | `.4.exit` — «Actualmente no tienes productos activos…» (la única vez que es verdad) |
| Dirección | siempre genérica: «la dirección registrada en nuestros sistemas» (dueño futuro: servicio de datos de la NET del roadmap) |

## 6 · Trampas conocidas al probar

- **Caché de operations (900 s por proceso)**: si creas un fixture DESPUÉS de una
  consulta fallida, el `not_found` queda cacheado — reinicia el servicio.
- Un PAN nuevo en fixtures necesita su JSON en `transactions/` **y** en `operations/`.
- Los arneses de `docs/pruebas` eligen el producto por máscara `•` cuando el literal
  «Tarjeta…» no casa (solo-FO); si escribes sondas propias, haz lo mismo.
