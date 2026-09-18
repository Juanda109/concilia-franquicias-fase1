"""Guardrail : alcance (scope) del routing inicial.

Reutiliza la decision del agente de routing (WorkflowRoutingDecision): aplica un
umbral de confianza y aporta la instruccion de alcance al system prompt del
router. No agrega llamadas extra al LLM.s
"""

from __future__ import annotations

# Confianzas aceptadas para enrutar automaticamente.
# Cambiar a frozenset({"high"}) para un modo mas estricto.
ALLOWED_CONFIDENCE: frozenset[str] = frozenset({"high", "medium"})


def accepts_routing(decision) -> bool:
    """True solo si el routing es un match dentro del umbral de confianza."""

    return bool(
        getattr(decision, "is_match", False)
        and getattr(decision, "workflow", "")
        and getattr(decision, "confidence", "none") in ALLOWED_CONFIDENCE
    )


def routing_scope_prompt_suffix() -> str:
    """Instruccion de alcance para anexar al system prompt del router."""

    return (
        "\n\nReglas de alcance (OBLIGATORIAS):\n"
        "- Solo atiendes temas de PQRS y servicios del banco descritos en available_workflows. "
        "Si la solicitud del usuario no corresponde con claridad a ningun workflow del catalogo "
        "(por ejemplo reservas, restaurantes, comida, recetas, clima, deportes, entretenimiento u "
        "otros temas ajenos al banco), responde con is_match=false, deja general_workflow_key y "
        "workflow vacios, usa confidence=none y redacta un clarification_message breve y amable "
        "indicando que solo puedes ayudar con temas del banco e invitando a describir su necesidad.\n"
        "- No fuerces coincidencias. Un saludo, una cortesia o un tema ajeno NUNCA deben enrutarse a "
        "una Pregunta Frecuente (FAQ) ni a ningun otro workflow para 'rellenar' una respuesta.\n"
        "- Solo enruta a 'Preguntas frecuentes' cuando el usuario haga una pregunta conceptual real "
        "sobre reportes o centrales de riesgo; si el mensaje no trata de eso, NO uses una FAQ.\n"
        "- Ante la duda entre responder fuera de alcance o forzar un workflow poco relacionado, "
        "prefiere is_match=false con un clarification_message amable."
    )
