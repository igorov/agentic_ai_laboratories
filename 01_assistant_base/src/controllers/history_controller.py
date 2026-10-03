from typing import List
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.dto.api_entities import HistoryItem, UserSessionsResponse
from src.repositories.impl.history_repository_impl import HistoryRepositoryImpl
from src.services.history_service import HistoryService
from src.utils.logger import get_logger

logger = get_logger(__name__)

async def handle_get_history(session_id: str, db: Session) -> List[HistoryItem]:
    try:
        UUID(str(session_id))
    except ValueError as exc:
        logger.error(f"session_id inválido: {session_id}")
        raise HTTPException(status_code=422, detail=f"session_id inválido: {exc}")

    repository = HistoryRepositoryImpl(db)
    service = HistoryService(repository)

    try:
        history = service.get_by_session(session_id)
        return [HistoryItem.model_validate(item) for item in history]
    except ValidationError as exc:
        logger.error(f"Error de validación al obtener el historial: {exc}")
        raise HTTPException(status_code=422, detail=exc.errors())
    except Exception as exc:
        logger.error(f"Error interno al obtener el historial: {exc}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

async def handle_get_sessions_by_user(user: str, db: Session) -> UserSessionsResponse:
    repository = HistoryRepositoryImpl(db)
    service = HistoryService(repository)

    try:
        sessions = service.get_sessions_by_user(user)
        return UserSessionsResponse.model_validate(
            {"user": user, "sessions": [str(session_id) for session_id in sessions]}
        )
    except ValidationError as exc:
        logger.error(f"Error de validación al obtener las sesiones del usuario: {exc}")
        raise HTTPException(status_code=422, detail=exc.errors())
    except Exception as exc:
        logger.error(f"Error interno al obtener las sesiones del usuario: {exc}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")
