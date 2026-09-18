# Guardrails de entrada — `co_pqrs_back_agent`

Todo el comportamiento vive en `src/guardrail/`. En el resto del proyecto solo hay
**hooks mínimos** que llaman a este paquete, para poder ajustar/quitar guardrails
sin tocar la lógica del agente.

## Las 3 fases

| Fase | Qué hace | Costo | Resuelve |
|------|----------|-------|----------|
| **1 — scope** | Umbral de confianza sobre la decisión de routing + endurecer el prompt del router | 0 tokens extra (reusa el LLM de routing) | Off-topic ("reserva de restaurante", "hamburguesa") |
| **2 — determinístico** | Filtro por patrones antes de cualquier LLM | 0 tokens | Inyección de prompt / jailbreak, vacío, longitud |
| **3 — LLM-as-judge** | Clasificador semántico de alcance (OPCIONAL, **OFF por defecto**) | 1 llamada LLM en routing | Refuerzo semántico de scope |

## Archivos

```
src/guardrail/
├── __init__.py        # API pública de Fase 1 y 2
├── input_screen.py    # Fase 2: screen_user_input(text) -> str | None
├── scope.py           # Fase 1: accepts_routing(decision), routing_scope_prompt_suffix(), ALLOWED_CONFIDENCE
├── judge.py           # Fase 3: judge_user_message(text), verdict_to_block(), judge_enabled()
└── tests/
    ├── test_input_screen.py   # Fase 2
    ├── test_scope.py          # Fase 1
    └── test_judge.py          # Fase 3 (piezas puras + no-op desactivado)
```

## Qué se tocó en el proyecto (hooks) y dónde

1. **`src/application/chat/chat_service.py`**
   - Imports añadidos:
     ```python
     from guardrail import accepts_routing, screen_user_input
     from guardrail.judge import judge_user_message
     ```
   - `_resolve_assistant_content` (inicio del turno) → **Fase 2**:
     ```python
     block_message = screen_user_input(user_content)
     if block_message:
         return block_message, turn_usage
     ```
   - `_resolve_start_phase` (antes del routing) → **Fase 3**:
     ```python
     judge_block = await judge_user_message(user_content)
     if judge_block:
         conversation.current_step = "start"
         conversation.status = ConversationStatus.ACTIVE
         return judge_block
     ```
   - `_resolve_start_phase` (compuerta de routing) → **Fase 1 (umbral)**:
     ```python
     if accepts_routing(routing_decision):   # antes: if routing_decision.is_match and routing_decision.workflow:
     ```

2. **`src/infrastructure/genai/llm/strands_workflow_agent.py`**
   - Import: `from guardrail import routing_scope_prompt_suffix`
   - `_build_routing_system_prompt` → **Fase 1 (prompt)**: el system prompt ahora termina con `+ routing_scope_prompt_suffix()`.

## Cómo activar / desactivar / ajustar

### Fase 3 (LLM-as-judge) — OPCIONAL
- **Activar**: en `co_pqrs_back_agent/.env` agregar `GUARDRAIL_JUDGE_ENABLED=true` (también vale como variable de entorno del proceso).
- **Desactivar**: poner `false` o quitar la variable. Por defecto está **OFF**, así que sin hacer nada queda solo Fase 1 + 2.
- **Quitarla del todo**: borra en `chat_service.py` la línea `from guardrail.judge import judge_user_message` y el bloque `judge_block = await judge_user_message(...)`. Fase 1 y 2 siguen funcionando.
- Usa el mismo modelo/credenciales del `.env` (`API_KEY`, `ENDPOINT`, `LLM_MODEL`, `SSL_VERIFY`). Es **fail-open**: si el LLM falla, deja pasar y Fase 1 sigue cubriendo scope.

### Fase 1 (scope)
- **Umbral**: `scope.py` → `ALLOWED_CONFIDENCE`. Default `{"high", "medium"}`. Para más estricto: `frozenset({"high"})`.
- **Mensaje/instrucción al router**: `scope.py` → `routing_scope_prompt_suffix()`.

### Fase 2 (determinístico)
- **Patrones / longitud / mensajes**: `input_screen.py` → `_INJECTION_PATTERNS`, `MAX_INPUT_LENGTH`, `_BLOCKED_MESSAGE`, `_INVALID_MESSAGE`.

> Mejorar Fase 1 o 2 **no requiere** tocar `chat_service.py` ni `strands_workflow_agent.py`: solo editas `scope.py` / `input_screen.py`.

## Tests

Ubicados en `src/guardrail/tests/`. Son livianos (no necesitan OpenSearch ni LLM):

```bash
cd co_pqrs_back_agent
PYTHONPATH=src python3 -m unittest discover -s src/guardrail/tests -t src -v
# o con el venv del proyecto:
PYTHONPATH=src uv run python -m unittest discover -s src/guardrail/tests -t src -v
```

- `test_scope.py`: inyecta decisiones de routing (`SimpleNamespace`) y valida el umbral.
- `test_input_screen.py`: valida bloqueo de inyección/vacío/longitud y paso de texto normal.
- `test_judge.py`: valida `verdict_to_block`, `judge_enabled` y que el juez es no-op cuando está desactivado (no prueba la llamada real al LLM).

## Notas y límites conocidos

- Fase 3 corre **solo en la fase de routing** (primer mensaje / re-routing), no en cada paso, para acotar costo.
- Los tokens del juez (Fase 3) se **loguean** pero no se suman al `TokenUsage` del turno (mejora futura).
- El mensaje de fuera-de-alcance es texto. Si el negocio espera "habilitar formulario de PQR" (ver caso CP-005 del set de pruebas), hay que definir ese mensaje/acción de fallback.
