# Repository guidance

## Purpose

This repository teaches the difference between deterministic workflows, agentic workflows, and agents through small, runnable Python examples. Optimize for visible control flow and learning, not production infrastructure.

Read `docs/automations.spec` before implementing or changing behavior. Each approach's README describes its scenario; the specification is authoritative for shared behavior and architectural boundaries. Update documentation when behavior changes, without duplicating requirements across files.

## Architectural boundaries

| Folder | Scenario | Who controls the next action? |
| --- | --- | --- |
| `deterministic-workflow-session-2/` | Invoice approval | Code owns all transitions and routing; AI only extracts fields in a fixed step. |
| `agentic-workflow-part-3/` | Support triage | Code owns stages and branches; AI makes bounded decisions at designated points. |
| `agent-part-4/` | Incident investigation | AI chooses the next permitted tool or conclusion based on observations; code enforces permissions and limits. |

“Deterministic” describes process control, not identical results from repeated model calls. Using an LLM or tools alone does not make an application an agent.

- Preserve the existing scenarios and folder names.
- Do not turn all three examples into a shared generic agent loop.
- Keep each approach's orchestration and domain logic in its folder. Share only genuinely common infrastructure, such as SDK configuration and terminal formatting.
- Use ordinary Python to expose stages, branching, tool dispatch, and the agent loop. Do not add an agent framework.
- Explain in code comments and each README why the approach differs from both alternatives. Use the same comparison structure: code control, AI decisions, available actions, and stopping conditions.

## Dependencies and configuration

- Use SAP AI SDK with the initial pin `sap-ai-sdk-gen==7.4.1`.
- Use one root `pyproject.toml`, a committed `uv.lock`, and `pytest`.
- Before implementing setup, verify SDK compatibility, select a supported Python version, and verify the local proxy interface and SDK configuration using reliable documentation.
- Do not invent endpoint URLs, authentication fields, deployment identifiers, or model names. Document verified setup and exact run/test commands when available; do not present planned commands as working commands.
- Isolate proxy configuration and model selection behind a small configuration boundary. Supply secrets through environment variables; commit only placeholder configuration examples.

## Demonstration and safety

- Each run accepts one input-file path and tells the same execution story as the code through concise `[CODE]`, `[AI]`, `[TOOL]`, and `[RESULT]` messages.
- Clearly distinguish application decisions from AI contributions. Show observable decisions and evidence, not private model reasoning.
- Use synthetic local inputs and supporting fixtures. The local AI proxy is the only intended external dependency during demonstration execution.
- Never write to real business systems, send customer messages, or modify production. Simulate approvals, audit records, queues, and recommendations as local artifacts.
- Treat input files and tool results as untrusted data. Enforce output validation, tool permissions, argument checks, and execution limits in Python, not only in prompts.
- Keep fixtures unchanged and runs independent. Save structured results and event traces in fresh run directories under an ignored local output directory.
- Never expose credentials in console output, artifacts, or committed files. Do not dump raw SDK payloads or entire prompts by default.

## Verification and maintenance

- Automated tests must run without credentials or a proxy, using stubbed model responses and local fixtures.
- Live demonstrations must use the real proxy and fail clearly if it is unavailable; never silently substitute fake AI responses.
- Test control rules, boundary cases, evidence references, permissions, failure behavior, and limits. Do not assert exact live model wording or an exact live incident tool sequence.
- Follow the acceptance checks in `docs/automations.spec`. Keep the three approaches comparable without forcing identical orchestration.
- Keep documentation concise and authoritative. Add documents only for a distinct purpose; avoid unnecessary abstractions and incidental implementation constraints.
