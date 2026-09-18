# Estrategia — sólo financial-overview (adiós Postgres/ADA)

**Fecha:** 24/08/2026 · **Decisión de Fabián:** la base Postgres (la imagen de esta
mañana) **no se usa**. La única fuente de productos es el **financial-overview**. Se
asume la pérdida de lo que el FO no trae (la dirección) y se busca la máxima
simplificación. A Luis se le pasa **solo la información útil extraída del FO**.

**Punto de partida verificado** (estrategia G0-G4 de hoy): la fuente `fo` ya funciona de
punta a punta — 59/59 del tramo, 4 rutas de error en pantalla, multiproducto, candado
con PAN — y el mensaje de reexpedición **ya degrada solo** cuando no hay dirección
(«a la dirección registrada en nuestros sistemas»). Esta estrategia no arranca de cero:
convierte aquel conmutador en el único camino.

---

## 1 · Diccionario de datos — análisis campo a campo del JSON de Nicolás

Del fichero real (`tests/fixtures/financial_overview_real_nicolas.json`, 8 contratos).
Primera decisión de método: **el contrato se filtra, luego se extrae** — solo
`productType=CARD` + `subProductType ∈ {DEBIT_CARD, CREDIT_CARD}` + estado operativo.

### 1.1 · Campos que SE EXTRAEN (los útiles)

| Ruta en el JSON | Ejemplo real | A qué campo del array va | Para qué sirve |
|---|---|---|---|
| `contracts[i].id` | `4912680517940068`¹ | `contract_id` | **el card_id** de movimientos, detalle y bloqueo; clave del candado A-3 |
| `contracts[i].number` (con `numberType.id="PAN"`) | `"2583"` | `last_four` | todas las máscaras que ve el cliente (`•2583`, `*2583`) |
| `contracts[i].product.name` | `"Visa Débito"`, `"VISA ORO"` | `product_desc` | la etiqueta del selector `[Producto] •[xxxx]` del tablero |
| `contracts[i].subProductType.id` | `DEBIT_CARD` / `CREDIT_CARD` | `tipo`, `sub_product_type` | la distinción TD/TC del roadmap |
| `contracts[i].status.id` (y `detail.status.id`) | `OPERATIVE` | filtro + `estado` | sólo tarjetas operativas |
| `contracts[i].id` (primer dígito) + `product.name` (respaldo) | `4…`→VISA, `5…/2…`→MASTER | `card_brand` | **la vigencia por franquicia** (VISA 180 / MASTER 120). Ver §3.1 — hoy se deriva sólo del nombre y eso es frágil |
| `contracts[i].detail.indicators[BLOCKABLE].isActive` | `true` | `bloqueable` | reserva para la pregunta de bloqueos→bono (Manuel Villamil) |
| `contracts[i].currencies[0].currency` | `COP` | `moneda` | trazabilidad; hoy sin lógica asociada |

¹ En el fichero compartido viene `********` por censura al compartirlo; el API real
entrega el PAN completo (confirmado por Fabián/Nicolás el 24/08).

### 1.2 · Campos que NO se extraen, y por qué (decisión explícita, no olvido)

| Ruta | Por qué se ignora |
|---|---|
| `family[]` (agregados por familia) | totales de saldo por familia — el TXNR no razona sobre saldos |
| `contracts[i].detail.specificAmounts` (saldos, cupos) | ídem: mostrar saldos exigiría garantías de frescura que este canal no da |
| `participant.name` (titular) | el canal ya está autenticado; repetir el nombre no aporta y es dato personal |
| `bank`, `branch`, `countryId` | constantes del banco / no aportan al flujo |
| `classification.level`, `formats[]`, `alias`, `isLegacy`, `relatedContracts` | metadatos del contrato sin uso en el TXNR |
| `detail.images`, `detail.rewards`, `detail.physicalSupport`, `embossingDate` | cosmética de la app |
| `detail.agreementContract` (token) | uso desconocido — se anota por si el ASO lo pide en otro servicio |
| `detail.expirationDate` | sin uso hoy; candidata si algún día se valida vigencia del plástico |
| Contratos `ACCOUNT` / `LOAN` / `INVESTMENT_FUND` | fuera del alcance TD-TC del tablero |

### 1.3 · Lo que se PIERDE al quitar Postgres (asumido por decisión)

| Dato | Dónde se usaba | Mitigación |
|---|---|---|
| `customer_address` | mensaje de reexpedición `.17.2` | el copy degrada solo: «a la dirección registrada en nuestros sistemas» — **verificado en G3.3**. Dueño futuro: el servicio de datos personales de la NET (roadmap) |
| `origin_flag` TDC/PASIVO de ADA | regla `pendiente_tdc` de la clasificación | con FO **todo lo que entra es tarjeta**: `origin_flag="TDC"` constante — la regla no cambia |
| `card_type` D/M | filtro del diagrama | equivale a `subProductType` DEBIT/CREDIT del FO |

### 1.4 · Riesgos de vocabulario detectados en el JSON real

- **Estados heterogéneos**: tarjetas `OPERATIVE`, cuentas `ACTIVATED`/`ACTIVE`, y
  `detail.status.name` en español («ACTIVADA»). El filtro acepta `{OPERATIVE,
  ACTIVATED, ACTIVE}` sobre los `id`, nunca sobre `name`.
- **`product.name` no siempre delata la franquicia** («TARJETA AQUA» no dice VISA) —
  motivo del §3.1.
- **Multimoneda**: la cuenta USD del ejemplo demuestra que `currencies[]` puede variar;
  para tarjetas se toma la primera.

## 2 · El contrato del array para Luis (v2 — sólo FO)

**v3 (24/08, tarde): `customer_address` retirado del array y del sobre.** Se verificó
que todas las lecturas del agente son `.get()` tolerantes (chat_service 1268/1271/1490,
workflow_actions 2055) y el `.17.2` degrada al copy genérico con el campo ausente —
probado en pantalla. Se reintroducirá cuando exista la fuente real (NET).

```json
{
  "contract_id": "<PAN completo>",      // card_id de todo el tramo ASO
  "last_four": "2583",
  "product_desc": "Visa Débito",
  "card_brand": "VISA",                  // ver §3.1: BIN primero, nombre de respaldo
  "origin_flag": "TDC",                  // constante: todo es tarjeta
  "tipo": "TARJETA_DEBITO",
  "sub_product_type": "DEBIT_CARD",
  "numero_type": "PAN",
  "estado": "OPERATIVE",
  "bloqueable": true,
  "moneda": "COP"
}
```

## 3 · Fases

### H1 · Endurecer la extracción (½ jornada)

1. **Franquicia por BIN** (`§1.4`): primer dígito del PAN (`4`→VISA, `5`/`2`→MASTER) y
   `product.name` como respaldo. Motivo: hoy una marca no reconocida hereda el trato
   VISA (180 días) — el **plazo más largo** por defecto, la familia de defectos que
   Fabián vetó (dato inventado). Con BIN, «desconocida» prácticamente desaparece.
2. Retirar de `productos_desde_fo` el campo `customer_address` de ADA (queda `""`).
3. Tests nuevos sobre el JSON de Nicolás: BIN 4→VISA en sus 2 tarjetas; casos 5/2/desconocido.

### H2 · `fo` pasa a ser el único camino (½ jornada)

1. `TRX_PRODUCTS_SOURCE` por defecto → `fo` (`config.py` + `.env.example` + `.env`).
2. La rama `fo` de `consultar_productos_activos` **pierde el enriquecimiento de
   dirección** (se va la llamada a `_load_products_from_postgres`).
3. La rama `postgres` se marca **deprecada** (log de aviso al arrancar si está
   configurada). **No se borra todavía**: retirar el código, los seeds
   (`dev/postgres/`), el contenedor y la imagen de esta mañana es la fase H5, con el
   visto bueno explícito de Fabián — borrar y desplegar el mismo día multiplica el
   riesgo sin necesidad.
4. IaC: `TRX_PRODUCTS_SOURCE=fo` en el configmap del servicio (rama dev).

### H3 · La batería entera con `fo` como defecto (½ jornada)

Ya no es el gemelo: es el contenedor normal. Se corre TODO, no sólo el tramo:
unitarias · suite 17 · mensajes 60 · contrato · tramo Luis (59) · **cobertura re-medida**
· re-captura y diff contra baseline (las etiquetas del selector cambian de
«Tarjeta de Credito» al nombre real — divergencia esperada, se re-basea).
El andador de `capturar_tramo_luis._elegir` recibe el mismo respaldo de selección por
máscara que ya tiene el verificador.

### H4 · Documentación y entrega a Luis (1 h)

- `PROBAR_PRODUCTOS_FO_EN_LOCAL.md`: pasa de «cómo probar el conmutador» a «así
  funciona la única fuente»; sección de dirección actualizada.
- `DECISIONES_PENDIENTES_TXNR.md`: la decisión 11 (candado LIC→PAN) pasa de hipótesis a
  **real** — hay que decidirla antes del despliegue; nueva entrada: retirada física de
  Postgres (H5) pendiente de OK.
- Mensaje para Luis: el contrato v2 del §2 con el diccionario del §1.

### H5 · Retirada física de Postgres (cuando Fabián dé el OK)

Borrar: rama `postgres` del servicio, `_load_products_from_postgres`, seeds
`dev/postgres/`, contenedor local, imagen/manifiestos de IaC de esta mañana, y la
variable de los configmaps. Es la fase **irreversible**: va sola, después de que
DEV ruede con `fo` unos días.

## 4 · Preguntas que esta estrategia deja explícitas

1. **Franquicia por BIN** — ¿confirmamos 4→VISA, 5/2→MASTER como criterio? (§3.1; hoy
   el desconocido hereda 180 días).
2. **Candado A-3** — clave LIC→PAN el día del switch (decisión 11): ¿aceptar ventana o
   normalizar a `last_four` antes?
3. **Dirección** — ¿cuándo llega el servicio de la NET del roadmap? Hasta entonces,
   copy genérico (ya verificado).
4. **H5** — ¿cuándo se borra físicamente Postgres? (imagen de esta mañana incluida).

---

## Resultado de la ejecución (24/08, tarde)

| Fase | Resultado |
|---|---|
| H1 | franquicia por **BIN** (4→VISA, 5/2→MASTER; nombre de respaldo; el BIN gana si contradicen; desconocida → vacía, sin adivinar). Servicio 81/81 |
| H2 | `fo` **por defecto y único**: la rama fo no toca Postgres (test que explota si lo hace); postgres deprecado con WARNING; IaC del servicio a `fo`; dirección siempre vacía |
| H3 | batería entera con `fo` de serie: **suite 17/17 · mensajes 60/60 · contrato OK · tramo 67/67 · cobertura 66/66**; multiproducto ampliado a **5 tarjetas** (Producto 2-5 renderizables); diff de capturas 22/22 clasificados (los dos cambios solo-FO esperados: nombre real del producto y dirección genérica); re-baseo hecho |
| H4 | docs limpiados y al día (`archivo/` para lo histórico); DECISIONES renumerado con las preguntas nuevas (BIN, candado, H5, roadmap pendiente) |
| H5 | **pendiente del OK de Fabián** (retirada física de Postgres) |

Divergencia única de arnés: la etiqueta del selector es el nombre real del producto;
los 5 scripts de pruebas llevan el respaldo de selección por máscara.
