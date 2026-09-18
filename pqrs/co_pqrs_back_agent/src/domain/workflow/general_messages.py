"""Shared general message catalog for start and control flow prompts."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from infrastructure.entrypoint.api.errors.exceptions import ConfigurationError


class GeneralMessages(BaseModel):
    """Reusable shared messages used outside the numbered workflow YAMLs."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start_greeting_template: str = Field(
        description="Greeting template used by POST /start."
    )
    start_greeting_template_no_name: str = Field(
        description=(
            "Greeting used by POST /start when the customer given name cannot be "
            "resolved (no 'cliente' placeholder). UX-reviewable."
        )
    )
    workflow_confirmation_suffix: str = Field(
        description="Message shown after the start-phase routing explanation."
    )
    routing_clarification_template: str = Field(
        description="Clarification message shown when routing cannot infer a workflow."
    )
    routing_clarification_messages: list[str] = Field(
        default_factory=list,
        description=(
            "Random pool of clarification messages shown when routing finds no "
            "workflow match (in-scope bank topic not supported). If empty, "
            "routing_clarification_template is used."
        ),
    )
    routing_retry_messages: list[str] = Field(
        default_factory=list,
        description=(
            "Random pool asking the customer to rephrase on the FIRST routing "
            "no-match, before escalating to the PQRS form. Tone: ask for more "
            "detail, never reject the topic. If empty, "
            "routing_clarification_messages is used."
        ),
    )
    unintelligible_input_messages: list[str] = Field(
        default_factory=list,
        description=(
            "Random pool for input with no interpretable words ('9+', '...'). "
            "If empty, routing_retry_messages is used."
        ),
    )
    confirmation_hints: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Frase natural por workflow_id para la confirmación de candidato "
            "ambiguo (confidence=low): '¿Te refieres a {hint}?'. Si falta, se usa "
            "el label del catálogo."
        ),
    )
    repeated_flow_warning_template: str = Field(
        description="Message shown when the client repeats a recently used flow."
    )
    repeated_flow_continue_message: str = Field(
        description="Message shown when the client wants to continue with a different request."
    )
    repeated_flow_decline_message: str = Field(
        description="Message shown when the client does not want to continue."
    )
    daily_session_limit_message: str = Field(
        description=(
            "Formal message shown at POST /start when the client reached the daily "
            "session limit (Layer A). UX-reviewable."
        )
    )
    repeat_flow_recheck_exhausted_message: str = Field(
        description=(
            "Formal message shown when the client exhausted the repeat-flow re-checks "
            "for the day (Layer B). UX-reviewable."
        )
    )
    satisfaction_questions: list[str] = Field(
        description="Random questions used in the satisfaction check step."
    )
    satisfaction_si_messages: list[str] = Field(
        description="Random closing messages when the customer confirms the info was helpful."
    )
    satisfaction_no_messages: list[str] = Field(
        description="Random closing messages when the customer says the info was not helpful."
    )


def load_general_messages(messages_path: str | Path | None = None) -> GeneralMessages:
    """Load the shared message catalog from the workflow directory."""

    path = (
        Path(messages_path)
        if messages_path is not None
        else Path(__file__).with_name("general_messages.yml")
    )

    if not path.exists():
        raise ConfigurationError(
            "General message catalog file not found.",
            details={"messages_path": str(path)},
        )

    raw_messages = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw_messages, dict):
        raise ConfigurationError(
            "General message catalog file is invalid.",
            details={"messages_path": str(path)},
        )

    return GeneralMessages.model_validate(raw_messages)
