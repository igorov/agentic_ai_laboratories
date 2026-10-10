import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    question: str
    user: str
    session_id: Optional[UUID] = None

class ChatResponse(BaseModel):
    user: str
    answer: str
    session_id: UUID
    trace_id: UUID

class HistoryItem(BaseModel):
    question: str
    answer: str
    trace_id: UUID
    session_id: UUID
    user: Optional[str] = None
    retrieved_contexts: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    is_ok: Optional[bool] = None
    feedback_comment: Optional[str] = None

    @field_validator("retrieved_contexts", mode="before")
    @classmethod
    def parse_retrieved_contexts(cls, value: Any) -> Any:
        if isinstance(value, str):
            return json.loads(value) if value else None
        return value

    class Config:
        from_attributes = True

class UserSessionsResponse(BaseModel):
    user: str
    sessions: List[str]


class FeedbackRequest(BaseModel):
    trace_id: UUID
    is_ok: bool
    comment: Optional[str] = Field(default=None, max_length=2000)

class FeedbackResponse(BaseModel):
    trace_id: UUID
    is_ok: bool
    comment: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    prompt_version: str
    model: str
    app_version: str
