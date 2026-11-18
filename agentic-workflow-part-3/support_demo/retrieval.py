"""Read-only local retrieval with a code-enforced scope and shared call budget."""

import os
import re
from pathlib import Path

from demo_common.errors import DemoError

from .models import Accounts, Knowledge, parse_model

PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT / "fixtures"
STOP_WORDS = {"a", "an", "and", "the", "how", "can", "i", "my", "our", "to", "for", "is", "it", "of", "with", "do", "in"}


def configured_limit() -> int:
    try:
        limit = int(os.environ.get("SUPPORT_MAX_RETRIEVAL_CALLS", "3"))
        if limit < 1:
            raise ValueError("Nonpositive budget")
        return limit
    except ValueError as exc:
        raise DemoError("invalid_configuration", "SUPPORT_MAX_RETRIEVAL_CALLS must be a positive integer.") from exc


def load_fixture(path: Path, schema):
    try:
        with path.open("rb") as handle:
            raw = handle.read(131_073)
        if len(raw) > 131_072:
            raise ValueError("Oversized fixture")
        return parse_model(raw.decode("utf-8"), schema, code="invalid_reference_data")
    except (OSError, UnicodeError, ValueError) as exc:
        raise DemoError("invalid_reference_data", "Local support fixtures are unreadable or invalid.") from exc


class RetrievalStore:
    def __init__(self, account_id: str, product_area: str, limit: int, *, fixtures: Path = FIXTURES):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise DemoError("invalid_configuration", "Retrieval budget must be a positive integer.")
        accounts = load_fixture(fixtures / "accounts.json", Accounts).accounts
        articles = load_fixture(fixtures / "knowledge.json", Knowledge).articles
        self.accounts = {account.id: account for account in accounts}
        self.articles = {article.id: article for article in articles}
        if len(self.accounts) != len(accounts) or len(self.articles) != len(articles):
            raise DemoError("invalid_reference_data", "Support fixture IDs must be unique.")
        self.account_id = account_id
        self.product_area = product_area
        self.limit = limit
        self.calls_used = 0

    @property
    def remaining(self):
        return self.limit - self.calls_used

    def call(self, name: str, arguments: dict):
        # The workflow owns tool availability and scope. The AI cannot change
        # the customer, product area, fixture paths, permissions, or budget.
        if not isinstance(arguments, dict):
            raise DemoError("unauthorized_retrieval", "Retrieval arguments must be a scoped object.")
        if name == "lookup_account":
            valid = arguments == {"account_id": self.account_id}
        elif name == "search_knowledge":
            query = arguments.get("query")
            valid = (set(arguments) == {"query"} and isinstance(query, str)
                     and bool(query.strip()) and len(query) <= 300)
        else:
            valid = False
        if not valid:
            raise DemoError("unauthorized_retrieval", "Retrieval tool or arguments are outside the allowed scope.")
        if self.remaining <= 0:
            raise DemoError("retrieval_limit", "Retrieval budget is exhausted; no tool was invoked.")
        self.calls_used += 1
        if name == "lookup_account":
            account = self.accounts.get(self.account_id)
            if account is None:
                raise DemoError("unknown_account", "The ticket account is not present in local fixtures.")
            return account

        terms = set(re.findall(r"[a-z0-9]+", arguments["query"].casefold())) - STOP_WORDS
        ranked = []
        for article in self.articles.values():
            if not article.approved or article.product_area != self.product_area:
                continue
            words = set(re.findall(r"[a-z0-9]+", (article.title + " " + article.content).casefold()))
            score = len(terms & words)
            if score:
                ranked.append((score, article))
        ranked.sort(key=lambda entry: (-entry[0], entry[1].id))
        return [article for _, article in ranked[:3]]
