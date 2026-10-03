from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class HistoryDTO(BaseModel):
    trace_id: UUID
    session_id: UUID
    question: str
    answer: str
    user: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    retrieved_contexts: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
