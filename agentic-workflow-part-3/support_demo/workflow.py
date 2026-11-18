"""Code owns every stage. Only the retrieval stage contains a bounded AI loop."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from demo_common.artifacts import Story
from demo_common.errors import DemoError

from .models import (
    Assessment,
    Classification,
    Draft,
    RetrievalDecision,
    Ticket,
    parse_model,
)
from .retrieval import FIXTURES, RetrievalStore, configured_limit

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT.parent / "outputs"


@dataclass(frozen=True)
class Run:
    result: dict
    directory: Path

    @property
    def exit_code(self):
        return 1 if self.result["outcome"] == "technical_failure" else 0


def read_ticket(path: Path) -> Ticket:
    try:
        if path.suffix.lower() != ".json" or not path.is_file():
            raise ValueError("Not a JSON file")
        with path.open("rb") as handle:
            raw = handle.read(32_769)
        if not raw or len(raw) > 32_768:
            raise ValueError("Empty or oversized ticket")
        return parse_model(raw.decode("utf-8"), Ticket, code="invalid_input")
    except (OSError, UnicodeError, ValueError) as exc:
        raise DemoError("invalid_input", "Select a readable UTF-8 JSON ticket of at most 32 KiB.") from exc


def validate_citations(citations: list[str], allowed: set[str], *, required: bool):
    if ((required and not citations) or len(citations) != len(set(citations))
            or not set(citations).issubset(allowed)):
        raise DemoError("invalid_evidence", "AI citations must identify distinct approved retrieved evidence.")


def escalation_reasons(classification: Classification, assessment: Assessment, *, exhausted: bool):
    reasons = []
    if classification.issue_type in {"billing", "legal"} or classification.product_area == "billing":
        reasons.append("billing_or_legal")
    if classification.requests_exception:
        reasons.append("customer_exception_request")
    if not assessment.sufficient:
        reasons.append("insufficient_documentation")
        if exhausted:
            reasons.append("retrieval_budget_exhausted")
    return reasons


def run_ticket(input_path: Path, *, decide: Callable[[str, dict], str] | None = None,
               output_root: Path = OUTPUT_ROOT, fixtures: Path = FIXTURES,
               max_retrieval_calls: int | None = None, stream: TextIO | None = None) -> Run:
    story = Story(output_root, stream, prefix="support-")
    details = {
        "ticket_id": None, "classification": None, "account": None,
        "retrieved_articles": [], "retrieval_calls": 0,
        "retrieval_limit": None, "retrieval_budget_exhausted": False,
        "assessment": None, "draft": None, "review_queue": None,
        "escalation": None, "simulated": True, "sent": False,
    }
    result = {"approach": "agentic_workflow", "input_reference": str(input_path),
              "outcome": None, "result": details}
    stage = "1/read_ticket"
    store = None
    try:
        story.event("CODE", stage, "Read one local ticket; invalid input is rejected before AI.")
        ticket = read_ticket(input_path)
        details["ticket_id"] = ticket.id
        limit = configured_limit() if max_retrieval_calls is None else max_retrieval_calls
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise DemoError("invalid_configuration", "Retrieval budget must be a positive integer.")
        details["retrieval_limit"] = limit
        if decide is None:
            from .ai import request
            decide = request

        stage = "2/classify"
        story.event("AI", stage, "Classify the ticket at a fixed decision point; AI cannot choose stages.")
        classification = parse_model(decide("classify", {"ticket": ticket.model_dump()}), Classification)
        if classification.customer_tier != ticket.customer_tier:
            raise DemoError("invalid_classification", "AI customer tier does not match the ticket metadata.")
        details["classification"] = classification.model_dump()
        story.event("AI", stage, ", ".join(f"{key}={value}" for key, value in classification.model_dump().items()), classification=classification.model_dump())

        stage = "3/retrieve"
        store = RetrievalStore(ticket.account_id, classification.product_area, limit, fixtures=fixtures)
        story.event("TOOL", stage, f"Call 1/{limit}: code-owned account lookup scoped to {ticket.account_id}.")
        account = store.call("lookup_account", {"account_id": ticket.account_id})
        if account.tier != ticket.customer_tier:
            raise DemoError("account_tier_mismatch", "Ticket tier does not match the authoritative local account.")
        details["account"] = account.model_dump()
        story.event("CODE", stage, f"Verified tier={account.tier}; loaded local history and entitlements.", evidence_reference=f"fixtures/accounts.json#{account.id}")
        documents = {}
        queries = []
        # Unlike invoice extraction, AI chooses queries and can stop this stage.
        # Unlike an agent, it cannot select another stage or tool family.
        while store.remaining > 0:
            context = {
                "ticket": ticket.model_dump(), "classification": classification.model_dump(),
                "account": account.model_dump(), "documents": [doc.model_dump() for doc in documents.values()],
                "previous_queries": list(queries), "remaining_tool_calls": store.remaining,
            }
            story.event("AI", stage, f"Choose a knowledge query or finish retrieval; {store.remaining} tool calls remain.")
            decision = parse_model(decide("retrieve", context), RetrievalDecision)
            if decision.action == "finish_retrieval":
                story.event("AI", stage, "Finish retrieval early; code advances to the fixed assessment stage.")
                break
            queries.append(decision.query)
            story.event("AI", stage, f"Selected search_knowledge query: {decision.query}")
            story.event("TOOL", stage, f"Call {store.calls_used + 1}/{limit}: search approved {classification.product_area} articles only.")
            found = store.call(decision.tool, {"query": decision.query})
            documents.update({doc.id: doc for doc in found})
            ids = [doc.id for doc in found]
            story.event("TOOL", stage, "Retrieved: " + (", ".join(ids) if ids else "no matching approved articles"), evidence_references=ids)
        details["retrieved_articles"] = list(documents)
        exhausted = store.remaining == 0
        if exhausted:
            story.event("CODE", stage, "Retrieval budget reached; no further search or query decision is allowed.")

        stage = "4/assess"
        context = {
            "ticket": ticket.model_dump(), "classification": classification.model_dump(),
            "account": account.model_dump(), "documents": [doc.model_dump() for doc in documents.values()],
        }
        story.event("AI", stage, "Assess evidence sufficiency from retrieved approved documentation, not a confidence score.")
        assessment = parse_model(decide("assess", context), Assessment)
        validate_citations(assessment.citations, set(documents), required=assessment.sufficient)
        details["assessment"] = assessment.model_dump()
        story.event("AI", stage, f"sufficient={assessment.sufficient}; evidence={assessment.citations}; {assessment.summary}", assessment=assessment.model_dump())

        stage = "5/route"
        reasons = escalation_reasons(classification, assessment, exhausted=exhausted)
        if reasons:
            # Even a confident/evidenced model response cannot bypass this branch.
            result["outcome"] = "escalated"
            details["escalation"] = {"reasons": reasons, "status": "pending_human_review"}
            story.event("CODE", stage, "Escalate to simulated human review: " + ", ".join(reasons) + "; do not draft or send.")
        else:
            story.event("CODE", stage, "Evidence and policy permit drafting only; human review remains mandatory.")
            stage = "6/draft"
            story.event("AI", stage, "Draft a response citing assessed evidence; no sending capability is available.")
            draft = parse_model(decide("draft", context | {"assessment": assessment.model_dump()}), Draft)
            validate_citations(draft.citations, set(assessment.citations), required=True)
            inline = set(re.findall(r"\[(KB-[^\]\r\n]+)\]", draft.body, flags=re.IGNORECASE))
            if inline != set(draft.citations):
                raise DemoError("invalid_evidence", "Draft citation markers must match its validated citation list.")
            details["draft"] = draft.model_dump()
            story.event("AI", stage, draft.body, citations=draft.citations)
            stage = "7/review"
            details["review_queue"] = {"status": "pending_human_review", "sent": False}
            result["outcome"] = "draft_for_review"
            story.event("CODE", stage, "Queue the local draft for human review. No customer message was sent.")
    except DemoError as exc:
        result["outcome"] = "technical_failure"
        details["error"] = {"code": exc.code, "message": str(exc), "stage": stage}
    except Exception:  # noqa: BLE001 - never expose raw SDK errors or untrusted payloads
        result["outcome"] = "technical_failure"
        details["error"] = {"code": "execution_failed", "message": "Support execution failed; no message was sent.", "stage": stage}
    finally:
        if store is not None:
            details["retrieval_calls"] = store.calls_used
            details["retrieval_budget_exhausted"] = store.remaining == 0

    message = details.get("error", {}).get("message", result["outcome"])
    story.event("RESULT", "final", message, outcome=result["outcome"])
    return Run(story.result(result), story.directory)
