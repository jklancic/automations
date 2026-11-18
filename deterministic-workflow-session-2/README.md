# Deterministic workflow: invoice approval

A runnable, local invoice-to-approval demonstration. AI extracts five fields from invoice text; ordinary Python validates them, checks local records, and selects a simulated routing outcome. No ERP integration, real approval, or production write occurs.

## Run it

From the repository root, with `uv` installed:

```sh
uv sync --locked
```

The root project uses Python 3.12 and pins `sap-ai-sdk-gen==7.4.1`. OpenAI is constrained to version 2 because SAP SDK 7.4.1 uses `httpx`, whereas OpenAI 3 switched to `httpx2`. The lockfile records the resolved versions. SDK dependencies include LangChain packages, but this demonstration does not import or use an agent framework.

Start your local HAI proxy separately, then set configuration in your shell:

```sh
export AI_PROXY_URL='http://localhost:6655/openai/v1'
export AI_MODEL='REPLACE_WITH_AN_AVAILABLE_CHAT_MODEL'
read -r -s -p 'Local proxy API key: ' AI_PROXY_API_KEY; printf '\n'
export AI_PROXY_API_KEY
```

The key belongs to the **local proxy**, not an SAP AI Core service key. Select an available OpenAI-compatible chat model supporting JSON-object responses and `max_completion_tokens`; no model name is hardcoded. SAP `cohere--` aliases are rejected because that SDK compatibility path removes the output-token cap. The example key prompt above uses Bash. In other shells, use their equivalent hidden-input mechanism; never commit the key or put it in a command saved in shell history.

`.env.example` lists the configuration variables; the application does **not** automatically load `.env` files. If you store settings in a root `.env`, add `--env-file .env` to `uv run` so uv loads them into the process environment; activating `.venv` alone does not do this. Use a loopback proxy URL without embedded credentials, query parameters, or fragments. Defaults are a 30-second request timeout and a 512-token output cap, configurable through positive finite `AI_TIMEOUT_SECONDS` and positive integer `AI_MAX_OUTPUT_TOKENS`. There is one extraction request and no automatic retry.

Select one bundled invoice:

```sh
uv run --locked --env-file .env python deterministic-workflow-session-2/run.py deterministic-workflow-session-2/inputs/auto-approval.txt
uv run --locked --env-file .env python deterministic-workflow-session-2/run.py deterministic-workflow-session-2/inputs/manager-review.txt
uv run --locked --env-file .env python deterministic-workflow-session-2/run.py deterministic-workflow-session-2/inputs/exception.txt
```

These commands assume a configured `.env`; omit `--env-file .env` if you used the shell exports above. They are live-proxy commands, not offline simulations. SDK request construction is tested with an in-memory HTTP transport; an end-to-end live run requires your key and model configuration. If configuration is absent or the proxy fails, execution exits nonzero with a clear error rather than substituting fake AI.

| Sample | Fields used by the tests | Expected business outcome |
| --- | --- | --- |
| `auto-approval.txt` | Northwind Office Supplies; INV-2026-101; EUR 750.00 | Simulated auto-approval, matching PO-101 |
| `manager-review.txt` | Contoso Training; INV-2026-202; EUR 1500.00 | Simulated manager review, matching PO-202 |
| `exception.txt` | Fabrikam Maintenance; INV-2026-303; EUR 900.00 | Duplicate invoice exception |

Expected live outcomes assume the model extracts the stated fields correctly. Process control is deterministic; repeated extraction calls need not return identical values.

## Follow the story

The fixed stages are visible in [`invoice_demo/workflow.py`](invoice_demo/workflow.py):

1. **Read input:** code rejects invalid files before AI.
2. **Extract fields:** AI returns vendor, invoice number, amount, currency, and due date; Python validates its schema.
3. **Validate:** code checks required fields and business formats.
4. **Detect duplicates:** code reads approved local reference records.
5. **Match a PO:** code compares vendor, decimal amount, and currency.
6. **Route:** code selects exception, simulated auto-approval, or simulated manager review.
7. **Audit:** code records the outcome in this run's append-only event trace and structured result.

Business failures take predefined exception branches. Invalid fields skip reference checks; duplicates skip PO matching. Neither the model nor a tool result can invent a new stage.

An illustrative auto-approval run includes:

```text
[CODE] 1/read_input: Read the selected local invoice; reject invalid files before AI.
[AI] 2/extract_fields: Extract five fields only; AI cannot approve or choose the next stage.
[AI] 2/extract_fields: Received 5/5 non-null fields; schema accepted. vendor=Northwind Office Supplies, invoice_number=INV-2026-101, amount=750.00, currency=EUR, due_date=2026-12-15
[CODE] 3/validate: Required fields valid; amount 750.00 EUR; date is valid ISO format.
[TOOL] 4/duplicate_check: Read approved local reference records; no network or model-directed tool use.
[CODE] 4/duplicate_check: No duplicate in bundled records; previous runs are not consulted.
[CODE] 5/match_purchase_order: Matched PO-101 on vendor, decimal amount, and currency.
[CODE] 6/route: Amount <= 1000.00 EUR: simulate auto-approval.
[CODE] 7/audit: Record outcome in this run's append-only trace and JSON result; fixtures stay unchanged.
[RESULT] final: auto_approved
[RESULT] Artifacts saved under .../outputs/invoice-...
```

`[TOOL]` identifies a **code-owned local lookup**, not a model tool call. Output summarizes observations and decisions, not private model reasoning or raw SDK payloads.

## Input, validation, and matching rules

Inputs are nonempty UTF-8 `.txt` files, at most 32 KiB, without binary/control data (newlines, carriage returns, and tabs are allowed). Missing business fields are not file-format failures. PDF parsing and OCR are outside this implementation.

AI must return exactly the five named JSON keys, each a string of at most 160 characters or `null`. Extra keys, missing keys, duplicate JSON keys, non-string values, refused/truncated responses, or requested tool/function calls are technical failures. `null` and blank strings represent missing business values and route to exception.

Python trims extracted fields and enforces:

- Every field is required.
- Vendor text must be printable and nonempty.
- Invoice numbers use 1–64 ASCII letters, digits, or hyphens, starting with a letter or digit.
- Amounts are positive decimal strings with at most two fractional digits and at most 12 integer digits; no floats, exponent notation, NaN, separators, or leading zeroes other than zero itself.
- Currency is exactly `EUR` for these fixtures.
- Due date is a valid calendar date in `YYYY-MM-DD` format. It is not compared with today's date, keeping runs independent of the clock.

[`fixtures/reference-data.json`](fixtures/reference-data.json) is the only business reference source:

- Duplicate key: trimmed, case-insensitive vendor + trimmed, case-sensitive invoice number.
- PO match: trimmed, case-insensitive vendor + equal decimal amount + exact currency. Invoice text need not contain a PO ID.
- Exactly one PO must match. No match or multiple matching POs routes to exception.
- A unique valid match with amount **<= 1,000 EUR** receives simulated auto-approval; a larger amount receives simulated manager review.

These are teaching rules, not real financial policy. Fixture corruption is a technical failure, not a business exception. Selected documents are untrusted data; the AI has no tools or approval authority. AI extraction can still be inaccurate, so this is not a production invoice-validation system.

## Artifacts and exit status

Every run creates a fresh `outputs/invoice-.../` directory at the repository root, ignored by Git:

- `result.json`: approach, input reference, outcome, extracted invoice, reasons, matching PO when applicable, and `simulated: true`. Technical failures add a safe error code, message, and stage.
- `trace.jsonl`: ordered, timestamped code/AI/tool/result events with summaries and fixture evidence references.

The trace is append-only within a run, not a production-grade immutable audit system. Fixtures remain unchanged, and earlier run artifacts are never used for duplicate detection. Credentials and raw SDK exceptions are not printed or saved.

Business outcomes (`auto_approved`, `manager_review`, `exception`) exit **0**. Technical failures exit **1**; CLI usage errors exit **2**. Failure artifacts are saved when possible. An artifact-write failure exits nonzero and does not claim results were saved.

## Why this is neither of the other approaches

| Comparison | This deterministic workflow | Other approach |
| --- | --- | --- |
| Code control | Every stage, permitted exception branch, and routing rule | An agentic workflow also has fixed stages, but delegates bounded decisions at designated points |
| AI decisions | Field extraction only; no process decisions | Support triage delegates classification, retrieval queries, and evidence sufficiency |
| Available actions | One AI extraction request; code-owned local lookups | An agent chooses its next permitted tool using observations |
| Stopping | Code-owned routing outcome or technical failure | Incident investigation can end with a model conclusion, insufficient evidence, or a budget limit |

Adding an LLM does not make this agentic. Adding a local lookup does not make it an agent. For identical extracted fields and reference records, Python always selects the same route.

## Tests and code map

```sh
uv run --locked pytest -q
uv run --locked python deterministic-workflow-session-2/run.py --help
```

Tests block real network connections and use stubbed extraction responses or an in-memory HTTP transport with the installed SAP SDK. They require no credentials or running proxy. Coverage includes sample outcomes, the exact 1,000 boundary, missing/invalid fields, duplicates and PO mismatches, malformed model output, guardrails, request limits, failure handling, artifact isolation, and credential redaction.

- [`run.py`](run.py), [`invoice_demo/cli.py`](invoice_demo/cli.py): one-file CLI and exit status.
- [`invoice_demo/workflow.py`](invoice_demo/workflow.py): fixed orchestration and exception branches.
- [`invoice_demo/domain.py`](invoice_demo/domain.py): structured fields and code-owned validation/matching/routing.
- [`invoice_demo/extraction.py`](invoice_demo/extraction.py): invoice prompt and the single extraction request through shared SDK transport.
- [`invoice_demo/artifacts.py`](invoice_demo/artifacts.py): compatibility import for shared terminal/artifact formatting.
- [`demo_common/`](../demo_common/): proxy configuration and adapter, SDK transport, safe errors, and terminal/artifact infrastructure. No invoice orchestration is shared.

Authoritative shared behavior and acceptance checks: [`docs/automations.spec`](../docs/automations.spec). SDK integration was verified against [SAP's documentation](https://help.sap.com/doc/generative-ai-hub-sdk/CLOUD/en-US/index.html) and the installed 7.4.1 source; the local route is the supplied HAI `/openai/v1` endpoint.
