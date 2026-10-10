from src.services import tracing
from src.services.tracing import anonymize


def test_anonymizer_enmascara_pii_y_secretos():
    data = {
        "messages": [
            {"content": "Mi DNI es 45678912, mi correo ana.perez@mail.com y mi celular 987654321"},
            {"content": "mi clave es sk-proj-abcdefghijklmnopqrstuvwxyz123456"},
        ]
    }

    masked = anonymize(data)

    first = masked["messages"][0]["content"]
    assert "45678912" not in first and "<DNI>" in first
    assert "ana.perez@mail.com" not in first and "<EMAIL>" in first
    assert "987654321" not in first and "<PHONE>" in first
    assert masked["messages"][1]["content"] == "mi clave es <SECRET>"


def test_anonymizer_no_toca_texto_normal():
    data = {"question": "¿Cuánto dura el programa de Data Engineer?"}
    assert anonymize(data) == {"question": "¿Cuánto dura el programa de Data Engineer?"}


def test_sin_tracing_no_hay_callbacks(monkeypatch):
    monkeypatch.setattr(tracing, "LANGSMITH_TRACING", False)
    assert tracing.get_tracing_callbacks() == []


def test_con_tracing_usa_tracer_con_anonymizer(monkeypatch):
    tracing.get_langsmith_client.cache_clear()
    monkeypatch.setattr(tracing, "LANGSMITH_TRACING", True)
    monkeypatch.setattr(tracing, "LANGSMITH_API_KEY", "lsv2_test")
    try:
        callbacks = tracing.get_tracing_callbacks()
        assert len(callbacks) == 1
        assert callbacks[0].project_name == tracing.LANGSMITH_PROJECT
    finally:
        tracing.get_langsmith_client.cache_clear()
