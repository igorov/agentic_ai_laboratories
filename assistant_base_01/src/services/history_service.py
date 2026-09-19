from typing import List, Optional

from src.repositories.history_repository import HistoryRepository
from src.repositories.models.history import History


class HistoryService:
    def __init__(self, repository: HistoryRepository) -> None:
            self._repo = repository

    def get_by_session(self, session_id: str) -> List[History]:
        return self._repo.get_all_by_session_id(session_id)

    def get_sessions_by_user(self, user: str) -> List[str]:
        return self._repo.get_sessions_by_user(user)

    def get_by_trace_id(self, trace_id: str) -> Optional[History]:
        return self._repo.get_by_trace_id(trace_id)
