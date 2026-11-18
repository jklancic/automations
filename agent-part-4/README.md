3. Agent: production incident investigator

Project: On-Call Incident Investigation Assistant

Build an assistant that receives an alert such as “checkout error rate is rising” and investigates it using a limited set of read-only tools: metrics, logs, deployment history, runbooks, and service dependency maps. The correct investigation path is not known ahead of time, so the model must decide what to inspect next based on what it observes. Agents are appropriate when the model must dynamically direct its process and tool use.

Example interaction

- Input: “Checkout latency is above SLO in EU-West.”

- The agent checks dashboards and identifies a latency spike.

- It correlates the spike with a recent deployment.

- It searches logs for a new error pattern.

- It reads the deployment diff and runbook.

- It proposes a likely root cause, evidence, blast radius, and a rollback recommendation.

- It stops before taking any production-changing action.

Guardrails to build

- Read-only tools only, or write actions requiring explicit human approval.

- A maximum number of investigation steps and token/tool budget.

- An allow-list of tools and services.

- Required structured output: hypothesis, evidence, confidence, recommended action, and unresolved questions.

- A deterministic “autonomy governor” that checks permissions and policy before each tool call.

Why it needs an agent: the system cannot enumerate every investigation path in advance; it must adapt based on intermediate evidence. The agent observes tool results, decides the next action, and repeats until it can form a defensible conclusion.