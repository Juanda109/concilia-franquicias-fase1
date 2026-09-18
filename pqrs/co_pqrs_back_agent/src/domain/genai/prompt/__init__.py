from __future__ import annotations

from abc import ABC, abstractmethod


class PromptRepository(ABC):
    def __enter__(self) -> PromptRepository:
        return self

    def __exit__(self, *args):
        self.close()

    @abstractmethod
    def get_prompt(self, template, template_parameters: dict = None):
        pass

    @abstractmethod
    def close(self):
        pass
