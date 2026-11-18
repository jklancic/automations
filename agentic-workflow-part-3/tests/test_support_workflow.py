import json
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest

from demo_common.errors import DemoError
from support_demo.cli import main
from support_demo.models import (
    Assessment,
    Classification,
    RetrievalDecision,
    parse_model,
)
from support_demo.retrieval import FIXTURES, RetrievalStore
from support_demo.workflow import PROJECT, run_ticket

TICKET = json.loads((PROJECT / "inputs" / "answerable.json").read_text())
CLASSIFY = {"product_area": "accounts", "issue_type": "how_to", "urgency": "normal",
            "customer_tier": "premium", "requests_exception": False}
SEARCH = {"action": "search", "tool": "search_knowledge", "query": "reset password"}
FINISH = {"action": "finish_retrieval", "tool": None, "query": None}
ASSESS = {"sufficient": True, "citations": ["KB-RESET"], "summary": "Approved reset instructions cover this ticket."}
DRAFT = {"body": "Select Forgot password on the sign-in page and enter your registered email address. [KB-RESET]",
         "citations": ["KB-RESET"]}
DEFAULT = [CLASSIFY, SEARCH, FINISH, ASSESS, DRAFT]


def run_case(tmp_path, responses=None, *, ticket=None, limit=None, fixtures=FIXTURES):
    path = tmp_path / "ticket.json"
    path.write_text(json.dumps(TICKET if ticket is None else ticket))
    responses = DEFAULT if responses is None else responses
    decide = Mock(side_effect=[json.dumps(value) if isinstance(value, dict) else value for value in responses])
    console = StringIO()
    run = run_ticket(path, decide=decide, output_root=tmp_path / "outputs",
                     max_retrieval_calls=limit, fixtures=fixtures, stream=console)
    return run, decide, console.getvalue()


def stages(decide):
    return [call.args[0] for call in decide.call_args_list]


def trace(run):
    return [json.loads(line) for line in (run.directory / "trace.jsonl").read_text().splitlines()]


def test_answerable_sample_reaches_review_never_send(tmp_path):
    run, decide, console = run_case(tmp_path)
    assert run.result["outcome"] == "draft_for_review"
    assert run.exit_code == 0
    result = run.result["result"]
    assert result["draft"] == DRAFT
    assert result["retrieval_calls"] == 2
    assert result["retrieval_limit"] == 3
    assert result["review_queue"] == {"status": "pending_human_review", "sent": False}
    assert result["sent"] is False and result["simulated"] is True
    assert stages(decide) == ["classify", "retrieve", "retrieve", "assess", "draft"]
    assert "Selected search_knowledge query: reset password" in console
    assert "Finish retrieval early" in console
    assert "No customer message was sent" in console
    assert json.loads((run.directory / "result.json").read_text()) == run.result
    events = trace(run)
    assert list(dict.fromkeys(event["stage"] for event in events)) == [
        "1/read_ticket", "2/classify", "3/retrieve", "4/assess", "5/route", "6/draft", "7/review", "final",
    ]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert {event["owner"] for event in events} == {"CODE", "AI", "TOOL", "RESULT"}


def test_mandatory_escalation_sample_overrides_sufficient_evidence(tmp_path):
    ticket = json.loads((PROJECT / "inputs" / "mandatory-escalation.json").read_text())
    classification = CLASSIFY | {"product_area": "billing", "issue_type": "billing",
                                "customer_tier": "standard", "requests_exception": True}
    search = SEARCH | {"query": "billing refund policy"}
    assessment = ASSESS | {"citations": ["KB-BILLING"]}
    run, decide, _ = run_case(tmp_path, [classification, search, FINISH, assessment], ticket=ticket)
    assert run.result["outcome"] == "escalated"
    result = run.result["result"]
    assert result["escalation"]["reasons"] == ["billing_or_legal", "customer_exception_request"]
    assert result["draft"] is None and result["review_queue"] is None
    assert result["sent"] is False and run.exit_code == 0
    assert "draft" not in stages(decide)


def test_insufficient_documentation_sample(tmp_path):
    ticket = json.loads((PROJECT / "inputs" / "insufficient-documentation.json").read_text())
    classification = CLASSIFY | {"product_area": "workspace", "issue_type": "technical", "customer_tier": "enterprise"}
    assessment = {"sufficient": False, "citations": [], "summary": "No approved offline hardware-key recovery procedure was retrieved."}
    run, decide, _ = run_case(tmp_path, [classification, SEARCH | {"query": "offline hardware recovery"}, FINISH, assessment], ticket=ticket)
    assert run.result["outcome"] == "escalated"
    assert run.result["result"]["escalation"]["reasons"] == ["insufficient_documentation"]
    assert "KB-UNAPPROVED" not in run.result["result"]["retrieved_articles"]
    assert "draft" not in stages(decide)
    docs = decide.call_args_list[-1].args[1]["documents"]
    assert all(doc["approved"] for doc in docs)


@pytest.mark.parametrize("change, reason", [
    ({"issue_type": "legal"}, "billing_or_legal"),
    ({"requests_exception": True}, "customer_exception_request"),
])
def test_policy_escalates_even_when_model_has_an_answer(tmp_path, change, reason):
    run, decide, _ = run_case(tmp_path, [CLASSIFY | change, SEARCH, FINISH, ASSESS])
    assert run.result["outcome"] == "escalated"
    assert reason in run.result["result"]["escalation"]["reasons"]
    assert stages(decide)[-1] == "assess"


def test_refinement_is_bounded_and_budget_can_end_with_sufficient_evidence(tmp_path):
    run, decide, _ = run_case(tmp_path, [CLASSIFY, SEARCH | {"query": "unmatchedterm"}, SEARCH, ASSESS, DRAFT])
    result = run.result["result"]
    assert result["retrieval_calls"] == 3
    assert result["retrieval_budget_exhausted"] is True
    assert run.result["outcome"] == "draft_for_review"
    assert stages(decide) == ["classify", "retrieve", "retrieve", "assess", "draft"]
    contexts = [call.args[1] for call in decide.call_args_list if call.args[0] == "retrieve"]
    assert [context["remaining_tool_calls"] for context in contexts] == [2, 1]
    assert contexts[1]["previous_queries"] == ["unmatchedterm"]


def test_exhausted_budget_without_evidence_escalates(tmp_path):
    insufficient = {"sufficient": False, "citations": [], "summary": "No documentation supports an answer."}
    responses = [CLASSIFY, SEARCH | {"query": "noresultone"}, SEARCH | {"query": "noresulttwo"}, insufficient]
    run, decide, _ = run_case(tmp_path, responses)
    assert run.result["outcome"] == "escalated"
    assert run.result["result"]["escalation"]["reasons"] == ["insufficient_documentation", "retrieval_budget_exhausted"]
    assert run.result["result"]["retrieval_calls"] == 3
    assert "draft" not in stages(decide)


def test_minimum_budget_allows_only_account_lookup(tmp_path):
    insufficient = {"sufficient": False, "citations": [], "summary": "No approved article was retrieved."}
    run, decide, _ = run_case(tmp_path, [CLASSIFY, insufficient], limit=1)
    assert run.result["outcome"] == "escalated"
    assert run.result["result"]["retrieval_calls"] == 1
    assert stages(decide) == ["classify", "assess"]


def test_configurable_budget_allows_third_search(tmp_path):
    run, decide, _ = run_case(tmp_path, [CLASSIFY, SEARCH | {"query": "noresultone"},
                                       SEARCH | {"query": "noresulttwo"}, SEARCH, ASSESS, DRAFT], limit=4)
    assert run.result["outcome"] == "draft_for_review"
    assert run.result["result"]["retrieval_calls"] == 4
    assert stages(decide).count("retrieve") == 3


@pytest.mark.parametrize("change", [
    {"product_area": "shell"}, {"issue_type": "unknown"}, {"urgency": "unbounded"},
    {"customer_tier": "VIP"}, {"requests_exception": "false"}, {"confidence": 0.99},
])
def test_unknown_or_malformed_classification_never_retrieves_or_drafts(tmp_path, change):
    run, decide, _ = run_case(tmp_path, [CLASSIFY | change])
    assert run.exit_code == 1
    assert run.result["result"]["error"]["code"] == "invalid_model_output"
    assert run.result["result"]["retrieval_calls"] == 0
    assert stages(decide) == ["classify"]


@pytest.mark.parametrize("decision", [
    SEARCH | {"tool": "read_file", "query": "/private/secret"},
    SEARCH | {"action": "send_email"}, SEARCH | {"path": "/private/secret"},
    SEARCH | {"query": " "}, FINISH | {"query": "extra"},
    {"action": "search", "tool": "search_knowledge"},
])
def test_ai_cannot_invent_tool_arguments_or_stages(tmp_path, decision):
    run, decide, _ = run_case(tmp_path, [CLASSIFY, decision])
    assert run.exit_code == 1
    assert run.result["result"]["retrieval_calls"] == 1  # Account only.
    assert run.result["result"]["draft"] is None
    assert stages(decide) == ["classify", "retrieve"]


@pytest.mark.parametrize("assessment", [
    ASSESS | {"citations": []}, ASSESS | {"citations": ["KB-MADEUP"]},
    ASSESS | {"citations": ["KB-BILLING"]}, ASSESS | {"citations": ["KB-UNAPPROVED"]},
    ASSESS | {"citations": ["KB-RESET", "KB-RESET"]}, ASSESS | {"confidence": 0.99},
])
def test_invalid_assessment_citations_never_produce_a_draft(tmp_path, assessment):
    run, decide, _ = run_case(tmp_path, [CLASSIFY, SEARCH, FINISH, assessment])
    assert run.exit_code == 1
    assert run.result["result"]["draft"] is None
    assert "draft" not in stages(decide)


@pytest.mark.parametrize("draft", [
    DRAFT | {"citations": []}, DRAFT | {"citations": ["KB-BILLING"]},
    DRAFT | {"body": "Uncited instructions"},
    DRAFT | {"body": "Do this. [KB-MADEUP]"}, DRAFT | {"send": True},
    DRAFT | {"body": DRAFT["body"] + " [KB-MadeUp]"},
    DRAFT | {"body": "Do this. [kb-reset]"},
])
def test_invalid_draft_never_reaches_review(tmp_path, draft):
    run, _, _ = run_case(tmp_path, [CLASSIFY, SEARCH, FINISH, ASSESS, draft])
    assert run.exit_code == 1
    assert run.result["result"]["review_queue"] is None
    assert run.result["result"]["sent"] is False


@pytest.mark.parametrize("name, contents", [
    ("missing.json", None), ("wrong.txt", b"{}"), ("empty.json", b""),
    ("malformed.json", b"{"), ("encoding.json", b"\xff"),
    ("oversized.json", b"x" * 32769), ("schema.json", b"{}"),
    ("extra.json", json.dumps(TICKET | {"send": True}).encode()),
    ("bad-account.json", json.dumps(TICKET | {"account_id": "../../private"}).encode()),
    ("duplicate.json", b'{"id":"A","id":"B"}'),
])
def test_invalid_input_causes_no_ai_call(tmp_path, name, contents):
    path = tmp_path / name
    if contents is not None:
        path.write_bytes(contents)
    decide = Mock()
    run = run_ticket(path, decide=decide, output_root=tmp_path / "outputs", stream=StringIO())
    assert run.exit_code == 1
    assert run.result["result"]["error"]["code"] == "invalid_input"
    decide.assert_not_called()


def test_unreadable_input_causes_no_ai_call(tmp_path, monkeypatch):
    path = tmp_path / "ticket.json"
    path.write_text(json.dumps(TICKET))
    original = Path.open

    def deny_input(self, *args, **kwargs):
        if self == path:
            raise PermissionError("Private filesystem details")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_input)
    decide = Mock()
    run = run_ticket(path, decide=decide, output_root=tmp_path / "outputs", stream=StringIO())
    assert run.exit_code == 1
    decide.assert_not_called()


@pytest.mark.parametrize("corruption", ["malformed", "duplicate_account", "duplicate_article"])
def test_bad_fixtures_fail_without_drafting(tmp_path, corruption):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for source in FIXTURES.glob("*.json"):
        (fixtures / source.name).write_bytes(source.read_bytes())
    if corruption == "malformed":
        (fixtures / "knowledge.json").write_text("not JSON")
    elif corruption == "duplicate_account":
        data = json.loads((fixtures / "accounts.json").read_text())
        data["accounts"].append(data["accounts"][0])
        (fixtures / "accounts.json").write_text(json.dumps(data))
    else:
        data = json.loads((fixtures / "knowledge.json").read_text())
        data["articles"].append(data["articles"][0])
        (fixtures / "knowledge.json").write_text(json.dumps(data))
    run, decide, _ = run_case(tmp_path, [CLASSIFY], fixtures=fixtures)
    assert run.exit_code == 1
    assert run.result["result"]["error"]["code"] == "invalid_reference_data"
    assert stages(decide) == ["classify"]


def test_injected_tool_failure_does_not_retry_or_advance_stages(tmp_path, monkeypatch):
    original = RetrievalStore.call
    calls = []

    def fail_search(self, name, arguments):
        calls.append(name)
        if name == "search_knowledge":
            raise RuntimeError("Private tool failure")
        return original(self, name, arguments)

    monkeypatch.setattr(RetrievalStore, "call", fail_search)
    run, decide, console = run_case(tmp_path, [CLASSIFY, SEARCH])
    assert run.exit_code == 1
    assert calls == ["lookup_account", "search_knowledge"]
    assert stages(decide) == ["classify", "retrieve"]
    assert "Private tool failure" not in console


def test_tier_is_verified_against_authoritative_account(tmp_path):
    run, decide, _ = run_case(tmp_path, [CLASSIFY | {"customer_tier": "standard"}], ticket=TICKET | {"customer_tier": "standard"})
    assert run.exit_code == 1
    assert run.result["result"]["error"]["code"] == "account_tier_mismatch"
    assert stages(decide) == ["classify"]
    assert run.result["result"]["retrieval_calls"] == 1


def test_unknown_account_is_a_tool_failure(tmp_path):
    run, decide, _ = run_case(tmp_path, [CLASSIFY], ticket=TICKET | {"account_id": "ACCT-UNKNOWN"})
    assert run.exit_code == 1
    assert run.result["result"]["error"]["code"] == "unknown_account"
    assert run.result["result"]["retrieval_calls"] == 1
    assert stages(decide) == ["classify"]


def test_fixtures_remain_unchanged_and_runs_do_not_share_business_state(tmp_path):
    snapshot = {path: path.read_bytes() for path in [*FIXTURES.glob("*.json"), *(PROJECT / "inputs").glob("*.json")]}
    first, _, _ = run_case(tmp_path)
    second, _, _ = run_case(tmp_path)
    assert first.directory != second.directory
    assert first.result == second.result
    assert all(path.read_bytes() == previous for path, previous in snapshot.items())


def test_raw_errors_and_credentials_are_not_exposed_or_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROXY_API_KEY", "private-test-key")
    path = tmp_path / "ticket.json"
    path.write_text(json.dumps(TICKET))
    decide = Mock(side_effect=RuntimeError("private-test-key raw SDK payload"))
    console = StringIO()
    run = run_ticket(path, decide=decide, output_root=tmp_path / "outputs", stream=console)
    assert run.exit_code == 1 and decide.call_count == 1
    output = console.getvalue() + (run.directory / "result.json").read_text() + (run.directory / "trace.jsonl").read_text()
    assert "private-test-key" not in output and "raw SDK payload" not in output


def test_model_echoed_credentials_are_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROXY_API_KEY", "private-test-key")
    run, _, console = run_case(tmp_path, [CLASSIFY, SEARCH, FINISH, ASSESS, DRAFT | {"body": DRAFT["body"] + " private-test-key"}])
    output = console + (run.directory / "result.json").read_text() + (run.directory / "trace.jsonl").read_text()
    assert "private-test-key" not in output and "[REDACTED]" in output


def test_cli_missing_configuration_is_nonzero_and_saved(tmp_path, capsys):
    path = tmp_path / "ticket.json"
    path.write_text(json.dumps(TICKET))
    assert main([str(path)], output_root=tmp_path / "outputs") == 1
    assert "Set AI_PROXY_API_KEY and AI_MODEL" in capsys.readouterr().out
    result = json.loads(next((tmp_path / "outputs").glob("*/result.json")).read_text())
    assert result["result"]["error"]["code"] == "missing_configuration"


def test_invalid_budget_is_rejected_before_ai(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPPORT_MAX_RETRIEVAL_CALLS", "0")
    run, decide, _ = run_case(tmp_path)
    assert run.exit_code == 1
    decide.assert_not_called()


def test_artifact_failure_never_claims_saved_result(tmp_path, capsys):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file")
    assert main(["missing.json"], output_root=blocker) == 1
    output = capsys.readouterr().out
    assert "Technical failure" in output and "Artifacts saved" not in output


@pytest.mark.parametrize("schema, payload", [(Classification, "[]"), (RetrievalDecision, "{}"), (Assessment, "not JSON")])
def test_model_payloads_are_structurally_validated(schema, payload):
    with pytest.raises(DemoError):
        parse_model(payload, schema)


@pytest.mark.parametrize("name, arguments", [
    ("read_file", {"path": "/private/secret"}),
    ("lookup_account", {"account_id": "ACCT-202"}),
    ("search_knowledge", {"query": "password", "path": "/private/secret"}),
    ("search_knowledge", {"query": " "}), ("search_knowledge", None),
])
def test_tool_guard_checks_scope_before_invocation(name, arguments):
    store = RetrievalStore("ACCT-101", "accounts", 3)
    with pytest.raises(DemoError, match="scope|scoped"):
        store.call(name, arguments)
    assert store.calls_used == 0


def test_tool_guard_enforces_budget_even_outside_orchestration():
    store = RetrievalStore("ACCT-101", "accounts", 1)
    store.call("lookup_account", {"account_id": "ACCT-101"})
    with pytest.raises(DemoError, match="exhausted"):
        store.call("search_knowledge", {"query": "password"})
    assert store.calls_used == 1


def test_search_never_returns_unapproved_or_cross_area_articles():
    store = RetrievalStore("ACCT-101", "accounts", 3)
    assert store.call("search_knowledge", {"query": "refund"}) == []
    workspace = RetrievalStore("ACCT-303", "workspace", 3)
    docs = workspace.call("search_knowledge", {"query": "offline hardware"})
    assert [doc.id for doc in docs] == ["KB-WORKSPACE"]
    assert all(doc.approved for doc in docs)
