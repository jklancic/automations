2. Agentic workflow: support-ticket triage and response

Project: Customer Support Triage and Draft-Reply System

Build a support system where tickets arrive in unstructured form, but the downstream process is still controlled. The model can classify the ticket, retrieve relevant knowledge, and draft a response, while your orchestration code defines the available stages, approvals, and escalation rules. This fits an agentic workflow: the model makes bounded decisions within a path the business designed.

Controlled flow:

1. Receive a customer ticket.

2. Classify product area, issue type, urgency, and customer tier.

3. Retrieve account history, entitlements, and relevant knowledge-base articles.

4. Assess whether approved local documentation provides sufficient evidence.

5. Escalate when evidence is insufficient, the issue is billing/legal, or the customer asks for an exception. Application code enforces these branches; no numerical model-confidence threshold is used.

6. Otherwise, draft a response with valid documentation citations.

7. Queue every draft for simulated support-agent review. Never send a customer message.

Where agency appears: the model chooses and refines retrieval queries within one bounded stage, classifies the ticket, and assesses whether available documentation is sufficient. Application code applies escalation policy to those validated assessments. The model cannot invent new stages, send email directly, or bypass approval.

Why it is agentic but not an agent: the overall flow is predefined—classify, retrieve, assess, then escalate or draft for review—but the model has discretion at specified decision points. It cannot restart arbitrary stages.

See [`docs/automations.spec`](../docs/automations.spec) for the authoritative behavioral contract and acceptance checks. Inputs and supporting data are synthetic local fixtures; review and escalation are local artifacts. This README describes the intended demonstration; execution instructions will be added after implementation.