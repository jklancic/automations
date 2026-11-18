3. Agent: production incident investigator

Project: On-Call Incident Investigation Assistant

Build an assistant that receives an alert such as “checkout error rate is rising” and investigates it using a limited set of read-only tools: metrics, logs, deployment history, runbooks, and service dependency maps. The correct investigation path is not known ahead of time, so the model must decide what to inspect next based on what it observes. Agents are appropriate when the model must dynamically direct its process and tool use.

Example interaction (illustrative, not a fixed tool sequence)

- Input: “Checkout latency is above SLO in EU-West.”

- The agent checks dashboards and identifies a latency spike.

- It correlates the spike with a recent deployment.

- It searches logs for a new error pattern.

- It reads the deployment diff and runbook.

- It proposes a likely root cause, evidence, blast radius, and a rollback recommendation.

- It stops before taking any production-changing action.

Guardrails to build

- Read-only tools over synthetic local fixtures only; no production-changing actions, even with approval.

- Code-enforced limits: at most eight tool calls and ten model turns by default, plus finite per-request timeout and output-token caps.

- An allow-list of tools and services.

- Required structured output: hypothesis (or explicitly no defensible hypothesis), evidence references, qualitative confidence, recommended action, and unresolved questions. Budget exhaustion produces an explicit incomplete result.

- A deterministic “autonomy governor” that checks permissions and policy before each tool call.

Why it needs an agent: the system cannot enumerate every investigation path in advance; it must adapt based on intermediate evidence. The agent observes tool results and decides the next action until it submits a conclusion, acknowledges insufficient evidence, reaches a limit, or encounters a technical failure.

See [`docs/automations.spec`](../docs/automations.spec) for the authoritative behavioral contract and acceptance checks. Recommendations are local artifacts, never production actions. This README describes the intended demonstration; execution instructions will be added after implementation.