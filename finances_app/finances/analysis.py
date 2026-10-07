"""Summaries of a classified transaction table (see Classifier.to_frame)."""

from __future__ import annotations

import pandas as pd

from .categories import CREDIT, DEBIT, INCOME, NEEDS, SAVINGS, WANTS

# The 50/30/20 guide: needs, wants and savings as a share of income
GUIDE = {NEEDS: 0.50, WANTS: 0.30, SAVINGS: 0.20}


def months_covered(frame: pd.DataFrame) -> float:
    """Length of the period in months (at least 1), from the first to the last date."""
    if frame.empty:
        return 1.0
    days = (frame["date"].max() - frame["date"].min()).days + 1
    return max(days / 30.44, 1.0)


def spend_in(frame: pd.DataFrame, group: str) -> float:
    """Net money that went to a group: money out minus anything that came back.

    For Savings this is what you saved after withdrawals; for Needs and
    Wants refunds and reversals in those groups reduce the total.
    """
    return round(-frame.loc[frame["group"] == group, "amount"].sum(), 2)


def summary(frame: pd.DataFrame) -> dict[str, float]:
    credits = frame[frame["direction"] == CREDIT]
    debits = frame[frame["direction"] == DEBIT]
    income = credits.loc[credits["group"] == INCOME, "amount"].sum()
    return {
        "money_in": round(credits["amount"].sum(), 2),
        "money_out": round(-debits["amount"].sum(), 2),
        "income": round(income, 2),
        NEEDS: spend_in(frame, NEEDS),
        WANTS: spend_in(frame, WANTS),
        SAVINGS: spend_in(frame, SAVINGS),
        "fees": round(-frame.loc[frame["category"] == "Bank Fees", "amount"].sum(), 2),
        "months": months_covered(frame),
        "to_review": int(frame["needs_review"].sum()),
    }


def income_split(frame: pd.DataFrame) -> pd.DataFrame:
    """Needs, wants and savings as a share of income, next to the 50/30/20 guide."""
    totals = summary(frame)
    income = totals["income"]
    rows = []
    for group, guide in GUIDE.items():
        amount = totals[group]
        rows.append({
            "group": group,
            "amount": amount,
            "share": amount / income if income else 0.0,
            "guide": guide,
        })
    return pd.DataFrame(rows)


def monthly(frame: pd.DataFrame) -> pd.DataFrame:
    """Per month: income, net spend on needs and wants, and net saved."""
    months = sorted(frame["month"].unique())
    table = pd.DataFrame(index=months)
    in_income = frame[(frame["direction"] == CREDIT) & (frame["group"] == INCOME)]
    table[INCOME] = in_income.groupby("month")["amount"].sum()
    for group in (NEEDS, WANTS, SAVINGS):
        table[group] = -frame[frame["group"] == group].groupby("month")["amount"].sum()
    table.index.name = "month"
    return table.fillna(0.0).round(2)


def by_category(frame: pd.DataFrame, direction: str = DEBIT) -> pd.DataFrame:
    """Totals per category for money out (net of refunds) or money in."""
    if direction == DEBIT:
        rows = frame[frame["group"].isin([NEEDS, WANTS, SAVINGS])]
        sign = -1
    else:
        rows = frame[(frame["direction"] == CREDIT) & (frame["group"] == INCOME)]
        sign = 1
    if rows.empty:
        return pd.DataFrame(columns=["category", "group", "total", "count", "share", "per_month"])
    months = months_covered(frame)
    table = (
        rows.groupby(["category", "group"])
        .agg(total=("amount", "sum"), count=("amount", "size"))
        .reset_index()
    )
    table["total"] = (table["total"] * sign).round(2)
    table = table[table["total"].abs() > 0.004]
    positive = table.loc[table["total"] > 0, "total"].sum()
    table["share"] = table["total"] / positive if positive else 0.0
    table["per_month"] = (table["total"] / months).round(2)
    return table.sort_values("total", ascending=False).reset_index(drop=True)


def top_merchants(frame: pd.DataFrame, limit: int = 15) -> pd.DataFrame:
    """Where money out went, by merchant or payee (excluding savings and fees)."""
    rows = frame[(frame["direction"] == DEBIT) & frame["group"].isin([NEEDS, WANTS]) & ~frame["is_fee"]]
    table = (
        rows.groupby("merchant")
        .agg(total=("amount", "sum"), count=("amount", "size"), category=("category", lambda c: c.mode().iat[0]))
        .reset_index()
    )
    table["total"] = -table["total"]
    return table.sort_values("total", ascending=False).head(limit).reset_index(drop=True)


def category_by_month(frame: pd.DataFrame, direction: str = DEBIT) -> pd.DataFrame:
    """Category x month table of net spend (or income)."""
    if direction == DEBIT:
        rows = frame[frame["group"].isin([NEEDS, WANTS, SAVINGS])]
        sign = -1
    else:
        rows = frame[(frame["direction"] == CREDIT) & (frame["group"] == INCOME)]
        sign = 1
    table = rows.pivot_table(index="category", columns="month", values="amount", aggfunc="sum", fill_value=0.0)
    table = (table * sign).round(2)
    table["Total"] = table.sum(axis=1)
    return table.sort_values("Total", ascending=False)


def review_queue(frame: pd.DataFrame) -> pd.DataFrame:
    """Transactions that need a human look, grouped by merchant / payee."""
    rows = frame[frame["needs_review"]]
    if rows.empty:
        return pd.DataFrame(columns=["merchant", "direction", "category", "count", "total"])
    table = (
        rows.groupby(["merchant", "direction", "category"])
        .agg(count=("amount", "size"), total=("amount", "sum"))
        .reset_index()
    )
    return table.reindex(table["total"].abs().sort_values(ascending=False).index).reset_index(drop=True)
