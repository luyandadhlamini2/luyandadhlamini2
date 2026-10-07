"""Read a Capitec "Main Account Statement" PDF into a :class:`Statement`.

The statement's Transaction History table has the columns

    Date | Description | Category | Money In | Money Out | Fee* | Balance

Long descriptions and categories wrap onto a second line, and amounts use a
space as the thousands separator ("-1 047.88"), so plain text extraction
mixes the columns up. Instead we work with word positions: the header row on
every page tells us where each column sits, and each word is placed in the
column it lines up with.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import IO, Iterable

import pdfplumber

from .models import RawTransaction, Statement

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
# A piece of an amount: "-2", "088.00", "-R1", "-350.00*", "17"
AMOUNT_FRAGMENT_RE = re.compile(r"^-?R?[\d.,]+\*?$")
SUMMARY_AMOUNT = r"(-?R\s?[\d ]+\.\d{2})"
# "MS THANDI M NKOSI   Capitec Bank Limited" on the address block's first line
HOLDER_RE = re.compile(
    r"^(?:MR|MRS|MS|MISS|DR|PROF|MNR|MEV|ME)\.?\s+([A-Z][A-Z' -]+?)(?:\s+Capitec Bank Limited)?$",
    re.MULTILINE,
)

LINE_TOLERANCE = 3.0  # words whose tops are this close (pt) share a line
AMOUNT_GAP = 4.0  # max gap (pt) between fragments of one amount, e.g. "-2" "088.00"
COLUMN_SNAP = 15.0  # how far (pt) an amount's right edge may sit from its column's


class StatementParseError(ValueError):
    """Raised when a PDF does not look like a Capitec statement we can read."""


@dataclass
class _Layout:
    """Column positions taken from a page's table header."""

    category_left: float  # words starting left of this are description
    money_right_edges: dict[str, float]  # column name -> right edge of its header


def parse_amount(text: str) -> float:
    """Turn "-R1 047.88", "17 540.05" or "-350.00*" into a float."""
    cleaned = text.replace("R", "").replace(" ", "").replace(",", "").replace("*", "")
    if cleaned in ("", "-"):
        raise ValueError(f"Not an amount: {text!r}")
    return round(float(cleaned), 2)


def _parse_date(text: str) -> date:
    return datetime.strptime(text, "%d/%m/%Y").date()


def parse_statement(source: str | IO[bytes], password: str | None = None) -> Statement:
    """Parse a Capitec statement from a path or a binary file object."""
    with pdfplumber.open(source, password=password or "") as pdf:
        if not pdf.pages:
            raise StatementParseError("The PDF has no pages.")
        statement = _parse_summary(pdf.pages[0].extract_text() or "")
        pages = (
            (number, page.extract_words(x_tolerance=1.5))
            for number, page in enumerate(pdf.pages, start=1)
        )
        statement.transactions = parse_transaction_words(pages)

    if not statement.transactions:
        raise StatementParseError(
            "No transactions found. Is this a Capitec account statement "
            "(not a tax certificate or proof of payment)?"
        )
    statement.balance_mismatches = reconcile(statement.transactions, statement.opening_balance)
    return statement


def _parse_summary(text: str) -> Statement:
    """Pull the account number, period and balances from page one."""
    statement = Statement()
    if match := re.search(HOLDER_RE, text):
        statement.account_holder = match.group(1).strip()
    if match := re.search(r"Account\s+(\d{6,})", text):
        statement.account_number = match.group(1)
    if match := re.search(r"From Date:\s*(\d{2}/\d{2}/\d{4})", text):
        statement.from_date = _parse_date(match.group(1))
    if match := re.search(r"To Date:\s*(\d{2}/\d{2}/\d{4})", text):
        statement.to_date = _parse_date(match.group(1))
    if match := re.search(r"Opening Balance:\s*" + SUMMARY_AMOUNT, text):
        statement.opening_balance = parse_amount(match.group(1))
    if match := re.search(r"Closing Balance:\s*" + SUMMARY_AMOUNT, text):
        statement.closing_balance = parse_amount(match.group(1))
    return statement


def parse_transaction_words(pages: Iterable[tuple[int, list[dict]]]) -> list[RawTransaction]:
    """Build transactions from ``(page number, pdfplumber words)`` pairs.

    Separated from :func:`parse_statement` so it can be tested with
    hand-made word positions.
    """
    transactions: list[RawTransaction] = []
    in_history = False
    for page_number, words in pages:
        layout: _Layout | None = None
        current: RawTransaction | None = None
        for line in _group_lines(words):
            texts = [w["text"] for w in line]
            joined = " ".join(texts)

            if "Transaction History" in joined:
                in_history = True
                continue
            if not in_history:
                continue
            if "Pending Card Transactions" in joined:
                return transactions  # pending items are not on the account yet
            if _is_header(texts):
                layout = _layout_from_header(line)
                continue
            if layout is None:
                continue
            if "Includes VAT" in joined or "Client Care Centre" in joined:
                layout = None  # bottom of this page's table
                continue

            if DATE_RE.match(texts[0]) and line[0]["x0"] < layout.category_left / 2:
                current = RawTransaction(date=_parse_date(texts[0]), description="", page=page_number)
                transactions.append(current)
                _fill_row(current, line[1:], layout)
            elif current is not None:
                _fill_row(current, line, layout)  # wrapped continuation line

    return transactions


def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Group words into visual lines, each sorted left to right."""
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - word["top"]) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _is_header(texts: list[str]) -> bool:
    return {"Date", "Description", "Balance"} <= set(texts) and "Out" in texts


def _layout_from_header(line: list[dict]) -> _Layout:
    by_text = {w["text"]: w for w in line}
    edges = {
        "money_in": by_text["In"]["x1"],
        "money_out": by_text["Out"]["x1"],
        "balance": by_text["Balance"]["x1"],
    }
    fee = by_text.get("Fee*") or by_text.get("Fee") or by_text.get("Fees")
    if fee:
        edges["fee"] = fee["x1"]
    if "Category" in by_text:
        category_left = by_text["Category"]["x0"] - 1.5
    else:  # older layouts without Capitec's category column
        category_left = by_text["Money"]["x0"] - 1.5
    return _Layout(category_left=category_left, money_right_edges=edges)


def _fill_row(row: RawTransaction, words: list[dict], layout: _Layout) -> None:
    """Add a line's words to a transaction's description, category and amounts."""
    description, category, fragments = [], [], []
    for word in words:
        if word["x0"] < layout.category_left:
            description.append(word["text"])
        elif AMOUNT_FRAGMENT_RE.match(word["text"]):
            fragments.append(word)
        else:
            category.append(word["text"])

    if description:
        row.description = " ".join(filter(None, [row.description, *description]))
    if category:
        row.bank_category = " ".join(filter(None, [row.bank_category, *category]))

    for text, right_edge in _join_fragments(fragments):
        column = _nearest_column(right_edge, layout)
        if column is None:
            row.bank_category = " ".join(filter(None, [row.bank_category, text]))
            continue
        value = parse_amount(text)
        if column == "balance":
            row.balance = value
        else:
            setattr(row, column, value)


def _join_fragments(fragments: list[dict]) -> list[tuple[str, float]]:
    """Join "-2" + "088.00" into "-2088.00"; returns (text, right edge) pairs."""
    amounts: list[tuple[str, float]] = []
    previous_right = None
    for word in sorted(fragments, key=lambda w: w["x0"]):
        if previous_right is not None and word["x0"] - previous_right <= AMOUNT_GAP:
            text, _ = amounts[-1]
            amounts[-1] = (text + word["text"], word["x1"])
        else:
            amounts.append((word["text"], word["x1"]))
        previous_right = word["x1"]
    return amounts


def _nearest_column(right_edge: float, layout: _Layout) -> str | None:
    name, edge = min(layout.money_right_edges.items(), key=lambda item: abs(item[1] - right_edge))
    return name if abs(edge - right_edge) <= COLUMN_SNAP else None


def reconcile(
    transactions: list[RawTransaction], opening_balance: float | None
) -> list[tuple[int, float, float]]:
    """Check the printed running balance against the amounts we read.

    Capitec sometimes prints a day's transactions in a different order from
    the one they were posted in, so a balance can look wrong for a few rows
    and then add up again. Only differences that never come right again are
    reported, as ``(index, expected, printed)``. A clean result means no row
    was dropped or misread.
    """
    running = opening_balance
    unresolved: list[tuple[int, float, float]] = []
    for index, tx in enumerate(transactions):
        if running is None:  # no opening balance: start from the first printed one
            if tx.balance is not None:
                running = tx.balance
            continue
        running = round(running + tx.amount + tx.fee, 2)
        if tx.balance is None:
            continue
        if abs(running - tx.balance) <= 0.005:
            unresolved.clear()  # earlier differences were just print order
        else:
            unresolved.append((index, running, tx.balance))
    return unresolved
