"""Exercise complete model-directed paths through the SAP SDK without networking."""

import json
from io import StringIO
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from demo_common.proxy import Settings, complete_json
from incident_agent import ai
from incident_agent.investigation import investigate

PROJECT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("sample, outcome, tool_count", [
    ("deployment-related.json", "concluded", 5),
    ("downstream-dependency.json", "concluded", 4),
    ("inconclusive.json", "insufficient_evidence", 3),
])
def test_complete_paths_use_local_sdk_with_enforced_limits(tmp_path, monkeypatch, agent_cases, sample, outcome, tool_count):
    settings = Settings("http://localhost:6655/openai/v1", "configured-test-model", SecretStr("test-key"), 12, 800)
    responses = iter(agent_cases[sample])
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "test-response", "object": "chat.completion", "created": 0,
            "model": settings.model,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(next(responses))}}],
        })

    def wire(prompt, context):
        return complete_json(prompt, context, settings=settings,
                             http_client=httpx.Client(transport=httpx.MockTransport(respond), trust_env=False))

    monkeypatch.setattr(ai, "complete_json", wire)
    run = investigate(PROJECT / "inputs" / sample, output_root=tmp_path, stream=StringIO())
    assert run.result["outcome"] == outcome
    assert run.result["result"]["tool_calls"] == tool_count
    assert run.result["result"]["model_turns"] == len(agent_cases[sample])
    assert len(requests) == len(agent_cases[sample])
    assert run.result["result"]["action_taken"] is False
    contexts = []
    for request in requests:
        assert str(request.url) == "http://localhost:6655/openai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert set(request.extensions["timeout"].values()) == {12}
        body = json.loads(request.content)
        assert body["max_completion_tokens"] == 800
        assert body["response_format"] == {"type": "json_object"}
        assert "tools" not in body and "functions" not in body
        assert "there is no\npredefined investigation sequence" in body["messages"][0]["content"]
        assert "untrusted data" in body["messages"][0]["content"]
        assert "test-key" not in request.content.decode()
        contexts.append(json.loads(body["messages"][1]["content"]))
    assert contexts[0]["observations"] == []
    assert contexts[0]["remaining_tool_calls"] == 8
    assert contexts[-1]["remaining_tool_calls"] == 8 - tool_count
    assert len(contexts[-1]["observations"]) == tool_count
    assert "METRIC-CHECKOUT-101" not in json.dumps(contexts[0])


def test_native_model_tool_requests_are_rejected_not_executed(tmp_path, monkeypatch):
    settings = Settings("http://localhost:6655/openai/v1", "configured-test-model", SecretStr("test-key"))

    def respond(request):
        return httpx.Response(200, json={
            "id": "test-response", "object": "chat.completion", "created": 0,
            "model": settings.model,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "rollback", "arguments": "{}"}}],
            }}],
        })

    def wire(prompt, context):
        return complete_json(prompt, context, settings=settings,
                             http_client=httpx.Client(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(ai, "complete_json", wire)
    run = investigate(PROJECT / "inputs" / "deployment-related.json", output_root=tmp_path, stream=StringIO())
    assert run.exit_code == 1
    assert run.result["result"]["tool_calls"] == 0
    assert run.result["result"]["error"]["code"] == "incomplete_model_response"
    assert run.result["result"]["action_taken"] is False
