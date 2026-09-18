"""
Registro de acciones del workflow.

Cada acción del workflow se registra por nombre y puede resolverse
en tiempo de ejecución sin agregar nuevos bloques if/elif en
workflow_actions.py.

Ejemplo:

    @register_action("mostrar_productos_activos_dc")
    def mostrar_productos_activos_dc(...):
        ...

El YAML solo conoce el nombre de la acción. No conoce el módulo de
Python ni la implementación que hay detrás de esa acción.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


ActionHandler = Callable[..., Any]

_ACTION_HANDLERS: dict[str, ActionHandler] = {}


def register_action(
    action: str,
) -> Callable[[ActionHandler], ActionHandler]:
    """
    Register a workflow action handler.

    Args:
        action: Action name declared by the workflow YAML.

    Returns:
        Decorator that registers the handler.
    """

    normalized_action = str(action or "").strip()

    if not normalized_action:
        raise ValueError("Action name cannot be empty")

    def decorator(handler: ActionHandler) -> ActionHandler:
        if normalized_action in _ACTION_HANDLERS:
            existing = _ACTION_HANDLERS[normalized_action]

            raise RuntimeError(
                "Workflow action already registered: "
                f"{normalized_action!r}. "
                f"Existing handler={existing!r}, "
                f"new handler={handler!r}"
            )

        _ACTION_HANDLERS[normalized_action] = handler

        return handler

    return decorator


def get_action_handler(
    action: str | None,
) -> ActionHandler | None:
    """
    Resolve an action handler by its YAML action name.

    Args:
        action: Action name.

    Returns:
        Registered handler or None when no handler exists.
    """

    normalized_action = str(action or "").strip()

    if not normalized_action:
        return None

    return _ACTION_HANDLERS.get(normalized_action)


def is_action_registered(
    action: str | None,
) -> bool:
    """
    Return whether an action has been registered.
    """

    return get_action_handler(action) is not None


def registered_actions() -> tuple[str, ...]:
    """
    Return all currently registered action names.

    Useful for diagnostics and tests.
    """

    return tuple(sorted(_ACTION_HANDLERS))
