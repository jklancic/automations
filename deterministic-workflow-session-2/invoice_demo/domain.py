"""Invoice policy is ordinary Python, independent of the model and SDK."""

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from .errors import DemoError

Text = Annotated[str, StringConstraints(max_length=160)]
APPROVAL_LIMIT = Decimal("1000.00")
CURRENCY = "EUR"


class InvoiceFields(BaseModel):
    # Null means a missing business field; a missing JSON key is malformed output.
    model_config = ConfigDict(strict=True, extra="forbid")
    vendor: Text | None
    invoice_number: Text | None
    amount: Text | None
    currency: Text | None
    due_date: Text | None


class PurchaseOrder(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    id: Text
    vendor: Text
    amount: Text
    currency: Text


class RecordedInvoice(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    vendor: Text
    invoice_number: Text


class ReferenceData(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    purchase_orders: list[PurchaseOrder]
    recorded_invoices: list[RecordedInvoice]


def parse_fields(payload: str) -> InvoiceFields:
    try:
        # Reject duplicate JSON keys instead of silently accepting the last value.
        def unique_keys(pairs):
            values = {}
            for key, value in pairs:
                if key in values:
                    raise ValueError("Duplicate key")
                values[key] = value
            return values

        data = json.loads(payload, object_pairs_hook=unique_keys)
        return InvoiceFields.model_validate(data)
    except (ValueError, TypeError, ValidationError) as exc:
        raise DemoError("invalid_model_output", "AI extraction returned invalid structured fields.") from exc


def money(value: str) -> Decimal | None:
    # No binary floats, exponent notation, NaN, separators, or sub-cent precision.
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?", value):
        return None
    amount = Decimal(value)
    return amount if amount > 0 else None


def validate_invoice(fields: InvoiceFields) -> tuple[InvoiceFields, list[str]]:
    fields = InvoiceFields(**{
        key: value.strip() if value is not None else None
        for key, value in fields.model_dump().items()
    })
    reasons = [f"missing_{key}" for key, value in fields.model_dump().items() if not value]
    if fields.invoice_number and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}", fields.invoice_number):
        reasons.append("invalid_invoice_number")
    if fields.vendor and any(not char.isprintable() for char in fields.vendor):
        reasons.append("invalid_vendor")
    if fields.amount and money(fields.amount) is None:
        reasons.append("invalid_amount")
    if fields.currency and fields.currency != CURRENCY:
        reasons.append("unsupported_currency")
    if fields.due_date:
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", fields.due_date):
                raise ValueError("Non-ISO date")
            date.fromisoformat(fields.due_date)
        except ValueError:
            reasons.append("invalid_due_date")
    return fields, reasons


def load_references(path: Path) -> ReferenceData:
    try:
        references = ReferenceData.model_validate_json(path.read_text(encoding="utf-8"))
        ids = set()
        for po in references.purchase_orders:
            if (not po.id.strip() or po.id in ids or not po.vendor.strip()
                    or po.currency != CURRENCY or money(po.amount) is None):
                raise ValueError("Invalid purchase order fixture")
            ids.add(po.id)
        for recorded in references.recorded_invoices:
            if not recorded.vendor.strip() or not recorded.invoice_number.strip():
                raise ValueError("Invalid recorded invoice fixture")
        return references
    except (OSError, UnicodeError, ValueError, ValidationError) as exc:
        raise DemoError("invalid_reference_data", "Local reference data is unreadable or invalid.") from exc


def is_duplicate(fields: InvoiceFields, references: ReferenceData) -> bool:
    return any(
        entry.vendor.strip().casefold() == fields.vendor.casefold()
        and entry.invoice_number.strip() == fields.invoice_number
        for entry in references.recorded_invoices
    )


def matching_orders(fields: InvoiceFields, references: ReferenceData) -> list[PurchaseOrder]:
    return [
        po for po in references.purchase_orders
        if po.vendor.strip().casefold() == fields.vendor.casefold()
        and po.currency == fields.currency
        and money(po.amount) == money(fields.amount)
    ]


def approval_route(fields: InvoiceFields) -> str:
    # The model cannot approve anything: only this fixed rule selects the route.
    return "auto_approved" if money(fields.amount) <= APPROVAL_LIMIT else "manager_review"
