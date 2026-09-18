"""Guardrails de entrada del agente PQRS.

API publica:
- Fase 1 (scope): accepts_routing, routing_scope_prompt_suffix, ALLOWED_CONFIDENCE
- Fase 2 (deterministico): screen_user_input
"""

from .input_screen import screen_user_input
from .scope import ALLOWED_CONFIDENCE, accepts_routing, routing_scope_prompt_suffix

__all__ = [
    "screen_user_input",
    "accepts_routing",
    "routing_scope_prompt_suffix",
    "ALLOWED_CONFIDENCE",
]
