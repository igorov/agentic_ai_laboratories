from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.controllers.chat_controller import handle_chat
from src.controllers.history_controller import handle_get_history, handle_get_sessions_by_user
from src.repositories import get_db
from src.dto.api_entities import ChatRequest, ChatResponse, HistoryItem, UserSessionsResponse

chat_router = APIRouter()

@chat_router.post("/api/chat", response_model=ChatResponse, tags=["chat"])
async def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    return await handle_chat(
        question=request.question,
        user=request.user,
        session_id=request.session_id,
        db=db,
    )

@chat_router.get("/api/history/{session_id}", response_model=List[HistoryItem], tags=["history"])
async def get_history(session_id: str, db: Session = Depends(get_db)) -> List[HistoryItem]:
    return await handle_get_history(session_id=session_id, db=db)

@chat_router.get("/api/sessions/{user}", response_model=UserSessionsResponse, tags=["history"])
async def get_sessions_by_user(user: str, db: Session = Depends(get_db)) -> UserSessionsResponse:
    return await handle_get_sessions_by_user(user=user, db=db)