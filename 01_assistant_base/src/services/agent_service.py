from typing import Optional
from uuid import UUID, uuid4

from src.dto.history_dto import HistoryDTO
from src.dto.api_entities import ChatResponse
from src.repositories.history_repository import HistoryRepository

from src.utils.logger import get_logger

logger = get_logger(__name__)

class AgentService:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repo = repository

    async def chat(self, question: str, user: str, session_id: Optional[UUID]) -> ChatResponse:
        logger.info(f"Pregunta entrante de {user}: {question}")
        session_id=session_id or uuid4()

        response = "Respuesta generada por el agente"  # Aquí iría la lógica para generar la respuesta del agente
        logger.info(f"Respuesta a la pregunta: {response}")

        # Guardar la interacción en la base de datos
        # Guardar el historial de la conversación en la base de datos
        historyDTO = HistoryDTO(
            trace_id=uuid4(),
            session_id=session_id,
            question=question,
            answer=response,
            user=user,
        )
        self._repo.save(historyDTO)

        return ChatResponse(
            user=user,
            answer=response,
            session_id=session_id or uuid4(),
            trace_id=uuid4(),
        )
