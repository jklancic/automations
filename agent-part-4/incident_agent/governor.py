"""Deterministic permission and budget enforcement, not an investigation plan."""

import os
from dataclasses import dataclass

from demo_common.errors import DemoError

from .models import Conclusion, ToolCall
from .tools import TOOL_DESCRIPTIONS, LocalTools


class BudgetReached(DemoError):
    """Expected incomplete investigation, distinct from technical failure."""


@dataclass(frozen=True)
class Limits:
    tool_calls: int = 8
    model_turns: int = 10

    def __post_init__(self):
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
               for value in (self.tool_calls, self.model_turns)):
            raise DemoError("invalid_configuration", "Agent tool and model limits must be positive integers.")

    @classmethod
    def from_env(cls):
        try:
            return cls(int(os.environ.get("AGENT_MAX_TOOL_CALLS", "8")),
                       int(os.environ.get("AGENT_MAX_MODEL_TURNS", "10")))
        except ValueError as exc:
            raise DemoError("invalid_configuration", "Agent tool and model limits must be positive integers.") from exc


class Governor:
    def __init__(self, tools: LocalTools, limits: Limits):
        self.tools = tools
        self.limits = limits
        self.model_turns = 0
        self.tool_calls = 0
        self.observations = []

    @property
    def remaining_tool_calls(self):
        return self.limits.tool_calls - self.tool_calls

    def begin_model_turn(self):
        if self.remaining_tool_calls <= 0:
            raise BudgetReached("tool_budget_exhausted", "Tool budget reached before a validated conclusion.")
        if self.model_turns >= self.limits.model_turns:
            raise BudgetReached("model_budget_exhausted", "Model-turn budget reached before a validated conclusion.")
        self.model_turns += 1

    def validate_call(self, call: ToolCall):
        # Repeat structural checks at the execution boundary, independently of
        # prompts and controller parsing. Never expand permissions from tool text.
        try:
            call = ToolCall.model_validate(call.model_dump())
        except ValueError as exc:
            raise DemoError("unauthorized_tool", "Tool request does not match the allowed argument schema.") from exc
        if call.tool not in TOOL_DESCRIPTIONS:
            raise DemoError("unauthorized_tool", "Only registered read-only tools are permitted.")
        if call.arguments.service not in self.tools.snapshot.allowed_services:
            raise DemoError("unauthorized_service", "Tool service is outside the approved incident allow-list.")
        self.tools.validate_resource(call)

    def authorize_batch(self, calls: list[ToolCall]):
        if not calls or len(calls) > 8:
            raise DemoError("unauthorized_tool", "Tool batch must contain between one and eight permitted calls.")
        if self.model_turns < 1 or self.model_turns > self.limits.model_turns:
            raise DemoError("unauthorized_turn", "Tool calls require an active permitted model turn.")
        # Preflight the entire batch before any call, preventing partial execution
        # of a batch containing an unauthorized later request.
        for call in calls:
            self.validate_call(call)
        if len(calls) > self.remaining_tool_calls:
            raise BudgetReached("tool_budget_insufficient_for_batch", "Requested tool batch exceeds the remaining budget; no calls in the batch were executed.")

    def execute(self, call: ToolCall):
        self.authorize_batch([call])
        self.tool_calls += 1  # A failed invocation still consumes a tool call.
        records = self.tools.read(call)
        summary = "; ".join(record["summary"] for record in records) if records else "No matching records in this approved snapshot."
        observation = {
            "id": f"OBS-{self.tool_calls}", "tool": call.tool,
            "arguments": call.arguments.model_dump(exclude_none=True),
            "summary": summary, "records": records,
        }
        self.observations.append(observation)
        return observation

    def validate_conclusion(self, conclusion: Conclusion):
        observed = {observation["id"] for observation in self.observations}
        observed.update(record["id"] for observation in self.observations for record in observation["records"])
        if any(evidence.reference not in observed for evidence in conclusion.evidence):
            raise DemoError("invalid_evidence", "Conclusion references must identify evidence actually observed in this run.")
