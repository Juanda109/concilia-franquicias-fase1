# G2 · Rutas de error con la fuente `fo` — evidencia (24/08/2026)

Contra el gemelo `trx-fo-probe` (`TRX_PRODUCTS_SOURCE=fo`). Los cuatro escenarios,
vistos EN PANTALLA (transcripción literal del bot), no solo en unitarias.

| # | Escenario | Paso | Resultado |
|---|---|---|---|
| G2.1 | Simulador (FO) parado en el turno del selector | `.4.error` | «En este momento no podemos consultar tus productos por un inconveniente técnico de nuestro lado…» + botón `Formulario PQR`. Frases falsas: **ninguna** |
| G2.2 | Simulador parado en el turno de la fecha (card-id + movimientos) | `.8.error` | «En este momento no podemos consultar los movimientos de tu producto… No queremos darte información incompleta…» + `Formulario PQR`. «No encontramos compras»: **no aparece** |
| G2.3 | Cliente `1013634959` (fixture FO solo-ACCOUNT) | `.4.exit` | «Actualmente no tienes productos activos con nosotros…» — la única vez que esa frase es VERDAD, y sale exactamente ahí |
| G2.4 | `trx-postgres-dev` parada (solo aporta la dirección) | — | endpoint `status=ok`, productos completos, `customer_address=""`; al volver Postgres, la dirección vuelve — fail-open verificado en las dos direcciones |

Nota de método: en G2.2 el andador de `capturar_tramo_luis` no lleva el respaldo de
selección por máscara (solo se añadió al verificador); la sonda eligió el producto por
`•` explícitamente. Si se generaliza el uso de `fo`, conviene llevar el mismo respaldo
a `capturar_tramo_luis._elegir`.
