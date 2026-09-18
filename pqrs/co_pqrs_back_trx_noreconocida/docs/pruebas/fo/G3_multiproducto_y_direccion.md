# G3 · Multiproducto y dirección con la fuente `fo` — evidencia (24/08/2026)

## G3.1 · Selector con 3 tarjetas y candado A-3 (cliente 1013634973)

Selector, literal:
```
VISA ORO LM •0081 · VISA CLASICA •0082 · MASTERCARD BLACK •0083
```
Tres nombres reales distintos (el `[Producto]` del tablero) y las 2 cuentas del fixture
excluidas. Se eligió la **segunda** tarjeta y el flujo entero salió con ella:
confirmación `*0082`, bloqueo `•0082`, paso final `.17.2`. El candado durable quedó
con la clave del PAN de ESA tarjeta:

```
bloqueo_ejecutado:permanente:1013634973_20260824:4912680517940082
```

## G3.2 · Reexpedición `.17.2` CON dirección (cliente M, 1013634970)

```
Te la enviaremos a la dirección CARRERA 15 # 88-64 OFICINA 301, BOGOTA
en un lapso de 10 días hábiles.
```
La dirección real de ADA, enriquecida en la rama `fo`, llega al mensaje.

## G3.3 · Reexpedición SIN dirección (multiproducto, sin `customer_address` en ADA)

```
Te la enviaremos a la dirección registrada en nuestros sistemas
en un lapso de 10 días hábiles.
```
**No hay hueco vacío**: el copy degrada al genérico. Cubre también el caso
Postgres-caída de G2.4 (mismo mecanismo). No hay hallazgo que escalar al PO.

## Notas de método (para el siguiente que pruebe)

1. **G0 quedó corto**: los PANes nuevos necesitaban también su fixture de
   `operations/` (el detalle `.10`), no solo `transactions/`. Copiados en G3.
2. **Caché de operations (900 s por proceso)**: si el fixture se crea DESPUÉS de una
   consulta fallida, el `not_found` queda cacheado — reiniciar el contenedor del
   servicio antes de repetir. Nos costó una sonda entender esto.
