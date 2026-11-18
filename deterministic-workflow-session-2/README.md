1. Deterministic workflow: invoice approval pipeline

Project: Invoice-to-ERP Approval Pipeline

Build a local demonstration that ingests a synthetic invoice text file, validates it, checks it against a local purchase order, and routes it for simulated approval or exception handling. PDF parsing and OCR are outside the initial scope. The sequence never changes; only the data and branch conditions change. This is a classic deterministic automation case: the code owns the rules and transitions.

Fixed pipeline:

1 Read the invoice text file selected by command-line path.

2 Extract fields—vendor, invoice number, amount, currency, due date.

3 Validate required fields and business rules.

4 Detect duplicates.

5 Match the invoice to a purchase order.

6 Route: simulate auto-approval, queue simulated manager review, or flag as an exception.

7 Record an append-only audit trail within the run's local artifacts, without modifying fixtures or carrying business state between runs.

Where AI appears: only inside the fixed structured-field extraction step. The application—not the model—decides whether the invoice passes validation and what happens next.

Why it is deterministic: every permitted state, transition, and action is known in advance; identical extracted fields and reference data always produce the same routing decision. This does not promise identical output from repeated AI extraction calls.

See [`docs/automations.spec`](../docs/automations.spec) for the authoritative behavioral contract and acceptance checks. This README describes the intended demonstration; execution instructions will be added after implementation.