from __future__ import annotations

import abc
from typing import Any


class AbstractPersistenceUnitOfWork(abc.ABC):
    _storage_connection: Any

    def __enter__(self) -> AbstractPersistenceUnitOfWork:
        return self

    def __exit__(self, *args):
        self.close()

    @abc.abstractmethod
    def get_connection(self):
        raise NotImplementedError

    @abc.abstractmethod
    def close(self):
        raise NotImplementedError
