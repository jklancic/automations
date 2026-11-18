"""A read-only tool registry over one approved local incident snapshot."""

import json
from pathlib import Path

from demo_common.errors import DemoError

from .models import Alert, Snapshots, ToolCall, parse_model

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "snapshots.json"
TOOL_DESCRIPTIONS = {
    "get_metrics": "Read service metrics and SLO observations. Arguments: service.",
    "search_logs": "Read service logs, optionally filtered by a literal substring. Arguments: service, optional query.",
    "get_deployments": "Read deployment history, including deployment IDs. Arguments: service.",
    "get_deployment_diff": "Read a deployment's configuration diff. Arguments: service, deployment_id.",
    "get_runbook": "Read the service runbook; recommendations require human review. Arguments: service.",
    "get_dependencies": "Read service dependencies. Arguments: service.",
}


def load_snapshot(alert: Alert, path: Path = SNAPSHOT_PATH):
    try:
        with path.open("rb") as handle:
            raw = handle.read(131_073)
        if len(raw) > 131_072:
            raise ValueError("Oversized fixture")
        snapshots = parse_model(raw.decode("utf-8"), Snapshots, code="invalid_reference_data").incidents
    except (OSError, UnicodeError, ValueError) as exc:
        raise DemoError("invalid_reference_data", "Local incident snapshots are unreadable or invalid.") from exc
    ids = [snapshot.id for snapshot in snapshots]
    if len(ids) != len(set(ids)):
        raise DemoError("invalid_reference_data", "Incident snapshot IDs must be unique.")
    selected = next((snapshot for snapshot in snapshots if snapshot.id == alert.id), None)
    if selected is None:
        raise DemoError("unknown_incident", "The alert has no approved local incident snapshot.")
    if selected.region != alert.region or alert.service not in selected.allowed_services:
        raise DemoError("unauthorized_scope", "Alert service or region is outside its approved snapshot scope.")
    return selected


class LocalTools:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def validate_resource(self, call: ToolCall):
        if call.tool == "get_deployment_diff" and not any(
            record.tool == call.tool and record.service == call.arguments.service
            and record.data.get("deployment_id") == call.arguments.deployment_id
            for record in self.snapshot.records
        ):
            raise DemoError("unknown_deployment", "Requested deployment diff is outside the approved service snapshot.")

    def read(self, call: ToolCall):
        # No paths, URLs, shell commands, or writes come from model arguments.
        records = [
            record for record in self.snapshot.records
            if record.tool == call.tool and record.service == call.arguments.service
        ]
        if call.tool == "search_logs" and call.arguments.query is not None:
            needle = call.arguments.query.casefold()
            records = [record for record in records if needle in (
                record.summary + " " + json.dumps(record.data, ensure_ascii=False)
            ).casefold()]
        if call.tool == "get_deployment_diff":
            records = [record for record in records if record.data.get("deployment_id") == call.arguments.deployment_id]
        return [record.model_dump() for record in records]
