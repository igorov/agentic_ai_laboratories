from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from src.dto.history_dto import HistoryDTO
from src.dto.api_entities import ChatResponse
from src.repositories.history_repository import HistoryRepository
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain.agents import create_agent
import uuid
import json

from src.utils.logger import get_logger
from src.utils.environment import (
    HISTORY_LIMIT,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from src.services.prompts import SYSTEM_PROMPT

logger = get_logger(__name__)

RETRIEVER_TOOL_NAME = "retrieve_documents"

_llm = ChatOpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY)


def build_agent(tools: list):
    """Construye el agente con el conjunto de tools provisto (locales + MCP)."""
    agent = create_agent(
        model=_llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )
    logger.info("Agente creado con %d tool(s): %s", len(tools), [t.name for t in tools])
    return agent

class AgentService:
    def __init__(self, repository: HistoryRepository, agent) -> None:
        self._repo = repository
        self._agent = agent

    async def chat(self, question: str, user: str, session_id: Optional[UUID]) -> ChatResponse:
        logger.info(f"Pregunta entrante de {user}: {question}")
        
        # True si es una nueva sesión (no se proporcionó session_id), False si es una sesión existente
        is_new_session = not session_id
        if is_new_session:
            logger.info("Creando nueva sesión")
            session_id = str(uuid.uuid4())

        # Recuperar el historial de la conversación desde la base de datos
        history_records = [] if is_new_session else self._repo.get_by_session_id(session_id, limit=HISTORY_LIMIT)

        # Construir la lista de mensajes para el agente
        history_messages: List[BaseMessage] = []
        for record in history_records:
            history_messages.append(HumanMessage(content=record.question))
            history_messages.append(AIMessage(content=record.answer))

        # Invocar el agente
        agent_response = await self._agent.ainvoke(
            {"messages": [*history_messages, HumanMessage(content=question)]}
        )
        result = self._parse_agent_response(agent_response)
        retrieved_contexts = self._extract_retrieved_contexts(agent_response)

        # Guardar la interacción en la base de datos
        # Guardar el historial de la conversación en la base de datos
        historyDTO = HistoryDTO(
            trace_id=uuid4(),
            session_id=session_id,
            question=question,
            answer=result["answer"],
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            user=user,
            retrieved_contexts=(
                json.dumps(retrieved_contexts, ensure_ascii=False)
                if retrieved_contexts
                else None
            ),
        )
        self._repo.save(historyDTO)

        return ChatResponse(
            user=user,
            answer=result["answer"],
            session_id=session_id or uuid4(),
            trace_id=uuid4(),
        )

    @staticmethod
    def _extract_retrieved_contexts(agent_response: dict) -> List[Dict[str, Any]]:
        contexts: List[Dict[str, Any]] = []
        for message in agent_response.get("messages", []):
            if isinstance(message, ToolMessage) and message.name == RETRIEVER_TOOL_NAME:
                artifact = getattr(message, "artifact", None)
                if artifact:
                    contexts.extend(artifact)
        return contexts

    @staticmethod
    def _parse_agent_response(agent_response: dict) -> dict:
        messages = agent_response.get("messages", [])
        answer = messages[-1].content if messages else ""

        input_tokens = 0
        output_tokens = 0
        for message in messages:
            usage = getattr(message, "usage_metadata", None)
            if usage:
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)

        return {
            "answer": answer,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }