"""Strict alert, tool-call, evidence, and conclusion contracts."""

import json
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from demo_common.errors import DemoError

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ToolName = Literal[
    "get_metrics", "search_logs", "get_deployments", "get_deployment_diff",
    "get_runbook", "get_dependencies",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Alert(StrictModel):
    id: Identifier
    service: Identifier
    region: Identifier
    summary: ShortText


class ToolArguments(StrictModel):
    service: Identifier
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    deployment_id: Identifier | None = None


class ToolCall(StrictModel):
    tool: ToolName
    arguments: ToolArguments

    @model_validator(mode="after")
    def tool_specific_arguments(self) -> Self:
        if self.arguments.query is not None and self.tool != "search_logs":
            raise ValueError("Only log searches accept a query")
        if self.tool == "get_deployment_diff":
            if self.arguments.deployment_id is None:
                raise ValueError("Deployment diff requires a deployment ID")
        elif self.arguments.deployment_id is not None:
            raise ValueError("Only deployment diff accepts a deployment ID")
        return self


class Evidence(StrictModel):
    reference: Identifier
    summary: ShortText


class Conclusion(StrictModel):
    hypothesis: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] | None
    evidence: Annotated[list[Evidence], Field(max_length=16)]
    confidence: Literal["low", "medium", "high"]
    recommended_action: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
    unresolved_questions: Annotated[list[ShortText], Field(max_length=8)]

    @model_validator(mode="after")
    def defensible_result(self) -> Self:
        if self.hypothesis is not None and not self.evidence:
            raise ValueError("A hypothesis requires observed evidence")
        if self.hypothesis is None and (self.confidence != "low" or not self.unresolved_questions):
            raise ValueError("Insufficient evidence requires low confidence and explicit open questions")
        references = [item.reference for item in self.evidence]
        if len(references) != len(set(references)):
            raise ValueError("Evidence references must be distinct")
        return self


class Decision(StrictModel):
    action: Literal["tools", "conclude"]
    calls: Annotated[list[ToolCall], Field(max_length=8)]
    conclusion: Conclusion | None

    @model_validator(mode="after")
    def one_action(self) -> Self:
        if self.action == "tools" and (not self.calls or self.conclusion is not None):
            raise ValueError("Tool action requires calls and no conclusion")
        if self.action == "conclude" and (self.calls or self.conclusion is None):
            raise ValueError("Conclusion action requires a conclusion and no calls")
        return self


class Record(StrictModel):
    id: Identifier
    service: Identifier
    tool: ToolName
    summary: ShortText
    data: dict


class IncidentSnapshot(StrictModel):
    id: Identifier
    region: Identifier
    allowed_services: Annotated[list[Identifier], Field(min_length=1, max_length=8)]
    records: Annotated[list[Record], Field(max_length=64)]

    @model_validator(mode="after")
    def coherent_scope(self) -> Self:
        if len(self.allowed_services) != len(set(self.allowed_services)):
            raise ValueError("Service allow-list must be distinct")
        ids = [record.id for record in self.records]
        if len(ids) != len(set(ids)) or any(reference.startswith("OBS-") for reference in ids):
            raise ValueError("Record IDs must be unique and not use reserved OBS- references")
        if any(record.service not in self.allowed_services for record in self.records):
            raise ValueError("Record service is outside the fixture allow-list")
        return self


class Snapshots(StrictModel):
    incidents: list[IncidentSnapshot]


def parse_model[Model: BaseModel](payload: str, schema: type[Model], *, code: str = "invalid_model_output") -> Model:
    def unique_keys(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError("Duplicate JSON key")
            values[key] = value
        return values

    def reject_constant(value):
        raise ValueError("Nonfinite JSON values are not permitted")

    try:
        return schema.model_validate(json.loads(payload, object_pairs_hook=unique_keys, parse_constant=reject_constant))
    except (ValueError, TypeError, ValidationError) as exc:
        messages = {
            "invalid_input": "Alert must match the documented JSON schema.",
            "invalid_reference_data": "Local incident snapshots are malformed or invalid.",
        }
        raise DemoError(code, messages.get(code, "AI returned an invalid or unauthorized investigation decision.")) from exc
