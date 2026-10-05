from datetime import date

import pytest

from finances import analysis, storage
from finances import categories as cats
from finances.categories import CREDIT, DEBIT, INCOME, NEEDS, SAVINGS, WANTS
from finances.classifier import Classifier, Preferences, UserRule, merchant_name
from finances.models import RawTransaction, Statement

HOLDER = "THANDI M NKOSI"


@pytest.mark.parametrize(
    "description, direction, bank_category, expected",
    [
        # Capitec's specific category is used as is
        ("Pick n Pay Waterfront (Card 1234)", DEBIT, "Groceries", "Groceries"),
        ("Tigers Milk Cape Town (Card 1234)", DEBIT, "Restaurants", "Restaurants"),
        ("Purchase Refund: Mr Price Sport Cape Town", CREDIT, "Refunds", "Refunds & Reversals"),
        ("Payment Received: Acme Payroll", CREDIT, "Salary", "Salary"),
        # ...but strong rules fix labels Capitec applies inconsistently
        ("DebiCheck Debit Order (1000000001): Dotsure (MT00000000)", DEBIT, "Pets", "Insurance"),
        ("Eft Debit Order (1000000002): Sl-debits (SANLAM 01)", DEBIT, "Investments", "Insurance"),
        ("Recurring Card Purchase: Netflix Amsterdam (Card 1234)", DEBIT, "Digital Subscriptions", "Subscriptions"),
        ("Recurring Card Purchase: Uber Eats Parktown Nort (Card 1234)", DEBIT, "Takeaways", "Takeaways & Coffee"),
        ("Recurring Card Purchase: Dl*uber Parktown (Card 1234)", DEBIT, "Public Transport", "Transport"),
        ("The Fitz Jewellery Milnerton (Card 1234)", DEBIT, "Personal Care", "Shopping"),
        # Generic Capitec labels are resolved by rules
        ("Live Better Round-up Transfer", DEBIT, "Transfer", "Savings"),
        ("Live Better Interest Sweep", DEBIT, "Transfer", "Savings"),
        ("Banking App Transfer to Holiday Account: Transfer", DEBIT, "Transfer", "Savings"),
        ("Banking App Transfer Received from Holiday Account: Transfer", CREDIT, "Transfer", "Savings"),
        ("Recurring Payment (10000003): Kasi Capital Stokvel", DEBIT, "Uncategorised", "Investments"),
        ("Recurring Payment (10000004): Family Equity Inve", DEBIT, "Uncategorised", "Investments"),
        ("Banking App External Payment: Rentpayments", DEBIT, "Uncategorised", "Housing"),
        ("Payment Received: Operat Rtc 00aa000000 October Rent", CREDIT, "Account Payment Received", "Rental Income"),
        ("Adjustment: Fee Netflix.com Purchase On 20 Nov", DEBIT, "Uncategorised", "Bank Fees"),
        ("Correction: Cash Sent: C0000000000", CREDIT, "Cash Withdrawal", "Refunds & Reversals"),
        ("Interest Received", CREDIT, "Interest", "Interest"),
        ("Immediate Capitec Pay Payment: 4racing (6859709)", DEBIT, "Digital Payments", "Gambling"),
        ("Banking App Immediate Payment: Smith Lawyer", DEBIT, "Digital Payments", "Legal & Professional"),
        ("Banking App External PayShap Payment: Dr J Smith", DEBIT, "Digital Payments", "Health & Medical"),
        ("Recurring Immediate Payment (10000005): Mom Support", DEBIT, "Digital Payments", "Family Support"),
        ("Banking App Prepaid Purchase: Electricity", DEBIT, "Electricity", "Utilities"),
        ("Banking App Prepaid Purchase: MTN", DEBIT, "Cellphone", "Cellphone & Internet"),
        # A street called "Dr ..." on an ATM is not a doctor
        ("ATM Cash Withdrawal: 320 Dr Pixley Kaseme Durban Za", DEBIT, "Cash Withdrawal", "Cash Withdrawals"),
        # Weak merchant rules, for statements without Capitec's category
        ("KFC Cape Town (Card 1234)", DEBIT, "", "Takeaways & Coffee"),
        ("Engen Winklespruit (Card 1234)", DEBIT, "", "Fuel"),
        ("Pep Home Century City (Card 1234)", DEBIT, "", "Home & Furniture"),
        # Payment type fallbacks
        ("Banking App Cash Sent: C*******851", DEBIT, "", "Cash Withdrawals"),
        ("Banking App Immediate Payment: Sipho M", DEBIT, "Digital Payments", "Payments to People"),
        ("Eft Debit Order (123): Unknown Co", DEBIT, "", "Other Bills"),
        ("PayShap Payment Received: Sipho", CREDIT, "Digital Payments", "Money Received"),
        ("Mystery Shop (Card 1234)", DEBIT, "Uncategorised", "Uncategorised"),
        ("Something Else", CREDIT, "", "Other Income"),
    ],
)
def test_classify(description, direction, bank_category, expected):
    result = Classifier(account_holder=HOLDER).classify(description, direction, bank_category)
    assert result.category == expected


def test_name_matching_spots_own_accounts_and_family():
    classifier = Classifier(account_holder=HOLDER)
    assert classifier.classify("Banking App External PayShap Payment: Thandifnb", DEBIT).category == "Own Account Transfers"
    assert classifier.classify("Banking App External PayShap Payment: Thandi N", DEBIT).category == "Own Account Transfers"
    assert classifier.classify("Banking App Immediate Payment: Sipho Nkosi", DEBIT).category == "Family Support"
    # A card purchase at a shop sharing the surname is not family support
    assert classifier.classify("Nkosi Butchery (Card 1234)", DEBIT).category != "Family Support"


def test_every_category_maps_to_a_valid_group():
    for category in cats.CATEGORIES:
        assert category.group in cats.ALL_GROUPS
    for target in [*cats.CAPITEC_TO_CATEGORY.values(), *cats.CAPITEC_CREDIT_TO_CATEGORY.values()]:
        assert target in cats.BY_NAME


def test_user_rules_win_and_can_set_the_group():
    prefs = Preferences(rules=[UserRule("Sipho M", "Gifts & Donations", group=NEEDS)])
    statement = Statement(transactions=[
        RawTransaction(date(2025, 10, 1), "Banking App Immediate Payment: Sipho M", money_out=-200, balance=800)
    ])
    row = Classifier(prefs).to_frame([statement]).iloc[0]
    assert (row["category"], row["group"], row["source"], row["needs_review"]) == (
        "Gifts & Donations", NEEDS, "Your rule", False)


def test_user_rule_can_match_a_merchant_name():
    prefs = Preferences(rules=[UserRule("ATM withdrawals", "Transport")])
    result = Classifier(prefs).classify("ATM Cash Withdrawal: Toti Mall Durban Za", DEBIT, "Cash Withdrawal")
    assert result.category == "Transport"


def sample_statement() -> Statement:
    return Statement(transactions=[
        RawTransaction(date(2025, 10, 1), "Payment Received: Acme Salary", "Salary", money_in=10000, balance=10000),
        RawTransaction(date(2025, 10, 2), "Pick n Pay Gardens (Card 1234)", "Groceries", money_out=-3000, balance=7000),
        RawTransaction(date(2025, 10, 3), "KFC Cape Town (Card 1234)", "Takeaways", money_out=-1000, balance=6000),
        RawTransaction(date(2025, 10, 3), "Banking App Cash Sent: C*******851", "Cash Withdrawal",
                       money_out=-500, fee=-10, balance=5490),
        RawTransaction(date(2025, 10, 4), "Banking App Transfer to Savings: Transfer", "Transfer",
                       money_out=-2500, balance=2990),
        RawTransaction(date(2025, 10, 5), "Banking App Transfer Received from Savings: Transfer", "Transfer",
                       money_in=500, balance=3490),
        RawTransaction(date(2025, 10, 5), "Exc W/lim Payflex Za", ""),  # declined, no money moved
    ])


def test_fees_become_their_own_rows_and_empty_rows_are_dropped():
    frame = Classifier().to_frame([sample_statement()])
    assert len(frame) == 7  # 6 transactions + 1 fee, the declined notice is gone
    fee = frame[frame["is_fee"]].iloc[0]
    assert (fee["category"], fee["amount"], fee["group"]) == ("Bank Fees", -10.0, NEEDS)
    assert frame["key"].is_unique


def test_duplicates_are_kept_within_a_statement_but_not_across_statements():
    twice = RawTransaction(date(2026, 8, 14), "Banking App Transfer Received from Pocket: Transfer",
                           "Transfer", money_in=5000, balance=6500.00)
    statement = Statement(transactions=[twice, twice])
    assert len(Classifier().to_frame([statement])) == 2
    assert len(Classifier().to_frame([statement, statement])) == 2


def test_summary_and_income_split():
    frame = Classifier().to_frame([sample_statement()])
    totals = analysis.summary(frame)
    assert totals["money_in"] == 10500
    assert totals["money_out"] == 7010
    assert totals["income"] == 10000
    assert totals[NEEDS] == 3010  # groceries + the cash fee
    assert totals[WANTS] == 1500  # takeaways + cash
    assert totals[SAVINGS] == 2000  # 2 500 saved, 500 taken back
    split = analysis.income_split(frame).set_index("group")
    assert split.loc[NEEDS, "share"] == pytest.approx(0.301)
    assert split.loc[SAVINGS, "guide"] == 0.20
    months = analysis.monthly(frame)
    assert months.loc["2025-10", INCOME] == 10000


def test_edits_override_rules_and_clear_the_review_flag():
    frame = Classifier().to_frame([sample_statement()])
    cash = frame[frame["category"] == "Cash Withdrawals"].iloc[0]
    assert cash["needs_review"]
    prefs = Preferences(edits={cash["key"]: {"category": "Transport"}})
    edited = Classifier(prefs).to_frame([sample_statement()]).set_index("key").loc[cash["key"]]
    assert (edited["category"], edited["group"], edited["needs_review"]) == ("Transport", NEEDS, False)


def test_category_group_overrides():
    prefs = Preferences(category_groups={"Takeaways & Coffee": NEEDS})
    frame = Classifier(prefs).to_frame([sample_statement()])
    assert frame.loc[frame["category"] == "Takeaways & Coffee", "group"].iat[0] == NEEDS


def test_preferences_round_trip(tmp_path):
    prefs = Preferences(rules=[UserRule("Sipho", "Gifts & Donations")], edits={"k": {"group": WANTS}},
                        category_groups={"Pets": WANTS})
    path = tmp_path / "prefs.json"
    storage.save(prefs, path)
    assert storage.load(path) == prefs
    assert storage.load(tmp_path / "missing.json") == Preferences()


@pytest.mark.parametrize(
    "description, merchant",
    [
        ("Recurring Card Purchase: Zapper1*advance Va Wat Cape Town (Card 5678)", "Zapper1*advance Va Wat Cape Town"),
        ("Eft Debit Order (1000000006): Afrihost (A00000000 0000)", "Afrihost"),
        ("Banking App Transfer to Holiday Account: Transfer", "Holiday Account"),
        ("Payment Received: Acme Salary 1000000007", "Acme Salary"),
        ("ATM Cash Withdrawal: Toti Mall Durban Za", "ATM withdrawals"),
        ("Live Better Round-up Transfer", "Live Better Round-up Transfer"),
    ],
)
def test_merchant_name(description, merchant):
    assert merchant_name(description) == merchant
