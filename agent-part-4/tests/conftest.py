"""Scripted agent paths for offline checks, not hardcoded application plans."""

import pytest


def tool(name, service="checkout", **arguments):
    return {"tool": name, "arguments": {"service": service, **arguments}}


def tools(*calls):
    return {"action": "tools", "calls": list(calls), "conclusion": None}


def finish(hypothesis, references, *, confidence="medium", questions=None):
    return {"action": "conclude", "calls": [], "conclusion": {
        "hypothesis": hypothesis,
        "evidence": [{"reference": reference, "summary": "Observed evidence supports this assessment."} for reference in references],
        "confidence": confidence,
        "recommended_action": "Ask the on-call owner to review the evidence and proposed action; do not change production automatically.",
        "unresolved_questions": questions or [],
    }}


@pytest.fixture
def agent_cases():
    return {
        "deployment-related.json": [
            tools(tool("get_metrics")),
            tools(tool("get_deployments")),
            tools(tool("get_deployment_diff", deployment_id="deploy-checkout-28"), tool("search_logs", query="connection pool"), tool("get_runbook")),
            finish("The connection pool reduction in checkout 2.8 likely caused pool exhaustion.",
                   ["DIFF-CHECKOUT-28", "LOG-CHECKOUT-POOL", "METRIC-CHECKOUT-101"]),
        ],
        "downstream-dependency.json": [
            tools(tool("get_dependencies")),
            tools(tool("get_metrics", "payments")),
            tools(tool("search_logs", "payments", query="retry storm"), tool("get_runbook", "payments")),
            finish("A payments gateway retry storm likely caused downstream checkout timeouts.",
                   ["DEPENDENCY-CHECKOUT-202", "LOG-PAYMENTS-RETRY", "METRIC-PAYMENTS-202"]),
        ],
        "inconclusive.json": [
            tools(tool("get_metrics", "inventory"), tool("search_logs", "inventory")),
            tools(tool("get_runbook", "inventory")),
            finish(None, ["METRIC-INVENTORY-GAP", "OBS-2"], confidence="low",
                   questions=["Can on-call obtain reliable metrics and current logs?"]),
        ],
    }
