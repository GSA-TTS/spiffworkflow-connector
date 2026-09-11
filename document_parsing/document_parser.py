from abc import ABC, abstractmethod
from typing import Any


class DocumentParser[T](ABC):
    def __init__(self, document: T) -> None:
        self.document = document

    @abstractmethod
    def extract_data(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def populate_document(self, data: dict[str, Any]) -> T:
        pass
