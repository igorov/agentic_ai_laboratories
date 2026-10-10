from datetime import datetime
from typing import Optional
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.controllers import feedback_controller
from src.dto.history_dto import HistoryDTO
from src.repositories import get_db
from src.routes.router import chat_router
from src.services import feedback_service
from src.services.feedback_service import FEEDBACK_KEY, FeedbackService, TraceNotFoundError


class FakeHistoryRepository:
    """Repositorio en memoria: solo lo que usa FeedbackService."""

    def __init__(self, existing_trace_ids=()):
        self.rows = {str(t): HistoryDTO(trace_id=t, session_id=uuid4(), question="q", answer="a")
                     for t in existing_trace_ids}

    def update_feedback(self, trace_id: str, is_ok: bool, comment: Optional[str]) -> Optional[HistoryDTO]:
        row = self.rows.get(trace_id)
        if row is None:
            return None
        row.is_ok, row.feedback_comment, row.feedback_at = is_ok, comment, datetime.now()
        return row


@pytest.fixture
def langsmith_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(feedback_service, "get_langsmith_client", lambda: client)
    return client


async def test_register_guarda_en_bd_y_envia_a_langsmith(langsmith_client):
    trace_id = uuid4()
    repo = FakeHistoryRepository([trace_id])

    result = await FeedbackService(repo).register(trace_id, is_ok=False, comment="mi correo es ana@mail.com")

    assert result.is_ok is False
    assert repo.rows[str(trace_id)].feedback_at is not None
    langsmith_client.create_feedback.assert_called_once()
    kwargs = langsmith_client.create_feedback.call_args.kwargs
    assert kwargs["run_id"] == trace_id
    assert kwargs["key"] == FEEDBACK_KEY
    assert kwargs["score"] == 0
    # El comentario viaja a LangSmith anonimizado; en la BD queda tal cual.
    assert kwargs["comment"] == "mi correo es <EMAIL>"
    assert repo.rows[str(trace_id)].feedback_comment == "mi correo es ana@mail.com"


async def test_register_trace_inexistente(langsmith_client):
    with pytest.raises(TraceNotFoundError):
        await FeedbackService(FakeHistoryRepository()).register(uuid4(), is_ok=True, comment=None)
    langsmith_client.create_feedback.assert_not_called()


async def test_register_no_falla_si_langsmith_falla(langsmith_client):
    langsmith_client.create_feedback.side_effect = RuntimeError("LangSmith caído")
    trace_id = uuid4()

    result = await FeedbackService(FakeHistoryRepository([trace_id])).register(trace_id, is_ok=True, comment=None)

    assert result.is_ok is True


async def test_register_sin_langsmith_configurado(monkeypatch):
    monkeypatch.setattr(feedback_service, "get_langsmith_client", lambda: None)
    trace_id = uuid4()

    result = await FeedbackService(FakeHistoryRepository([trace_id])).register(trace_id, is_ok=True, comment=None)

    assert result.is_ok is True


@pytest.fixture
def api(monkeypatch, langsmith_client):
    """App con solo el router: sin lifespan (no construye el agente ni conecta MCP)."""
    existing = uuid4()
    repo = FakeHistoryRepository([existing])
    monkeypatch.setattr(feedback_controller, "HistoryRepositoryImpl", lambda db: repo)

    app = FastAPI()
    app.include_router(chat_router)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app), existing


def test_endpoint_feedback_ok(api):
    client, trace_id = api
    response = client.post("/api/feedback", json={"trace_id": str(trace_id), "is_ok": True})
    assert response.status_code == 200
    assert response.json() == {"trace_id": str(trace_id), "is_ok": True, "comment": None}


def test_endpoint_feedback_404(api):
    client, _ = api
    response = client.post("/api/feedback", json={"trace_id": str(uuid4()), "is_ok": False})
    assert response.status_code == 404


def test_endpoint_feedback_422_sin_is_ok(api):
    client, trace_id = api
    response = client.post("/api/feedback", json={"trace_id": str(trace_id)})
    assert response.status_code == 422


def test_endpoint_health(api):
    client, _ = api
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert {"prompt_version", "model", "app_version"} <= body.keys()
