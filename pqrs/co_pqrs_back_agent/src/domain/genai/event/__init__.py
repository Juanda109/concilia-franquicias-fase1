from __future__ import annotations

import abc
from typing import Any


class AbstractEventUnitOfWork(abc.ABC):
    _embedding: Any

    def __enter__(self) -> AbstractEventUnitOfWork:
        return self

    def __exit__(self, *args):
        pass

    @abc.abstractmethod
    def get(self):
        raise NotImplementedError

    @abc.abstractmethod
    def send_event(self, message: dict, partition_key: str):
        raise NotImplementedError
