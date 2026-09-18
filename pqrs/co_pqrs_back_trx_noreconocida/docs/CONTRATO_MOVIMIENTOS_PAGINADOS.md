# Contrato — movimientos paginados en el servicio (Fase 0)

**Para:** Fabián, Luis · **De:** Pablo · **Fecha:** 04/09/2026
**Estado:** APROBADO (Fabián + Luis) e IMPLEMENTADO el 04/09.

> Decisiones firmadas: **Sabor A** (fetch único cacheado + slice en el
> servicio), endpoint **nuevo** `GET /v1/trx/movimientos-pagina`, `page_size=5`
> por defecto, e `id` de la operación como clave de selección estable dentro
> del día. El texto de abajo queda como referencia del contrato entregado.

## Por qué

Hoy la paginación del listado de movimientos vive en el agente: el servicio
trae todos los del día en una llamada (`pageSize=100`) y el agente los trocea de
5 en 5 para el chat. Fabián pidió que esa lógica viva en el servicio y que el
agente quede fino. Además falta el botón para volver a la página anterior.

Este documento fija el contrato del endpoint paginado. Con él acordado se
implementa el servicio, luego el agente (que consume el contrato y muestra
"Anterior" / "Ver más"), y de paso se cierra lo del botón atrás.

## El endpoint

```
GET /v1/trx/movimientos-pagina
```

### Parámetros

| Parámetro | Tipo | Requerido | Nota |
|---|---|---|---|
| `card_id` | string | sí | PAN de la tarjeta (mismo que hoy usa `movimientos-aso`) |
| `fecha` | string | sí | DD/MM/AAAA |
| `from_amount` | number | no | filtro de importe (igual que hoy) |
| `to_amount` | number | no | filtro de importe |
| `page` | int | no | página solicitada, base 1. Por defecto 1 |
| `page_size` | int | no | tamaño de página. Por defecto 5 |

### Respuesta

```json
{
  "status": "ok",
  "page": 2,
  "page_size": 5,
  "total": 70,
  "total_pages": 14,
  "has_prev": true,
  "has_next": true,
  "movimientos": [
    { "id": "TXF006", "descripcion": "FARMACIA CRUZ VERDE", "valor": 70000, "fecha": "2026-08-06" }
  ]
}
```

Campos:

- `page`, `page_size`: los efectivos (si piden una página fuera de rango, se
  devuelve la última válida y `page` refleja la real).
- `total`: movimientos del día dentro del rango de importe.
- `total_pages`: `ceil(total / page_size)`; mínimo 1.
- `has_prev` = `page > 1`; `has_next` = `page < total_pages`.
- `movimientos`: los de ESA página. Cada uno con `id` estable (el `id` de la
  operación del ASO). El `id` es lo que permite que la selección deje de ser
  posicional: el agente devuelve el `id` elegido al gate de detalle.

### Casos borde

| Situación | Respuesta |
|---|---|
| Día vacío | `total:0`, `total_pages:1`, `movimientos:[]`, `has_prev:false`, `has_next:false` |
| `page` mayor que `total_pages` | se acota a la última; `page` = `total_pages` |
| `page` < 1 | se acota a 1 |
| Fallo del ASO | mismo criterio que `movimientos-aso` hoy: `status:"error"`, sin inventar "no hay compras" (fail-closed) |

## Decisión de diseño: cómo trae los datos el servicio

**Sabor A (recomendado): fetch único cacheado + slice en el servicio.**
El servicio pide `pageSize=100` al ASO (una vez, ya cacheado 900s por
card+fecha) y rebana la página en memoria. Ventajas: una sola llamada al ASO,
navegación instantánea entre páginas, sin re-granting por página. Sin tope de
movimientos por día: el servicio recorre todas las páginas del ASO
(`pagination.totalPages`) y las acumula antes de rebanar.

**Sabor B: paginación nativa del ASO.**
Cada página pide `pageSize=5&paginationKey=page` al ASO. Escala por encima de
100, pero es una llamada por página y la caché actual (por card+fecha) no
ayuda. `paginationKey` es un entero (número de página, no cursor), así que el
acceso a cualquier página — incluida la anterior — funciona.

Recomendación: **A**. Cubre el caso real (70 movimientos) sin multiplicar
llamadas al ASO, y deja el B como evolución si algún día un día supera 100.

## Qué cambia en el agente (resumen, para contexto)

- El agente pasa `page` y pinta lo que llega. Muestra "Anterior" si `has_prev`,
  "Ver más movimientos" si `has_next".
- La selección pasa a ser local a la página visible (`movimiento_1..5` → los 5
  que se ven). El movimiento elegido se identifica por `id`.
- El gate de detalle (`2.4.0.1.10`) y la clasificación leen el movimiento
  elegido por `id`, no por índice en la lista completa.
- No cambian los steps 2.x.x.x ni las reglas de negocio.

## Lo que hay que validar (Fabián / Luis)

1. ¿Sabor **A** o **B**?
2. ¿El nombre y la forma del endpoint encajan con lo que tienes en mente, o
   prefieres extender `movimientos-aso` en vez de un endpoint nuevo?
3. ¿`page_size=5` por defecto (5 casillas del selector) o lo dejamos configurable?
4. Confirmar que el `id` de la operación del ASO es estable dentro del día
   (es la clave de la selección por id).

Con estas cuatro respuestas se arranca la Fase 1 (el endpoint) con su batería de
tests, luego la Fase 2 (agente fino + botón Anterior) y el E2E.
