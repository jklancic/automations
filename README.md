# Automation control: workflows and agents

Three Python demonstrations of **who controls the next action: application code or the model**.

The examples use SAP AI SDK and a local AI proxy. They favor readable code and visible terminal execution over production infrastructure. Different business scenarios make each approach natural; a common comparison framework makes their architectural differences explicit.

## The three approaches

| Approach | Scenario | Code controls | AI decides | Status |
| --- | --- | --- | --- | --- |
| [Deterministic workflow](deterministic-workflow-session-2/README.md) | Invoice approval | Every stage, exception branch, and routing rule | Field extraction inside one fixed step | Implemented |
| [Agentic workflow](agentic-workflow-part-3/README.md) | Support-ticket triage and draft replies | Fixed stages, permitted branches, escalation, and review | Bounded classification, retrieval, evidence assessment, and drafting | Specified; not implemented |
| [Agent](agent-part-4/README.md) | Incident investigation | Permissions, validation, execution limits, and safety checks | Next permitted tool or conclusion, based on observations | Specified; not implemented |

**Deterministic does not mean identical AI output.** It means code owns process control: identical extracted fields and reference data produce identical invoice routing. Calling an LLM or using a tool alone does not make a system an agent.

Start with the invoice workflow, then compare its fixed orchestration with the other two designs. Each folder README explains available actions, stopping conditions, and why its approach differs from both alternatives.

## Quick start: invoice workflow

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/), Python 3.12 (which uv can provision), and a running local HAI proxy for live AI calls.

Run commands from the repository root:

```sh
uv sync --locked
```

Configure your shell using the [invoice setup instructions](deterministic-workflow-session-2/README.md#run-it):

- `AI_PROXY_API_KEY`: your local proxy key, kept out of source control and shell history.
- `AI_MODEL`: an available OpenAI-compatible chat model.
- `AI_PROXY_URL`: defaults to `http://localhost:6655/openai/v1`.

[`.env.example`](.env.example) lists configuration variables. **The application does not automatically load `.env` files**; variables must be supplied through the process environment.

Then select one sample invoice:

```sh
uv run --locked python deterministic-workflow-session-2/run.py \
  deterministic-workflow-session-2/inputs/auto-approval.txt
```

Other bundled inputs demonstrate simulated manager review and a duplicate-invoice exception. See the [invoice README](deterministic-workflow-session-2/README.md) for their commands, expected outcomes, business rules, and code map.

Live execution uses the real proxy. Missing configuration or a failed request produces a technical failure, never a silent fallback to fake AI. SDK request construction is tested offline; end-to-end live execution requires your key and model configuration.

## Watch the code's story

Terminal output distinguishes application decisions from AI contributions:

- `[CODE]`: fixed stages, validation, policy checks, and routing.
- `[AI]`: request purpose and validated extracted fields or other model contributions.
- `[TOOL]`: local lookups or tool activity, with ownership explained by the approach.
- `[RESULT]`: final outcome and artifact location.

Runs save `result.json` and an ordered `trace.jsonl` in fresh directories under the ignored `outputs/` folder. These show observable actions and evidence, not private model reasoning.

All business data is synthetic and local. Approvals, review queues, and recommendations are simulated. No real ERP writes, customer messages, or production changes occur.

## Verify without a proxy

```sh
uv run --locked pytest -q
```

The current suite covers the invoice workflow and its SAP SDK adapter. Tests block real network connections and use stubbed extraction responses or an in-memory HTTP transport, so no credentials or proxy are required.

One root [`pyproject.toml`](pyproject.toml) and [`uv.lock`](uv.lock) manage the shared environment, including `sap-ai-sdk-gen==7.4.1`. Orchestration and domain logic remain inside each approach's folder; no additional agent framework is used.

## Documentation map

- **This README:** repository overview, implementation status, and getting started.
- **Folder READMEs:** scenario explanations, architectural comparisons, and implementation-specific instructions.
- **[`docs/automations.spec`](docs/automations.spec):** authoritative behavioral contract and acceptance checks for all three approaches.
- **[`AGENTS.md`](AGENTS.md):** repository-wide guidance for coding assistants.
