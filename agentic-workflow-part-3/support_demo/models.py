"""Validated boundaries for tickets, local fixtures, and bounded AI decisions."""

import json
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
    model_validator,
)

from demo_common.errors import DemoError

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")]
ArticleID = Annotated[str, StringConstraints(pattern=r"^KB-[A-Z0-9-]{1,60}$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
ProductArea = Literal["accounts", "workspace", "billing"]
CustomerTier = Literal["standard", "premium", "enterprise"]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Ticket(StrictModel):
    id: Identifier
    account_id: Identifier
    customer_tier: CustomerTier
    subject: ShortText
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class Classification(StrictModel):
    product_area: ProductArea
    issue_type: Literal["how_to", "technical", "billing", "legal"]
    urgency: Literal["low", "normal", "high", "critical"]
    customer_tier: CustomerTier
    requests_exception: bool


class Account(StrictModel):
    id: Identifier
    tier: CustomerTier
    entitlements: list[ShortText]
    history: list[ShortText]


class Accounts(StrictModel):
    accounts: list[Account]


class Article(StrictModel):
    id: ArticleID
    product_area: ProductArea
    approved: bool
    title: ShortText
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Knowledge(StrictModel):
    articles: list[Article]


class RetrievalDecision(StrictModel):
    action: Literal["search", "finish_retrieval"]
    tool: Literal["search_knowledge"] | None
    query: ShortText | None

    @model_validator(mode="after")
    def bounded_action(self) -> Self:
        if self.action == "search" and (self.tool is None or self.query is None):
            raise ValueError("Search requires the allowed tool and a query")
        if self.action == "finish_retrieval" and (self.tool is not None or self.query is not None):
            raise ValueError("Finish cannot carry a tool or arguments")
        return self


class Assessment(StrictModel):
    sufficient: bool
    citations: list[ArticleID]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class Draft(StrictModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2400)]
    citations: list[ArticleID]


def parse_model[Model: BaseModel](payload: str, schema: type[Model], *, code: str = "invalid_model_output") -> Model:
    def unique_keys(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError("Duplicate JSON key")
            data[key] = value
        return data

    try:
        return schema.model_validate(json.loads(payload, object_pairs_hook=unique_keys))
    except (ValueError, TypeError, ValidationError) as exc:
        messages = {
            "invalid_input": "Ticket must match the documented JSON schema.",
            "invalid_reference_data": "Local support fixtures are malformed or invalid.",
        }
        raise DemoError(code, messages.get(code, "AI returned an invalid or unauthorized structured decision.")) from exc
