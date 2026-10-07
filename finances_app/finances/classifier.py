"""Give every transaction a direction, group and category.

Order of precedence for a transaction's category:

1. Your own rules ("anything containing 'Gogo Support' is Family Support").
2. Strong keyword rules (see rules.py).
3. Capitec's category, when it is specific (e.g. "Groceries").
4. Name matching against the account holder: transfers to your own accounts
   at other banks, and payments to people who share your surname.
5. Weak keyword rules for well-known merchants.
6. The payment type: cash, a transfer to a person, a debit order.
7. Uncategorised (money out) or Other Income (money in).

Fees Capitec prints in the separate Fee column become their own "Bank Fees"
rows, so category totals add up to the total that left the account.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd

from . import categories as cats
from .categories import CREDIT, DEBIT
from .models import RawTransaction, Statement
from .rules import FALLBACK_RULES, STRONG_RULES, WEAK_RULES, Rule

# Sources, shown in the app so people can see why something landed where it did
SOURCE_USER = "Your rule"
SOURCE_EDIT = "Your edit"
SOURCE_KEYWORD = "Keyword"
SOURCE_CAPITEC = "Capitec category"
SOURCE_NAME = "Name match"
SOURCE_TYPE = "Payment type"
SOURCE_FEE = "Fee column"
SOURCE_NONE = "No match"

OTHER_BANKS = ("fnb", "absa", "nedbank", "standard bank", "stanbic", "tyme", "discovery", "investec", "african bank", "capitec", "bank zero", "old mutual")

COLUMNS = [
    "key", "date", "month", "description", "merchant", "amount", "direction",
    "group", "category", "needs_review", "source", "bank_category", "balance", "is_fee",
]


@dataclass
class UserRule:
    """'If the description contains `match`, it's `category`' (and optionally `group`)."""

    match: str
    category: str
    group: str | None = None

    def matches(self, description: str, merchant: str = "") -> bool:
        needle = self.match.strip().lower()
        return bool(needle) and (needle in description.lower() or needle == merchant.lower())


@dataclass
class Preferences:
    """Everything a user has taught the app. Saved as JSON between sessions."""

    rules: list[UserRule] = field(default_factory=list)
    # Per-transaction edits, keyed by transaction key: {"category": ..., "group": ...}
    edits: dict[str, dict[str, str]] = field(default_factory=dict)
    # Move a whole category to another group, e.g. {"Clothing & Shoes": "Needs"}
    category_groups: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rules": [vars(rule) for rule in self.rules],
            "edits": self.edits,
            "category_groups": self.category_groups,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Preferences":
        return cls(
            rules=[UserRule(**rule) for rule in data.get("rules", [])],
            edits=dict(data.get("edits", {})),
            category_groups=dict(data.get("category_groups", {})),
        )


@dataclass
class Classification:
    category: str
    source: str
    group: str | None = None  # only set when a user rule picks the group too


class Classifier:
    def __init__(self, preferences: Preferences | None = None, account_holder: str = ""):
        self.preferences = preferences or Preferences()
        self.first_name, self.surname = _holder_names(account_holder)

    def classify(self, description: str, direction: str, bank_category: str = "") -> Classification:
        merchant = merchant_name(description)
        for rule in self.preferences.rules:
            if rule.matches(description, merchant):
                return Classification(rule.category, SOURCE_USER, rule.group)

        if rule := _first_match(STRONG_RULES, description, direction):
            return Classification(rule.category, SOURCE_KEYWORD)

        if category := _from_capitec(bank_category, direction):
            return Classification(category, SOURCE_CAPITEC)

        if category := self._from_name(description, direction):
            return Classification(category, SOURCE_NAME)

        if rule := _first_match(WEAK_RULES, description, direction):
            return Classification(rule.category, SOURCE_KEYWORD)

        if rule := _first_match(FALLBACK_RULES, description, direction):
            return Classification(rule.category, SOURCE_TYPE)

        fallback = cats.FALLBACK_CREDIT if direction == CREDIT else cats.FALLBACK_DEBIT
        return Classification(fallback, SOURCE_NONE)

    def group_for(self, category: str) -> str:
        return self.preferences.category_groups.get(category) or cats.get(category).group

    def _from_name(self, description: str, direction: str) -> str | None:
        """Spot transfers to your own accounts and payments to relatives."""
        if not self.surname:
            return None
        payee = _payee(description).lower()
        words = re.findall(r"[a-z]+", payee)
        if self.first_name and payee.startswith(self.first_name):
            rest = payee[len(self.first_name):]
            initial = re.search(rf"\b{self.surname[0]}\b", rest)
            if self.surname in rest or initial or any(bank in rest for bank in OTHER_BANKS):
                return "Own Account Transfers"
        if direction == DEBIT and self.surname in words and _first_match(FALLBACK_RULES, description, DEBIT):
            return "Family Support"
        return None

    # --- turning statements into a table ----------------------------------

    def to_frame(self, statements: Iterable[Statement]) -> pd.DataFrame:
        """One row per transaction (plus one per fee), sorted by date.

        Transactions repeated in an earlier statement (overlapping periods) are
        dropped. Repeats inside one statement are kept: the same transfer can
        genuinely happen twice in a day, even at the same balance.
        """
        rows = []
        earlier: Counter = Counter()  # identities from statements already added
        occurrences: Counter = Counter()  # to give repeated transactions unique keys
        for statement in statements:
            this_statement: Counter = Counter()
            for tx in statement.transactions:
                identity = (tx.date, tx.description, tx.amount, tx.fee, tx.balance)
                this_statement[identity] += 1
                if this_statement[identity] <= earlier[identity]:
                    continue  # already have it from an overlapping statement
                occurrences[identity] += 1
                rows.extend(self._rows_for(tx, occurrences[identity]))
            earlier |= this_statement
        frame = pd.DataFrame(rows, columns=COLUMNS)
        if frame.empty:
            return frame
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.sort_values("date", kind="stable").reset_index(drop=True)
        return self.apply_edits(frame)

    def _rows_for(self, tx: RawTransaction, occurrence: int = 1) -> list[dict]:
        base_key = f"{tx.date.isoformat()}|{tx.description}|{tx.amount:.2f}|{tx.balance}"
        if occurrence > 1:
            base_key += f"#{occurrence}"
        common = {
            "date": tx.date,
            "month": tx.date.strftime("%Y-%m"),
            "bank_category": tx.bank_category,
            "balance": tx.balance,
            "merchant": merchant_name(tx.description),
        }
        rows = []
        if tx.amount:
            direction = CREDIT if tx.amount > 0 else DEBIT
            result = self.classify(tx.description, direction, tx.bank_category)
            rows.append(self._row(common, base_key, tx.description, tx.amount, direction, result))
        if tx.fee:
            direction = CREDIT if tx.fee > 0 else DEBIT
            category = "Bank Fees" if tx.fee < 0 else cats.REFUND
            result = Classification(category, SOURCE_FEE)
            row = self._row(common, base_key + "|fee", f"Fee: {tx.description}", tx.fee, direction, result)
            row["is_fee"] = True
            row["merchant"] = "Capitec fees"
            rows.append(row)
        # Rows with neither (declined card attempts, "Exc W/lim" notices) moved no money
        return rows

    def _row(self, common: dict, key: str, description: str, amount: float, direction: str, result: Classification) -> dict:
        category = cats.get(result.category)
        return {
            **common,
            "key": key,
            "description": description,
            "amount": round(amount, 2),
            "direction": direction,
            "category": result.category,
            "group": result.group or self.group_for(result.category),
            # Anything the user classified themselves is settled
            "needs_review": result.source != SOURCE_USER
            and (category.review or result.source in (SOURCE_NAME, SOURCE_NONE)),
            "source": result.source,
            "is_fee": False,
        }

    def apply_edits(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Apply the user's per-transaction edits on top of the rules."""
        frame = frame.copy()
        edited = frame["key"].isin(self.preferences.edits.keys())
        for index in frame.index[edited]:
            edit = self.preferences.edits[frame.at[index, "key"]]
            if category := edit.get("category"):
                frame.at[index, "category"] = category
                frame.at[index, "group"] = self.group_for(category)
            if group := edit.get("group"):
                frame.at[index, "group"] = group
            frame.at[index, "source"] = SOURCE_EDIT
            frame.at[index, "needs_review"] = False
        return frame


def _first_match(rules: Iterable[Rule], description: str, direction: str) -> Rule | None:
    return next((rule for rule in rules if rule.matches(description, direction)), None)


def _from_capitec(bank_category: str, direction: str) -> str | None:
    if bank_category in cats.CAPITEC_GENERIC:
        return None
    if direction == CREDIT:
        if category := cats.CAPITEC_CREDIT_TO_CATEGORY.get(bank_category):
            return category
        # Money back in a spending category, e.g. a reversed cash send
        return cats.REFUND if bank_category in cats.CAPITEC_TO_CATEGORY else None
    return cats.CAPITEC_TO_CATEGORY.get(bank_category)


def _holder_names(account_holder: str) -> tuple[str, str]:
    names = [n for n in re.findall(r"[a-z]+", account_holder.lower()) if len(n) > 1]
    if len(names) < 2:
        return "", ""
    first, surname = names[0], names[-1]
    return (first if len(first) >= 3 else ""), (surname if len(surname) >= 3 else "")


def _payee(description: str) -> str:
    return description.rsplit(": ", 1)[-1] if ": " in description else description


TYPE_WORDS = re.compile(
    r"\b(purchase|payment|order|withdrawal|deposit|received|sent|transfer|refund|correction|adjustment|cashback)\b",
    re.IGNORECASE,
)


def merchant_name(description: str) -> str:
    """A short merchant / payee name for grouping, e.g. 'Pick n Pay Waterfront'."""
    text = description
    lowered = text.lower()
    if "cash sent" in lowered:
        return "Cash Sent"
    if "atm cash withdrawal" in lowered:
        return "ATM withdrawals"
    if match := re.match(r"banking app transfer (?:to|received from|from) (.+?):", text, re.IGNORECASE):
        return match.group(1).strip()
    if ": " in text:
        prefix, rest = text.split(": ", 1)
        if TYPE_WORDS.search(prefix):
            text = rest
    text = re.sub(r"\((card \d+|[^)]*)\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{6,}\b", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text or description
