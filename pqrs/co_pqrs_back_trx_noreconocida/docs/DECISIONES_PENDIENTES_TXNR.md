# Decisiones pendientes — flujo TXNR

**Actualizado:** 31/08/2026 (noche) · **Rama:** `feature/PQRSdev` @ `a4f4159` · **Sin token de git hasta la daily del 01/09**
**Para:** Fabián (jefe/PO), Luis, Nicolás y Jessica (Data/ASO)

Sólo preguntas y pendientes abiertos. Lo resuelto vive en el historial de git,
`docs/archivo/` y `docs/report/`.

---

## Para Fabián / PO

### 1 · 🟠 Salidas tempranas y el bucle multi-transacción (A-4)

Los cuatro desenlaces ofrecen «¿reportamos la siguiente?»; las salidas tempranas no
(quien declara 3 y la primera resulta *pendiente* pierde las otras 2 sin aviso).

> **Pregunta:** ¿en qué salidas se ofrece continuar? El mecanismo (`.20.0`) existe;
> conectar cada salida es una línea de YAML.

### 2 · 🔴 Franquicia en producción: el BIN murió con la tokenización

El ASO real entrega los `card_id` **tokenizados** a nuestro consumidor → el primer
dígito ya no es un BIN → la franquicia depende **100 % de `product.name`**
(«Visa Clásica» → VISA). Una tarjeta cuyo nombre no diga Visa/Master queda sin marca
y hereda el trato VISA (180 días, el plazo más largo).

> **Pregunta:** ¿`product.name` del FO SIEMPRE trae la marca? Si no, ¿pedir al ASO el
> campo de franquicia (`brandAssociation` venía `null` en las muestras)?

**Actualización 31/08:** el fix de #3 (PAN desde `formats[].number`) revive la
derivación por BIN — la franquicia dejará de depender solo de `product.name`.
Este pendiente baja de gravedad en cuanto ese fix entre.

### 3 · 🔴→🟢 H-1 RESUELTO EN DIAGNÓSTICO (31/08): el PAN siempre estuvo en el FO

La traza completa del `financial_overview` del 30/08 cerró el caso. Cada
contrato trae DOS identificadores: el token en `contracts[].id` (estable por
tarjeta — H-2) y **el PAN real en `contracts[].formats[].number`**
(`4504…1106`, `4912…2289`). `operations` exige el PAN; nuestro
`productos_desde_fo` (aso_rules.py:514) envía el token — una asunción heredada
del JSON anonimizado («el valor ES el PAN») que la data real desmintió. El
fallback del agente que sí resuelve el PAN jamás dispara porque el token nunca
está vacío.

> **Fix (listo para aplicar con el token de git del 01/09):** `productos_desde_fo`
> toma el PAN de `formats[].number` con `numberType=PAN` (como ya hace
> `extraer_card_id`), token como fallback. Toca SOLO el servicio TXNR → una
> imagen. Desbloquea el E2E conversacional completo en DEV y revive la
> franquicia por BIN (#2).

> **Para ratificar con Fabián/Nicolás (PCI):** el fix implica que el PAN en
> claro viaja a `operations` y se persiste como `card_id` de la conversación
> (hoy lo hace el token). Es lo que el ASO exige — pero conviene decirlo alto.

> **Pregunta a Nicolás, rebajada a confirmación:** ¿correcto que `operations`
> solo acepta PAN y no hay variante tokenizada? (La evidencia dice que sí.)

### 4 · ⛔ H5 (retirada de Postgres) — CANCELADA (25-26/08)

Postgres tiene dos consumidores de nuevo: la **dirección** del bloqueo definitivo
(vía back_data en `.17.3`) y el **`personal_id`** del `profileId` de la subida de
nivel. La rama `postgres` del servicio sigue deprecada solo para PRODUCTOS.

### 4b · 🟡 Riesgo aceptado: semántica del 204 del ASO

`2xx sin cuerpo = «el cliente no tiene datos»` → `.4.exit`. Si un 204 viniera de una
sesión mal autenticada (el incidente del 25/08, ya resuelto), el bot diría «no tienes
productos» a quien sí los tiene.

> **Pregunta:** ¿confirmó Nicolás que un FO **bien autenticado** de un cliente CON
> productos jamás devuelve 204?

Dato a favor (30/08): los rechazos del ASO observados en la sesión llegaron como
**400 con cuerpo**, no como 204 — el riesgo de confundir «error» con «sin datos»
parece menor de lo temido.

### 5 · 🟡 Roadmap del PO — estado de implementación

| Qué | Estado |
|---|---|
| Listado con abonos (sin filtro EXPENSE) | ✅ implementado (dev 25/08) · ⛔ en DEV solo funciona con PAN en claro (H-1/#3): con clientes tokenizados el listado no sale |
| OOB / subida de nivel (push App BBVA) | ✅ implementado y **probado E2E en local** (28/08, ceremonia completa). En DEV faltan la cédula (#13), el usuario enrolado (#14) y además lo frena H-1/#3 |
| Descripción·Valor·Fecha correctos para el cliente | ✅ implementado (PR #85, 27/08) |
| Vigencia VISA nacional 180 / interop-internacional 120 | ⏳ pendiente (hoy no distinguimos ámbito) |
| Dirección de reexpedición desde el servicio NET | ⏳ pendiente (hoy: back_data/Postgres) |

### 6 · 🟠 Valores definitivos para QA/PRD

`MAX_DAILY_*`/`MAX_REPEAT_RECHECKS` (dev: **1000**; el recheck ya no tiene tope por
diseño nuevo), `DIAS_HABILES_DEVOLUCION` (40), `DIAS_HABILES_TARJETA` (5),
`VIGENCIA_VISA_DIAS`/`VIGENCIA_MASTER_DIAS` (180/120).

### 7 · ✅→ratificar · Decisiones de Pablo que cambian lo que ve el cliente

- Fallo del ASO → aviso de incidencia + **formulario, sin reintento**.
- Bucle tras cualquier desenlace; cierre «ya reportaste todas» **sólo** para 2-3.

### 8 · 🟠 Operativos inmediatos

1. ✅ resuelto (27/08) · El arreglo del servicio de movimientos se integró (PR #87).
2. ✅ resuelto (30/08) · Las cuatro imágenes reconstruidas desde `a4f4159` y
   desplegadas en OKD (PRs #90, #91 y #92 dentro). Manifiestos IaC en
   `test_v1.0.2`; si el próximo build usa tag nuevo, actualizarlos.
3. **Título del Swagger dice «(MOCK)»** — rótulo heredado; actualizar
   `FastAPI(title=…)` para credibilidad de evidencias.
4. 🔴 **NUEVO (30/08, H-3): la traza del granting guarda el password en claro.**
   El `body_enviado` de `operation: "tsec"` en MinIO incluye usuario y contraseña
   del consumidor. Mientras se arregla: NO compartir esos JSON sin redactar.

   > **Tarea:** enmascarar `authenticationData` en el trazador (aso_client ya lo
   > hace con el tsec — extender la misma allowlist al body del granting).

---

## Para Luis

### 9 · ✅ resuelto (28/08) · Fixtures OOB del simulador local

La ceremonia completa corre en local (E2E del 28/08 con el cliente 1010223694).
La causa raíz del `denied` no eran solo los fixtures: eran **tres bugs reales**
arreglados en el PR #90 — el estado TXNR se aplanaba al persistirse (el challenge
se perdía entre turnos), un escritor saltaba la serialización (el guardado del
turno moría en OpenSearch), y el agente sondeaba el reto contra una ruta
inexistente del servicio (404). Los tres habrían pasado igual en DEV/PRD.

### 9b · 🟡 Handlers async con cliente síncrono (parcialmente resuelto 28/08)

El caso grave (`subida_nivel_estado`, que además dormía con `time.sleep`) quedó
resuelto en el PR #91: consulta única y handler síncrono → threadpool. Los DEMÁS
handlers del servicio siguen siendo `async def` con el cliente httpx síncrono:
cada llamada al ASO congela el event loop lo que dure esa llamada.

> **Tarea (decisión, no esfuerzo):** quitar el `async` de los handlers que no
> hacen `await` real (opción A, ya propuesta). `subida_nivel` necesita además
> una variante síncrona de su fetch a back_data.

### 9c · 🟡 NUEVO (30/08, H-4): el script E2E no corrió en el terminal del pod

El script de chat por terminal no arrancó en el bash del pod de trx (causa sin
diagnosticar: ¿`python3` en la imagen? ¿DNS del Service? ¿pegado troceado por el
terminal web?). Hay vía alternativa documentada (Swagger del agente, guía §2.0),
así que no urge — pero si el pod no resuelve `co-pqrs-back-agent`, eso avisaría
de un NetworkPolicy que también afectaría al agente↔servicio.

> **Tarea:** en la próxima sesión con `oc`, capturar el error exacto del script
> (guía §2.1 trae el diagnóstico paso a paso).

### 10 · 🟡 Siete `options` muertas en el YAML

> **Pregunta:** ¿las quitamos o las dejamos comentadas?

### 11 · 🟡 Fila del RPA Tantia (NO=23) — comprobar en DEV tras el despliegue

### 12 · 🟡 `--reload` en la imagen del agente (bandera de desarrollo)

---

## Para Nicolás / Jessica

### 13 · 🟠 La cédula (`personal_id`) del usuario de pruebas `00235597`

Necesaria para el `profileId` (`CC` + cédula rellenada a 15 dígitos — formato
confirmado por el contrato del ASO, PR #92) de `/subida-nivel`. No está en
nuestra tabla ADA (padrones distintos) — la fuente autoritativa es quien creó el
usuario. El 30/08 volvió a ser el tope de la evidencia 5 de la guía.

### 14 · 🟠 Usuario de pruebas CON dispositivo App BBVA enrolado

Sin dispositivo, el push del OOB no tiene a dónde llegar: la subida de nivel solo se
puede probar de punta a punta con un usuario enrolado en dev. En **local** la
ceremonia ya está verificada E2E (28/08); esto queda como el único hueco en DEV.

### 15 · ✅ registrado · El patrón de `observations` es estable (Jessica, 27/08)

Garantía sobre la que se construyó el arreglo de la descripción (5º bloque = comercio).
Si algún día cambia el layout, avisar: hay 4 tests que lo vigilan.

### 16 · 🔴→🟡 REBAJADO (31/08) · El `customer_id` del titular de la tarjeta `…9784`

Con la causa raíz de H-1 identificada (#3), este dato ya NO es la única vía:
el fix del PAN desbloquea el E2E con `00235597` directamente. Sigue siendo útil
como segundo cliente de pruebas (matriz de desenlaces más rica).

### 17 · 🟡 NUEVO (30/08) · Dos verificaciones del contrato ASO (doc de Luis)

1. **Refresco del tsec:** el contrato dice que el 403 del paso 2 y el 401 del
   paso 3 devuelven un `tsec` «actualizado». Nuestro servicio obtiene el tsec una
   vez (granting) y lo reutiliza en toda la ceremonia. ¿Lo exige el ASO?
2. **`expired`:** el contrato dice «reiniciar el flujo de autorización»; el
   pliego de escenarios de Luis decía «terminar correctamente» — y así está
   implementado. Decidir con Fabián cuál vale.

---

## Tickets de equipo (fuera del tramo TXNR)

| # | Qué | Estado |
|---|---|---|
| T-1 | **Enrutador**: si el LLM falla, derivar al formulario PQR en vez de adivinar | por planificar |
| T-2 | **Entorno local**: corta procesos cada 3-4 min | por abrir |
| T-3 | **H-13**: índice de movimiento fuera de rango deriva a PQR en vez de repreguntar | abierto |
