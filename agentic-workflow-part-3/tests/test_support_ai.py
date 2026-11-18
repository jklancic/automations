"""Run complete support flows through the installed SAP SDK using in-memory HTTP."""

import json
from io import StringIO

import httpx
import pytest
from pydantic import SecretStr

from demo_common.errors import DemoError
from demo_common.proxy import Settings, complete_json
from support_demo import ai
from support_demo.workflow import PROJECT, run_ticket


@pytest.mark.parametrize("sample, area, issue, tier, exception, query, sufficient, citations, outcome", [
    ("answerable.json", "accounts", "how_to", "premium", False, "reset password", True, ["KB-RESET"], "draft_for_review"),
    ("mandatory-escalation.json", "billing", "billing", "standard", True, "billing refund", True, ["KB-BILLING"], "escalated"),
    ("insufficient-documentation.json", "workspace", "technical", "enterprise", False, "offline hardware", False, [], "escalated"),
])
def test_complete_flow_uses_local_sdk_requests_only(tmp_path, monkeypatch, sample, area, issue, tier, exception, query, sufficient, citations, outcome):
    responses = [
        {"product_area": area, "issue_type": issue, "urgency": "normal", "customer_tier": tier, "requests_exception": exception},
        {"action": "search", "tool": "search_knowledge", "query": query},
        {"action": "finish_retrieval", "tool": None, "query": None},
        {"sufficient": sufficient, "citations": citations, "summary": "Approved evidence covers the request." if sufficient else "No documented recovery procedure."},
    ]
    if outcome == "draft_for_review":
        responses.append({"body": "Select Forgot password and use your registered email address. [KB-RESET]", "citations": citations})
    expected_count = len(responses)
    payloads = iter(responses)
    requests = []
    settings = Settings("http://localhost:6655/openai/v1", "configured-test-model", SecretStr("test-key"), 12, 800)

    def respond(request):
        requests.append(request)
        payload = next(payloads)
        return httpx.Response(200, json={
            "id": "test-completion", "object": "chat.completion", "created": 0,
            "model": settings.model,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(payload)}}],
        })

    def wire_request(prompt, context):
        client = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
        return complete_json(prompt, context, settings=settings, http_client=client)

    monkeypatch.setattr(ai, "complete_json", wire_request)
    run = run_ticket(PROJECT / "inputs" / sample, output_root=tmp_path, stream=StringIO())
    assert run.result["outcome"] == outcome
    assert run.result["result"]["sent"] is False
    assert len(requests) == expected_count
    for request in requests:
        assert str(request.url) == "http://localhost:6655/openai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert set(request.extensions["timeout"].values()) == {12}
        body = json.loads(request.content)
        assert body["max_completion_tokens"] == 800
        assert body["response_format"] == {"type": "json_object"}
        assert "tools" not in body and "functions" not in body
        assert "untrusted ticket and retrieved document data" in body["messages"][0]["content"]
        assert "JSON schema" in body["messages"][0]["content"]
        assert "test-key" not in request.content.decode()
    assessment_context = json.loads(json.loads(requests[3].content)["messages"][1]["content"])
    assert all(doc["approved"] and doc["product_area"] == area for doc in assessment_context["documents"])
    assert run.result["result"]["retrieval_calls"] == 2


def test_ai_request_cannot_select_an_unimplemented_stage():
    with pytest.raises(DemoError, match="permitted support stage"):
        ai.request("send_email", {})
