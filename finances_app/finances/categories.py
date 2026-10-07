"""The three classification levels and the categories that live in them.

Level 1 - direction: did money come in (Credit) or leave (Debit)?
Level 2 - group:     Needs, Wants or Savings for money out; Income or Savings
                     for money in (money coming back from savings).
Level 3 - category:  what the money was for, e.g. Groceries or Transport.

Every category belongs to one default group. Users can move a single
transaction to another group, or change a category's group for all its
transactions, from the app.
"""

from __future__ import annotations

from dataclasses import dataclass

CREDIT = "Credit"
DEBIT = "Debit"

NEEDS = "Needs"
WANTS = "Wants"
SAVINGS = "Savings"
INCOME = "Income"

DEBIT_GROUPS = (NEEDS, WANTS, SAVINGS)
CREDIT_GROUPS = (INCOME, SAVINGS)
ALL_GROUPS = (NEEDS, WANTS, SAVINGS, INCOME)


@dataclass(frozen=True)
class Category:
    name: str
    group: str
    direction: str  # CREDIT, DEBIT, or "" when it can be either
    icon: str
    help: str
    review: bool = False  # purpose unclear, so ask the user to check it


CATEGORIES: tuple[Category, ...] = (
    # --- Needs: essentials you'd struggle to cut -----------------------------
    Category("Groceries", NEEDS, DEBIT, "🛒", "Supermarkets, butchers, fruit & veg"),
    Category("Housing", NEEDS, DEBIT, "🏠", "Rent, bond, levies"),
    Category("Utilities", NEEDS, DEBIT, "💡", "Electricity, water, municipal bills"),
    Category("Transport", NEEDS, DEBIT, "🚕", "Uber, Bolt, taxis, buses, trains"),
    Category("Fuel", NEEDS, DEBIT, "⛽", "Petrol and diesel"),
    Category("Parking & Tolls", NEEDS, DEBIT, "🅿️", "Parking and toll fees"),
    Category("Vehicle Costs", NEEDS, DEBIT, "🔧", "Services, parts, tyres, licence"),
    Category("Insurance", NEEDS, DEBIT, "🛡️", "Car, life, funeral, legal and pet cover"),
    Category("Health & Medical", NEEDS, DEBIT, "🩺", "Medical aid, pharmacy, doctors"),
    Category("Cellphone & Internet", NEEDS, DEBIT, "📱", "Airtime, data, contracts, fibre"),
    Category("Education", NEEDS, DEBIT, "🎓", "School and study fees, books, stationery"),
    Category("Debt Repayments", NEEDS, DEBIT, "💳", "Store accounts, loans, buy-now-pay-later"),
    Category("Family Support", NEEDS, DEBIT, "👪", "Money for parents, children and relatives"),
    Category("Personal Care", NEEDS, DEBIT, "🧴", "Toiletries and personal care"),
    Category("Home Maintenance", NEEDS, DEBIT, "🔨", "Repairs, hardware, domestic help"),
    Category("Pets", NEEDS, DEBIT, "🐾", "Vet, pet food"),
    Category("Legal & Professional", NEEDS, DEBIT, "⚖️", "Lawyers and professional services"),
    Category("Bank Fees", NEEDS, DEBIT, "🏦", "Bank charges and penalty fees"),
    Category("Other Bills", NEEDS, DEBIT, "🧾", "Debit orders we couldn't identify", review=True),
    # --- Wants: nice to have ---------------------------------------------------
    Category("Restaurants", WANTS, DEBIT, "🍽️", "Sit-down meals"),
    Category("Takeaways & Coffee", WANTS, DEBIT, "🍔", "Fast food, deliveries, coffee"),
    Category("Alcohol", WANTS, DEBIT, "🍺", "Liquor stores, bars, taverns"),
    Category("Entertainment", WANTS, DEBIT, "🎟️", "Movies, events, activities, going out"),
    Category("Subscriptions", WANTS, DEBIT, "📺", "Streaming and app-store subscriptions"),
    Category("Software & Tech", WANTS, DEBIT, "💻", "Software, cloud services, games"),
    Category("Clothing & Shoes", WANTS, DEBIT, "👕", "Clothes, shoes, accessories"),
    Category("Shopping", WANTS, DEBIT, "🛍️", "Online stores, gadgets, general shopping"),
    Category("Home & Furniture", WANTS, DEBIT, "🛋️", "Furniture, appliances, decor, upgrades"),
    Category("Travel & Holidays", WANTS, DEBIT, "✈️", "Flights, accommodation, outings away"),
    Category("Sport & Hobbies", WANTS, DEBIT, "🏋️", "Gym, sport, hobbies"),
    Category("Tobacco & Vaping", WANTS, DEBIT, "🚬", "Cigarettes, vapes, related shops"),
    Category("Gambling", WANTS, DEBIT, "🎰", "Betting and lottery"),
    Category("Gifts & Donations", WANTS, DEBIT, "🎁", "Presents, charity, church"),
    Category("Payments to People", WANTS, DEBIT, "👤", "Transfers to people, purpose unknown", review=True),
    Category("Cash Withdrawals", WANTS, DEBIT, "💵", "ATM and Cash Sent, spending not tracked", review=True),
    Category("Uncategorised", WANTS, DEBIT, "❓", "We couldn't tell what this was", review=True),
    # --- Savings: money put away (or, as a credit, taken back out) ------------
    Category("Savings", SAVINGS, "", "🐷", "Transfers to and from your savings accounts"),
    Category("Investments", SAVINGS, "", "📈", "Investments, stokvels, retirement"),
    Category("Own Account Transfers", SAVINGS, "", "🔁", "Money moved to or from your other banks", review=True),
    # --- Income: money in -----------------------------------------------------
    Category("Salary", INCOME, CREDIT, "💼", "Salary and wages"),
    Category("Rental Income", INCOME, CREDIT, "🏘️", "Rent you received"),
    Category("Interest", INCOME, CREDIT, "🪙", "Interest earned"),
    Category("Refunds & Reversals", INCOME, CREDIT, "↩️", "Refunds, corrections, reversed fees"),
    Category("Loans", INCOME, CREDIT, "🧾", "Loans received or repaid to you"),
    Category("Money Received", INCOME, CREDIT, "🤝", "Payments from people"),
    Category("Cash Deposits", INCOME, CREDIT, "💰", "Cash you deposited"),
    Category("Other Income", INCOME, CREDIT, "➕", "Money in we couldn't identify", review=True),
)

BY_NAME: dict[str, Category] = {c.name: c for c in CATEGORIES}

FALLBACK_DEBIT = "Uncategorised"
FALLBACK_CREDIT = "Other Income"
REFUND = "Refunds & Reversals"


def get(name: str) -> Category:
    return BY_NAME.get(name, BY_NAME[FALLBACK_DEBIT])


def names_for(direction: str) -> list[str]:
    """Category names that make sense for money in (Credit) or out (Debit)."""
    return [c.name for c in CATEGORIES if c.direction in (direction, "")]


def label(name: str) -> str:
    """'🛒 Groceries' style label for display."""
    category = BY_NAME.get(name)
    return f"{category.icon} {name}" if category else name


# Capitec prints its own category next to each transaction. Most are specific
# merchant labels (from card merchant codes, or set by the client in the app)
# that map straight onto ours. Generic ones say how money moved, not what it
# was for, so they are left to our rules.
CAPITEC_GENERIC = {
    "",
    "Uncategorised",
    "Digital Payments",
    "Transfer",
    "Other Income",
    "Payment Received",
    "Account Payment Received",
}

CAPITEC_TO_CATEGORY: dict[str, str] = {
    "Groceries": "Groceries",
    "Clothing & Shoes": "Clothing & Shoes",
    "Parking": "Parking & Tolls",
    "Takeaways": "Takeaways & Coffee",
    "Cash Withdrawal": "Cash Withdrawals",
    "Fuel": "Fuel",
    "Restaurants": "Restaurants",
    "Fees": "Bank Fees",
    "Alcohol": "Alcohol",
    "Cellphone": "Cellphone & Internet",
    "Telephone": "Cellphone & Internet",
    "Internet": "Cellphone & Internet",
    "Other Communication": "Cellphone & Internet",
    "Public Transport": "Transport",
    "Other Transport": "Transport",
    "Personal Care": "Personal Care",
    "Other Personal & Family": "Personal Care",
    "Holiday": "Travel & Holidays",
    "Activities": "Entertainment",
    "Going Out": "Entertainment",
    "Movies": "Entertainment",
    "Software/Games": "Software & Tech",
    "Online Store": "Shopping",
    "Gadgets": "Shopping",
    "Electricity": "Utilities",
    "Municipal Bill": "Utilities",
    "Water": "Utilities",
    "Tobacco": "Tobacco & Vaping",
    "Store Account Payments": "Debt Repayments",
    "Other Loans & Accounts": "Debt Repayments",
    "Credit Card": "Debt Repayments",
    "Personal Loan": "Debt Repayments",
    "Vehicle Finance": "Debt Repayments",
    "Home Loan": "Housing",
    "Rent": "Housing",
    "Digital Subscriptions": "Subscriptions",
    "TV Subscriptions": "Subscriptions",
    "Home Improvements": "Home & Furniture",
    "Furniture & Appliances": "Home & Furniture",
    "Home Maintenance": "Home Maintenance",
    "Housekeeping": "Home Maintenance",
    "Legal Fees": "Legal & Professional",
    "Medical Aid": "Health & Medical",
    "Pharmacy": "Health & Medical",
    "Doctors & Therapists": "Health & Medical",
    "Vehicle Insurance": "Insurance",
    "Life Insurance": "Insurance",
    "Funeral Cover": "Insurance",
    "Home Insurance": "Insurance",
    "Vehicle Maintenance": "Vehicle Costs",
    "Licence": "Vehicle Costs",
    "Children & Dependants": "Family Support",
    "Allowance": "Family Support",  # as a debit; see CAPITEC_CREDIT_TO_CATEGORY
    "Investments": "Investments",
    "Savings": "Savings",
    "Sport & Hobbies": "Sport & Hobbies",
    "Pets": "Pets",
    "Books/Stationery": "Education",
    "Education": "Education",
    "School Fees": "Education",
    "Gifts": "Gifts & Donations",
    "Donations": "Gifts & Donations",
    "Gambling": "Gambling",
}

CAPITEC_CREDIT_TO_CATEGORY: dict[str, str] = {
    "Salary": "Salary",
    "Interest": "Interest",
    "Rental Income": "Rental Income",
    "Refunds": REFUND,
    "Loans": "Loans",
    "Cash Deposit": "Cash Deposits",
    "Allowance": "Money Received",
    "Savings": "Savings",
    "Investments": "Investments",
}
