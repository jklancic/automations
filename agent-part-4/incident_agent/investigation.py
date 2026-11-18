"""A model-directed observe/act loop, with no predefined investigation path."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from demo_common.artifacts import Story
from demo_common.errors import DemoError

from .governor import BudgetReached, Governor, Limits
from .models import Alert, Decision, parse_model
from .tools import SNAPSHOT_PATH, TOOL_DESCRIPTIONS, LocalTools, load_snapshot

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "outputs"


@dataclass(frozen=True)
class Run:
    result: dict
    directory: Path

    @property
    def exit_code(self):
        return 1 if self.result["outcome"] == "technical_failure" else 0


def read_alert(path: Path) -> Alert:
    try:
        if path.suffix.lower() != ".json" or not path.is_file():
            raise ValueError("Not a JSON file")
        with path.open("rb") as handle:
            raw = handle.read(32_769)
        if not raw or len(raw) > 32_768:
            raise ValueError("Empty or oversized alert")
        return parse_model(raw.decode("utf-8"), Alert, code="invalid_input")
    except (OSError, UnicodeError, ValueError) as exc:
        raise DemoError("invalid_input", "Select a readable UTF-8 JSON alert of at most 32 KiB.") from exc


def investigate(input_path: Path, *, decide: Callable[[dict], str] | None = None,
                output_root: Path = OUTPUT_ROOT, snapshot_path: Path = SNAPSHOT_PATH,
                limits: Limits | None = None, stream: TextIO | None = None) -> Run:
    story = Story(output_root, stream, prefix="incident-")
    details = {
        "alert_id": None, "hypothesis": None, "evidence": [], "confidence": "low",
        "recommended_action": "Request human investigation before any production action.",
        "unresolved_questions": [], "observations": [], "model_turns": 0, "tool_calls": 0,
        "limits": None, "scope": None, "read_only": True, "simulated": True, "action_taken": False,
    }
    result = {"approach": "agent", "input_reference": str(input_path), "outcome": None, "result": details}
    stage = "1/read_alert"
    governor = None
    try:
        story.event("CODE", stage, "Read one local alert; reject invalid input before AI.")
        alert = read_alert(input_path)
        details["alert_id"] = alert.id
        limits = limits or Limits.from_env()
        details["limits"] = {"tool_calls": limits.tool_calls, "model_turns": limits.model_turns}
        stage = "2/scope"
        snapshot = load_snapshot(alert, snapshot_path)
        details["scope"] = {"region": snapshot.region, "services": snapshot.allowed_services, "tools": list(TOOL_DESCRIPTIONS)}
        governor = Governor(LocalTools(snapshot), limits)
        story.event("CODE", stage, f"Read-only scope: {snapshot.region}, services={snapshot.allowed_services}; tool limit={limits.tool_calls}, model-turn limit={limits.model_turns}.")
        if decide is None:
            from .ai import next_action
            decide = next_action

        # Unlike both workflows, code does not select metrics, logs, deployments,
        # or a dependency next. The model chooses from observations each turn.
        while True:
            stage = "budget_check"
            governor.begin_model_turn()
            turn = governor.model_turns
            stage = f"turn{turn}/next_action"
            context = {
                "alert": alert.model_dump(), "allowed_services": list(snapshot.allowed_services),
                "region": snapshot.region, "tools": dict(TOOL_DESCRIPTIONS),
                "remaining_tool_calls": governor.remaining_tool_calls,
                "remaining_model_turns_after_this_request": limits.model_turns - turn,
                "observations": deepcopy(governor.observations),
            }
            story.event("CODE", stage, f"Governor permits model turn {turn}/{limits.model_turns}; {governor.remaining_tool_calls} tool calls remain.")
            story.event("AI", stage, "Choose useful read-only tools or submit a conclusion based on observations.")
            decision = parse_model(decide(context), Decision)
            if decision.action == "conclude":
                stage = f"turn{turn}/conclusion"
                governor.validate_conclusion(decision.conclusion)
                details.update(decision.conclusion.model_dump())
                result["outcome"] = "concluded" if decision.conclusion.hypothesis is not None else "insufficient_evidence"
                story.event("AI", stage, f"Hypothesis: {details['hypothesis'] or 'No defensible hypothesis'}; confidence={details['confidence']}.", evidence=details["evidence"])
                story.event("AI", stage, f"Proposed human-reviewed action: {details['recommended_action']}", unresolved_questions=details["unresolved_questions"])
                story.event("CODE", stage, "Accepted structured conclusion with observed references; no production action is executed.")
                break

            stage = f"turn{turn}/governor"
            governor.authorize_batch(decision.calls)
            story.event("CODE", stage, f"Approved {len(decision.calls)} read-only requests against permissions, resources, and remaining budget.")
            for call in decision.calls:
                stage = f"turn{turn}/tool{governor.tool_calls + 1}"
                arguments = call.arguments.model_dump(exclude_none=True)
                story.event("AI", stage, f"Selected {call.tool} with {arguments}.")
                story.event("TOOL", stage, f"Invoke {call.tool}; code rechecks permissions before execution.")
                observation = governor.execute(call)
                references = [record["id"] for record in observation["records"]]
                story.event("TOOL", stage, f"{observation['id']}: {observation['summary']}", observation_reference=observation["id"], evidence_references=references)
    except BudgetReached as exc:
        result["outcome"] = "incomplete"
        details["limit_reached"] = {"code": exc.code, "message": str(exc)}
        details["unresolved_questions"] = ["What additional evidence is needed to establish or rule out a defensible cause?"]
        story.event("CODE", stage, str(exc) + " Preserve observations; do not invent a root cause.")
    except DemoError as exc:
        result["outcome"] = "technical_failure"
        details["error"] = {"code": exc.code, "message": str(exc), "stage": stage}
    except Exception:  # noqa: BLE001 - keep raw SDK errors and untrusted payloads out of output
        result["outcome"] = "technical_failure"
        details["error"] = {"code": "execution_failed", "message": "Incident investigation failed; no production action was taken.", "stage": stage}
    finally:
        if governor is not None:
            details["model_turns"] = governor.model_turns
            details["tool_calls"] = governor.tool_calls
            details["observations"] = governor.observations
            if result["outcome"] in {"incomplete", "technical_failure"}:
                details["evidence"] = [{"reference": observation["id"], "summary": observation["summary"][:500]}
                                       for observation in governor.observations[:16]]

    message = details.get("error", {}).get("message", result["outcome"])
    story.event("RESULT", "final", message, outcome=result["outcome"])
    return Run(story.result(result), story.directory)
