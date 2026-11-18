2. Agentic workflow: support-ticket triage and response

Project: Customer Support Triage and Draft-Reply System

Build a support system where tickets arrive in unstructured form, but the downstream process is still controlled. The model can classify the ticket, retrieve relevant knowledge, and draft a response, while your orchestration code defines the available stages, approvals, and escalation rules. This fits an agentic workflow: the model makes bounded decisions within a path the business designed.

Controlled flow:

1. Receive a customer ticket.

2. Classify product area, issue type, urgency, and customer tier.

3. Retrieve account history, entitlements, and relevant knowledge-base articles.

4. Decide whether the case is answerable from approved documentation.

5. Draft a response with citations.

6. If confidence is low, the issue is billing/legal, or the customer asks for an exception, escalate to a human.

7. Queue the draft for support-agent review before sending.

Where agency appears: the model chooses which retrieval queries to run, decides whether the available documentation is sufficient, and determines whether an escalation branch is needed. But it cannot invent new stages, send email directly, or bypass approval.

Why it is agentic but not an agent: the overall flow is predefined—classify, retrieve, draft, review, escalate—but the model has discretion at specified decision points.