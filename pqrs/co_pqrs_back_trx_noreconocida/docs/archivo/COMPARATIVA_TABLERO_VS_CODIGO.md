# Comparativa — el tablero original vs la implementación actual

**Fecha:** 21/08/2026 · **Rama:** `fix/merge-trx-costuras`
**Fuentes:** las 17 capturas del tablero V.2 (13/08, `.claude/Roadmap_Pieces/`) contra el
grafo **real** extraído del YAML (`trx_no_reconocida.yml`, 48 pasos) y de los gates de
`chat_service.py` — no de memoria.

**Cómo leer los diagramas** (misma leyenda en ambos):

| Estilo | Significado |
|---|---|
| nodo azul (por defecto) | igual en tablero y código |
| nodo **verde** | existe **sólo en el código** — robustez añadida (fail-closed, candados, cierre del bucle) |
| nodo **amarillo** | existe en ambos pero **se comporta distinto** — divergencia documentada |
| nodo **rojo punteado** | el tablero lo pide y **no está** en el código |
| rombo | decisión automática (gate que el cliente no ve) |

Se renderizan en cualquier visor de Mermaid (VS Code, mermaid.live, GitLab/GitHub).

---

## 1 · El TABLERO, como lo dibujó el PO

Lo verde-sombreado del tablero (backoffice) queda fuera: no es alcance del bot.

```mermaid
flowchart TD
    classDef faltante fill:#FFC7CE,stroke:#C00000,stroke-dasharray: 5 5
    classDef divergente fill:#FFEB9C,stroke:#BF8F00

    SUC["Sucesos: cambiazo / hurto o perdida /<br/>tus datos bancarios / hiciste una compra"]
    FORM123["Caso requiere revision a fondo<br/>Formulario PQR"]
    RREC{"Se identifica interaccion<br/>en los ultimos 6 meses?"}
    PQRREC["Gestion reciente encontrada<br/>Formulario PQR"]
    CANT["Cuantas transacciones quieres reportar?<br/>1 / 2 / 3 / Mas de 3"]
    MAS3["Mas de 3: informacion completa<br/>en un solo tramite - Formulario PQR"]
    UNAVEZ["Revisaremos una transaccion a la vez"]
    LIMITES["Hasta 3 transacciones de entre<br/>35.000 y 500.000. Datos actualizados"]
    RPROD{"Se validan los productos<br/>del cliente"}
    SINPROD["Actualmente no tienes<br/>productos activos - fin"]
    SEL["Selecciona la cuenta o tarjeta en la que<br/>aparece la compra que no reconoces<br/>botones: Producto •xxxx"]
    RANGO["Rango del valor:<br/>menor / entre / mayor"]
    RANGOPQR["Fuera de rango:<br/>Formulario PQR"]
    FECHA["Escribe la fecha DD/MM/AAAA"]:::divergente
    CAL["BOT IA: muestra CALENDARIO<br/>para elegir un solo dia"]:::faltante
    RVIG{"Supera el plazo<br/>de la franquicia?"}
    VENCIDA["Plazo superado: contacta<br/>al comercio - fin"]
    RMOV{"Existen compras registradas<br/>en la fecha?"}
    SINMOV["No encontramos compras:<br/>otra fecha / otro producto / terminar"]
    LISTA["Listado: TODOS los movimientos,<br/>inclusive los abonos"]:::divergente
    NOENC["No encuentro la transaccion:<br/>puedes elegir otra fecha"]
    CONF["Confirma los datos:<br/>descripcion, valor, fecha,<br/>producto terminado en ••••xxxx"]:::divergente
    RPEND{"Movimiento pendiente en TDC?<br/>No, o ya supero los 7 dias"}
    PEND["Compra en estado pendiente:<br/>vuelve mas adelante - fin"]
    INV["Iniciar investigacion?"]
    RBLQ{"Bloqueo definitivo<br/>o temporal?"}
    TEMP["Apagada temporalmente:<br/>podras encenderla - fin"]
    DEF["Cancelada por seguridad. Nueva tarjeta<br/>a la direccion tipo de calle xx-xx<br/>en x dias habiles"]
    REV["Revisaremos la informacion<br/>de la transaccion"]
    RCHIP{"Compra con chip<br/>en tienda fisica?"}
    PRES["Compra presencial validada como<br/>autorizada - no procede devolucion"]
    RREV{"Tx reversada<br/>o anulada?"}
    REEM["Ya fue devuelta. Detalle:<br/>transaccion + MONTO DEVUELTO<br/>+ ver paso a paso"]
    RECI{"Es responsabilidad del comercio?<br/>ECI contracargable: 0,1,2,3,7"}
    DEVO["Devolucion automatica:<br/>abono en x dias habiles"]
    PQRECI["No podemos resolver en este canal:<br/>Formulario PQR"]
    ROTRA{"Desea reportar<br/>otra tx?"}
    FIN["Feedback y fin"]

    SUC -->|"opciones 1-3"| FORM123 --> FIN
    SUC -->|"compra"| RREC
    RREC -->|"si"| PQRREC --> FIN
    RREC -->|"no"| CANT
    CANT -->|"mas de 3"| MAS3 --> FIN
    CANT -->|"1-3"| UNAVEZ --> LIMITES --> RPROD
    RPROD -->|"sin productos"| SINPROD
    RPROD -->|"con productos"| SEL --> RANGO
    RANGO -->|"menor o mayor"| RANGOPQR --> FIN
    RANGO -->|"entre"| FECHA
    CAL -.-> FECHA
    FECHA --> RVIG
    RVIG -->|"si"| VENCIDA
    RVIG -->|"no"| RMOV
    RMOV -->|"no"| SINMOV
    SINMOV -->|"otra fecha"| FECHA
    SINMOV -->|"otro producto"| SEL
    RMOV -->|"si"| LISTA
    LISTA -->|"no encuentro"| NOENC --> FECHA
    LISTA --> CONF
    CONF -->|"ya reconozco"| FIN
    CONF -->|"continuar"| RPEND
    RPEND -->|"pendiente"| PEND
    RPEND -->|"no / +7 dias"| INV
    INV -->|"no"| FIN
    INV -->|"si"| RBLQ
    RBLQ -->|"temporal"| TEMP
    RBLQ -->|"definitivo"| DEF --> REV --> RCHIP
    RCHIP -->|"si"| PRES --> FIN
    RCHIP -->|"no"| RREV
    RREV -->|"si"| REEM --> ROTRA
    RREV -->|"no"| RECI
    RECI -->|"si"| DEVO --> ROTRA
    RECI -->|"no"| PQRECI --> ROTRA
    ROTRA -->|"si"| UNAVEZ
    ROTRA -->|"no"| FIN
```

---

## 2 · El CÓDIGO, hoy (48 pasos, gates reales)

Los rombos son los **gates automáticos**: pasos con acción que el cliente nunca ve porque
`chat_service` reescribe el destino en el mismo turno.

```mermaid
flowchart TD
    classDef nuevo fill:#C6EFCE,stroke:#2E7D32
    classDef divergente fill:#FFEB9C,stroke:#BF8F00

    S0["2.4.0 sucesos"]
    S1["2.4.1 cambiazo -> formulario"]:::divergente
    S2["2.4.2 hurto -> formulario"]:::divergente
    S3["2.4.3 datos -> formulario"]:::divergente
    GREC{"2.4.0.1 gate recurrencia<br/>Salesforce + candado bot"}
    PQRR["2.4.0.pqr_recurrencia"]
    CANT["2.4.0.1.1 cantidad"]
    MAS3["2.4.0.1.1.pqr mas de 3"]
    UNA["2.4.0.1.2 una a la vez"]
    LIM["2.4.0.1.3 limites<br/>(reentrada del bucle)"]
    G4{"2.4.0.1.4 gate productos<br/>Postgres + resolucion PAN en FO"}
    EX4["2.4.0.1.4.exit sin productos"]
    ER4["2.4.0.1.4.error servicio caido<br/>fail-closed"]:::nuevo
    SEL["2.4.0.1.5 selector<br/>copy tablero, botones •xxxx"]
    RAN["2.4.0.1.6 rango"]
    PQR6["2.4.0.1.6.pqr fuera de rango"]
    FEC["2.4.0.1.7 fecha texto libre<br/>sin calendario"]:::divergente
    EX7["2.4.0.1.7.exit vigencia vencida<br/>VISA 180 / MASTER 120"]
    G8{"2.4.0.1.8 gate vigencia+ASO<br/>fallo NO se memoriza"}
    RET8["2.4.0.1.8.return sin compras<br/>o fuera de rango H-14"]:::divergente
    ER8["2.4.0.1.8.error ASO caido<br/>fail-closed"]:::nuevo
    LIS["2.4.0.1.9 listado tope 5 + aviso<br/>(tablero pide todos+abonos)"]:::divergente
    EX9["2.4.0.1.9.exit no encuentro"]
    G10{"2.4.0.1.10 gate detalle"}
    PQR10["2.4.0.1.10.pqr detalle<br/>no disponible"]:::nuevo
    CON["2.4.0.1.11 confirmacion<br/>tipo producto *xxxx"]
    G12{"2.4.0.1.12 gate pendiente TDC<br/>observations contiene pendiente"}
    EX12["2.4.0.1.12.exit compra pendiente"]
    INV["2.4.0.1.13 iniciar investigacion"]
    B15{"2.4.0.1.15 tipo de bloqueo<br/>+ salto si ya bloqueada"}:::nuevo
    T16["2.4.0.1.16 confirmar apagado"]
    G161{"2.4.0.1.16.1 gate bloqueo temporal<br/>candado durable anti-doble"}
    PQR161["2.4.0.1.16.1.pqr bloqueo fallo"]:::nuevo
    T162["2.4.0.1.16.2 apagada •xxxx"]
    D17["2.4.0.1.17 confirmar definitivo"]
    G171{"2.4.0.1.17.1 gate bloqueo permanente<br/>candado durable anti-doble"}
    PQR171["2.4.0.1.17.1.pqr bloqueo fallo"]:::nuevo
    D172["2.4.0.1.17.2 cancelada •xxxx<br/>+ direccion real de ADA"]
    REV["2.4.0.1.18 revisaremos"]
    G19{"2.4.0.1.19 gate clasificacion<br/>eci=9 / reversa / ECI set / else"}
    R191["2.4.0.1.19.1 presencial"]
    R192["2.4.0.1.19.2 reembolso<br/>transaccion + monto devuelto"]
    GUIA["2.4.0.1.19.2.guia paso a paso"]
    RPQR["2.4.0.1.19.pqr no contracargable"]
    DEV["2.4.0.1.20 devolucion automatica"]
    G200{"2.4.0.1.20.0 gate cierre bucle<br/>quedan? / declaro mas de 1?"}:::nuevo
    L201["2.4.0.1.20.1 reportar la siguiente?"]
    L202["2.4.0.1.20.2 ya reportaste todas"]:::nuevo
    FIN["satisfaction_check y fin"]

    S0 --> S1 --> FIN
    S0 --> S2 --> FIN
    S0 --> S3 --> FIN
    S0 -->|"hiciste una compra"| GREC
    GREC -->|"recurrencia SF o bot"| PQRR --> FIN
    GREC -->|"sin recurrencia"| CANT
    CANT -->|"mas de 3"| MAS3 --> FIN
    CANT -->|"1-3"| UNA --> LIM
    LIM -->|"si"| G4
    LIM -->|"finalizar"| FIN
    G4 -->|"error o FO caido"| ER4 --> FIN
    G4 -->|"vacio real"| EX4 --> FIN
    G4 -->|"productos"| SEL
    SEL --> RAN
    RAN -->|"menor/mayor"| PQR6 --> FIN
    RAN -->|"entre"| FEC --> G8
    G8 -->|"fecha ilegible"| FEC
    G8 -->|"vigencia vencida"| EX7 --> FIN
    G8 -->|"ASO caido"| ER8 --> FIN
    G8 -->|"sin compras"| RET8
    RET8 -->|"otra fecha"| FEC
    RET8 -->|"otro producto"| SEL
    RET8 -->|"terminar"| FIN
    G8 -->|"movimientos"| LIS
    LIS -->|"no encuentro."| EX9
    EX9 -->|"nueva fecha"| FEC
    EX9 -->|"finalizar"| FIN
    LIS -->|"mov 1-5"| G10
    G10 -->|"sin detalle"| PQR10 --> FIN
    G10 -->|"detalle"| CON
    CON -->|"ya reconozco"| FIN
    CON -->|"continuar"| G12
    G12 -->|"pendiente"| EX12 --> FIN
    G12 -->|"no"| INV
    INV -->|"no"| FIN
    INV -->|"si"| B15
    B15 -->|"ya bloqueada antes"| REV
    B15 -->|"temporal"| T16
    B15 -->|"definitivo"| D17
    T16 -->|"no"| FIN
    T16 -->|"si"| G161
    G161 -->|"fallo"| PQR161 --> FIN
    G161 -->|"ok"| T162 --> FIN
    D17 -->|"no"| FIN
    D17 -->|"si"| G171
    G171 -->|"fallo"| PQR171 --> FIN
    G171 -->|"ok"| D172 --> REV --> G19
    G19 -->|"eci 9"| R191 --> G200
    G19 -->|"reversa aceptada"| R192
    R192 -->|"paso a paso"| GUIA --> G200
    R192 -->|"finalizar"| G200
    G19 -->|"no contracargable"| RPQR --> G200
    G19 -->|"contracargable 0,1,2,3,7"| DEV --> G200
    G200 -->|"quedan tx"| L201
    G200 -->|"declaro 2-3 y no quedan"| L202 --> FIN
    G200 -->|"declaro 1"| FIN
    L201 -->|"si"| LIM
    L201 -->|"no"| FIN
```

---

## 3 · Las diferencias, en una tabla

### 3.1 · Lo que el código AÑADE sobre el tablero (verde)

| Nodo | Por qué existe |
|---|---|
| `.4.error` / `.8.error` / `.10.pqr` | **fail-closed**: antes que afirmar «no tienes productos» o «no hay compras» con el servicio caído, un aviso honesto + formulario (petición de Fabián) |
| `.16.1.pqr` / `.17.1.pqr` | el bloqueo puede **fallar**: el tablero no lo contempla |
| candados de los gates de bloqueo | evitan la **doble reexpedición** de tarjeta ante un reintento |
| salto de `.15` → `.18` | no volver a pedir el bloqueo de una tarjeta **ya bloqueada** en esta conversación |
| `.20.0` + `.20.2` | los **cuatro** desenlaces ofrecen reportar la siguiente, y el cierre es explícito («ya reportaste todas») — sólo para quien declaró 2-3 |
| gate `.8` sin memoria de fallos | un error técnico no se convierte en «no hay compras» mañana |

### 3.2 · Lo que difiere en comportamiento (amarillo)

| Ítem | Tablero | Código | Estado |
|---|---|---|---|
| Listado `.9` | *todos* los movimientos, **incluidos abonos** | tope 5 + aviso de resto; filtro `EXPENSE` excluye abonos | decisión de negocio pendiente (H-14-3) |
| Fecha `.7` | **calendario** de un día | texto libre `DD/MM/AAAA` con reprompt | widget del front, no del bot |
| Sucesos 1-3 | **un** mensaje común | tres pasos (`2.4.1/2/3`), dos con texto idéntico | cosmético |
| Máscara de confirmación | `••••xxxx` | `*xxxx` | decisión **explícita** de Fabián (20/08) que prevalece sobre el tablero |

### 3.3 · Lo que el tablero pide y NO está (rojo punteado)

| Ítem | Nota |
|---|---|
| Calendario en `.7` | requiere trabajo de **front**; el bot no puede pintarlo |

### 3.4 · Lo que ya NO difiere (cerrado esta semana)

Copys del selector, sucesos 3-4, colas de `2.4.2`/`2.4.3`, ítems del listado, «No
encuentro…» con punto, viñeta de descripción cruda, tipo de producto interpolado, tildes
completas, máscaras (`•` selector/bloqueos, `*` confirmación), «Monto devuelto» del
reembolso, regla de pendiente por `observations`, regla ECI con el `0`, y la dirección real
en la reexpedición.

---

## 4 · Cómo mantener esto vivo

El diagrama del código sale del YAML y de los gates: si el flujo cambia, **este fichero
queda viejo**. La fuente de verdad operativa sigue siendo `ESPECIFICACION_FLUJO.md` + el
YAML; esta comparativa es una foto para la conversación con Fabián y PO. Si se quiere
regenerar, el volcado del grafo está a un comando:

```bash
cd co_pqrs_back_agent && uv run --with pyyaml python - <<'EOF'
import yaml
S=yaml.safe_load(open("src/domain/workflow/trx_no_reconocida/trx_no_reconocida.yml"))["steps"]
for k,s in S.items():
    for o in (s.get("options") or []):
        print(f"{k} --[{o.get('label')}]--> {o.get('next_step')}")
EOF
```
