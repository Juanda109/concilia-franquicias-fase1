"""
Workflow actions package.

Import workflow-specific action modules here so their decorators execute
during application startup/import.
"""

from application.chat.actions import doble_cobro as _doble_cobro

__all__ = [
    "_doble_cobro",
]
