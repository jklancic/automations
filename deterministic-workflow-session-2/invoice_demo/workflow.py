"""Read this function to see the whole fixed pipeline and its exception branches."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .artifacts import Story
from .domain import (
    approval_route,
    is_duplicate,
    load_references,
    matching_orders,
    money,
    parse_fields,
    validate_invoice,
)
from .errors import DemoError

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT.parent / "outputs"
REFERENCE_PATH = PROJECT / "fixtures" / "reference-data.json"
MAX_INPUT_BYTES = 32_768


@dataclass(frozen=True)
class Run:
    result: dict
    directory: Path

    @property
    def exit_code(self):
        return 1 if self.result["outcome"] == "technical_failure" else 0


def read_input(path: Path) -> str:
    if path.suffix.lower() != ".txt":
        raise DemoError("invalid_input", "Select one UTF-8 .txt invoice file.")
    try:
        if not path.is_file():
            raise OSError("Not a regular file")
        with path.open("rb") as handle:
            data = handle.read(MAX_INPUT_BYTES + 1)
        if not data or len(data) > MAX_INPUT_BYTES:
            raise ValueError("Empty or oversized invoice")
        text = data.decode("utf-8")
        if not text.strip() or any(not char.isprintable() and char not in "\n\r\t" for char in text):
            raise ValueError("Not invoice text")
        return text
    except (OSError, UnicodeError, ValueError) as exc:
        raise DemoError("invalid_input", "Invoice must be readable, nonempty UTF-8 text of at most 32 KiB, without binary/control data.") from exc


def run_invoice(input_path: Path, *, extract: Callable[[str], str] | None = None,
                output_root: Path = DEFAULT_OUTPUT_ROOT,
                reference_path: Path = REFERENCE_PATH,
                stream: TextIO | None = None) -> Run:
    story = Story(output_root, stream, prefix="invoice-")
    result = {
        "approach": "deterministic_workflow",
        "input_reference": str(input_path),
        "outcome": None,
        "result": {"invoice": None, "reasons": [], "purchase_order": None, "simulated": True},
    }
    stage = "1/read_input"
    try:
        story.event("CODE", stage, "Read the selected local invoice; reject invalid files before AI.")
        text = read_input(input_path)

        # Neither a bounded decision workflow nor an agent: the model gets no
        # tools, routing decisions, or next-step choices. This is its only call.
        stage = "2/extract_fields"
        story.event("AI", stage, "Extract five fields only; AI cannot approve or choose the next stage.")
        if extract is None:
            from .extraction import extract_invoice
            extract = extract_invoice
        fields = parse_fields(extract(text))
        present = sum(value is not None for value in fields.model_dump().values())
        summary = ", ".join(
            f"{name}={value if value is not None else '(missing)'}"
            for name, value in fields.model_dump().items()
        )
        story.event("AI", stage, f"Received {present}/5 non-null fields; schema accepted. {summary}", fields=fields.model_dump())

        stage = "3/validate"
        fields, reasons = validate_invoice(fields)
        result["result"]["invoice"] = fields.model_dump()
        result["result"]["reasons"] = reasons
        if reasons:
            story.event("CODE", stage, "Business validation failed: " + ", ".join(reasons))
            story.event("CODE", "4-5/reference_checks", "Skip duplicate/PO checks: code routes invalid business fields to exception.")
        else:
            amount = money(fields.amount)
            story.event("CODE", stage, f"Required fields valid; amount {amount:.2f} EUR; date is valid ISO format.")
            stage = "4/duplicate_check"
            story.event("TOOL", stage, "Read approved local reference records; no network or model-directed tool use.", evidence_reference="fixtures/reference-data.json")
            references = load_references(reference_path)
            if is_duplicate(fields, references):
                reasons.append("duplicate_invoice")
                story.event("CODE", stage, "Vendor + invoice number already exist in bundled records.")
                story.event("CODE", "5/match_purchase_order", "Skip PO matching: duplicate invoices go directly to exception.")
            else:
                story.event("CODE", stage, "No duplicate in bundled records; previous runs are not consulted.")
                stage = "5/match_purchase_order"
                orders = matching_orders(fields, references)
                if len(orders) != 1:
                    reasons.append("purchase_order_mismatch" if not orders else "ambiguous_purchase_order")
                    story.event("CODE", stage, "No unique PO match on vendor, decimal amount, and currency.")
                else:
                    result["result"]["purchase_order"] = orders[0].id
                    story.event("CODE", stage, f"Matched {orders[0].id} on vendor, decimal amount, and currency.", evidence_reference=f"fixtures/reference-data.json#{orders[0].id}")

        stage = "6/route"
        if reasons:
            outcome = "exception"
            message = "Route to exception: " + ", ".join(reasons) + "; no approval performed."
        else:
            outcome = approval_route(fields)
            message = (
                "Amount <= 1000.00 EUR: simulate auto-approval."
                if outcome == "auto_approved"
                else "Amount > 1000.00 EUR: queue simulated manager review."
            )
        result["outcome"] = outcome
        story.event("CODE", stage, message)
        stage = "7/audit"
        story.event("CODE", stage, "Record outcome in this run's append-only trace and JSON result; fixtures stay unchanged.")
    except DemoError as exc:
        result["outcome"] = "technical_failure"
        result["result"]["error"] = {"code": exc.code, "message": str(exc), "stage": stage}
    except Exception:  # noqa: BLE001 - sanitize unexpected errors at the CLI-facing boundary
        # Do not print a traceback containing SDK payloads, credentials, or inputs.
        result["outcome"] = "technical_failure"
        result["result"]["error"] = {
            "code": "execution_failed",
            "message": "Execution failed; no approval was completed.",
            "stage": stage,
        }

    message = result["result"].get("error", {}).get("message", result["outcome"])
    story.event("RESULT", "final", message, outcome=result["outcome"])
    return Run(story.result(result), story.directory)
