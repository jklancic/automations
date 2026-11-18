# Agent: read-only incident investigator

A model-directed incident investigation assistant. Given an alert, AI chooses the next permitted tool or submits a conclusion based on observations. **There is no predefined metrics → deployments → logs pipeline.** Python enforces permissions, data scope, evidence validation, and execution limits.

All evidence is synthetic and local. Recommendations are for human review only: the application cannot roll back, deploy, send messages, run shell commands, or modify production—even with approval.

## Run it

From the repository root:

```sh
uv sync --locked
```

Use the same Python 3.12 environment, SAP AI SDK, and local proxy configuration as the two workflows. The default proxy route is `http://localhost:6655/openai/v1`; set `AI_PROXY_API_KEY` and an available `AI_MODEL`. See the [shared setup](../README.md#quick-start-invoice-workflow) and [configuration template](../.env.example).

With a configured root `.env`:

```sh
uv run --locked --env-file .env python agent-part-4/run.py \
  agent-part-4/inputs/deployment-related.json

uv run --locked --env-file .env python agent-part-4/run.py \
  agent-part-4/inputs/downstream-dependency.json

uv run --locked --env-file .env python agent-part-4/run.py \
  agent-part-4/inputs/inconclusive.json
```

Omit `--env-file .env` if variables are already exported. Activating `.venv` selects Python and installed packages; it does not load `.env`. Never commit the local proxy key.

These commands use the real proxy, with no stub fallback. Offline tests exercise the installed SDK with in-memory HTTP responses; a live run still requires your key, a supported model, and service availability. Choose an OpenAI-compatible chat model supporting JSON-object responses and `max_completion_tokens`.

| Sample | Local evidence | Representative outcome |
| --- | --- | --- |
| `deployment-related.json` | Checkout latency/error spike, release-correlated pool exhaustion, configuration diff | A supported deployment-related hypothesis and proposed human-reviewed action |
| `downstream-dependency.json` | Checkout dependency map, payments latency and gateway retry errors | A downstream hypothesis reached through a different investigation path |
| `inconclusive.json` | Inventory collection gap and missing logs | Explicit insufficient evidence, no defensible hypothesis |

Live tool order and conclusions may differ. The test paths demonstrate valid alternatives; they are not application scripts imposed on the model.

## Read the agent loop

[`incident_agent/investigation.py`](incident_agent/investigation.py) contains the complete controller:

1. Code validates the alert and selects its approved local snapshot and service scope.
2. The governor checks that another model turn is permitted.
3. AI receives the alert, tool registry, remaining budgets, and observations collected so far.
4. AI chooses a batch of read-only tool calls **or** a structured conclusion.
5. For tools, code validates the batch, checks permissions before every invocation, records results, and returns to the model with new observations.
6. For a conclusion, code validates structure and observed evidence references, then stops without taking a production action.

The controller does not decide which investigation tool comes next. It does not branch on “a deployment was found” or prescribe a dependency traversal. The model must adapt its choices to the evidence.

Requests use validated JSON rather than the provider's native tool-calling API. This is still an agent: **the model chooses the next action across the investigation**, regardless of the transport protocol. Native tool requests are rejected; only the application's governed registry can execute a read.

### Permitted tools

Every tool requires `service`, restricted to the selected incident's allow-list. Region and incident scope are fixed by code and cannot be passed as overriding arguments.

| Tool | Reads | Additional arguments |
| --- | --- | --- |
| `get_metrics` | Service metrics and SLO observations | None |
| `search_logs` | Local logs, optionally filtered by literal case-insensitive substring | Optional `query`, at most 200 trimmed characters |
| `get_deployments` | Deployment history and IDs | None |
| `get_deployment_diff` | A scoped deployment's configuration diff | Required `deployment_id` matching an available service diff |
| `get_runbook` | Service runbook and human-reviewed recommendations | None |
| `get_dependencies` | Local service dependency map | None |

The model may inspect any allowed service, including a relevant dependency. Tool content cannot add services or tools to the allow-list. Unknown tools, invalid arguments, foreign deployments, and out-of-scope services are rejected before invocation. Paths, URLs, region overrides, and write requests are not supported arguments.

A tool decision looks like:

```json
{
  "action": "tools",
  "calls": [
    {"tool": "get_metrics", "arguments": {"service": "checkout"}},
    {"tool": "search_logs", "arguments": {"service": "checkout", "query": "connection pool"}}
  ],
  "conclusion": null
}
```

A batch contains 1–8 calls. Code preflights the entire batch before executing any of it, then executes permitted calls in order with per-call guard checks. Results reach the model on the next turn. If one choice depends on another tool's result, the model must use a later turn rather than invent the unseen result inside a batch.

### Budgets and failures

Default limits:

- **Eight tool invocations**, counting each batch member separately. Failed invocations also count.
- **Ten model turns**, counting attempted decisions, including failed requests.
- Shared per-request settings: **30-second timeout** and **512 output-token cap**. These are per-request limits, not a cumulative token-usage meter.

Set positive integer `AGENT_MAX_TOOL_CALLS` and `AGENT_MAX_MODEL_TURNS` to change the investigation limits. Timeout and output cap use the shared `AI_TIMEOUT_SECONDS` and `AI_MAX_OUTPUT_TOKENS` settings.

Once either investigation budget is exhausted, code makes no extra model request to obtain a final answer. A conclusion must arrive before the tool budget is exhausted; a valid conclusion on the final permitted model turn is accepted. A batch larger than the remaining tool budget stops the investigation as incomplete without executing a subset. The model is told these stopping rules, but code enforces them independently.

Budget stops preserve observations and unresolved questions with `hypothesis: null` and low confidence. They never claim a root cause. Malformed model output, permission failures, invalid references, and SDK/tool failures terminate as technical failures; there is no automatic retry or model-output repair.

## Evidence and conclusions

Each successful tool invocation creates an observation such as `OBS-1`. Its records also carry fixture evidence IDs such as `DIFF-CHECKOUT-28`. An empty result is still an observation, so the agent can cite the absence of matching records without inventing evidence.

A conclusion decision has `action: "conclude"`, `calls: []`, and a `conclusion` object containing:

- `hypothesis`: a nonblank statement or `null` for no defensible hypothesis.
- `evidence`: distinct `{reference, summary}` objects, citing only records or observations actually seen in this run.
- `confidence`: `low`, `medium`, or `high`.
- `recommended_action`: a proposal for human review, never an executed operation.
- `unresolved_questions`: explicit remaining questions.

A hypothesis requires evidence. A null hypothesis requires low confidence and at least one unresolved question. Unknown, duplicate, or unseen evidence references are rejected. Evidence-reference checks establish traceability, not the factual or causal correctness of the model's hypothesis; this is not a production incident-response system.

## Input and local data scope

Input is one nonempty UTF-8 `.json` file of at most 32 KiB, with exactly `id`, `service`, `region`, and `summary`. Identifiers use 1–64 ASCII letters, digits, or hyphens, starting with a letter or digit; summary is nonblank text of at most 500 trimmed characters.

[`fixtures/snapshots.json`](fixtures/snapshots.json) contains three synthetic, fixed incident snapshots. Alert `id` selects a snapshot; service and region must match its approved scope. Unknown IDs and scope mismatches fail before AI. No ID or model argument is converted to a filesystem path or external endpoint.

Fixture incident/record IDs must be unique within their scope, record services must be allowed, and `OBS-` is reserved for generated observation references. Malformed fixtures are technical failures. Treat alert and tool content as untrusted data, not authoritative instructions, even when the source is approved for reading.

## Terminal story and artifacts

`[CODE]` reports scope, governor checks, and budget stops. `[AI]` reports selected tools and validated conclusions. `[TOOL]` shows invocations and meaningful observation summaries. `[RESULT]` reports the final outcome and artifact directory. None of this claims to reveal private model reasoning.

Every run creates an ignored `outputs/incident-.../` directory with:

- `result.json`: common envelope, hypothesis/evidence/confidence/recommendation/questions, observed local records, limits and counters, scope, and `action_taken: false`.
- `trace.jsonl`: append-only ordered execution events, model-selected actions, guard checks, tool activity, and evidence references.

Outcomes `concluded`, `insufficient_evidence`, and `incomplete` exit **0**, but remain distinct in the result. Technical failures exit **1**; CLI usage errors exit **2**. Failure artifacts are saved when possible; artifact-write failures never claim a saved result. Fixtures remain unchanged, and investigations do not share business state.

## Compare the approaches

| Dimension | Deterministic invoice workflow | Agentic support workflow | This incident agent |
| --- | --- | --- | --- |
| Code control | Every stage, branch, and routing rule | Fixed stages, bounded retrieval, escalation, and review | Scope, permissions, budgets, validation, and termination safeguards |
| AI decisions | Field extraction only | Classification, knowledge queries, evidence sufficiency, and draft | Next investigation tool family, arguments, and when to conclude |
| Available actions | Code-owned reference checks | Account lookup and bounded approved knowledge search | Metrics, logs, deployments/diffs, runbooks, and dependencies selected dynamically |
| Stopping | Code-owned invoice route or failure | Code-owned escalation or review queue, or failure | Model conclusion or insufficient evidence; code-owned limit stop or failure |

All three use the same SDK and output infrastructure. What changes is ownership of the next action, not the presence of an LLM, tools, or a loop.

## Verify and navigate

```sh
uv run --locked pytest -q
uv run --locked pytest agent-part-4/tests -q
uv run --locked python agent-part-4/run.py --help
```

Tests deny real network access and cover different tool paths, observation-dependent choices, batches, exact limits, null hypotheses, invalid evidence, permissions, malformed inputs/fixtures/decisions, failure handling, artifact isolation, and full paths through the installed SDK with in-memory HTTP responses. They do not assert an exact live tool sequence or wording.

- [`incident_agent/investigation.py`](incident_agent/investigation.py): model-directed loop and outcomes.
- [`incident_agent/governor.py`](incident_agent/governor.py): code-owned scope and budget enforcement.
- [`incident_agent/tools.py`](incident_agent/tools.py): approved snapshot selection and read-only registry.
- [`incident_agent/models.py`](incident_agent/models.py): strict input, decision, and evidence contracts.
- [`incident_agent/ai.py`](incident_agent/ai.py): next-action prompt and shared SDK call.
- [`demo_common/`](../demo_common/): shared transport, configuration, safe errors, and output formatting—no shared orchestration.

Authoritative behavioral contract and acceptance checks: [`docs/automations.spec`](../docs/automations.spec).
