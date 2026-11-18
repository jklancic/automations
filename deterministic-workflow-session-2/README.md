1. Deterministic workflow: invoice approval pipeline

Project: Invoice-to-ERP Approval Pipeline

Build a service that ingests an invoice PDF, validates it, checks it against a purchase order, and routes it for approval or exception handling. The sequence never changes; only the data and branch conditions change. This is a classic deterministic automation case: the code owns the rules and transitions.

Fixed pipeline:

1 Receive an invoice upload.

2 Extract fields—vendor, invoice number, amount, currency, due date.

3 Validate required fields and business rules.

4 Detect duplicates.

5 Match the invoice to a purchase order.

6 Route: auto-approve, send to manager approval, or flag as an exception.

7 Record an immutable audit trail.

Where AI may appear: only inside a fixed extraction step, such as OCR plus structured-field extraction. The application—not the model—decides whether the invoice passes validation and what happens next.

Why it is deterministic: every permitted state, transition, and action is known in advance; the same invoice data should always produce the same routing decision.