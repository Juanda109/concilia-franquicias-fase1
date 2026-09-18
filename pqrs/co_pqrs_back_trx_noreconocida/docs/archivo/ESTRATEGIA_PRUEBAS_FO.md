# Estrategia — probar a fondo la fuente `fo` (productos desde el financial-overview)

**Fecha:** 24/08/2026 · **Rama:** `fix/fo-filtro-contrato-prd`
**Punto de partida:** la validación de productos está probada (15 unitarias sobre el JSON
real de Nicolás + endpoint en vivo + llegada al selector). **Lo que nunca se ha ejecutado
con `fo` es todo lo que viene después del selector.** Esta estrategia cierra esos huecos
con el mismo método de la batería: recorridos dirigidos, verificación por estado en
OpenSearch, y logs como evidencia empírica.

## Principios

1. **La fuente por defecto no se toca.** Todo corre contra un contenedor gemelo
   (`trx-fo-probe`) con `TRX_PRODUCTS_SOURCE=fo`; el original se restaura al final y se
   prueba que quedó bien (la restauración también es una prueba).
2. **Reusar la batería, no inventar otra.** `verificar_tramo_luis.py` ya recorre bloqueo,
   desenlaces, bucle y bloqueo repetido; se ejecuta tal cual contra el gemelo. Las
   divergencias de literal esperadas (el selector dice ahora el nombre real del producto)
   se anotan ANTES de correr, para clasificar cada aviso como *esperado* o *sorpresa*.
3. **Entorno inestable (T-2):** lotes de 2-3 comandos, stack reiniciado antes de cada
   pasada larga, repetir en aislamiento lo que falle.

---

## G0 · Preparar el terreno (~15 min)

| Tarea | Detalle |
|---|---|
| Fixture FO del **multiproducto** | `co_pqrs_back_trx_aso_simulator/data/financial_overview/1013634973.json`: sus 3 tarjetas de ADA (…0081/…0082/…0083, `CREDIT_CARD`) **+ 2 cuentas** `ACCOUNT` como negativos — mismo formato que `1013634960.json` |
| Fixture FO del cliente **fuera de plazo** | `1013634965.json`: 1 tarjeta (…0065) |
| Fixture FO del cliente **sin tarjetas** | `1013634959.json`: SOLO contratos `ACCOUNT` → debe dar `not_found` → `.4.exit` |
| Gemelo `fo` arriba | receta del doc `PROBAR_PRODUCTOS_FO_EN_LOCAL.md` §4A; verificar `TRX_PRODUCTS_SOURCE=fo` con `docker exec` |
| Baseline de endpoint | `curl /productos-activos` por cada cliente de la tabla → guardar en `docs/pruebas/fo/` |

Los fixtures son **data del simulador** (no viajan en la imagen del servicio): riesgo cero
para las fuentes reales.

## G1 · El tramo completo con `fo` (el hueco grande)

Correr contra el gemelo, por lotes:

```
verificar_tramo_luis.py bloqueo            (11 comprobaciones)
verificar_tramo_luis.py desenlaces         (39)
verificar_tramo_luis.py bucle              (4)
verificar_tramo_luis.py bloqueo_repetido   (5)  ← necesita el fixture G0 del multiproducto
```

**Divergencias esperadas** (todo lo demás es sorpresa y se investiga):
- etiquetas del selector: `Tarjeta de Credito •XXXX` → `VISA ORO LM •XXXX` (nombre real del FO);
- ninguna otra: máscaras, montos, fechas y desenlaces deben ser idénticos.

**Verificación empírica extra** (la que responde al hueco #1): en los logs del gemelo,
el paso de movimientos debe mostrar `card_id` = PAN del FO (`contracts[i].id`) y el
listado debe casar por `last_four`. Un grep, no una suposición.

## G2 · Las rutas de error con `fo` en pantalla

| Escenario | Cómo se fuerza | Qué debe pasar |
|---|---|---|
| FO caído | parar el simulador en el turno del selector | `.4.error` («no podemos consultar tus productos…») y **ninguna** frase falsa |
| FO caído en movimientos | parar el simulador tras elegir producto, antes de la fecha | `.8.error` |
| Cliente sin tarjetas | cliente `1013634959` (fixture solo-ACCOUNT) | `.4.exit` («Actualmente no tienes productos activos…») — aquí esa frase SÍ es verdad |
| Postgres caída (solo dirección) | `docker stop trx-postgres-dev` y recorrer | productos salen; ver G3 para el mensaje `.17` |

## G3 · Multiproducto y dirección (los dos finos)

1. **Selector con 3 tarjetas** (`1013634973`): las tres visibles con su máscara, elegir
   la 2ª, verificar en OpenSearch que la clave del producto (candado A-3) ahora es el
   **PAN** y el flujo sigue entero.
2. **Reexpedición `.17` con dirección**: recorrer hasta «Te la enviaremos a la
   dirección…» y verificar la dirección real de ADA en el mensaje.
3. **Reexpedición con Postgres caída**: la dirección llega vacía — ¿el mensaje queda
   con un hueco? Si sí, es **hallazgo** (¿mensaje alternativo? ¿pedir la dirección?):
   se documenta y se plantea al PO, no se parchea en caliente.

## G4 · Cierre y restauración

1. `docker rm -f trx-fo-probe && docker start trx-esqueleto`.
2. Smoke con la fuente original: `verificar_tramo_luis.py bloqueo` → 11/11.
3. Evidencias a `docs/pruebas/fo/` (capturas de endpoint, transcripciones, greps de logs).
4. Actualizar `PROBAR_PRODUCTOS_FO_EN_LOCAL.md` §6 (límites que se cierren) y
   `DECISIONES_PENDIENTES_TXNR.md` si G3.3 destapa la pregunta de la dirección.
5. Anotar el caso de borde de **migración del candado A-3** (clave LIC→PAN el día del
   switch en un entorno con historia) — no es de local, pero no debe perderse.

## Criterio de aceptación

- Las 59 comprobaciones del tramo (11+39+4+5) en verde con `fo`, con los avisos de
  literal **clasificados uno a uno** (esperado/sorpresa, cero sorpresas sin explicar).
- Las 4 rutas de error de G2 vistas **en pantalla**, no solo en unitarias.
- El `card_id` del paso de movimientos verificado en logs como PAN del FO.
- Restauración probada (smoke `postgres` en verde).
- Todo hallazgo con su decisión: corregido aquí, o documentado para el PO.

## Qué NO cubre (y a quién le toca)

- **El FO real de producción** (forma exacta del JSON del API): prueba en desplegado
  con el usuario de Fabián — es el «ajustamos a partir de data real» del equipo.
- **Los abonos en el listado** (H-14-3): decisión ya tomada en el tablero, cambio aparte.
- **La fuente futura de la dirección** (servicio NET del roadmap): fuera del alcance.

---

## Resultado de la ejecución (24/08, tarde)

| Fase | Resultado |
|---|---|
| G0 | fixtures FO de `…65`/`…73`/`…59` + transactions/operations de los PANes 0081-0082; baseline de endpoint de 7 clientes en `fo/` |
| G1 | **59/59** (bloqueo 11 · desenlaces 39 · bucle 4 · bloqueo_repetido 5), 0 avisos; card_id de movimientos/bloqueo = PAN del FO, verificado en logs (`fo/G1_logs_card_id_pan.txt`) |
| G2 | las 4 rutas de error EN PANTALLA: `.4.error`, `.8.error`, `.4.exit` honesto, fail-open de dirección con recuperación (`fo/G2_rutas_de_error.md`) |
| G3 | selector 3 tarjetas con nombres reales; flujo entero por la 2ª; candado A-3 = PAN de esa tarjeta; `.17.2` con dirección real y degradación limpia sin dirección — **sin hallazgos para el PO** (`fo/G3_multiproducto_y_direccion.md`) |
| G4 | restauración verificada: contenedor original con `postgres`, smoke bloqueo 11/11 |

**Criterio de aceptación: cumplido entero.** Divergencia única y explicada: la etiqueta
del selector pasa a ser el nombre real del producto (respaldo de selección añadido al
verificador). El caso de borde de la migración del candado (clave LIC→PAN el día del
switch en entornos con historia) queda anotado en DECISIONES.
