"""Parser tests built from hand-made word positions that mimic a real statement.

Real statements contain personal data and are never committed. To also run
the parser over one of yours, set CAPITEC_STATEMENT=/path/to/statement.pdf.
"""

import os
from datetime import date

import pytest

from finances.models import RawTransaction, Statement
from finances.parser import parse_amount, parse_statement, parse_transaction_words, reconcile

CHAR_WIDTH = 4.4  # rough width of one character in the statement's font
SPACE = 2.2


def words(text: str, x0: float, top: float) -> list[dict]:
    """Left-aligned words starting at x0, as pdfplumber would return them."""
    result, x = [], x0
    for part in text.split():
        x1 = x + CHAR_WIDTH * len(part)
        result.append({"text": part, "x0": x, "x1": x1, "top": top})
        x = x1 + SPACE
    return result


def right_aligned(text: str, right: float, top: float) -> list[dict]:
    """Right-aligned amount; "-2 088.00" becomes two words like in the PDF."""
    result, x1 = [], right
    for part in reversed(text.split()):
        x0 = x1 - CHAR_WIDTH * len(part)
        result.insert(0, {"text": part, "x0": x0, "x1": x1, "top": top + 0.1})
        x1 = x0 - SPACE
    return result


HEADER_TOP = 30.0
HEADER = (
    words("Date", 35.1, HEADER_TOP)
    + words("Description", 84.6, HEADER_TOP)
    + words("Category", 282.5, HEADER_TOP)
    + [{"text": "Money", "x0": 363.3, "x1": 388.6, "top": HEADER_TOP},
       {"text": "In", "x0": 390.8, "x1": 397.9, "top": HEADER_TOP},
       {"text": "Money", "x0": 419.8, "x1": 445.1, "top": HEADER_TOP},
       {"text": "Out", "x0": 447.3, "x1": 461.1, "top": HEADER_TOP},
       {"text": "Fee*", "x0": 491.8, "x1": 508.7, "top": HEADER_TOP},
       {"text": "Balance", "x0": 529.5, "x1": 560.2, "top": HEADER_TOP}]
)
IN, OUT, FEE, BALANCE = 397.1, 460.3, 507.9, 559.4


def row(top, day, description, category="", money_in=None, money_out=None, fee=None, balance=None):
    result = words(day, 34.4, top) + words(description, 83.8, top)
    if category:
        result += words(category, 281.7, top)
    for value, edge in ((money_in, IN), (money_out, OUT), (fee, FEE), (balance, BALANCE)):
        if value:
            result += right_aligned(value, edge, top)
    return result


def page(*lines):
    return [word for line in lines for word in line]


def test_parse_amount():
    assert parse_amount("-R1 047.88") == -1047.88
    assert parse_amount("17 540.05") == 17540.05
    assert parse_amount("-350.00*") == -350.0
    assert parse_amount("R0.50") == 0.5
    with pytest.raises(ValueError):
        parse_amount("-")


def test_reads_columns_wrapped_lines_and_split_amounts():
    first_page = page(
        words("Transaction History", 40.4, 10),
        HEADER,
        row(45, "01/10/2025", "Spar Western Cape (Card 1234)", "Groceries", money_out="-36.24", balance="9 963.76"),
        row(57, "01/10/2025", "Gelmar Richards Bay (Card 1234)", "Home", money_out="-2 088.00", balance="7 875.76"),
        words("Improvements", 281.7, 69),
        row(81, "01/10/2025", "Recurring Card Purchase: Zapper1*advance Va Wat", "Parking",
            money_out="-10.00", fee="-2.00", balance="7 863.76"),
        words("Cape Town (Card 5678)", 83.8, 93),
        row(105, "02/10/2025", "Payment Received: Salary", "Salary", money_in="25 000.00", balance="32 863.76"),
        row(117, "02/10/2025", "Monthly Account Admin Fee", "Fees", fee="-7.50", balance="32 856.26"),
        words("* Includes VAT at 15%", 480, 130),
        words("24hr Client Care Centre 0860 10 20 43", 200, 800),
    )
    second_page = page(
        HEADER,
        row(45, "03/10/2025", "Banking App Prepaid Purchase: MTN", "Cellphone",
            money_out="-105.00*", fee="-0.50", balance="32 750.76"),
        words("Pending Card Transactions", 40, 70),
        row(85, "04/10/2025", "Shell Cape Town (Card 1234)", money_out="-151.80"),
    )
    rows = parse_transaction_words([(1, first_page), (2, second_page)])

    assert [r.description for r in rows] == [
        "Spar Western Cape (Card 1234)",
        "Gelmar Richards Bay (Card 1234)",
        "Recurring Card Purchase: Zapper1*advance Va Wat Cape Town (Card 5678)",
        "Payment Received: Salary",
        "Monthly Account Admin Fee",
        "Banking App Prepaid Purchase: MTN",
    ]  # the pending transaction is not on the account yet, so it's skipped
    gelmar = rows[1]
    assert gelmar.bank_category == "Home Improvements"
    assert gelmar.money_out == -2088.0 and gelmar.balance == 7875.76
    parking = rows[2]
    assert (parking.money_out, parking.fee, parking.bank_category) == (-10.0, -2.0, "Parking")
    salary = rows[3]
    assert salary.money_in == 25000.0 and salary.amount == 25000.0
    admin_fee = rows[4]
    assert admin_fee.amount == 0 and admin_fee.fee == -7.5
    prepaid = rows[5]
    assert (prepaid.money_out, prepaid.fee, prepaid.page) == (-105.0, -0.5, 2)
    assert reconcile(rows, opening_balance=10000.00) == []


def test_ignores_dates_before_the_transaction_history():
    summary = page(words("Scheduled Payments", 40, 10), row(30, "04/10/2025", "Afrihost", money_out="-289.35"))
    assert parse_transaction_words([(1, summary)]) == []


def tx(amount, balance, day=1):
    return RawTransaction(date=date(2025, 10, day), description="x", money_out=min(amount, 0),
                          money_in=max(amount, 0), balance=balance)


def test_reconcile_tolerates_same_day_rows_printed_out_of_order():
    # Posted -90 before -60, but printed the other way round
    rows = [tx(-60, 850.0), tx(-90, 910.0), tx(-170, 680.0), tx(-70, 610.0)]
    assert reconcile(rows, opening_balance=1000.0) == []


def test_reconcile_reports_a_misread_amount():
    rows = [tx(-60, 940.0), tx(-50, 840.0), tx(-10, 830.0)]  # second row really was -100
    mismatches = reconcile(rows, opening_balance=1000.0)
    assert mismatches[0] == (1, 890.0, 840.0)


def test_statement_reconciled_checks_closing_balance():
    statement = Statement(opening_balance=100.0, closing_balance=50.0, transactions=[tx(-50, 50.0)])
    assert statement.reconciled
    statement.closing_balance = 60.0
    assert not statement.reconciled


@pytest.mark.skipif(not os.environ.get("CAPITEC_STATEMENT"), reason="set CAPITEC_STATEMENT to a real statement PDF")
def test_real_statement_reconciles():
    statement = parse_statement(os.environ["CAPITEC_STATEMENT"])
    assert statement.transactions
    assert statement.reconciled, statement.balance_mismatches[:5]
