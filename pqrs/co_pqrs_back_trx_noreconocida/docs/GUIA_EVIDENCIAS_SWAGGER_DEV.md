# Guía — evidencias del pipeline TXNR en DEV (Swagger + terminal)

**Fecha:** 31/08/2026 (v9, causa raíz de H-1 identificada) · **Autor:** Pablo (con Claude)
**Swagger del servicio:** `https://co-pqrs-back-trx-noreconocida-pqr-genai-dev.apps.work.ocp.co.igrupobbva/docs`
**Usuarios de prueba:** `00235597` (tokenizado) · tarjeta de Jessica `4593170753249784` (PAN en claro)
**Desplegado en OKD:** las cuatro imágenes construidas el 30/08 desde `a4f4159`
(PRs #90, #91 y #92 incluidos).

## Cómo usar esta guía

La sesión del 30/08 ya demostró qué funciona y qué está bloqueado — esta versión
lo refleja: cada paso dice si es **ejecutable**, si su «fallo» **es la evidencia**
(demuestra un corte real que hay que reportar), o si está **bloqueado** y por qué
pendiente. Nada de perseguir resultados que hoy no pueden salir.

| Parte | Vía | Estado hoy |
|---|---|---|
| 1 | **Swagger del servicio** (UI de OKD), endpoint a endpoint | 1.1–1.4 ejecutables · 1.5–1.7 con cortes documentados |
| 2 | **E2E conversacional** (Swagger del agente o terminal) | hasta el selector de tarjeta; el resto bloqueado por H-1 |
| 3 | **Respaldos** (MinIO + `oc logs`) | ejecutable |
| 4 | **Checklist maestro** | con columna de estado |

El anexo A guarda los datos de la tarjeta de Jessica — hoy son **el único camino
completo** para listado y clasificación. El glosario cierra.

## Hallazgos de la sesión del 30/08 (leer primero)

- **H-1 · `operations` exige PAN — y el PAN SIEMPRE estuvo en el FO (causa
  raíz nuestra, 31/08).** Tres intentos de movimientos con el token de la Visa
  Clásica •1106 (`WcQzt…`) → **400**; con el PAN de Jessica → **200**. El
  análisis de la traza completa del FO cerró el diagnóstico: cada contrato trae
  el token en `contracts[].id` **y el PAN real en `contracts[].formats[].number`**
  (`4504…1106`, `4912…2289`). Nuestro `productos_desde_fo` toma `id` (token) —
  asunción heredada del JSON anonimizado de Nicolás. El fix es leer
  `formats[].number` (una función vecina, `extraer_card_id`, ya lo hace bien).
  **No depende del ASO ni de Nicolás** — se aplica en cuanto haya token de git.
- **H-2 · El token es estable por tarjeta.** El de la Visa Débito •2289
  (`rqNPg…`) se repitió idéntico entre el 26/08 y el 30/08. Bueno para el
  candado anti doble-bloqueo (probablemente no hay que cambiarle la clave).
- **H-3 · Las trazas del granting llevan la contraseña en claro.** El
  `body_enviado` incluye usuario y password del consumidor. **Redactar ese campo
  antes de compartir cualquier traza**, y pedir al equipo que el trazador
  enmascare `authenticationData` como ya hace con el tsec.
- **H-4 · El terminal del pod no corrió el script del E2E** → se añadió la vía
  2.0 (Swagger del agente), que lo sustituye desde la UI.

## 0 · Verificar la versión desplegada (1 minuto, y la captura vale de evidencia)

Las cuatro imágenes se reconstruyeron el 30/08 desde `a4f4159` — llevan todo lo
del 28/08 (persistencia del estado, ruta del sondeo, firma de `/subida-nivel`,
comercio en la descripción) más los PRs #91 y #92. Para dejar constancia de que
el pod corre esa versión (y no una cacheada), un pantallazo:

en el Swagger, abrir `GET /v1/trx/subida-nivel/estado` y mirar la descripción
del parámetro `intentos`:

- «Obsoleto: se consulta una sola vez» → imagen del 30/08 ✅ — seguir con la guía
- «Sondeos dentro de esta llamada» → el pod arrancó con la imagen vieja ⚠️ —
  forzar el redeploy (`oc rollout restart deploy/co-pqrs-back-trx-noreconocida`)
  antes de tomar evidencias del OOB

## Advertencias globales

- **El título del Swagger dice «(MOCK)»** — rótulo heredado del esqueleto inicial,
  NO significa datos simulados (la config del paso 1.1 y las trazas de MinIO
  demuestran ASO real). Aclararlo en el documento final y pedir al equipo
  actualizar el `FastAPI(title=…)`.
- **PAN en claro**: en el documento final, enmascarar como el flujo (`•9784`)
  salvo en el pantallazo técnico. Y por H-3: **jamás adjuntar la traza del
  granting sin redactar el password**.
- ☠️ **`POST /v1/trx/bloqueo` ejecuta un bloqueo DE VERDAD** — jamás sin OK
  explícito de Fabián (detalle en 1.7).

---

# Parte 1 · Swagger del servicio — endpoint a endpoint

## 1.0 · Preparación (2 minutos)

1. Abre el Swagger (URL de arriba). Verás la lista de endpoints bajo el grupo `trx`.
2. Ten a mano un bloc para ir **copiando valores intermedios**:

| Valor | Sale de | Lo usa |
|---|---|---|
| `card_id` (token largo) | 1.2 | 1.3a (evidencia del corte H-1) y 1.5 |
| PAN de Jessica `4593170753249784` | anexo A | 1.3b, 1.4 |
| `tx_id` (id del movimiento) | 1.3b | 1.4 |
| `challenge` + `authentication_state` | 1.5 (si el push sale) | 1.6, 1.7 |

3. **Cómo se ejecuta cualquier endpoint**: click en la fila → `Try it out` →
   rellenar los campos → `Execute`. La evidencia SIEMPRE es el bloque que aparece
   debajo: **Request URL + Code + Response body** en un mismo pantallazo.
   ⚠️ Pegar los tokens **sin comillas** — el 30/08 un intento salió con comillas
   literales y ensució la muestra.

> **¿Y el tsec? — No hace falta: lo gestiona el servicio por dentro.**
>
> ```
> TU POSTMAN (diagnóstico directo)             EL SWAGGER (esta guía)
> ─────────────────────────────────            ──────────────────────
> tú → ASO real directamente                   tú → NUESTRO servicio → ASO real
>      (el tsec lo conseguías a                     │
>       mano: POST al granting y                    ├─ 1. él hace el POST del granting
>       pegarlo en la cabecera)                     ├─ 2. él extrae el tsec (cabecera)
>                                                   ├─ 3. él llama al FO con ese tsec
>                                                   └─ 4. te devuelve el array filtrado
> ```
>
> Dentro de un único `Execute` el servicio hace toda la ceremonia con las
> credenciales del configmap. Aplica a TODOS los endpoints de esta guía: ninguno
> pide tsec. El token **nunca** aparece en el Swagger ni en las trazas; la prueba
> de que la autenticación ocurrió es la traza de MinIO `operation: "tsec"` con
> `outcome: "ok"`.

## 1.1 · `GET /v1/trx/debug/env` — la configuración viva del pod ✅

- **Parámetros:** ninguno. `Try it out` → `Execute`.
- **Qué esperar:** un JSON con la config del pod. Verificar tres cosas:
  `ASO_SOURCE=real`, la URL del ASO (`dev-arqaso…`), y la fuente de productos `fo`.
- **📸 Evidencia 1:** la respuesta completa.

## 1.2 · `GET /v1/trx/productos-activos` — el selector del bot ✅

- **Parámetros:** `customer_id = 00235597`.
- **Qué esperar:** `status: "ok"` y `data.products` con **2 tarjetas**:
  `Visa Clásica •1106` (crédito, token `WcQzt…`) y `Visa Débito •2289` (débito,
  token `rqNPg…`).
- **⚠️ Los `card_id` son tokens** — el ASO enmascara los PAN (correcto por PCI).
  Por H-2, los tokens se repiten entre sesiones: si `rqNPg…` sale igual que el
  26/08, esa captura **también evidencia la estabilidad del token**.
- **📸 Evidencia 2:** Request URL + respuesta con las 2 tarjetas.
- *Equivale a:* la pantalla del bot «Selecciona la cuenta o tarjeta…».

## 1.3a · `GET /v1/trx/movimientos-aso` con el TOKEN — el fallo ES la evidencia ⚠️

- **Parámetros:** `card_id = <token de 1.2, sin comillas>` · `fecha = 25/08/2026`.
- **Qué esperar:** `status: "error"`, `movimientos: []` — por debajo el ASO
  devuelve **400** (verlo en la traza de MinIO o en `oc logs`).
- **📸 Evidencia 3a:** este error, junto a la traza del 400, **documenta H-1**:
  `operations` no acepta el token que el FO nos entrega. Es la prueba que
  necesita Nicolás — no un paso fallido de la guía.

## 1.3b · `GET /v1/trx/movimientos-aso` con el PAN de Jessica — el listado ✅

- **Parámetros:** `card_id = 4593170753249784` · `fecha = 14/04/2026`
  (`2026-04-14` también vale — verificado el 30/08).
- **Qué esperar:** `status: "ok"` y el movimiento `000007731` con
  `descripcion: "EDS COMBUS LLANOS"` (el comercio del 5º bloque de
  `observations`, no «ACEPTADA» — fix del 27/08 desplegado).
  **Copiar el `id`** (será `tx_id`).
- **📸 Evidencia 3b:** Request URL + listado.
- *Equivale a:* «Encontré estas transacciones en la fecha indicada…».

## 1.4 · `GET /v1/trx/detalle` — la clasificación ✅ (solo con el PAN)

- **Parámetros:** `card_id = 4593170753249784` · `fecha = 14/04/2026` ·
  `tx_id = 000007731` · `origin_flag = TDC`.
- **Qué esperar:** `status: "ok"`, el `detalle` y el bloque `clasificacion`
  (el 30/08 salió `resultado: "pqr"` con `response: "660926"` y ECI vacío).
- **📸 Evidencia 4:** Request URL + respuesta con la clasificación visible.
- *Nota:* con `00235597` este paso es **inejecutable** — sin listado (H-1) no hay
  `tx_id`. No insistir: queda cubierto con la tarjeta de Jessica.

## 1.5 · `POST /v1/trx/subida-nivel` — la ceremonia OOB ⚠️ ejecutable hasta su corte

Dos insumos siguen pendientes, y sin ellos el paso termina en un corte — que
también es evidencia, porque la respuesta dice exactamente dónde:

| Falta | Pendiente | Sin él… |
|---|---|---|
| la cédula de `00235597` | #13 (Jessica/Nicolás) | no se puede armar el `profileId`; probar con una cédula equivocada termina en `etapa: "dispositivo"` |
| usuario con App BBVA enrolada | #14 | el push no tiene a dónde llegar |

- **Parámetros:** `card_id = <token de 1.2>` · `personal_id = <cédula>` (el
  servicio arma `profileId = CC + cédula rellenada con ceros a 15 dígitos`, el
  formato del contrato del ASO real — PR #92).
- **Validación para la evidencia:** en `oc logs deploy/co-pqrs-back-trx-noreconocida
  | grep profile_id`, el `profile_id` debe salir con **15 dígitos tras el CC**.
- **Qué esperar:** la respuesta trae `etapa` — el corte exacto:
  - `etapa: "tsec"` → falló el granting (credenciales);
  - `etapa: "dispositivo"` → sin App BBVA enrolada (lo esperable hoy);
  - `etapa: "reto"` → hubo dispositivo pero el reto no devolvió challenge;
  - `status: "ok"` + `challenge` → el push salió: anotar `challenge` y
    `authentication_state`.
- **📸 Evidencia 5:** la respuesta con su `etapa` — cualquiera evidencia, porque
  con el `profileId` ya bien formado (sección 0) el corte que salga es genuino.

## 1.6 · `GET /v1/trx/subida-nivel/estado` ⛔ hoy bloqueado (necesita el push de 1.5)

- **Parámetros:** `challenge = <el anotado en 1.5>`. La consulta es ÚNICA (sin
  sondeo ni espera); `intentos`/`espera` existen por compatibilidad y se ignoran.
- **Qué esperar:** `pending` (nadie aceptó aún) o `accepted`.
- **📸 Evidencia 6** — cuando #13 y #14 estén resueltos.

## 1.7 · `POST /v1/trx/bloqueo` — ☠️ NO EJECUTAR sin OK explícito de Fabián ⛔

Ejecuta el bloqueo **de verdad**, ya con la autorización del cliente:

- `tipo = temporal` → PATCH de apagado (`ON_OFF, isActive=false`) — reversible
  desde la app, no llama al tercer POST del reto.
- `tipo = permanente` → tercer POST del reto (200 = ejecutado, 400 = no
  autorizado); exige `challenge` + `authentication_state` — **sin autorización
  aceptada no puede ejecutar**.

Hoy doblemente bloqueado: por autorización de Fabián y porque 1.5 no llega al
push. Si algún día se aprueba con el usuario de pruebas: siempre `temporal`.

---

# Parte 2 · El E2E conversacional — hasta donde H-1 permite

**Estado real:** el flujo conversacional usa el mismo camino token→movimientos
que 1.3a, así que con `00235597` la conversación avanza hasta el selector de
tarjeta y **muere en la fecha** («no encontramos compras…»). Eso da estas
evidencias:

- **E-T1** (selector con las tarjetas del FO real) → ✅ alcanzable hoy.
- **E-T2…E-T5** → ⛔ bloqueadas por H-1. Se desbloquean con el fix del PAN
  (`formats[].number` en `productos_desde_fo`) — pendiente solo del token de git
  y del redeploy del servicio. E-T4/E-T5 siguen necesitando además el usuario
  enrolado (#14).

Vale la pena capturar el corte HOY, antes del fix: la conversación que muere en
la fecha, junto a la traza del 400, es el «antes» — la misma conversación tras
el redeploy será el «después», la pareja de evidencias más contundente del
informe.

## 2.0 · Sin terminal: el E2E desde el Swagger del AGENTE (UI) — vía recomendada

El agente expone su propio Swagger — la conversación completa se recorre a golpe
de `Execute`, con captura en cada turno (H-4: el terminal del pod no corrió el
script el 30/08).

**URL:** `https://co-pqrs-back-agent-pqr-genai-dev.apps.work.ocp.co.igrupobbva/docs`
(si difiere, `oc get routes -n pqr-genai-dev | grep agent` la dice; si el agente
no tiene Route, `oc port-forward deploy/co-pqrs-back-agent 8000:8000` y abrir
`http://localhost:8000/docs`).

El turno a turno:

1. **`POST /start`** con body `{"user_id": "00235597"}` → responde el saludo y el
   `conversation_id` (p. ej. `00235597_20260830`). Anotarlo: va en TODOS los
   turnos siguientes.
   - Si devuelve `409` (sesión de hoy aún activa): **`POST /end`** con
     `{"conversation_id": "00235597_20260830"}` y repetir el `/start`.
2. **`POST /chat`** con `{"conversation_id": "<el anotado>", "content": "<respuesta>"}`.
   En `content` va **la key de la opción elegida** (el JSON de la respuesta
   anterior trae `message.content.options` con pares `key`/`label` — copiar la
   `key`; el texto libre, como la fecha `25/08/2026`, va tal cual).
3. Si `/chat` responde `204` (sin cuerpo) o «estoy revisando tu información…»:
   el turno sigue en segundo plano. **`POST /polling`** con el mismo body hasta
   recibir `303`, y entonces **`GET /polling/{conversation_id}`** devuelve el
   mensaje final. (Es el contrato de turnos largos — el 204/303 en la captura es
   evidencia de que funciona, no un error.)
4. Repetir el paso 2 siguiendo el guion de 2.3. Al terminar: **`POST /end`**.

📸 La captura de cada `Execute` (request + response con las `options`) equivale a
la transcripción del terminal.

## 2.1 · Terminal del pod (alternativa)

```bash
oc rsh deploy/co-pqrs-back-trx-noreconocida
```

Desde ahí el agente se alcanza por su Service interno: `http://co-pqrs-back-agent:8000`
(si el nombre difiere, `oc get svc | grep agent` lo dice).

**Si el script no arranca** (caso del 30/08): probar `python` en vez de
`python3`; comprobar el DNS del Service (`getent hosts co-pqrs-back-agent`); y
si el terminal web de OKD trocea el pegado largo, usar `oc rsh` desde tu
máquina. Con cualquier traba, la vía 2.0 da lo mismo.

## 2.2 · El script (pegar tal cual en el terminal del pod)

Es un chat interactivo: imprime lo que dice el bot con sus opciones numeradas; tú
escribes el número (o texto libre, p. ej. la fecha). Gestiona solo el contrato de
turnos largos (204 → polling → 303) y guarda la transcripción en
`/tmp/evidencia_chat.txt`.

```bash
python3 - <<'CHAT'
import json, re, sys, time, urllib.request, urllib.error

BASE = "http://co-pqrs-back-agent:8000"
USER = input("customer_id (ej. 00235597): ").strip() or "00235597"

def pedir(path, payload=None, metodo="POST"):
    datos = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=datos,
        headers={"Content-Type": "application/json"}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try: return e.code, json.loads(raw) if raw.strip() else None
        except Exception: return e.code, {"raw": raw[:200]}

def leer(body):
    cont = ((body or {}).get("message") or {}).get("content") or {}
    if isinstance(cont, str): return cont, []
    ops = [(str(o.get("key","")), str(o.get("label","")))
           for o in (cont.get("options") or []) if isinstance(o, dict)]
    return cont.get("label") or "", ops

def sondear(cid):
    for _ in range(60):
        code, _ = pedir("/polling", {"conversation_id": cid})
        if code == 303:
            return pedir(f"/polling/{cid}", metodo="GET")[1]
        time.sleep(1.0)
    return None

from datetime import datetime, timedelta, timezone
hoy = datetime.now(timezone.utc)
for d in (-1, 0, 1):
    pedir("/end", {"conversation_id": USER + "_" + (hoy+timedelta(days=d)).strftime("%Y%m%d")})
code, body = pedir("/start", {"user_id": USER})
if code not in (200, 201):
    sys.exit(f"/start devolvio {code}: {body}")
cid = body.get("conversation_id", "")
log = open("/tmp/evidencia_chat.txt", "a")
log.write(f"\n===== {datetime.now(timezone.utc).isoformat()} cid={cid} =====\n")
texto, ops = leer(body)
while True:
    print("\nBOT:", " ".join((texto or "").split()))
    for i, (_k, lab) in enumerate(ops, 1): print(f"  {i}. {lab}")
    log.write(f"BOT: {' '.join((texto or '').split())}\nOPC: {[l for _,l in ops]}\n")
    entrada = input("> ").strip()
    if entrada.lower() in ("salir", "exit"): break
    if entrada.isdigit() and 0 < int(entrada) <= len(ops):
        contenido = ops[int(entrada)-1][0] or ops[int(entrada)-1][1]
        log.write(f"YO: [{entrada}] {ops[int(entrada)-1][1]}\n")
    else:
        contenido = entrada
        log.write(f"YO: {entrada}\n")
    code, body = pedir("/chat", {"conversation_id": cid, "content": contenido})
    if code == 204 or body is None: body = sondear(cid)
    texto, ops = leer(body)
    if "estoy revisando" in (texto or "").lower() or (body or {}).get("status") == "Running":
        body = sondear(cid); texto, ops = leer(body)
log.close()
print("\nTranscripcion completa en /tmp/evidencia_chat.txt")
CHAT
```

## 2.3 · El guion completo (para cuando H-1 se desbloquee)

| Turno | Qué responder | 📸 Evidencia si… |
|---|---|---|
| Entrada | «No reconozco esta compra» | — |
| Suceso / cuántas | según el caso · `1` | — |
| Selector de tarjeta | la tarjeta del cliente | **E-T1**: las tarjetas salen del FO real (tokens) — ✅ alcanzable HOY |
| Rango / fecha | rango del importe · la fecha con movimientos | **E-T2**: el listado muestra el COMERCIO, no «ACEPTADA» — ⛔ H-1 |
| Confirmación | el movimiento a reportar | **E-T3**: Descripción·Valor·Fecha·`•últimos4` correctos — ⛔ H-1 |
| Reporte → investigación → bloqueo | «Sí, …» en cada una | — |
| Push enviado | *«Enviamos una notificación a tu App BBVA…»* | **E-T4** — ⛔ H-1 y #14 |
| «Continuar» tras aceptar en la app | la confirmación del bloqueo | **E-T5** — ⛔ H-1 y #14 |

---

# Parte 3 · Respaldos que atan las evidencias

## 3.1 · MinIO — una traza por cada evidencia del Swagger

Las trazas de llamadas hechas por Swagger (sin conversación) caen en la ruta
`conversation=no-conversation/`. Para cada paso:

| Paso | `operation` en la traza | Qué mirar |
|---|---|---|
| 1.2 | `tsec` y `financial_overview` | `outcome: ok`; en `request_summary`, la petición exacta |
| 1.3a | `operations` | `outcome: error`, `status_code: 400` — **la prueba de H-1** |
| 1.3b / 1.4 | `operations` | `outcome: ok` (cacheada 900 s: puede no repetirse en 1.4) |
| 1.5 | la del push / subida de nivel | `outcome` y `status_code` del ASO |

**📸 Evidencia 7:** la traza de `financial_overview` con `outcome: ok` — la
prueba de que el dato salió del ASO real y no de un mock.

⚠️ **H-3:** la traza de `operation: "tsec"` incluye el password del granting en
`body_enviado`. Redactarlo antes de compartir. No adjuntar ese JSON en bruto.

## 3.2 · `oc logs` — el pod en vivo (segunda terminal)

```bash
# SERVICIO — en vivo mientras ejecutas cada paso del Swagger
oc logs -f deploy/co-pqrs-back-trx-noreconocida | grep -iE "tsec|financial_overview|operations|productos|movimientos parseados|SUBIDA"

# la peticion exacta que salio hacia el ASO en el ultimo paso (fallback si MinIO tarda)
oc logs deploy/co-pqrs-back-trx-noreconocida --since=10m | grep -iE "ASO|request_debug" | tail -20

# AGENTE — la secuencia del OOB (PRs #90/#91): guardado y recuperacion del reto
oc logs -f deploy/co-pqrs-back-agent | grep -E "SUBIDA NIVEL 08|AUTH CHECK 01|ESTADO RETO"
```

Cuando el OOB sea alcanzable (tras #13/#14), la pareja de líneas que demuestra la
persistencia del reto, en turnos DISTINTOS del mismo `conversation_id`:

```
TXNR SUBIDA NIVEL 08 reto guardado challenge=True ...            <- turno del push
TXNR AUTH CHECK 01 challenge='...' auth_keys=[...]               <- turno siguiente: el reto SOBREVIVIO
TXNR ASO ESTADO RETO REQUEST url=.../v1/trx/subida-nivel/estado  <- la ruta buena
```

**📸 E-T6** — ese pantallazo, cuando llegue.

---

# Parte 4 · Checklist maestro de evidencias

| # | Vía | Evidencia | Estado 30/08 | ¿Qué demuestra? |
|---|---|---|---|---|
| 0 | Swagger | descripción de `intentos` en `/estado` | ✅ tomable | versión desplegada del 30/08 |
| 1 | Swagger | `debug/env` | ✅ tomada | configuración real (ASO real, fuente fo) |
| 2 | Swagger | productos-activos con 2 tarjetas | ✅ tomada | autenticación + FO + filtro; y H-2 si el token se repite |
| 3a | Swagger | movimientos con token → error | ✅ tomada | **H-1**: `operations` no acepta el token del FO |
| 3b | Swagger | movimientos con PAN → listado con comercio | ✅ tomada | listado correcto + fix descripción |
| 4 | Swagger | detalle + clasificación (PAN) | ✅ tomada | la lógica de desenlaces contra data real |
| 5 | Swagger | subida-nivel con su `etapa` | ⚠️ falta cédula (#13) | el corte exacto del OOB real |
| 6 | Swagger | estado del challenge | ⛔ #13 + #14 | el push llegó / pendiente |
| 7 | MinIO | traza de `financial_overview` ok | ✅ tomable | trazabilidad extremo a extremo |
| E-T1 | E2E | selector con tarjetas del FO | ✅ tomable | el bot arma productos del ASO real |
| E-T2/3 | E2E | listado y confirmación vistos por el cliente | ⛔ H-1 | la vista cliente (y H-1 «visto por el cliente» si se captura el corte) |
| E-T4/5 | E2E | push y confirmación del bloqueo | ⛔ H-1 + #14 | la ceremonia OOB completa |
| E-T6 | `oc logs` | pareja `reto guardado`/`AUTH CHECK 01` | ⛔ H-1 + #14 | el reto sobrevive entre turnos |

**Qué desbloquea qué:** el fix del PAN (`formats[].number`, listo para aplicar
con el token de git de mañana) desbloquea 3a→listado real, E-T2/E-T3 y revive la
franquicia por BIN. La cédula de `00235597` (#13) desbloquea la evidencia 5; el
usuario enrolado (#14), E-T4/E-T5 y E-T6.

---

# Anexo A · Datos de la tarjeta de Jessica — hoy, el único camino completo

**Fuente:** Jessica Cárdenas Rodríguez (25/08) · `cardId: 4593170753249784`
(VISA, BIN 4) · `operationDate: 2026-04-14`.

## A.1 · Valores exactos que funcionaron el 30/08

| Campo | Valor |
|---|---|
| `card_id` | `4593170753249784` (sin comillas) |
| `fecha` | `14/04/2026` — `2026-04-14` y `20260414` también valen |
| `tx_id` (para `/detalle`) | `000007731` |
| `origin_flag` | `TDC` |

Resultado observado: 1 movimiento, `EDS COMBUS LLANOS`, $96.930, clasificación
`resultado: "pqr"` (`response: "660926"`, ECI vacío).

## A.2 · Matices para el documento final

1. **Falta el `customer_id` del titular** — pedirlo a Jessica. Con él, el paso
   1.2 mostraría esta tarjeta **tokenizada** (token y PAN conviviendo) y, más
   importante, **desbloquearía el E2E conversacional completo** (Parte 2).
2. **Vigencia**: 14/04 → fuera ya de los 120 de Master y cerca de los 180 de
   VISA — anotar la fecha de la prueba para que la evidencia no confunda.
3. ☠️ **Jamás usar este PAN en `/bloqueo`** sin OK explícito de Fabián:
   bloquearía la tarjeta de pruebas de verdad.

---

# Glosario en una línea

- **tsec / granting ticket**: el token de sesión que el servicio pide antes de llamar al ASO; viaja en la cabecera `tsec`.
- **FO (financial-overview)**: el servicio del ASO que devuelve el portafolio del cliente; nuestra única fuente de productos.
- **token de tarjeta**: identificador del contrato en `contracts[].id`, estable por tarjeta (H-2); `operations` no lo acepta — el PAN real viaja en `contracts[].formats[].number` (H-1).
- **OOB / subida de nivel**: autorización por segundo canal (push a la App BBVA) antes del bloqueo; en el ASO real es una ceremonia de 4 llamadas.
- **204**: respuesta correcta sin contenido; en el FO significa «no hay datos» (p. ej. sesión sin contexto de cliente).
