from __future__ import annotations

import abc
from typing import Any


class AbstractLlmUnitOfWork(abc.ABC):
    _model: Any

    def __enter__(self) -> AbstractLlmUnitOfWork:
        return self

    def __exit__(self, *args):
        pass

    @abc.abstractmethod
    def get(self):
        raise NotImplementedError

    @abc.abstractmethod
    def execute_prompt(self, prompt):
        pass
