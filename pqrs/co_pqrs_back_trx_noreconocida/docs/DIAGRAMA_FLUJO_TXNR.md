# Flujo TXNR — tramo de análisis (entrada → confirmación de la compra)

**Transacción no reconocida · BBVA Colombia** · Actualizado el 18/08/2026

Estos diagramas describen **lo implementado y verificado**, no lo previsto: se han
generado contra el árbol de pasos y las llamadas reales del agente y del servicio.

**Alcance:** desde la entrada al flujo hasta la confirmación de la compra
(`2.4.0.1.11`). Desde la validación de movimiento pendiente (`2.4.0.1.12`) en adelante
corresponde al otro tramo del equipo y se muestra sólo como frontera.

---

## 1 · Recorrido conversacional

```mermaid
flowchart TD
    A([Cliente: no reconozco esta compra]) --> B{Suceso ocurrido}

    B -->|Cambiazo| PQR1[Formulario PQR]
    B -->|Hurto o pérdida| PQR1
    B -->|Obtuvieron mis datos| PQR1
    B -->|Compra presencial o por internet| G1

    G1[/Validación de recurrencia<br/>Salesforce · últimos 6 meses/]
    G1 -->|Ya tiene gestión| PQR2[Formulario PQR]
    G1 -->|Sin gestión previa| C{Cuántas transacciones}

    C -->|Más de 3| PQR3[Formulario PQR]
    C -->|1, 2 ó 3| D[Aviso: una transacción a la vez]
    D --> E{Confirmación de datos<br/>de contacto y dirección}
    E -->|Finalizar| FIN
    E -->|Sí, continuar| G2

    G2[/Consulta de productos<br/>ADA · PostgreSQL/]
    G2 -->|Sin productos vigentes| X1[Aviso: sin productos<br/>consulta la app BBVA] --> FIN
    G2 -->|Con productos| F[Selección de producto]

    F --> H{Rango de valor}
    H -->|Menor a $35.000| PQR4[Formulario PQR]
    H -->|Mayor a $500.000| PQR4
    H -->|Entre $35.000 y $500.000| I[/Fecha de la compra<br/>DD/MM/AAAA/]

    I --> G3[/Vigencia de contracargo<br/>y consulta de movimientos/]
    G3 -->|Fecha fuera de plazo| X2[Aviso: plazo de franquicia<br/>superado] --> FIN
    G3 -->|Sin movimientos ese día| R{Reintentar}
    R -->|Elegir otra fecha| I
    R -->|Seleccionar otro producto| F
    R -->|Terminar| FIN
    G3 -->|Con movimientos| J[Listado de movimientos]

    J -->|No encuentro la transacción| S{Nueva fecha}
    S -->|Seleccionar nueva fecha| I
    S -->|Finalizar| FIN
    J -->|Selecciona un movimiento| G4

    G4[/Detalle de la operación/]
    G4 -->|Sin detalle disponible| PQR5[Formulario PQR]
    G4 -->|Detalle obtenido| K[Confirmación de la compra<br/>descripción · valor · fecha · producto]

    K -->|Ya reconozco la transacción| FIN
    K -->|Sí, continuar con el reporte| FRONTERA

    FRONTERA[[Validación de movimiento pendiente<br/>y proceso de investigación]]
    FIN([Cierre con encuesta de satisfacción])

    PQR1 --> FIN
    PQR2 --> FIN
    PQR3 --> FIN
    PQR4 --> FIN
    PQR5 --> FIN

    classDef gate fill:#e8eefc,stroke:#1f3864,stroke-width:2px
    classDef salida fill:#fdeaea,stroke:#b03a3a
    classDef frontera fill:#e9f6ec,stroke:#2e7d46,stroke-width:2px
    class G1,G2,G3,G4 gate
    class PQR1,PQR2,PQR3,PQR4,PQR5,X1,X2 salida
    class FRONTERA frontera
```

Los bloques con borde azul son **puntos de consulta a sistemas**: se ejecutan sin turno
de conversación —el cliente no ve un "estoy validando"— y encaminan según el resultado.

---

## 2 · Servicios consultados y momento de la llamada

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente
    participant B as Agente (Blue)
    participant S as Servicio TXNR
    participant P as ADA (PostgreSQL)
    participant A as ASO

    C->>B: No reconozco esta compra
    B-->>C: Selección del suceso

    C->>B: Compra presencial o por internet
    B->>S: Validar recurrencia
    S->>A: Salesforce · issues por documento
    A-->>S: Gestiones de la tipología
    S-->>B: ¿Recurrencia en 6 meses?
    B-->>C: ¿Cuántas transacciones? (sin turno intermedio)

    C->>B: Cantidad, aviso y confirmación de datos
    B->>S: Productos vigentes
    S->>P: ada_info_detail
    P-->>S: Productos con franquicia
    S-->>B: Lista de productos
    B-->>C: Selección de producto · rango de valor · fecha

    C->>B: Fecha (DD/MM/AAAA)
    B->>S: Vigencia por franquicia
    Note over B,S: VISA 180 días · MASTER 120<br/>Si supera el plazo, no se consulta ASO
    B->>S: Movimientos del día
    S->>A: Financial Overview · card_id
    S->>A: Transacciones de la tarjeta
    Note over S,A: Filtro en la propia consulta:<br/>$35.000 – $500.000
    A-->>S: Movimientos del día
    S-->>B: Listado
    B-->>C: Movimientos encontrados

    C->>B: Selecciona un movimiento
    B->>S: Detalle de la operación
    S->>A: Operaciones del día
    A-->>S: descProvision · ECI · eCard · estado
    S-->>B: Detalle clasificado
    B-->>C: Confirma los datos de la compra

    C->>B: Sí, continuar con el reporte
    Note over B: Frontera: continúa el proceso<br/>de investigación
```

---

## 3 · Simplificación (implementada el 18/08)

Hoy el detalle se consulta **una vez por cada movimiento** que el cliente selecciona,
aunque el servicio devuelve **todas las operaciones del día** en una sola respuesta.

```mermaid
flowchart LR
    subgraph HOY [Situación actual]
        direction TB
        A1[Listado] -->|llamada 1| T1[(Transacciones)]
        A2[Confirmación] -->|llamada 2| O1[(Operaciones del día)]
        A3[Segunda transacción<br/>del mismo caso] -->|llamada 3| O2[(Operaciones del día)]
    end

    subgraph PROPUESTA [Con caché por tarjeta y fecha]
        direction TB
        B1[Listado] -->|llamada 1| T2[(Transacciones)]
        B1 -->|llamada 2| O3[(Operaciones del día)]
        B2[Confirmación] -.->|sin llamada| CACHE[(Caché)]
        B3[Segunda transacción] -.->|sin llamada| CACHE
        O3 --> CACHE
    end

    classDef ahorro fill:#e9f6ec,stroke:#2e7d46
    class CACHE ahorro
```

**Efecto medido:** con tres movimientos distintos del mismo día, el servicio hace **una
sola** consulta de operaciones en vez de tres. La descripción de la confirmación pasa a
tomarse de `descProvision` (la glosa del establecimiento), con el concepto del listado
como respaldo.

**Precisión importante:** el listado y el detalle son **dos servicios ASO distintos**
—transacciones de tarjeta y operaciones— y el segundo es el único que aporta ECI, eCard
y estado de la operación, que son los campos que deciden el desenlace del caso. No pueden
unificarse en una sola llamada sin perder esa clasificación; lo que sí se elimina es la
**repetición** de la segunda.

---

## 4 · Reglas de negocio vigentes

| Regla | Valor | Dónde se aplica |
|---|---|---|
| Transacciones por caso | hasta 3 | selección de cantidad |
| Rango por transacción | $35.000 – $500.000 | **filtro en la consulta al ASO**, no en memoria |
| Vigencia de contracargo | VISA 180 días · MASTER 120 | antes de consultar movimientos |
| Recurrencia | gestión de la misma tipología en 6 meses | al entrar al flujo |
| Formato de fecha | se solicita `DD/MM/AAAA` | se aceptan además `DD-MM-AAAA`, `AAAA-MM-DD` y sin ceros; una fecha futura se rechaza con aviso propio |

---

## 5 · Estado de verificación

| Comprobación automática | Alcance | Resultado |
|---|---|---|
| Recorridos extremo a extremo | 17 escenarios del tramo | 17 / 17 |
| Contrato con el tramo siguiente | 25 claves de la entrega | 25 / 25 |
| Exactitud de los mensajes con datos del cliente | 61 comprobaciones | 61 / 61 |
| Documentación de pruebas contra el sistema real | 25 recorridos | 25 / 25 |

Los mensajes que muestran datos del cliente se verifican **contra la fuente del dato**
—no contra un texto fijo—, comprobando procedencia, formato, comportamiento ante datos
ausentes y limpieza entre pasos.
