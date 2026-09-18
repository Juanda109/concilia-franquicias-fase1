import abc
import logging

log = logging.getLogger(__name__)


class AbstractFileSystemUnitOfWork(abc.ABC):
    _route: str

    @abc.abstractmethod
    def get_file(self, file) -> bytes:
        raise NotImplementedError

    @abc.abstractmethod
    def upload_file(self, file_route: str, name: str = None) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def create_text_file(self, text: str, file: str, encoding: str = "utf-8") -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def list_folder(self, prefix: str) -> list:
        raise NotImplementedError

    @abc.abstractmethod
    def move_file(self, old_file: str, new_file: str, new_route: str = None) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_file(self, file: str) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def move_route(self, route):
        raise NotImplementedError
