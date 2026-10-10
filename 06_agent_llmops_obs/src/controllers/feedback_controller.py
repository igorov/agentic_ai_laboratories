from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.dto.api_entities import FeedbackResponse
from src.repositories.impl.history_repository_impl import HistoryRepositoryImpl
from src.services.feedback_service import FeedbackService, TraceNotFoundError
from src.utils.logger import get_logger

logger = get_logger(__name__)

async def handle_feedback(trace_id: UUID, is_ok: bool, comment: Optional[str], db: Session) -> FeedbackResponse:
    repository = HistoryRepositoryImpl(db)
    service = FeedbackService(repository)

    try:
        updated = await service.register(trace_id=trace_id, is_ok=is_ok, comment=comment)
        return FeedbackResponse(trace_id=updated.trace_id, is_ok=updated.is_ok, comment=updated.feedback_comment)
    except TraceNotFoundError:
        logger.warning(f"Feedback para un trace_id inexistente: {trace_id}")
        raise HTTPException(status_code=404, detail=f"No existe una interacción con trace_id {trace_id}")
    except Exception as exc:
        logger.error(f"Error interno al registrar el feedback: {exc}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")
