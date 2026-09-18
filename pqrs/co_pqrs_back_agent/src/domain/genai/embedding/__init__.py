from __future__ import annotations

import abc
from typing import Any


class AbstractEmbeddingUnitOfWork(abc.ABC):
    _embedding: Any

    def __enter__(self) -> AbstractEmbeddingUnitOfWork:
        return self

    def __exit__(self, *args):
        pass

    @abc.abstractmethod
    def get(self):
        raise NotImplementedError

    @abc.abstractmethod
    def execute_embedding(self, text, input_model_name=None):
        raise NotImplementedError
