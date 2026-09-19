from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.dto.history_dto import HistoryDTO
from src.repositories.history_repository import HistoryRepository
from src.repositories.models.history import History


class HistoryRepositoryImpl(HistoryRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def save(self, history: HistoryDTO) -> HistoryDTO:
        model = self._to_model(history)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_dto(model)

    def get_by_trace_id(self, trace_id: str) -> Optional[HistoryDTO]:
        model = self.db.query(History).filter(History.trace_id == trace_id).first()
        return self._to_dto(model) if model else None

    def get_by_session_id(self, session_id: str, limit: int = 10) -> List[HistoryDTO]:
        models = (
            self.db.query(History)
            .filter(History.session_id == session_id)
            .order_by(History.created_at.asc())
            .limit(limit)
            .all()
        )
        return [self._to_dto(model) for model in models]

    def get_all_by_session_id(self, session_id: str) -> List[HistoryDTO]:
        models = (
            self.db.query(History)
            .filter(History.session_id == session_id)
            .order_by(History.created_at.asc())
            .all()
        )
        return [self._to_dto(model) for model in models]

    def get_sessions_by_user(self, user: str) -> List[str]:
        rows = (
            self.db.query(History.session_id)
            .filter(History.user == user)
            .group_by(History.session_id)
            .order_by(func.max(History.created_at).desc())
            .all()
        )
        return [row.session_id for row in rows]

    def _to_dto(self, history: History) -> HistoryDTO:
            return HistoryDTO.model_validate(history)
    
    def _to_model(self, history: HistoryDTO) -> History:
        return History(
            trace_id=history.trace_id,
            session_id=history.session_id,
            question=history.question,
            answer=history.answer,
            user=history.user,
            input_tokens=history.input_tokens,
            output_tokens=history.output_tokens,
            retrieved_contexts=history.retrieved_contexts,
        )