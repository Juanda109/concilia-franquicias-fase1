"""Pydantic schemas for Strands-based workflow validations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StepOptionClassification(BaseModel):
    """Classification result for a smart-routed workflow step option."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    is_match: bool = Field(
        description="Whether the entry hint clearly maps to one of the available options."
    )
    option_key: str = Field(
        default="",
        description="Key of the matched option when is_match is True.",
    )
    confidence: Literal["high", "medium", "low", "none"] = Field(
        default="none",
        description="Confidence level for the option classification.",
    )
    rationale: str = Field(
        default="",
        description="Brief explanation of why the option was selected.",
    )


class WorkflowAnswerValidation(BaseModel):
    """Structured validation result returned by the Strands workflow agent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    is_valid: bool = Field(
        description="Whether the user answer correctly addresses the current workflow question."
    )
    normalized_answer: str = Field(
        default="",
        description="Normalized answer that should be persisted when the input is valid.",
    )
    captured_data: dict[str, str] = Field(
        default_factory=dict,
        description="Structured data extracted from the user response.",
    )
    validation_reason: str | None = Field(
        default=None,
        description="Short explanation of why the answer is valid or invalid.",
    )
    assistant_message: str = Field(
        default="",
        description="Message that should be sent back to the user when the answer is invalid.",
    )


class WorkflowRoutingDecision(BaseModel):
    """Structured workflow-routing result returned during the start phase."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    is_match: bool = Field(
        description="Whether the user request can be routed to a known workflow."
    )
    general_workflow_key: str = Field(
        default="",
        description="Stable key of the matched general workflow group.",
    )
    workflow: str = Field(
        default="",
        description="Technical identifier of the matched workflow.",
    )
    confidence: Literal["high", "medium", "low", "none"] = Field(
        default="none",
        description="Confidence level for the workflow-routing decision.",
    )
    rationale: str = Field(
        default="",
        description="Short explanation of why the workflow was selected.",
    )
    assistant_message: str = Field(
        default="",
        description=(
            "Friendly user-facing explanation of what was understood and why the "
            "suggested workflow is the best fit."
        ),
    )
    clarification_message: str = Field(
        default="",
        description="Short message to request a clearer user description when there is no confident match.",
    )

class GroupRoutingDecision(BaseModel):
    """Nivel 1: categorias mas probables para la solicitud del usuario."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    group_keys: list[str] = Field(
        default_factory=list,
        description="Claves de las 2 categorias mas probables, la mejor primero.",
    )
    confidence: Literal["high", "medium", "low", "none"] = Field(
        default="none",
        description="Confianza en la seleccion de categoria.",
    )
    rationale: str = Field(
        default="",
        description="Breve explicacion de por que se eligieron esas categorias.",
    )
