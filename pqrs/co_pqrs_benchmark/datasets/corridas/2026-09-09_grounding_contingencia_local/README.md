# Corrida: grounding en contingencia (local, 9-sep-2026)

- Agente local con `LOCAL_CONTINGENCY_MODE=true` (sin LLM) y `LLM_CLOSURE_ENABLED=false`
  (valor por defecto): los cierres son el texto aprobado del YAML y el router no redacta
  aclaraciones. back_data con `LOCAL_IDENTITY_CSV=identidad_grounding` (nombres de pila).
- Dataset `datasets/grounding.json` (23 casos), `BENCHMARK_SOURCE=grounding`,
  `BENCHMARK_MAX_TURNS=12`, `RUN_NAME=grounding-contingencia-local`, 24 eventos publicados.
- Resultado: **13/23 = 56,5 %**. Fallos: 5 de ruteo, 1 `invented`, 4 `grounding`, 0 `leak`.

## Por punto

| Punto | Casos | Fieles | Lectura |
|---|---|---|---|
| saludo | 6 | 5 | Con fuente: nombres de pila sin apellido, en los tres clientes. Sin fuente: plantilla sin nombre, sin artefactos. **Hallazgo**: la persona jurídica recibe "Hola, Inversiones El Roble Sas": la razón social no es un nombre de pila. Decisión de producto pendiente (tratar `personal_type=02` como sin nombre). |
| cierre_guia | 7 | 3 | Límites, puntos y embargos: la fuente está y no hay promesas. 4x1000 y cuota de manejo fallan por **ruteo** del fallback por palabras clave, no por el cierre. Con `LLM_CLOSURE_ENABLED=false`, `response_source` vacío: el texto es el YAML. |
| aclaracion | 5 | 0 | El fallback por palabras clave rutea directo y nunca pide reformular. Con el LLM, si el router responde `is_match=false` el cliente ve el texto determinista de aclaración (el `clarification_message` del modelo no se muestra desde agosto): eso es lo que el caso exige encontrar. |
| validacion_fecha | 5 | 5 | 30/02 y "la semana pasada" y "no me acuerdo" → repregunta con el formato, sin corregir por su cuenta. 31/12/2099 → "todavía no ha ocurrido", sin consultar movimientos. 05/08/2026 → consulta esa fecha (sin compras para el producto del simulador). Estas validaciones son deterministas en el agente (`_trx_parse_date`, `_trx_fecha_futura`), así que valen con y sin LLM. |

## Qué cambia con el LLM real

Los 5 de ruteo y los 4 de aclaración se miden de verdad con el modelo. Para acreditar el
grounding **generativo** del cierre hay que correr además con `LLM_CLOSURE_ENABLED=true` en el
agente: ahí `response_source=model` y `must_not_invent` vigila promesas y plazos inventados.
