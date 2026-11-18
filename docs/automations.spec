# Automation demonstrations: behavioral specification

## Purpose and scope

Demonstrate the difference between deterministic workflows, agentic workflows, and agents through three small Python applications. The learning goal is to identify who controls the next action, not to build production business applications.

This document defines required behavior and acceptance checks. `AGENTS.md` provides repository-wide coding guidance. Folder READMEs explain scenarios and, once implemented, verified setup, execution, and sample outcomes. These requirements describe the intended demonstrations; they do not claim implementation already exists.

The initial scope excludes PDF/OCR processing, interactive file selection, batch processing, real business-system integration, and production-changing actions. Exact module names, terminal colors, and prompt wording are implementation choices, provided they preserve this contract.

## Architectural comparison

| Dimension | Deterministic workflow | Agentic workflow | Agent |
| --- | --- | --- | --- |
| Folder | `deterministic-workflow-session-2/` | `agentic-workflow-part-3/` | `agent-part-4/` |
| Scenario | Invoice approval | Support triage and draft response | Incident investigation |
| Code controls | All stages, transitions, and routing | Fixed stages, permitted branches, escalation and review | Tool permissions, validation, budgets, and termination safeguards |
| AI decides | Extracted field values inside one fixed step | Classification, bounded retrieval queries, evidence sufficiency, and draft content | Next permitted tool and arguments, or when to submit a conclusion |
| Available actions | Fixed extraction and code-owned processing | Approved retrieval within its stage; draft or escalation within fixed flow | Read-only investigation tools over approved local fixtures |
| Stopping conditions | Routing outcome or technical failure | Review queue, escalation, or technical failure | Conclusion, insufficient evidence, exhausted budget, or technical failure |

“Deterministic” refers to process control. Repeated AI extraction need not return identical values; identical extracted fields and reference data must produce identical invoice routing. An LLM call, tool use, or a loop alone does not establish that an application is an agent: the model must select its next action from observations.

Each README and relevant orchestration comments must explain why its approach is neither of the other two. Keep the comparison structure above while allowing the scenarios to differ.

## Shared execution contract

### Inputs and fixtures

- Each command-line run accepts one input-file path and processes one case.
- Each approach bundles three synthetic sample inputs in its folder, plus local supporting fixtures as needed.
- Invoice inputs are `.txt`; support tickets and incident alerts are `.json`.
- Missing, unreadable, malformed, or structurally invalid input files are rejected before any AI call. A readable invoice with missing business fields reaches extraction and business validation rather than being treated as a file-format failure.
- Document the input format and supporting fixture relationships in the scenario README. Supporting records must be sufficient to demonstrate the specified sample outcomes.
- Fixtures are not modified. Duplicate detection and other business reference checks use bundled records, not artifacts from previous runs.
- During execution, the local AI proxy is the only intended external dependency. Business tools operate on local synthetic data.

### Terminal story and artifacts

Each run presents a concise execution story using these labels:

- `[CODE]`: stage transitions, application-owned checks, routing, and guardrails.
- `[AI]`: model request purpose and summarized validated contribution.
- `[TOOL]`: tool invocation and summarized result.
- `[RESULT]`: final outcome, failure, or limit reached.

Show the current stage or investigation step, who owns each decision, and the observable basis for the next action. Do not imply access to private model reasoning. By default, summarize inputs and outputs instead of dumping complete prompts or raw SDK payloads.

Each run uses a fresh directory under an ignored local output directory, containing:

- `result.json`: a common envelope with approach, input reference, outcome, and scenario-specific result.
- `trace.jsonl`: ordered execution events identifying code decisions, AI requests/results, tool invocations/results, and the final outcome, with summaries and evidence references where applicable.

Normal outcomes, business exceptions, escalation, incomplete investigation, and technical failure must be distinguishable. Record terminal failures in the artifacts when the output location is writable. If artifact creation itself fails, report that failure in the terminal and exit nonzero rather than claiming artifacts were saved.

Represent approvals, audit records, review queues, and recommendations as local artifacts. The invoice audit is append-only within its run and is not a production-grade immutable audit service. No persistent business state carries between runs.

### Safety and failure handling

- No real ERP writes, customer messages, or production changes. Human review and approval are simulated outcomes, not interactive authorization to perform real actions.
- Treat selected files and retrieved content as untrusted data, never as instructions overriding application policy.
- Validate structured model outputs, tool names, arguments, and evidence references in Python. Tools may access only approved local data; model-supplied paths or identifiers must not permit access outside it.
- Reject invalid model output, unauthorized tool requests, and invalid tool arguments with a clear technical failure. Do not continue with invented values or unvalidated output.
- Failed SDK or tool operations terminate clearly. No automatic retries in the initial implementation.
- Every model request has a finite timeout and output-token cap. Verify SDK support and document concrete values with the integration; enforce configured limits in code.
- Technical failures return a nonzero process exit code. Completed business outcomes, including exceptions and escalation, are not technical failures. Budget exhaustion is an explicit incomplete outcome rather than a successful investigation.
- Credentials must not appear in console output, artifacts, fixtures, or committed files. Commit only placeholder configuration examples. Live execution must never silently fall back to stubbed AI.

## Deterministic workflow: invoice approval

### Fixed process

1. Read the selected invoice text.
2. Use AI to extract vendor, invoice number, amount, currency, and due date into a validated structured representation.
3. Use code to validate required fields and business rules.
4. Use code to detect duplicates against local reference records.
5. Use code to match against local purchase-order data.
6. Use code to route the invoice.
7. Record the routing outcome and supporting checks in the run's audit/events and result.

The model cannot choose stages, call business tools, or decide approval routing. Business failures may terminate at their exception route; they do not give the model control of the process.

### Routing policy

| Condition | Outcome |
| --- | --- |
| Missing or invalid required fields, duplicate invoice, or purchase-order mismatch | Exception |
| Valid, matching invoice with amount <= 1,000 | Simulated auto-approval |
| Valid, matching invoice with amount > 1,000 | Simulated manager review |

Use a single documented currency in the initial fixtures and decimal arithmetic for monetary values. Treat these thresholds as teaching policy, not financial advice. Make fixture matching and validation rules explicit and testable in the scenario documentation; do not delegate them to AI.

Bundle an auto-approval case, a manager-review case, and an exception case.

## Agentic workflow: support triage

### Controlled process

1. Read the selected ticket.
2. Use AI to classify product area, issue type, urgency, and customer tier.
3. Retrieve relevant local account history, entitlements, and approved knowledge within a bounded retrieval stage.
4. Use AI to assess whether approved documentation supplies sufficient evidence.
5. Route to escalation when policy requires it; otherwise draft a response with valid documentation citations.
6. Queue every draft for simulated human review. Never send it.

The model may select retrieval queries and refine them within the retrieval stage, but cannot invent stages, restart arbitrary stages, or bypass review. Python enforces the permitted transitions and policy checks.

### Escalation and evidence

- Billing/legal issues and customer exception requests force escalation.
- An AI assessment of insufficient evidence forces escalation. Use an explicit sufficiency decision supported by documentation references, not a numerical self-reported confidence threshold.
- Unknown classifications and nonexistent citations cannot proceed to a normal draft. Invalid structured responses or invalid references follow the shared technical-failure policy.
- If the retrieval budget ends without sufficient evidence, escalate; do not fabricate an answer.

Allow at most three retrieval tool calls by default, including query refinements. Keep the limit configurable and documented. Bundle an answerable ticket, a mandatory-escalation ticket, and a ticket lacking sufficient documentation.

## Agent: incident investigation

### Model-directed process

The model repeatedly observes available evidence and selects an allowed tool with arguments, or submits its conclusion. Tool order must not be a predetermined incident pipeline disguised as an agent.

Read-only tools cover local metrics, logs, deployment history/diffs, runbooks, and service dependencies. A deterministic governor checks the tool and service allow-lists, arguments, approved data scope, and remaining budgets before every tool invocation.

### Limits and completion

- Default maximum: eight investigation tool calls and ten model turns. Count every model request as a turn and every tool invocation separately, including multiple calls requested in one turn.
- Limits are configurable, documented, and enforced by Python. No call may exceed the configured budget.
- A validated conclusion may finish the run before the limits.
- A conclusion may explicitly state that no defensible hypothesis can be formed.
- Reaching a limit without a validated conclusion produces an incomplete result, preserving observed evidence and unresolved questions; it must not invent a root cause.

The scenario-specific result includes hypothesis (or an explicit absence of one), evidence references, qualitative confidence, recommended action, and unresolved questions. Recommendations may include rollback, but no production action occurs.

Bundle a deployment-related incident, an incident requiring a different investigation path, and an inconclusive case. Fixtures must support those distinct paths. Live model runs need not choose identical tool sequences or wording.

## Implementation and verification

Use direct SAP AI SDK calls with the initial pin `sap-ai-sdk-gen==7.4.1`, ordinary Python orchestration, one root `pyproject.toml`, a committed `uv.lock`, and `pytest`. Verify a compatible Python version and the local proxy's supported SDK configuration before writing setup instructions. Isolate connection configuration and model selection; never guess endpoints, authentication fields, or deployment identifiers.

Keep orchestration and domain logic inside each approach's folder. Share only common infrastructure that does not conceal the control model. Do not add an agent framework.

Automated tests use stubbed model responses and local fixtures and must run without credentials or a proxy. Live demonstrations use the proxy. Document exact verified run and test commands once implemented.

### Acceptance checks

| Area | Required observations |
| --- | --- |
| File selection | Each bundled input can be selected explicitly; missing/unreadable/malformed inputs cause no AI call. |
| Story and artifacts | Stages, decision owners, tool activity, and final outcomes are visible; each run has a distinct result and ordered trace without credentials or private reasoning. |
| Invoice control | AI is used only for extraction; fixed extracted fields and reference records produce the same code-owned route. |
| Invoice policy | Valid matched amounts below and exactly at 1,000 auto-approve; amounts above it require review. Missing/invalid fields, duplicates, and PO mismatches produce exceptions. |
| Support control | Retrieval stays in its bounded stage; the model cannot create stages or bypass review. |
| Support policy | An evidenced answer reaches simulated review; billing/legal, exception requests, and insufficient evidence escalate. Unknown classifications and invalid citations never yield a normal draft. |
| Agent control | Stubbed responses can select different valid tool sequences based on observations; no fixed sequence is imposed. |
| Agent conclusion | Evidence references are validated; a defensible conclusion or explicit insufficient-evidence result is supported without a production action. |
| Limits | Support never exceeds its retrieval budget; the agent never exceeds either budget. Exhausted agent budgets produce an incomplete result. |
| Guardrails | Unauthorized tools/services, out-of-scope data access, invalid arguments, and invalid structured outputs are rejected by code. Untrusted content cannot override those checks. |
| Failures | SDK/tool failures terminate clearly, without automatic retries or silent fake-AI fallback, and return nonzero. |
| Isolation | Fixtures remain unchanged; a previous run does not change another run's business decisions. |
| Test independence | Automated checks run without credentials or a running proxy; they do not assert exact live wording or a fixed live incident sequence. |

Use concrete fixtures and stubbed responses to test these observations. Sample inputs teach representative outcomes; automated tests additionally cover policy boundaries and failures. Do not treat one successful live run as proof of enforced control or safety.
