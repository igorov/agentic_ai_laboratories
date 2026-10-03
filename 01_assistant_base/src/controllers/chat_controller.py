from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.dto.api_entities import ChatResponse
from src.repositories.impl.history_repository_impl import HistoryRepositoryImpl
from src.services.agent_service import AgentService
from src.utils.logger import get_logger

logger = get_logger(__name__)

async def handle_chat(question: str, user: str, session_id: str, db: Session) -> ChatResponse:
    # Instanciamos las clases concretas y las inyectamos en el servicio
    repository = HistoryRepositoryImpl(db)
    service = AgentService(repository)

    try:
        result = await service.chat(question=question, user=user, session_id=session_id)
        return ChatResponse.model_validate(result)
    except ValidationError as exc:
        logger.error(f"Error de validación en la respuesta del agente: {exc}")
        raise HTTPException(status_code=422, detail=exc.errors())
    except Exception as exc:
        logger.error(f"Error interno al procesar el chat: {exc}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")
