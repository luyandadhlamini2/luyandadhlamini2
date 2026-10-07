"""Plain data containers shared by the parser, classifier and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class RawTransaction:
    """One row of the "Transaction History" table, exactly as printed."""

    date: date
    description: str
    bank_category: str = ""  # Capitec's own label, e.g. "Groceries" or "Uncategorised"
    money_in: float = 0.0  # positive
    money_out: float = 0.0  # negative
    fee: float = 0.0  # usually negative, positive for a fee reversal
    balance: float | None = None
    page: int = 0

    @property
    def amount(self) -> float:
        """Signed amount excluding the fee: + money in, - money out."""
        return round(self.money_in + self.money_out, 2)


@dataclass
class Statement:
    """Everything we extract from a Capitec statement PDF."""

    account_number: str = ""
    account_holder: str = ""  # e.g. "THANDI M NKOSI", used to spot own-account transfers
    from_date: date | None = None
    to_date: date | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None
    transactions: list[RawTransaction] = field(default_factory=list)
    # Rows whose running balance did not reconcile: (row index, expected, printed)
    balance_mismatches: list[tuple[int, float, float]] = field(default_factory=list)

    @property
    def masked_account(self) -> str:
        if len(self.account_number) <= 4:
            return self.account_number
        return "•••• " + self.account_number[-4:]

    @property
    def reconciled(self) -> bool:
        """True when the amounts we read add up to every printed balance."""
        if not self.transactions or self.balance_mismatches:
            return False
        if self.opening_balance is None or self.closing_balance is None:
            return True
        total = sum(tx.amount + tx.fee for tx in self.transactions)
        return abs(self.opening_balance + total - self.closing_balance) <= 0.01
