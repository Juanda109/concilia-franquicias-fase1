"""
Dispatcher genérico de acciones del workflow.

El dispatcher resuelve una acción mediante el registro de acciones
(action registry).

No contiene reglas de negocio específicas de ningún workflow.
"""

from __future__ import annotations

import inspect
from typing import Any

from application.chat.actions.registry import get_action_handler
from domain.conversation.models import Conversation
from domain.workflow.models import WorkflowStep
from infrastructure.core.logger import get_logger, log_execution


logger = get_logger(__name__)


@log_execution
def dispatch_workflow_action(
    *,
    conversation: Conversation,
    step: WorkflowStep,
) -> tuple[bool, Any]:
    """
    Dispatch a workflow action through the registry.

    Args:
        conversation:
            Current conversation.

        step:
            Current workflow step.

    Returns:
        Tuple:

            (handled, result)

        handled=True:
            Action was found in the new registry.

        handled=False:
            Action is not registered and should be handled by legacy
            compatibility code.
    """

    action = str(step.action or "").strip()

    if not action:
        return False, None

    handler = get_action_handler(action)

    if handler is None:
        return False, None

    logger.info(
        "Dispatching registered workflow action "
        "conversation_id=%s workflow=%s action=%s handler=%s",
        conversation.conversation_id,
        conversation.workflow,
        action,
        getattr(handler, "__name__", repr(handler)),
    )

    result = handler(
        conversation=conversation,
        step=step,
    )

    if inspect.isawaitable(result):
        raise RuntimeError(
            "Async workflow action handlers are not supported by the "
            "synchronous dispatcher yet. "
            f"action={action!r}"
        )

    return True, result
