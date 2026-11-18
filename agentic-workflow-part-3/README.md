# Agentic workflow: support triage and draft replies

A local customer-support demonstration where **code owns the stages, but AI makes bounded decisions within them**. The model classifies tickets, selects knowledge queries, assesses documentation, and drafts an evidenced reply. Python enforces scope, escalation, retrieval limits, and mandatory human review.

No customer message, refund, policy exception, or business-system write is performed.

## Run it

From the repository root:

```sh
uv sync --locked
```

Use the same Python 3.12 environment and SAP AI SDK connection as the invoice demonstration. Start the local HAI proxy separately and configure `AI_PROXY_API_KEY` and `AI_MODEL`; the proxy URL defaults to `http://localhost:6655/openai/v1`. See the [shared setup](../README.md#quick-start-invoice-workflow) and [configuration template](../.env.example). The key is for the local proxy, not SAP AI Core.

If you keep configuration in a root `.env` file, explicitly ask **uv** to load it:

```sh
uv run --locked --env-file .env python agentic-workflow-part-3/run.py \
  agentic-workflow-part-3/inputs/answerable.json

uv run --locked --env-file .env python agentic-workflow-part-3/run.py \
  agentic-workflow-part-3/inputs/mandatory-escalation.json

uv run --locked --env-file .env python agentic-workflow-part-3/run.py \
  agentic-workflow-part-3/inputs/insufficient-documentation.json
```

Omit `--env-file .env` if variables are already exported in your shell. The application does not load `.env` itself. Do not commit credentials. Choose an available OpenAI-compatible chat model supporting JSON-object responses and `max_completion_tokens`. Per-request timeout and output-token settings are shared with the invoice workflow; defaults remain 30 seconds and 512 output tokens, with no automatic retries or fake-AI fallback.

| Sample | Expected outcome | What it demonstrates |
| --- | --- | --- |
| `answerable.json` | `draft_for_review` | Approved password-reset instructions support a cited reply, which is never sent |
| `mandatory-escalation.json` | `escalated` | Billing and an exception request require a human even if the model finds sufficient evidence |
| `insufficient-documentation.json` | `escalated` | Approved documents do not cover custom offline hardware-key recovery; unapproved draft notes cannot be used |

Live outcomes depend on valid model decisions. All three paths are also tested through the installed SDK with an in-memory HTTP transport. A live end-to-end run requires your proxy key and an available model; the tests do not establish live service availability or model quality.

## Read the controlled flow

[`support_demo/workflow.py`](support_demo/workflow.py) exposes the entire orchestration:

1. **Read ticket — code:** validate one JSON input before any AI call.
2. **Classify — AI:** choose allowed product area, issue type, urgency, customer tier, and whether an exception is requested. Code validates the result.
3. **Retrieve — code and bounded AI:** code retrieves the selected account's history and entitlements, then AI selects approved knowledge queries or finishes this stage early.
4. **Assess — AI:** determine whether retrieved approved documentation supports an answer, with evidence references and a concise summary, not a numerical confidence score.
5. **Route — code:** enforce escalation for billing/legal cases, exception requests, or insufficient evidence.
6. **Draft — AI, only when permitted:** produce a response with validated citations.
7. **Review — code:** queue every valid draft for simulated human review; never send it.

Escalation is a predefined terminal branch that skips drafting. Retrieval is the **only** stage with a model-directed loop. Classification, assessment, and drafting each happen at most once; the model cannot restart stages or choose arbitrary actions.

### Retrieval permissions and budget

The default budget is **three tool calls total**, including:

- One code-owned `lookup_account` call, scoped to the input account.
- Up to two AI-selected `search_knowledge` calls, including refinements.

Set `SUPPORT_MAX_RETRIEVAL_CALLS` to a positive integer to change the total budget. A budget of one leaves no knowledge searches and therefore no valid sufficient-evidence answer. Python checks scope, arguments, and remaining budget before tool execution. Reaching the limit stops retrieval; it does not prevent drafting if sufficient evidence has already been retrieved. Without sufficient evidence, the case escalates.

The model's retrieval decision is one of two validated JSON objects:

```json
{"action":"search","tool":"search_knowledge","query":"forgotten password reset"}
```

```json
{"action":"finish_retrieval","tool":null,"query":null}
```

There are no native model tool calls. Python validates the bounded decision and dispatches the permitted local search. Unknown tools, stages, extra arguments, or malformed output terminate as technical failures.

`search_knowledge` matches distinct lowercase alphanumeric query terms against article titles and content, excluding common stop words. It returns up to three matching articles ordered by match count, then article ID. Only **approved** articles in the classified product area are eligible. Queries are search text, not paths, URLs, code, or filesystem commands. Retrieved documents accumulate across refinements, and the model sees previous queries, observations, and the remaining budget.

## Follow the terminal story

The output makes each decision owner visible. For an answerable ticket, representative messages include:

```text
[AI] 2/classify: product_area=accounts, issue_type=how_to, urgency=normal, customer_tier=premium, requests_exception=False
[TOOL] 3/retrieve: Call 1/3: code-owned account lookup scoped to ACCT-101.
[AI] 3/retrieve: Selected search_knowledge query: reset password
[TOOL] 3/retrieve: Call 2/3: search approved accounts articles only.
[TOOL] 3/retrieve: Retrieved: KB-RESET
[AI] 3/retrieve: Finish retrieval early; code advances to the fixed assessment stage.
[AI] 4/assess: sufficient=True; evidence=['KB-RESET']; Approved reset instructions cover this ticket.
[CODE] 5/route: Evidence and policy permit drafting only; human review remains mandatory.
[CODE] 7/review: Queue the local draft for human review. No customer message was sent.
[RESULT] final: draft_for_review
```

Actual queries, assessment summaries, and draft wording may differ. The terminal also shows the validated draft. Output records observable contributions and evidence, not private model reasoning or raw SDK payloads.

## Input, fixtures, and evidence rules

A ticket is a nonempty UTF-8 `.json` file of at most 32 KiB, with exactly:

- `id`, `account_id`: 1–64 ASCII letters, digits, or hyphens, starting with a letter or digit.
- `customer_tier`: `standard`, `premium`, or `enterprise`.
- `subject`: nonblank text, at most 300 characters after trimming.
- `body`: nonblank text, at most 8,000 characters after trimming.

The declared tier is metadata, not authorization. AI must preserve it, and code checks it against the authoritative account returned by the scoped lookup. Unknown accounts or tier mismatches terminate as technical failures.

AI classification uses product areas `accounts`, `workspace`, or `billing`; issue types `how_to`, `technical`, `billing`, or `legal`; urgency `low`, `normal`, `high`, or `critical`; and a boolean `requests_exception`. Unknown labels and extra fields cannot proceed. Code escalates any billing product-area case, billing/legal issue type, or classified exception request.

Local read-only supporting data lives in [`fixtures/accounts.json`](fixtures/accounts.json) and [`fixtures/knowledge.json`](fixtures/knowledge.json). Duplicate fixture IDs or malformed records are technical failures.

A sufficient assessment requires at least one distinct citation to an approved article actually retrieved in this run. Every reference is validated even when the assessment is insufficient. Draft citations must be a nonempty subset of assessed evidence and match the body's `[KB-ARTICLE-ID]` markers. Nonexistent, unretrieved, unapproved, duplicate, or mismatched citations are technical failures, not a license to improvise.

Citation validation establishes reference integrity, not factual correctness of every sentence. AI can misclassify or misunderstand evidence. Mandatory human review and the absence of any sending capability are enforced regardless of model accuracy. Tickets and retrieved content are untrusted data and cannot change the tool registry, data scope, stage graph, or review policy.

## Artifacts and verification

Each run creates an ignored `outputs/support-.../` directory containing:

- `result.json`: approach, input reference, outcome, classification, local account context, retrieved article IDs, retrieval counts/limit, assessment, draft or escalation, simulated review state, and `sent: false`.
- `trace.jsonl`: append-only ordered execution events, tool activity, validated AI contributions, and evidence references.

Failures record a safe error code, message, and stage when artifacts can be written. Fixtures never change, and previous runs are not used as business state. Draft-for-review and escalation outcomes exit **0**; technical failures exit **1**; CLI usage errors exit **2**. Artifact failures never claim that results were saved.

```sh
uv run --locked pytest -q
uv run --locked pytest agentic-workflow-part-3/tests -q
uv run --locked python agentic-workflow-part-3/run.py --help
```

Tests block real network access. They cover all sample outcomes, query refinement and early finish, exact budget enforcement, tier/scope checks, malformed decisions, invalid citations, forced escalation, no sending, fixture isolation, credential redaction, and complete SDK-backed flows using in-memory responses.

## Why this differs from both alternatives

| Dimension | This agentic workflow | Deterministic invoice workflow | Incident agent |
| --- | --- | --- | --- |
| Code control | Fixed stages and permitted branches, scopes, limits, review | All process decisions and routing | Permissions and budgets, not a predefined investigation sequence |
| AI decisions | Classification, retrieval queries/early finish, sufficiency, draft | Extraction only | Next tool or conclusion based on observations |
| Available actions | Scoped account lookup and bounded approved knowledge search | Code-owned reference checks after one extraction | Multiple investigation tool families selected dynamically |
| Stopping | Code-owned escalation or review queue, or technical failure | Code-owned invoice route or technical failure | Conclusion, insufficient evidence, budget limit, or failure |

The retrieval loop supplies bounded agency; it does not turn the whole application into an autonomous agent.

## Code map

- [`run.py`](run.py), [`support_demo/cli.py`](support_demo/cli.py): one-ticket CLI.
- [`support_demo/workflow.py`](support_demo/workflow.py): stages, branches, escalation, and review.
- [`support_demo/models.py`](support_demo/models.py): input, fixture, and decision schemas.
- [`support_demo/retrieval.py`](support_demo/retrieval.py): local tool permissions, search, and call budget.
- [`support_demo/ai.py`](support_demo/ai.py): stage-specific prompts and schemas.
- [`demo_common/`](../demo_common/): shared SAP SDK transport, configuration, safe errors, and terminal/artifact formatting—no shared orchestration.

Authoritative behavioral contract and acceptance checks: [`docs/automations.spec`](../docs/automations.spec).
