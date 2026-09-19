from abc import ABC, abstractmethod
from typing import List, Optional

from src.dto.history_dto import HistoryDTO


class HistoryRepository(ABC):
    @abstractmethod
    def save(self, history: HistoryDTO) -> HistoryDTO:
        raise NotImplementedError

    @abstractmethod
    def get_by_trace_id(self, trace_id: str) -> Optional[HistoryDTO]:
        raise NotImplementedError

    @abstractmethod
    def get_by_session_id(self, session_id: str, limit: int = 10) -> List[HistoryDTO]:
        raise NotImplementedError

    @abstractmethod
    def get_all_by_session_id(self, session_id: str) -> List[HistoryDTO]:
        raise NotImplementedError

    @abstractmethod
    def get_sessions_by_user(self, user: str) -> List[str]:
        raise NotImplementedError
