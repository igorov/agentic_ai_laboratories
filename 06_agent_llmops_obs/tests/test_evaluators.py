from evals.evaluators import guardrail_behavior, tool_selection


def test_guardrail_behavior_bloqueo_esperado():
    assert guardrail_behavior({}, {"blocked": True}, {"expected_behavior": "block"})["score"] == 1
    assert guardrail_behavior({}, {"blocked": False}, {"expected_behavior": "block"})["score"] == 0


def test_guardrail_behavior_falso_positivo():
    assert guardrail_behavior({}, {"blocked": True}, {"expected_behavior": "answer"})["score"] == 0


def test_tool_selection():
    ref = {"expected_tool": "retrieve_documents"}
    assert tool_selection({}, {"tools": ["retrieve_documents"]}, ref)["score"] == 1
    assert tool_selection({}, {"tools": []}, ref)["score"] == 0
    assert tool_selection({}, {"tools": []}, {})["score"] is None
