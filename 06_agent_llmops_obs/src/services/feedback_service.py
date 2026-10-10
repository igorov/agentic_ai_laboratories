import asyncio
from typing import Optional
from uuid import UUID

from src.dto.history_dto import HistoryDTO
from src.repositories.history_repository import HistoryRepository
from src.services.tracing import anonymize, get_langsmith_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Clave del feedback en LangSmith: se usa en dashboards, filtros y reglas
# (por ejemplo, mandar los runs con user_score = 0 a una annotation queue).
FEEDBACK_KEY = "user_score"


class TraceNotFoundError(Exception):
    """El trace_id no existe en la tabla history."""


class FeedbackService:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repo = repository

    async def register(self, trace_id: UUID, is_ok: bool, comment: Optional[str]) -> HistoryDTO:
        """Guarda el feedback (👍/👎) en la BD y lo envía al trace de LangSmith.

        La BD es la fuente de verdad: si LangSmith falla, solo se registra un
        warning y el request no falla.
        """
        updated = self._repo.update_feedback(str(trace_id), is_ok, comment)
        if updated is None:
            raise TraceNotFoundError(str(trace_id))

        logger.info("Feedback registrado", extra={"trace_id": str(trace_id), "is_ok": is_ok})
        await self._send_to_langsmith(trace_id, is_ok, comment)
        return updated

    @staticmethod
    async def _send_to_langsmith(trace_id: UUID, is_ok: bool, comment: Optional[str]) -> None:
        client = get_langsmith_client()
        if client is None:
            return
        try:
            # El SDK de LangSmith es síncrono: se ejecuta en un hilo para no
            # bloquear el event loop. El comentario se anonimiza igual que el trace.
            await asyncio.to_thread(
                client.create_feedback,
                run_id=trace_id,
                key=FEEDBACK_KEY,
                score=1 if is_ok else 0,
                comment=anonymize(comment) if comment else None,
            )
        except Exception as exc:
            logger.warning(
                "No se pudo enviar el feedback a LangSmith: %s", exc,
                extra={"trace_id": str(trace_id)},
            )
