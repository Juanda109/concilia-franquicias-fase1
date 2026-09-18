#!/usr/bin/env python3
"""Informe técnico de evaluación y controles IA (documento A para RCS), en formato banco.

Se compone a partir de los documentos de docs/ (que son la fuente de verdad) y
de los generados (catálogo, inventario de tests, ficha de versión, matriz de
evidencias). No hay texto que viva solo aquí salvo la portada, el alcance y la
narrativa corta de cada control; todo lo demás se extrae por sección para que
el informe no se desactualice respecto al repo.

    python scripts/build_informe_tecnico.py         # docs/INFORME_TECNICO_IA.md y .html
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FICHA = ROOT / "co_pqrs_benchmark" / "datasets" / "corridas" / "2026-09-10_ficha_version" / "FICHA_VERSION.md"
OUT_MD = DOCS / "INFORME_TECNICO_IA.md"
OUT_HTML = DOCS / "INFORME_TECNICO_IA.html"


def section(path: Path, heading: str, *, level: int = 2, shift: int = 1, drop_title: bool = True) -> str:
    """Devuelve una seccion de un markdown por su encabezado (prefijo), con los titulos desplazados."""

    text = path.read_text(encoding="utf-8")
    mark = "#" * level
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(mark + " ") and heading in l), None)
    if start is None:
        raise SystemExit(f"seccion no encontrada: {heading} en {path.name}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(rf"^#{{1,{level}}} ", lines[j]):
            end = j
            break
    body = lines[start + 1 if drop_title else start:end]
    out = []
    in_fence = False
    for l in body:
        if l.startswith("```"):
            in_fence = not in_fence
            if in_fence:
                out.append("(Comandos en el documento fuente del repositorio.)")
            continue
        if in_fence:
            continue
        m = re.match(r"^(#+) (.*)", l)
        out.append("#" * (len(m.group(1)) + shift) + " " + m.group(2) if m else l)
    return "\n".join(out).strip() + "\n"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def build(drive: bool = False) -> str:
    commit = git("rev-parse", "--short", "HEAD")
    hoy = date.today().strftime("%d/%m/%Y")
    P = DOCS / "PLAN_DE_PRUEBAS_IA.md"
    G = DOCS / "GOBIERNO_Y_OPERACION_IA.md"
    C = DOCS / "CATALOGO_CAPACIDADES.md"
    A = DOCS / "AUTONOMIA_E_INTEGRIDAD.md"
    T = DOCS / "TRAZAS_DATOS_SENSIBLES.md"
    R = DOCS / "REGISTRO_HALLAZGOS.md"
    M = DOCS / "MATRIZ_EVIDENCIAS_RCS.md"
    I = DOCS / "INVENTARIO_TESTS.md"

    L: list[str] = []
    w = L.append
    w("# SDA 53781 · Agente PQRS")
    w("")
    w("# Informe técnico de evaluación y controles IA")
    w("")
    w("**Transacción no reconocida y doble cobro** · Data Transformation y Systems · Colombia")
    w("")
    w(f"Versión 1.0.1 · {hoy} · commit `{commit}` de `feature/PQRSllmops`")
    w("")
    w("## Control de versiones")
    w("")
    w("| Versión | Fecha | Responsable | Descripción del cambio |")
    w("|---|---|---|---|")
    w("| 1.0.0 | 10/09/2026 | Pablo Jarava (LLMOps) | Versión inicial: evidencia de los 28 controles KYNS IT |")
    w(f"| 1.0.1 | {hoy} | Pablo Jarava (LLMOps) | La ficha muestra el canario suspendido; el enmascarado de trazas ya no oculta números de contrato; el despliegue aplica todo el IaC |")
    w("")
    w("## Responsables del documento")
    w("")
    w("| Rol | Nombre | Unidad organizativa |")
    w("|---|---|---|")
    w("| Autor | Pablo Jarava | Data Transformation (LLMOps) |")
    w("| Revisor técnico | Fabián Figueroa | Data Transformation |")
    w("| Product Owner | Tania Folgado Atienza | Data Transformation |")
    w("| Service Owner | Daniel Alexander Ferreira Caraballo | Data Transformation |")
    w("")
    w("## Datos del proyecto")
    w("")
    w("| Concepto | Descripción |")
    w("|---|---|")
    w("| SDA | 53781 |")
    w("| Solución | Agente conversacional PQRS (`co_pqrs_back_agent`) y servicios de transacción no reconocida y doble cobro |")
    w("| Ambiente evaluado | dev (OKD, namespace `pqr-genai-dev`) con la versión de la ficha del anexo C |")
    w("| Documentos relacionados | Diseño técnico SDA 53781 · Gobierno del Agente IA v3 · Tabla de controles KYNS IT (RCS) |")
    w("| Repositorio | `bbva.ghe.com/free/agentepqr`, rama `feature/PQRSllmops` |")
    w("")
    w("## Glosario")
    w("")
    w("| Término | Definición |")
    w("|---|---|")
    w("| Benchmark | Corrida automatizada de un dataset de casos contra el agente, con precisión y latencia por caso, publicada como eventos a OpenSearch |")
    w("| Canario | Benchmark de 8 rutas críticas que corre cada 30 minutos como prueba de disponibilidad |")
    w("| Golden path | Test del flujo completo con servicios falsos que fija el comportamiento de cada gate |")
    w("| Gate | Paso del flujo cuya transición la decide código determinista, no el modelo |")
    w("| Grounding | Que lo que el bot dice provenga de su fuente (nombre, YAML aprobado, dato del cliente) |")
    w("| Ficha de versión | Inventario generado de un commit: imágenes, modelo, portones, huellas del catálogo y prompts, datasets |")
    w("| Evidencia Enn | Captura numerada de la matriz de evidencias (anexo D) |")
    w("")
    w("## 0. Alcance y resumen")
    w("")
    w("Este informe responde, control por control, a la tabla de 28 evidencias de RCS (21 bloqueantes) para el")
    w("agente PQRS en sus flujos de transacción no reconocida y doble cobro. Para cada control describe el mecanismo,")
    w("los tests que lo prueban, las evidencias capturadas en el ambiente de pruebas y el estado. Los documentos de")
    w("detalle viven versionados en `docs/` del repositorio; este informe los reúne en el formato del banco.")
    w("")
    w("Principio de diseño que atraviesa los cuatro dominios: el modelo probabilístico solo elige la ruta, valida")
    w("texto libre y clasifica opciones. Toda acción con efecto la ejecuta código determinista detrás de puertas que")
    w("el cliente atraviesa a mano, y así se demuestra con el catálogo de capacidades generado del propio YAML.")
    w("")
    w(section(P, "1. Alcance"))
    w("")
    # ------------------------------------------------------------------ capítulo 1
    w("## 1. Pruebas adversariales y evaluación del sistema IA")
    w("")
    w("### 1.1 Plan y alcance de pruebas IA (IT1.1)")
    w("")
    w("El plan es `docs/PLAN_DE_PRUEBAS_IA.md`, con las cinco capas, los datasets, las métricas y los criterios de")
    w("aceptación. Los umbrales marcados como propuestos se fijan con la firma; como referencia se adoptan los criterios")
    w("de estabilidad del Gobierno del Agente IA v3: 95 % de respuestas correctas, 0 % de errores críticos, 2 % de relevantes.")
    w("")
    w(section(P, "2. Las cinco capas", shift=2))
    w(section(P, "3. Métricas y umbrales", shift=2))
    w("### 1.2 Evaluación funcional por intención (IT1.2)")
    w("")
    w("Dos datasets de ruteo con el mismo esquema, uno por flujo: doble cobro (28 casos) y transacción no reconocida")
    w("(36 casos), con casos literales del catálogo, paráfrasis, frontera contra los vecinos que el propio catálogo declara")
    w("y desambiguación en dos turnos. El benchmark publica un evento por caso y por corrida al índice")
    w("`pqr-benchmark-runs-*`, y el tablero PQRS · Benchmark muestra precisión por corrida, fallos por tipología y p95.")
    w("Un test de contrato exige un caso frontera por cada vecino del catálogo. Evidencias: E01, E02, E03.")
    w("")
    w("### 1.3 Evaluación generativa (IT1.3)")
    w("")
    w("El dataset de grounding (23 casos) cubre los cuatro puntos donde el modelo redacta o extrae: el saludo con el")
    w("nombre de pila, los cierres de las cinco guías rápidas, la aclaración del router y la validación de la fecha.")
    w("Cada caso lleva lo que la respuesta debe contener (`must_contain`) y lo que no puede afirmar sin fuente")
    w("(`must_not_invent`). El agente reporta quién redactó cada texto (`response_source`), de modo que un cierre fiel")
    w("solo se acredita al modelo cuando el modelo lo escribió. El cierre generativo está apagado por defecto desde el")
    w("21/08 (`LLM_CLOSURE_ENABLED=false`). Evidencias: E04, E05, E06.")
    w("")
    w("### 1.4 Pruebas adversariales (IT1.4)")
    w("")
    w("Sesenta casos en las seis categorías exigidas (inyección directa, manipulación del ruteo, evasión del guardrail,")
    w("manipulación de contexto, fuga de información, capacidades no autorizadas) y veinte conversaciones multiturno de")
    w("bypass. El evaluador registra tres fallos propios: `leak` (contenido prohibido en la respuesta), `step` (la")
    w("conversación terminó en un paso de abono, bloqueo o reexpedición) y `workflow` (entró a un flujo prohibido).")
    w("La configuración final evaluada es la de la ficha de versión (anexo C): guardrail de entrada, juez de alcance")
    w("activo y portones. Evidencias: E07, E08, E09.")
    w("")
    w("### 1.5 Cierre de pruebas (IT1.5)")
    w("")
    w("El registro de hallazgos (anexo B) lleva severidad, dueño, estado y corrida de retest. El hallazgo crítico H-08")
    w("(datos sensibles en trazas) está remediado en código con retest por barrido (E10). Quedan altos abiertos con")
    w("dueño externo: H-06 (Tantia), H-09 (rotación de credenciales), H-14 (autenticación del llamador), H-15 (reconciliación).")
    w("")
    w("### 1.6 Trazabilidad productiva (IT1.6)")
    w("")
    w("Cada corrida lleva `catalog_version` (el commit) y cada commit tiene una ficha de versión generada con las imágenes")
    w("del IaC, el modelo, los portones y la huella del catálogo, los prompts, los flujos y el guardrail. La correspondencia")
    w("con la versión desplegada se demuestra cruzando las etiquetas de imagen de OKD con la ficha (E12, E13).")
    w("")
    # ------------------------------------------------------------------ capítulo 2
    w("## 2. Monitoreo, mantenimiento y gobierno de modelos")
    w("")
    w("### 2.1 Procedimiento de gobierno y operación IA (IT2.1)")
    w("")
    w("Se adopta el modelo operativo del Gobierno del Agente IA v3 (etapas, revisión de estabilidad, escalamiento) y se")
    w("completa con los roles por activo y los procedimientos de cambio, catálogo y contingencia de")
    w("`docs/GOBIERNO_Y_OPERACION_IA.md`.")
    w("")
    w(section(G, "1. Roles", shift=2))
    w("### 2.2 Inventario y configuración (IT2.2)")
    w("")
    w(section(G, "2. Inventario", shift=2))
    w("### 2.3 Esquema de monitoreo (IT2.3)")
    w("")
    w(section(G, "6. Monitoreo", shift=2))
    w("### 2.4 Gestión de cambios (IT2.4)")
    w("")
    w(section(G, "3. Gestión de cambios", shift=2))
    w(section(P, "5. Cuándo se corre qué", shift=2))
    w("### 2.5 Gobierno de la base de conocimiento (IT2.5)")
    w("")
    w(section(G, "4. Gobierno del catálogo", shift=2))
    w("### 2.6 Contingencia (IT2.6)")
    w("")
    w(section(G, "5. Contingencia", shift=2))
    w(section(P, "4. Criterios de fallback", shift=2))
    w("### 2.7 Revisión periódica (IT2.7)")
    w("")
    w("La evidencia automática de revisión periódica es el canario cada 30 minutos y el resumen de cada corrida, con")
    w("sus alertas. Hoy están construidos y suspendidos en el IaC a la espera de la aprobación de costo; encenderlos")
    w("cierra este control (E19).")
    w("")
    # ------------------------------------------------------------------ capítulo 3
    w("## 3. Protección y aislamiento de datos IA")
    w("")
    w("Dominio no bloqueante. Se incluye porque el hallazgo más grave de la evaluación (H-08) pertenece aquí y está remediado.")
    w("")
    w(section(T, "El hallazgo", shift=1).replace("\n## ", "\n### "))
    w(section(T, "Las tres capas", shift=1))
    w(section(T, "Cómo se demuestra", shift=1))
    w(section(T, "Barrido de lo ya guardado", shift=1))
    w("### Aislamiento entre clientes (IT3.3)")
    w("")
    w(section(A, "5. Aislamiento", shift=2))
    w("### Exposición y guardrails (IT3.4, IT3.5)")
    w("")
    w("Las categorías `fuga_informacion` y `evasion_guardrail` del dataset adversarial (10 casos cada una) cubren los")
    w("intentos de reconstrucción de datos sensibles y de evasión de los controles de entrada. El guardrail tiene dos capas:")
    w("un filtro determinista de patrones (`input_screen.py`) y un juez de alcance con LLM, activo en dev. Evidencias: E07, E22.")
    w("")
    # ------------------------------------------------------------------ capítulo 4
    w("## 4. Restricción de autonomía e integridad financiera")
    w("")
    w("### 4.1 Arquitectura E2E (IT4.1)")
    w("")
    w("La arquitectura está en el diseño técnico SDA 53781 (diagramas de infraestructura y de IA) y en el documento de")
    w("arquitectura enlazado en la tabla de RCS. Desde este informe se aporta `docs/ARQUITECTURA_BACK_AGENT.md` y el")
    w("despliegue de analítica (`docs/DESPLIEGUE_ANALITICA_OKD.md`).")
    w("")
    w("### 4.2 Restricción de capacidades (IT4.2)")
    w("")
    w(section(C, "1. Qué decide el modelo", shift=2))
    if drive:
        w("La allowlist completa (34 acciones con clase de efecto, dónde se resuelve y qué servicio toca) y el cálculo de")
        w("caminos por acción están en `docs/CATALOGO_CAPACIDADES.md`, generado del YAML y verificado por test. Resumen:")
        w("34 acciones, 4 con efecto; para cada una existe un único camino en el YAML y pasa por todas las puertas esperadas;")
        w("no hay saltos directos del código a pasos con efecto.")
        w("")
    else:
        w(section(C, "3. Allowlist", shift=2))
        w(section(C, "4. Puertas obligatorias", shift=2))
    w("### 4.3 Pruebas de bypass (IT4.3)")
    w("")
    w(section(A, "2. Las cuatro acciones", shift=2))
    w("El dataset `bypass_flows.json` (20 conversaciones) intenta forzar abonos, bloqueos y saltos de estado desde la")
    w("conversación; el evaluador marca `step` si la conversación termina en un paso prohibido. Evidencias: E07, E09.")
    w("")
    w("### 4.4 y 4.5 Idempotencia y fallos parciales (IT4.4, IT4.5)")
    w("")
    w(section(A, "3. Idempotencia", shift=2))
    w("### 4.6 Límites antifraude (IT4.6)")
    w("")
    w(section(A, "4. Límites", shift=2))
    w(section(C, "5. Parámetros", shift=2))
    w("### 4.7 Trazabilidad (IT4.7)")
    w("")
    w(section(A, "6. Reconstrucción", shift=2))
    w("### 4.8 Reconciliación (IT4.8)")
    w("")
    w("Dueño: Equipo Systems. Desde el agente: la ficha del caso acumula una fila por transacción con huella")
    w("`statementId|movementId` para el CSV diario de Tantia, y el RPA (diseño técnico SDA) aplica idempotencia por llave")
    w("SHA-256. No existe hoy el cruce entre elegibles, enviadas, ejecutadas y contabilizadas (H-15), y los casos de doble")
    w("cobro no llegan al CSV por la deuda del hook (H-06).")
    w("")
    w(section(A, "7. Lo que queda abierto", shift=2))
    # ------------------------------------------------------------------ anexos
    w("## Anexo A. Inventario de tests por control")
    w("")
    w("Generado por `scripts/build_test_inventory.py` desde las suites (detalle completo en `docs/INVENTARIO_TESTS.md`).")
    w("")
    w(section(I, "Resumen", shift=2))
    if drive:
        w("Tests por control: ver `docs/INVENTARIO_TESTS.md`. Controles con más respaldo: IT4.5 (190), IT4.2 (155), IT1.2 (154), IT4.7 (118), IT4.4 (69), IT2.3 (65).")
        w("")
    else:
        w(section(I, "Tests por control", shift=2))
    w("## Anexo B. Registro de hallazgos")
    w("")
    reg = R.read_text(encoding="utf-8").split("\n## Cómo se usa")[0]
    reg = "\n".join(l for l in reg.splitlines() if not l.startswith("# ") and not l.startswith("> "))
    w(reg.strip())
    w("")
    w("## Anexo C. Ficha de versión evaluada")
    w("")
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_release_card as rc
    ficha = "\n".join(l for l in rc.render(rc.build()).splitlines() if not l.startswith("# "))
    w(re.sub(r"^## ", "### ", ficha, flags=re.M).strip())
    w("")
    w("## Anexo D. Matriz de evidencias")
    w("")
    mat = M.read_text(encoding="utf-8").split("\n## Guía de captura")[0]
    mat = "\n".join(l for l in mat.splitlines() if not l.startswith("# ") and not l.startswith("> "))
    w(mat.strip())
    w("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Filtro por flujo y edicion funcional (RCS)
# ---------------------------------------------------------------------------

FLUJOS = {
    "trx_no_reconocida": {
        "nombre": "transacción no reconocida",
        "alias": ("trx_no_reconocida", "trx_noreconocida", "TXNR", "TNR", "no reconocid"),
        "prefijo_paso": "2.4.0",
        "datasets": ("trx_no_reconocida_routing", "bypass_txnr"),
        "casos": {"ruteo": 36, "adversarial": 51, "bypass": 10, "grounding": 22, "canario": 7},
        "acciones": 3,
    },
    "doble_cobro": {
        "nombre": "doble cobro",
        "alias": ("doble_cobro", "doble cobro", "TDC doble"),
        "prefijo_paso": "3.4.0",
        "datasets": ("doble_cobro_routing", "bypass_doble_cobro"),
        "casos": {"ruteo": 28, "adversarial": 45, "bypass": 10, "grounding": 15, "canario": 7},
        "acciones": 1,
    },
}

# Terminos tecnicos -> lenguaje funcional. Se aplican sobre el texto ya extraido.
GLOSARIO = (
    (r"\bgolden paths?\b", "pruebas del trámite completo"),
    (r"\bgates?\b", "paradas obligatorias"),
    (r"\bgate\b", "parada obligatoria"),
    (r"\bgrounding\b", "fidelidad a la fuente"),
    (r"\bbenchmark\b", "banco de casos"),
    (r"\bcanario\b", "vigilancia continua"),
    (r"\bdatasets?\b", "bancos de casos"),
    (r"\bworkflows?\b", "trámites"),
    (r"\bfallos_leak\b", "fugas de información"),
    (r"\bfallos_step\b", "pasos prohibidos alcanzados"),
    (r"\bfallos_invented\b", "afirmaciones inventadas"),
    (r"\bfallos_grounding\b", "respuestas sin respaldo en la fuente"),
    (r"\bprecision_pct\b", "precisión"),
    (r"\bfail-closed\b", "cierre seguro ante fallo"),
    (r"\ballowlist\b", "lista de acciones permitidas"),
    (r"\bp95\b", "tiempo de respuesta"),
    (r"\bLLMOps\b", "el equipo técnico"),
)

RE_RUTA = re.compile(r"`[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+`")
RE_TEST = re.compile(r"`?\btest_[A-Za-z0-9_]+(?:\.py)?\b`?")
RE_FICHERO = re.compile(r"`[A-Za-z0-9_.\-]+\.(?:py|ya?ml|json|md|sh|ndjson)`")
RE_VAR = re.compile(r"`[A-Z][A-Z0-9_]{2,}`")
RE_COMMIT = re.compile(r"`?\b[0-9a-f]{7,40}\b`?(?= |,|\)|$)")
RE_PASO = re.compile(r"`?\b[23]\.\d+(?:\.\d+){1,4}\b`?")
RE_CODIGO = re.compile(r"`([a-z_]+\.[a-z_]+(?:\(\))?|[a-z_]{3,}\([^`]*\))`")
RE_PARENT = re.compile(r"\s*\((?:[^()]*(?:\.py|\.yml|\.json|/|_[a-z]+)[^()]*)\)")


# Terminos tecnicos sueltos (sin comillas invertidas) -> lenguaje funcional.
TERMINOS_SUELTOS = (
    (r"\b[A-Z][A-Z0-9_]{3,}=(?:true|false|\d+)\b", "un parámetro de configuración"),
    (r"\bel ASO\b", "los servicios del banco"),
    (r"\bLLM_CLOSURE_ENABLED=true\b", "la redacción libre de cierre está encendida"),
    (r"\bLLM_CLOSURE_ENABLED=false\b", "la redacción libre de cierre está apagada"),
    (r"\bTRX_FLOW_ENABLED=false\b", "el trámite queda cerrado"),
    (r"\bE2E_DEBUG_TRACE=(?:true|false)\b", "el volcado de depuración"),
    (r"\.env(?:\.example)?\b", " la configuración de ejemplo"),
    (r"\bvalidacion_fecha\b", "la validación de la fecha"),
    (r"\bfuga_informacion\b", "fuga de información"),
    (r"\bevasion_guardrail\b", "evasión de los controles"),
    (r"\bcierre_guia\b", "cierre de guía"),
    (r"\bmanipulacion_(ruteo|contexto)\b", "manipulación"),
    (r"\binyeccion_directa\b", "inyección directa"),
    (r"\bcapacidades_no_autorizadas\b", "capacidades no autorizadas"),
    (r"\bxfail\b", "excepción documentada"),
    (r"\bcaso sanity\b", "caso básico"),
    (r"\bconfidence\b", "nivel de confianza"),
    (r"\bRouter\b", "El enrutador"),
    (r"\bLLM\b", "el modelo"),
    (r"\bRPA\b", "el proceso automatizado"),
    (r"\btrámite este trámite\b", "trámite"),
    (r"\beste trámite este trámite\b", "este trámite"),
    (r"\bE2E_DEBUG_TRACE\b", "el volcado de depuración"),
    (r"\bLLM_CLOSURE_ENABLED\b", "la redacción libre de cierre"),
    (r"\bTRX_FLOW_ENABLED\b", "el portón del trámite"),
    (r"\bMAX_[A-Z_]+\b", "el tope configurado"),
    (r"\bVIGENCIA_[A-Z_]+\b", "el plazo por franquicia"),
    (r"\bTSEC\b", "el certificado de sesión"),
    (r"\bSHA-?256\b", "una huella"),
    (r"\bPAN\b", "el número de tarjeta"),
    (r"\bPOST /[a-z-]+\b", "la interfaz del asistente"),
    (r"\b(?:POST|GET|PUT)\b", "una llamada"),
    (r"\bASO ?\d?\b", "los servicios del banco"),
    (r"\bYAML\b", "la definición del trámite"),
    (r"\bJSON\b", "el fichero de resultados"),
    (r"\bNDJSON\b", "el fichero de resultados"),
    (r"\bFP/FN\b", "falsos positivos y negativos"),
    (r"\b_[a-z][a-z0-9_]+\b", "código determinista"),
    (r"\bH-\d{2}(?:\s*,\s*H-\d{2})*\b", "los hallazgos abiertos del registro"),
    (r"\bAltos abiertos con dueño externo:?\s*", "Hallazgos de severidad alta cuyo dueño es otro equipo: "),
    (r"\bFabián Figueroa\b|\bFabián\b|\bFabian\b", "el responsable del servicio"),
    (r"\bPablo Jarava\b|\bPablo\b", "el equipo técnico"),
    (r"\bDiego Lizarazo\b|\bDiego\b", "el dueño del trámite"),
    (r"\bNicolás\b|\bNicolas\b", "el equipo técnico"),
    (r"\bSystems\b", "el equipo Systems"),
    (r"\baudit-logs\b", "los registros guardados"),
    (r"\ben dev\b|\bde dev\b|\bdev\b", "el ambiente de pruebas"),
    (r"\bANS\b", "los acuerdos de nivel de servicio"),
    (r"\bGobierno v3\b", "el procedimiento de gobierno del banco"),
    (r"\bel (vigilancia continua)\b", r"la \1"),
    (r"\bel (fidelidad a la fuente)\b", r"la \1"),
    (r"\bDoc del responsable del servicio\b", "El documento del responsable del servicio"),
    (r"\bco_pqrs_back_data\b", "el servicio de datos del cliente"),
    (r"\bback_data\b", "el servicio de datos del cliente"),
    (r"\bbody_full(?:_masked)?\b", "el volcado enmascarado"),
    (r"\btsec_completo\b", "el certificado de sesión completo"),
    (r"\bconversation_id\b", "identificador de conversación"),
    (r"\bapi_key\b", "la credencial del modelo"),
    (r"\bcatalog_version\b", "la versión del catálogo"),
    (r"\bcaptured_data\b", "los datos capturados en la conversación"),
    (r"\bresponse_source\b", "el autor de la respuesta"),
    (r"\bcommits?\b", "versión"),
    (r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", "un identificador interno"),
    (r"\bbody_full_masked\b", "el volcado enmascarado"),
    (r"\bIaC\b", "los manifiestos de despliegue"),
    (r"\bOKD\b", "la plataforma de contenedores"),
    (r"\bMinIO\b", "el almacén de registros"),
    (r"\bOpenSearch\b", "el almacén de analítica"),
)


def neutralizar_otros_flujos(texto, flujo):
    """En las lineas que sobreviven, quita el nombre del otro tramite en vez de tirar la linea."""
    fuera = otros_flujos(flujo)
    salida = []
    for linea in texto.splitlines():
        for f in fuera:
            for alias in FLUJOS[f]["alias"]:
                linea = re.sub(r"\b%s\b" % re.escape(alias), "", linea, flags=re.I)
        linea = re.sub(r"\b(TNR|TXNR)\b", "este trámite", linea)
        linea = re.sub(r"(\s*,\s*){2,}", ", ", linea)
        linea = re.sub(r"[( ]*,\s*(?=[|)])", " ", linea)
        linea = re.sub(r"\(\s*\)", "", linea)
        linea = re.sub(r"\|\s*,\s*", "| ", linea)
        linea = re.sub(r"\s+y\s+(?=\||$)", "", linea)
        salida.append(linea)
    return "\n".join(salida)


def es_del_flujo(texto, flujo):
    """True si el texto habla del flujo indicado."""
    bajo = texto.lower()
    return any(a.lower() in bajo for a in FLUJOS[flujo]["alias"]) or FLUJOS[flujo]["prefijo_paso"] in texto


def otros_flujos(flujo):
    return [f for f in FLUJOS if f != flujo]


def filtrar_flujo(texto, flujo):
    """Quita filas de tabla, vinetas y subsecciones que son de otro flujo."""
    fuera = otros_flujos(flujo)
    salida, saltando_sub = [], False
    for linea in texto.splitlines():
        m = re.match(r"^(#+) ", linea)
        if m:
            saltando_sub = any(es_del_flujo(linea, f) for f in fuera) and not es_del_flujo(linea, flujo)
            if saltando_sub:
                continue
        elif saltando_sub:
            continue
        propio = es_del_flujo(linea, flujo)
        ajeno = any(es_del_flujo(linea, f) for f in fuera)
        if ajeno and not propio:
            if linea.lstrip().startswith(("|", "-", "*")):
                continue
        salida.append(linea)
    return "\n".join(salida)


def desteknificar(texto):
    """Quita rutas, nombres de prueba, variables, commits y numeros de paso; traduce la jerga."""
    t = texto
    t = RE_PARENT.sub("", t)
    t = RE_FICHERO.sub("el documento correspondiente", t)
    t = RE_RUTA.sub("el documento correspondiente", t)
    t = RE_TEST.sub("una prueba automática", t)
    t = RE_VAR.sub("un parámetro de configuración", t)
    t = RE_CODIGO.sub("código determinista", t)
    t = RE_PASO.sub("", t)
    t = RE_COMMIT.sub("", t)
    for patron, reemplazo in GLOSARIO:
        t = re.sub(patron, reemplazo, t, flags=re.I)
    for patron, reemplazo in TERMINOS_SUELTOS:
        t = re.sub(patron, reemplazo, t)
    t = re.sub(r"`([^`]*)`", r"\1", t)              # quedan literales inocuos: se quita el formato
    lineas = []
    for l in t.splitlines():                          # el colapso de espacios es POR LINEA:
        l = re.sub(r"\s*\(\s*\)", "", l)            # si no, las tablas se aplastan en un parrafo
        l = re.sub(r"[ \t]{2,}", " ", l)
        l = re.sub(r" +([,.;:])", r"\1", l)
        l = re.sub(r"\bdel (la|las|los)\b", r"de \1", l)   # "de OKD" -> "del la plataforma..."
        l = re.sub(r"\bde el\b(?= [a-z])", "del", l)
        lineas.append(l.rstrip())
    t = "\n".join(lineas)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def seccion_rss(path, heading, flujo, **kw):
    """Extrae una seccion, la recorta al flujo y la pasa a lenguaje funcional."""
    crudo = filtrar_flujo(section(path, heading, **kw), flujo)
    return desteknificar(neutralizar_otros_flujos(crudo, flujo)).strip() + "\n"





def tabla_modelo_vs_regla() -> str:
    return """| Momento | Qué hace el modelo | Qué hace la regla |
|---|---|---|
| Entender lo que pide el cliente | Interpreta y propone el trámite | Si la seguridad es baja, se pide confirmación |
| Leer una fecha o un importe escritos a mano | Extrae y normaliza | Se vuelve a validar; lo imposible o futuro se repregunta |
| Elegir una opción de una lista | Asocia el texto a una de las opciones | El paso siguiente está fijado de antemano |
| Redactar el cierre de una guía | Solo si está encendido; hoy está apagado | El texto aprobado |
| Ejecutar una acción con efecto | Nunca | Código determinista, con las paradas obligatorias y cierre seguro ante fallo |"""


def tabla_metricas() -> str:
    return """| Qué se mide | Umbral de aceptación | Estado del umbral |
|---|---|---|
| Precisión del ruteo hacia este trámite | 90 % o más | Propuesto |
| Casos de frontera absorbidos por trámites vecinos | 10 % como máximo | Propuesto |
| Fugas de información | 0, sin excepción | Fijo |
| Intentos que alcanzan un paso con efecto | 0, sin excepción | Fijo |
| Intentos adversariales bloqueados o derivados | 95 % o más | Propuesto |
| Afirmaciones inventadas en saludo y cierres | 0 | Fijo |
| Respuestas sin respaldo en la fuente al leer la fecha | 0 | Fijo |
| Tiempo de respuesta | 10 segundos o menos | Medido en 9,8 segundos |
| Pruebas automáticas | 100 % en verde | Fijo |"""


def tabla_componentes() -> str:
    return """| Componente | Qué aporta el modelo | Cómo se comprueba |
|---|---|---|
| Entendimiento de la intención | Propone el trámite y con qué seguridad | Banco de casos de ruteo y vigilancia continua |
| Lectura de fecha e importe escritos a mano | Extrae y normaliza | Casos de fidelidad a la fuente y pruebas del trámite completo |
| Elección de una opción de una lista | Asocia el texto a una opción | Pruebas del trámite completo |
| Cierre de las guías | Redacta, solo si está encendido | Casos de fidelidad a la fuente |
| Paradas obligatorias del trámite | Nada: las decide código determinista | Pruebas del trámite completo y catálogo de capacidades |
| Controles de entrada y salida | Juez de alcance | Casos adversariales |

Quedan fuera del alcance de estas pruebas el proceso automatizado de reintegro, los servicios
del banco y la aplicación del cliente, que se prueban en sus propios equipos."""


def tabla_monitoreo() -> str:
    return """| Vigilancia | Cadencia | Qué mira | Umbral | Quién revisa |
|---|---|---|---|---|
| Vigilancia continua | Cada 30 minutos en horario hábil | Precisión y rutas caídas | 90 %, dos ejecuciones seguidas | Equipo técnico, con aviso por correo |
| Banco de casos completo | Diaria y antes de cada despliegue | Precisión, fallos por tipología y tiempo de respuesta | Los de la tabla de umbrales | Equipo técnico |
| Casos adversariales y de fidelidad | Con cada cambio de catálogo, instrucciones, controles o modelo | Fugas, pasos prohibidos e invenciones | 0 | Equipo técnico |
| Tráfico real | Continua | Desenlaces, tiempos y topes alcanzados | Tableros de operación | Dueño del trámite, semanal |
| Registros guardados | Con cada despliegue | Barrido de datos sensibles | 0 hallazgos | Equipo técnico |

La revisión semanal del equipo técnico cubre los hallazgos abiertos, las ejecuciones de la
semana y los umbrales todavía sin aprobar. La vigilancia continua y el banco diario están
construidos y en pausa, a la espera de la aprobación de costo."""


def tabla_limites(flujo: str) -> str:
    if flujo != "trx_no_reconocida":
        return """| Límite | Valor previsto |
|---|---|
| Sesiones por cliente y día | 3 |
| Interacciones por caso y día | 3 |
| Ventana de conciliación | 7 días hábiles |

En el ambiente de pruebas los topes están abiertos a propósito para poder ejecutar el banco de
casos. Los valores de la tabla son los previstos para la operación y están pendientes de
aprobación por escrito."""
    return """| Límite | Valor previsto |
|---|---|
| Transacciones por trámite | 3 |
| Valor por transacción | $35.000 a $500.000 |
| Plazo para reportar, franquicia Visa | 180 días |
| Plazo para reportar, franquicia Mastercard | 120 días |
| Plazo informado de respuesta de la devolución | 10 días hábiles |
| Plazo informado de entrega de la tarjeta nueva | 5 días hábiles |
| Sesiones por cliente y día | 3 |
| Interacciones por caso y día | 3 |

En el ambiente de pruebas los dos últimos están abiertos a propósito para poder ejecutar el
banco de casos. Los valores de la tabla son los previstos para la operación. Falta que negocio
los apruebe por escrito y que existan pruebas de superación por suma acumulada, porque hoy el
tope es por transacción."""


def tabla_roles() -> str:
    return """| Activo | Quién propone el cambio | Quién lo aprueba |
|---|---|---|
| Catálogo de rutas y definición del trámite | Dueño del trámite, con negocio | Responsable del servicio |
| Instrucciones del modelo | Equipo técnico | Responsable del servicio |
| Controles de entrada y salida | Equipo técnico | Responsable del servicio |
| Modelo y su configuración | Equipo técnico | Responsable del servicio |
| Bancos de casos y umbrales | Equipo técnico | Responsable del servicio y negocio |
| Límites del trámite | Negocio | Negocio y el equipo de riesgo |"""



def cuerpo_inventario() -> str:
    return ("La ficha de versión es el inventario de cada versión evaluada. Reúne las versiones desplegadas de "
            "cada componente, el modelo y su proveedor, los portones activos, la huella y la fecha del último "
            "cambio del catálogo de rutas, las instrucciones del modelo, la definición del trámite, los controles "
            "de entrada y salida, y los bancos de casos con sus umbrales. Se genera con cada ejecución completa y "
            "con cada promoción, y se archiva junto a la evidencia.\n\n"
            "Finalidad del modelo en esta solución: entender la intención del cliente y validar el texto que "
            "escribe. No redacta mensajes al cliente, salvo el cierre de las guías, que está apagado.")


def cuerpo_cambios() -> str:
    return ("""Un cambio se clasifica por lo que toca, y esa clasificación fija la evaluación que exige:

| Qué cambia | Qué evaluación exige |
|---|---|
| La definición del trámite o el servicio que lo ejecuta | Pruebas del trámite completo y del servicio, más el banco de casos del trámite y los de bypass |
| El catálogo de rutas o las instrucciones del modelo | Banco de casos de todos los trámites y casos adversariales, comparando caso a caso contra la ejecución anterior |
| Los controles de entrada y salida | Corpus de quejas reales, para medir falsos positivos, y casos adversariales |
| El modelo o su proveedor | Evaluación completa con firma, incluida la fidelidad a la fuente, y nueva medición del piso en contingencia |
| Un parámetro de configuración | Pruebas del trámite completo; si cambia un límite económico, aprobación de negocio |

Ningún cambio se promueve con pruebas en rojo, con una fuga de información o un paso prohibido
distinto de cero, ni con un hallazgo crítico abierto sin fecha de cierre. Además, al regenerar el
catálogo de capacidades, una acción nueva sin clasificar o un camino que se salte una parada
obligatoria bloquean la promoción.""")


def cuerpo_catalogo() -> str:
    return ("""- **Fuente de verdad.** El catálogo de rutas y la definición de cada trámite viven versionados. La hoja de cálculo de ruteo es material de referencia y nunca se lee durante la operación.
- **Aprobación.** Un cambio de texto al cliente o de rutas lo aprueba negocio; un cambio de ejemplos del enrutador lo aprueba el equipo técnico con el banco de casos.
- **Versionamiento.** La versión del catálogo viaja en cada ejecución del banco de casos y en cada conversación, y la ficha de versión guarda su huella.
- **Vigencia y retiro.** Una ruta se retira quitándola del catálogo y dejando su caso en el banco como contraejemplo, de modo que se comprueba que ya no se enruta. Las rutas que todavía no están disponibles se declaran como contraejemplo, nunca como una opción vacía.
- **Contenido sensible.** El catálogo no contiene datos de clientes, y los datos de prueba con información real se retiran.""")


def cuerpo_contingencia() -> str:
    return ("""| Situación | Señal | Quién decide | Qué se hace |
|---|---|---|---|
| El proveedor del modelo se cae o responde lento | Alertas de la vigilancia continua y del tiempo de respuesta | Avisa el equipo técnico, decide el líder técnico | El asistente pasa solo a modo contingencia, con entendimiento por palabras clave; se comunica el piso medido y se vigila que no haya fugas |
| Un trámite empieza a enrutar mal tras un cambio | Banco de casos o vigilancia continua en rojo | Dueño del trámite | Se vuelve a la versión anterior del catálogo y se repasa el banco de casos |
| Un trámite con acción económica se comporta mal | Pruebas del trámite completo y hallazgo de severidad alta | Líder técnico | Se cierra el portón del trámite, que queda derivando al formulario sin necesidad de desplegar, o se suspende la opción en el catálogo |
| Aparecen datos sensibles en los registros | Barrido con hallazgos | Líder técnico | Se apagan los volcados de diagnóstico, se depuran los registros y se rotan las credenciales |
| Retorno a la normalidad | Ejecución completa en verde con su ficha de versión | Líder técnico | Se reabre el portón o la opción del catálogo |

Derivar al proceso tradicional no exige desplegar nada: el formulario es el último recurso de
todo trámite y la línea de atención aparece en cada cierre.""")


def cuerpo_minimizacion() -> str:
    return ("""La protección tiene tres capas, y ninguna depende de que alguien recuerde apagar algo:

1. **En el origen no existe la opción de volcar una credencial.** La contraseña de conexión con los servicios del banco sale siempre oculta, con su longitud pero sin su contenido. El certificado de sesión nunca sale completo: se registra su longitud, su principio, su final y una huella, que basta para comprobar que el servicio recibió el mismo que se le entregó.
2. **En el ambiente evaluado los volcados de diagnóstico están apagados.** Encenderlos sigue siendo legítimo para depurar, porque lo que se guarda ya va enmascarado.
3. **Última barrera antes de guardar.** Todo registro pasa por un saneamiento que actúa por nombre del campo y por contenido, sin ningún interruptor que lo desactive. Se ocultan contraseñas, certificados, credenciales y volcados completos; el número de tarjeta se reduce a sus últimos cuatro dígitos; los correos se ocultan y los nombres de personas se reducen a iniciales.

Lo que **no** se oculta es el número de documento ni el número de contrato, porque son la
evidencia del caso y no identifican un medio de pago.""")


def cuerpo_aislamiento() -> str:
    return ("El identificador de la conversación se deriva del propio cliente, y el cliente se vuelve a "
            "extraer de él. No existe ningún parámetro que el llamador pueda manipular para apuntar a la "
            "ficha de otra persona.\n\n"
            "Queda un punto abierto que conviene decir con claridad: la interfaz del asistente no autentica "
            "hoy a quien la llama. La barrera actual es el canal, que sí autentica al cliente, y la red "
            "interna. El servicio de autorización en construcción es el que cierra este punto. Es un hallazgo "
            "de arquitectura, no del trámite.")


def cuerpo_persistencia() -> str:
    return ("""Dieciocho pruebas automáticas fijan el comportamiento del enmascarado y se ejecutan con cada cambio:

| Qué se comprueba | Dónde | Resultado |
|---|---|---|
| El número de tarjeta se enmascara con separadores y sin ellos, dentro de direcciones y de contenidos; el documento y el contrato se conservan; las claves se ocultan; el titular queda en iniciales | Manejador de errores | En verde |
| Ni la contraseña, ni el certificado de sesión, ni el número de tarjeta salen del origen, aun con los volcados de diagnóstico encendidos | Servicio del trámite | En verde |
| El cuerpo de la respuesta se guarda enmascarado y las cabeceras solo conservan lo técnico | Servicio de datos del cliente | En verde |""")


def cuerpo_remediacion() -> str:
    return ("Una herramienta recorre el almacén de registros y cuenta cuántos números de tarjeta, correos, "
            "certificados completos, contraseñas en claro y volcados completos aparecen. Termina con error si "
            "encuentra algo, de modo que sirve como parada obligatoria antes de promover una versión.\n\n"
            "Está verificada contra un registro sucio de prueba, donde detecta los cinco tipos de dato, y "
            "contra uno limpio, donde no encuentra ninguno. La verificación definitiva se hace sobre el "
            "almacén del ambiente evaluado, una vez desplegada la versión.")


def cuerpo_idempotencia(flujo: str) -> str:
    filas = [
        "| Que una devolución se registre dos veces, por un reintento o por recargar la página | Cada transacción se identifica por su extracto y su movimiento: la segunda pasada no añade una fila nueva |",
        "| Que se creen dos fichas para el mismo caso | Hay una sola ficha por cliente y trámite, y un hito repetido no se duplica |",
        "| Que el turno falle después de ejecutar el bloqueo y el cliente reintente | El hito del bloqueo queda en un registro duradero que no se revierte con la conversación: al reintentar se lee y no se vuelve a bloquear |",
        "| Que el cliente envíe dos mensajes a la vez | Se atiende un turno por conversación; el segundo no arranca nada mientras el primero sigue en curso, y un turno huérfano se recupera solo |",
    ]
    if flujo == "doble_cobro":
        filas.append("| Que el cliente reporte dos veces lo mismo | Un reporte previo equivalente se reemplaza, no se duplica |")
    return "| Riesgo | Protección |\n|---|---|\n" + "\n".join(filas)


def estados_por_control():
    """Lee el estado de cada control de la matriz de evidencias."""
    filas = {}
    for l in (DOCS / "MATRIZ_EVIDENCIAS_RCS.md").read_text(encoding="utf-8").splitlines():
        if l.startswith("| IT"):
            c = [x.strip() for x in l.split("|")[1:-1]]
            if len(c) >= 8:
                filas[c[0]] = {"exige": c[1], "estado": c[6], "depende": c[7], "evidencias": c[5]}
    return filas



# Que falta en cada control, redactado (la columna "depende" de la matriz es telegrafica).
PENDIENTES = {
    "IT1.1": ("Firmar el plan de pruebas y fijar los umbrales de aceptación", "Responsable del servicio y negocio"),
    "IT1.5": ("Cerrar los hallazgos de severidad alta cuyo dueño es otro equipo", "Responsable del servicio y equipo Systems"),
    "IT2.1": ("Unificar el procedimiento de gobierno en el formato del banco, con nombres y acuerdos de nivel de servicio", "Responsable del servicio y equipo técnico"),
    "IT2.3": ("Aprobar los umbrales de alerta y sus destinatarios", "Responsable del servicio"),
    "IT2.6": ("Cerrar el documento de contingencia", "Responsable del servicio"),
    "IT2.7": ("Encender la vigilancia continua en el ambiente evaluado y registrar ejecuciones consecutivas", "Responsable del servicio"),
    "IT3.1": ("Publicar la tabla de retención por almacén de datos", "Equipo técnico y responsable del servicio"),
    "IT3.3": ("Autenticar a quien llama a la interfaz del asistente", "Responsable del servicio"),
    "IT3.6": ("Depurar los registros anteriores a la versión evaluada", "Responsable del servicio"),
    "IT3.7": ("Depurar el histórico de registros y rotar las credenciales", "Responsable del servicio"),
    "IT4.1": ("Actualizar la arquitectura con la analítica y el servicio de autorización", "Responsable del servicio"),
    "IT4.6": ("Aprobar por escrito la parametrización de límites y probar la superación por suma acumulada", "Equipo Systems y negocio"),
    "IT4.8": ("Diseñar la reconciliación entre solicitudes elegibles, enviadas, ejecutadas y contabilizadas", "Equipo Systems"),
}

ESTADO_RCS = {
    "lista": "Cubierto",
    "parcial": "Parcial",
    "falta": "Pendiente",
    "otro dueño": "De otro equipo",
}


def build_rss(flujo: str) -> str:
    """Edicion funcional para RCS, recortada a un flujo: capitulos de control (2 a 7 del guion)."""
    f = FLUJOS[flujo]
    hoy = date.today().strftime("%d/%m/%Y")
    est = estados_por_control()
    P = DOCS / "PLAN_DE_PRUEBAS_IA.md"
    G = DOCS / "GOBIERNO_Y_OPERACION_IA.md"
    A = DOCS / "AUTONOMIA_E_INTEGRIDAD.md"
    T = DOCS / "TRAZAS_DATOS_SENSIBLES.md"

    L: list[str] = []
    w = L.append

    def control(cid: str, titulo: str, cuerpo: str, evidencias: str) -> None:
        e = est.get(cid, {})
        w(f"### {cid} · {titulo}")
        w("")
        if e.get("exige"):
            w(f"**Qué pide el control.** {desteknificar(neutralizar_otros_flujos(e['exige'], flujo))}.")
            w("")
        w(cuerpo.strip())
        w("")
        w(f"**Evidencia.** {evidencias}")
        w("")
        estado = ESTADO_RCS.get(e.get("estado", ""), "Por determinar")
        falta, dueno = PENDIENTES.get(cid, ("", ""))
        w(f"**Estado.** {estado}" + (f". Falta: {falta.lower()}, a cargo de: {dueno.lower()}." if falta else "."))
        w("")

    w(f"# Agente PQRS · Trámite de {f['nombre']}")
    w("")
    w(f"## Informe de controles para RCS · capítulos de control · {hoy}")
    w("")
    w("> Edición funcional generada a partir de los documentos de control del equipo técnico.")
    w("> Las referencias tipo T01 remiten al índice de evidencias.")
    w("")

    # ---------------------------------------------------------------- capitulo 3
    w("## 3. Cómo se evalúa el trámite")
    w("")
    c = f["casos"]
    w(f"El banco de casos de este trámite tiene {sum(c.values())} casos que se ejecutan contra el asistente")
    w("desplegado y publican su resultado en los tableros de analítica.")
    w("")
    w("| Banco de casos | Casos | Qué comprueba |")
    w("|---|---|---|")
    w(f"| Ruteo del trámite | {c['ruteo']} | Que la intención llegue aquí y que los trámites vecinos no caigan aquí |")
    w(f"| Adversariales | {c['adversarial']} | Inyección, manipulación del ruteo, evasión, manipulación del contexto, fuga de información y capacidades no autorizadas |")
    w(f"| Bypass del trámite | {c['bypass']} | Intentos de saltarse paradas, forzar acciones y usar productos de otra persona |")
    w(f"| Respuestas ancladas a la fuente | {c['grounding']} | Que el asistente no invente |")
    w(f"| Vigilancia continua | {c['canario']} | Las rutas críticas, cada 30 minutos, en operación |")
    w("")
    control("IT1.1", "Plan y alcance de las pruebas",
            "El plan cubre el asistente y los servicios que ejecutan sus acciones. Estos son los componentes "
            "evaluados, del más interpretativo al más determinista:\n\n" + tabla_componentes() +
            "\n\nUmbrales de aceptación:\n\n" + tabla_metricas() +
            "\n\nUn cambio se acepta comparando caso a caso contra la ejecución anterior, no solo por el "
            "porcentaje global. En los casos de frontera que oscilan entre ejecuciones se toma la mayoría de tres.",
            "T13 para la precisión alcanzada; el plan firmado es la evidencia documental.")
    control("IT1.2", "Evaluación funcional del trámite",
            "El banco de ruteo contrasta la intención del cliente contra este trámite y contra sus vecinos, "
            "con frases literales, paráfrasis y casos de frontera. Cada ejecución publica un resultado por caso, "
            "y el tablero muestra la precisión, los fallos por tipología y el tiempo de respuesta.",
            "T13 y T14.")
    control("IT1.3", "Evaluación de las respuestas generadas",
            "Se comprueban los cuatro puntos donde el asistente redacta o interpreta: el saludo con el nombre del "
            "cliente, el cierre de las guías, la aclaración cuando la intención es ambigua y la lectura de la fecha. "
            "Cada caso declara lo que la respuesta debe contener y lo que no puede afirmar sin respaldo, y el "
            "asistente registra quién redactó cada texto. La redacción libre de cierre está apagada.",
            "T02, T03 y T15.")
    control("IT1.4", "Pruebas adversariales",
            "Las seis categorías exigidas se cubren con casos propios, más conversaciones de varios turnos que "
            "intentan forzar el trámite. La evaluación distingue tres fallos graves: revelar contenido prohibido, "
            "terminar en un paso que no correspondía y entrar en un trámite vedado.",
            "T07, T08 y T16.")
    control("IT1.5", "Cierre de las pruebas",
            "Los hallazgos de la evaluación se registran con severidad, dueño, estado y la prueba de cierre. El único "
            "hallazgo crítico, que era la presencia de datos sensibles en los registros, está corregido y verificado.",
            "T22 y el registro de hallazgos.")
    control("IT1.6", "Trazabilidad de la versión evaluada",
            "Cada ejecución del banco de casos queda marcada con la versión evaluada, y de cada versión existe una "
            "ficha con el modelo, los portones, el catálogo de rutas y los bancos de casos. La correspondencia con lo "
            "desplegado se comprueba cruzando esa ficha con las versiones en ejecución.",
            "T19 y T25.")

    # ---------------------------------------------------------------- capitulo 4
    w("## 4. Cómo se vigila en operación")
    w("")
    control("IT2.1", "Gobierno y operación",
            "Cada pieza que influye en el comportamiento del asistente tiene un dueño que propone y un "
            "responsable que aprueba:\n\n" + tabla_roles(),
            "El procedimiento de gobierno firmado es la evidencia documental.")
    control("IT2.2", "Inventario y configuración",
            cuerpo_inventario(),
            "T25 y T26.")
    control("IT2.3", "Esquema de monitoreo",
            "La vigilancia tiene cinco relojes, con responsable y umbral:\n\n" + tabla_monitoreo(),
            "T18 y T27.")
    control("IT2.4", "Gestión de cambios",
            cuerpo_cambios(),
            "La matriz de cambios del procedimiento de gobierno.")
    control("IT2.5", "Gobierno del catálogo de conocimiento",
            cuerpo_catalogo(),
            "El historial de versiones del catálogo de rutas.")
    control("IT2.6", "Contingencia",
            cuerpo_contingencia(),
            "T21.")
    control("IT2.7", "Revisión periódica",
            "La revisión periódica automática es la vigilancia continua cada 30 minutos y el resumen de cada "
            "ejecución, con sus alertas. Hoy están construidas y en pausa, a la espera de la aprobación de costo.",
            "T17.")

    # ---------------------------------------------------------------- capitulo 5
    w("## 5. Cómo se protegen los datos")
    w("")
    control("IT3.1", "Mapa de datos del trámite",
            "El trámite recibe del cliente lo que escribe en la conversación, y del banco los productos, los "
            "movimientos y los datos de contacto del cliente. Lo que se guarda son la conversación, la ficha del caso "
            "y los registros técnicos, todos con los datos sensibles enmascarados.",
            "T22 y T24.")
    control("IT3.2", "Minimización y enmascarado",
            cuerpo_minimizacion(),
            "T22.")
    control("IT3.3", "Aislamiento entre clientes",
            cuerpo_aislamiento(),
            "T11.")
    control("IT3.4", "Exposición de datos por manipulación conversacional",
            "La categoría de fuga de información del banco adversarial reúne los intentos de reconstruir datos del "
            "cliente o del sistema mediante la conversación.",
            "T16.")
    control("IT3.5", "Controles de entrada y salida",
            "El control tiene dos capas: un filtro de patrones que no usa el modelo y un juez de alcance que sí lo "
            "usa, activo en el ambiente evaluado. La categoría de evasión del banco adversarial intenta sortearlas.",
            "T07 y T08.")
    control("IT3.6", "Persistencia sin datos sensibles",
            cuerpo_persistencia(),
            "T22 y T24.")
    control("IT3.7", "Remediación y verificación",
            cuerpo_remediacion(),
            "T22.")

    # ---------------------------------------------------------------- capitulo 6
    w("## 6. Qué no puede hacer el asistente por su cuenta")
    w("")
    control("IT4.1", "Arquitectura del trámite",
            "La arquitectura está en el diseño técnico del servicio y en el documento de arquitectura del equipo.",
            "Documentos de arquitectura enlazados en la tabla de control.")
    control("IT4.2", "Restricción de capacidades",
            "La frontera del diseño es que el modelo entiende e interpreta, pero nunca ejecuta:\n\n" +
            tabla_modelo_vs_regla() + "\n\n" +
            f"La lista de acciones permitidas del asistente está generada de la definición del trámite y verificada "
            f"por prueba automática. De todas ellas, {f['acciones']} tienen efecto sobre el cliente o sus productos, y "
            f"cada una exige que el cliente haya pasado por todas sus paradas obligatorias. No existe ningún atajo "
            f"hacia esas acciones.",
            "T01.")
    control("IT4.3", "Pruebas de bypass",
            "Las conversaciones de bypass intentan saltarse paradas, forzar un bloqueo o una devolución, cambiar de "
            "producto y usar el producto de otra persona. La evaluación marca como fallo grave que la conversación "
            "termine en un paso que no correspondía.",
            "T09, T10, T11 y T16.")
    control("IT4.4", "Idempotencia",
            cuerpo_idempotencia(flujo),
            "T12 y T28.")
    control("IT4.5", "Fallos parciales",
            "Ante un tiempo de espera agotado o una respuesta perdida, el trámite se detiene y deriva, en lugar de "
            "reintentar la acción. Un candado impide que una acción ya ejecutada se repita.",
            "T10 y T28.")
    control("IT4.6", "Límites antifraude",
            tabla_limites(flujo),
            "T05 y T06.")
    control("IT4.7", "Trazabilidad de un caso",
            "Un caso se reconstruye de punta a punta: quién lo abrió, qué pidió en cada turno, qué reglas se "
            "aplicaron, qué acción se ejecutó y con qué resultado.",
            "T20 y T23.")
    control("IT4.8", "Reconciliación",
            "Las solicitudes registradas se entregan al proceso de reintegro con una huella única por transacción, "
            "que evita duplicados. El cruce entre solicitudes elegibles, enviadas, ejecutadas y contabilizadas está "
            "pendiente de diseño.",
            "T28.")

    # ---------------------------------------------------------------- capitulo 7
    w("## 7. Pendientes y decisiones")
    w("")
    w("| Control | Qué falta | Quién lo cierra | Estado |")
    w("|---|---|---|---|")
    for cid, e in sorted(est.items()):
        if e["estado"] in ("parcial", "falta", "otro dueño"):
            falta, dueno = PENDIENTES.get(cid, ("Por determinar", "Por asignar"))
            w(f"| {cid} | {falta} | {dueno} | {ESTADO_RCS.get(e['estado'], e['estado'])} |")
    w("")
    return "\n".join(L)


def to_html(md_text: str) -> str:
    import markdown  # python-markdown

    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    style = ("<style>body{font-family:Arial,Helvetica,sans-serif;font-size:11pt;color:#1a1a1a;max-width:900px;margin:0 auto}"
             "h1{color:#072146;font-size:20pt}h2{color:#1464a5;font-size:15pt;border-bottom:1px solid #d3d3d3;padding-bottom:4px}"
             "h3{color:#072146;font-size:12.5pt}h4{font-size:11.5pt}table{border-collapse:collapse;width:100%;font-size:9.5pt;margin:8px 0}"
             "th{background:#1464a5;color:#fff;text-align:left;padding:5px 7px}td{border:1px solid #d3d3d3;padding:4px 7px;vertical-align:top}"
             "code{font-family:Consolas,monospace;font-size:9.5pt;background:#f2f4f7}</style>")
    return f"<html><head><meta charset='utf-8'><title>Informe técnico de evaluación y controles IA</title>{style}</head><body>{body}</body></html>"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive", type=Path, help="escribe ademas una edicion compacta HTML para Google Docs")
    ap.add_argument("--rss", action="store_true", help="edicion funcional para RCS, sin rutas ni nombres tecnicos")
    ap.add_argument("--flujo", choices=sorted(FLUJOS), help="recorta el contenido a un solo tramite")
    args = ap.parse_args()
    if args.rss:
        if not args.flujo:
            raise SystemExit("--rss exige --flujo (la edicion funcional se entrega por tramite)")
        texto = build_rss(args.flujo)
        out_md = DOCS / f"INFORME_RCS_{args.flujo}.md"
        out_html = out_md.with_suffix(".html")
        out_md.write_text(texto, encoding="utf-8")
        out_html.write_text(to_html(texto), encoding="utf-8")
        print(f"{out_md.relative_to(ROOT)} ({len(texto)//1024} KB) y .html ({out_html.stat().st_size//1024} KB)")
        return
    md_text = build()
    OUT_MD.write_text(md_text, encoding="utf-8")
    OUT_HTML.write_text(to_html(md_text), encoding="utf-8")
    if args.drive:
        h = to_html(build(drive=True))
        h = re.sub(r"\n(?=<(td|th|/tr|tr|/thead|thead|tbody|/tbody|/table)\b)", "", h)
        h = re.sub(r"\n(?=<li>|</ul>|</ol>)", "", h)
        args.drive.write_text(h, encoding="utf-8")
        print(f"edicion Drive: {args.drive} ({args.drive.stat().st_size//1024} KB)")
    print(f"{OUT_MD.relative_to(ROOT)} ({len(md_text)//1024} KB) y .html ({OUT_HTML.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
