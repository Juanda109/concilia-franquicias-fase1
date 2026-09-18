"""Pydantic schemas for workflow catalog definitions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowSelectorOption(BaseModel):
    """Workflow option exposed in the initial greeting."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(description="Stable key used to match a workflow selection.")
    label: str = Field(description="User-facing label shown by the agent.")
    description: str | None = Field(
        default=None,
        description="Short description used to explain or route the workflow.",
    )
    examples: list[str] = Field(
        default_factory=list,
        description="Optional examples of user requests that should map to this workflow.",
    )
    no_usar: str | None = Field(
        default=None,
        description="When NOT to route here and where to route instead (disambiguation boundary).",
    )
    se_confunde_con: str | None = Field(
        default=None,
        description="Neighbouring workflows this one is often confused with.",
    )
    preconditions: str | None = Field(
        default=None,
        description="Preconditions/intent signals that must hold to route to this workflow.",
    )
    contraejemplos: list[str] = Field(
        default_factory=list,
        description="Negative examples: phrases that look similar but must NOT map here.",
    )
    workflow: str = Field(
        description="Workflow associated with the selected option."
    )


class WorkflowSelectorGroup(BaseModel):
    """Top-level business group that contains a set of workflows."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(description="Stable key used to match the general workflow.")
    label: str = Field(description="User-facing label shown for the general workflow.")
    message: str = Field(
        description="Message shown before listing the workflows available in the group."
    )
    routing_criteria: str | None = Field(
        default=None,
        description="Group-level routing criteria used to disambiguate between similar categories.",
    )
    limit_category: str | None = Field(
        default=None,
        description=(
            "Daily-interaction limit category this group belongs to (e.g. 'centrales' "
            "or 'general'). Used by the per-category daily cap. Defaults to 'general' "
            "when unset."
        ),
    )
    options: list[WorkflowSelectorOption] = Field(
        default_factory=list,
        description="Workflows available inside the selected general workflow.",
    )


class WorkflowPrompt(BaseModel):
    """Welcome prompt and available general workflow groups."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(description="Initial greeting sent by the assistant.")
    groups: list[WorkflowSelectorGroup] = Field(
        default_factory=list,
        description="List of available general workflows that the user can choose from.",
    )


class WorkflowStepOption(BaseModel):
    """Available option for a workflow choice step."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(description="Stable key used to match the user response.")
    label: str = Field(description="User-facing label shown as an available option.")
    next_step: str = Field(description="Numeric identifier of the next workflow step.")


class WorkflowStep(BaseModel):
    """Single numbered step in a workflow decision tree."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(description="Question or message sent to the user.")
    action: str | None = Field(
        default=None,
        description=(
            "Optional technical action identifier associated with the step. "
            "It can be used in the future to trigger business logic for guide flows."
        ),
    )
    input_type: Literal["choice", "text", "date", "number", "multi_select", "terminal"] = Field(
        description="Type of input expected from the user."
    )
    save_as: str | None = Field(
        default=None,
        description="Conversation answer key used to persist the user response.",
    )
    next_step: str | None = Field(
        default=None,
        description="Default next step when the current step does not branch by options.",
    )
    options: list[WorkflowStepOption] = Field(
        default_factory=list,
        description="List of available options when the step expects a choice.",
    )
    terminal: bool = Field(
        default=False,
        description="Whether this step closes the workflow.",
    )
    smart_route: bool = Field(
        default=False,
        description=(
            "When True, the engine tries to auto-select an option using the conversation "
            "entry hint before showing the choice menu to the user."
        ),
    )


class WorkflowDefinition(BaseModel):
    """Workflow definition loaded from the YAML catalog."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: int = Field(description="Workflow definition version.")
    start_step: str = Field(description="First numbered step after workflow selection.")
    steps: dict[str, WorkflowStep] = Field(
        default_factory=dict,
        description="Mapping of numeric step identifiers to workflow steps.",
    )


class WorkflowCatalog(BaseModel):
    """Full workflow catalog loaded from the YAML file."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    welcome: WorkflowPrompt
    flows: dict[str, WorkflowDefinition] = Field(
        default_factory=dict,
        description="Workflow definitions grouped by business workflow.",
    )


class WorkflowRoutingEntry(BaseModel):
    """Normalized workflow metadata used during the initial routing stage."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    general_workflow_key: str = Field(
        description="Stable key of the general workflow group."
    )
    general_workflow_label: str = Field(
        description="User-facing label of the general workflow group."
    )
    routing_criteria: str | None = Field(
        default=None,
        description="Group-level routing criteria used to disambiguate between similar categories.",
    )
    workflow: str = Field(description="Technical workflow identifier.")
    workflow_label: str = Field(description="User-facing workflow label.")
    description: str = Field(description="Short summary of what the workflow resolves.")
    examples: list[str] = Field(
        default_factory=list,
        description="Example phrases that should map to the workflow.",
    )
    steps_preview: list[str] = Field(
        default_factory=list,
        description="High-level preview of the numbered steps configured in the workflow.",
    )
    no_usar: str | None = Field(
        default=None,
        description="When NOT to route here and where to route instead (disambiguation boundary).",
    )
    se_confunde_con: str | None = Field(
        default=None,
        description="Neighbouring workflows this one is often confused with.",
    )
    preconditions: str | None = Field(
        default=None,
        description="Preconditions/intent signals that must hold to route to this workflow.",
    )
    contraejemplos: list[str] = Field(
        default_factory=list,
        description="Negative examples: phrases that look similar but must NOT map here.",
    )


class WorkflowGeneralCatalog(BaseModel):
    """General workflow selector catalog loaded from `general.yml`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    welcome: WorkflowPrompt
