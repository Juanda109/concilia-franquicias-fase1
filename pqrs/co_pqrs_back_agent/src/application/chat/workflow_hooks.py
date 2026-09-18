"""Registro genérico de hooks por workflow.

Propósito: evitar que chat_service.py crezca con un if/elif por cada
nuevo workflow. Cada workflow que necesite lógica en Python
(prefetch/precargas o validaciones antes de renderizar un step)
registra su propio hook async aquí, en su propio módulo dentro de
`application/chat/workflows/`.

chat_service solo llama a `get_prefetch_hook(...)`; nunca importa
ni conoce un workflow específico.

Agregar lógica Python para un nuevo workflow = crear un nuevo archivo
dentro de workflows/ + un decorador
`@register_prefetch_hook("mi_workflow")`.

Cero líneas nuevas en chat_service.py.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from domain.conversation.models import Conversation

PrefetchHook = Callable[..., Awaitable[None]]

_PREFETCH_HOOKS: dict[str, PrefetchHook] = {}


def register_prefetch_hook(workflow: str) -> Callable[[PrefetchHook], PrefetchHook]:
    """Decorator: register `fn` as the prefetch hook for `workflow`."""

    def _decorator(fn: PrefetchHook) -> PrefetchHook:
        _PREFETCH_HOOKS[workflow] = fn
        return fn

    return _decorator


def get_prefetch_hook(workflow: str | None) -> PrefetchHook | None:
    return _PREFETCH_HOOKS.get(workflow or "")
