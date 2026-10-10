from typing import List
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.controllers.chat_controller import handle_chat
from src.controllers.feedback_controller import handle_feedback
from src.controllers.history_controller import handle_get_history, handle_get_sessions_by_user
from src.repositories import get_db
from src.dto.api_entities import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    HistoryItem,
    UserSessionsResponse,
)
from src.utils.environment import APP_VERSION, OPENAI_MODEL, PROMPT_VERSION

chat_router = APIRouter()

@chat_router.post("/api/chat", response_model=ChatResponse, tags=["chat"])
async def chat(request: ChatRequest, http_request: Request, db: Session = Depends(get_db)) -> ChatResponse:
    return await handle_chat(
        question=request.question,
        user=request.user,
        session_id=request.session_id,
        db=db,
        agent=http_request.app.state.agent
    )

@chat_router.get("/api/history/{session_id}", response_model=List[HistoryItem], tags=["history"])
async def get_history(session_id: str, db: Session = Depends(get_db)) -> List[HistoryItem]:
    return await handle_get_history(session_id=session_id, db=db)

@chat_router.get("/api/sessions/{user}", response_model=UserSessionsResponse, tags=["history"])
async def get_sessions_by_user(user: str, db: Session = Depends(get_db)) -> UserSessionsResponse:
    return await handle_get_sessions_by_user(user=user, db=db)

@chat_router.post("/api/feedback", response_model=FeedbackResponse, tags=["feedback"])
async def feedback(request: FeedbackRequest, db: Session = Depends(get_db)) -> FeedbackResponse:
    return await handle_feedback(
        trace_id=request.trace_id,
        is_ok=request.is_ok,
        comment=request.comment,
        db=db,
    )

@chat_router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    # Lo usan el smoke test del CD y la prueba de carga: no toca BD ni LLM.
    return HealthResponse(
        status="ok",
        prompt_version=PROMPT_VERSION,
        model=OPENAI_MODEL,
        app_version=APP_VERSION,
    )
