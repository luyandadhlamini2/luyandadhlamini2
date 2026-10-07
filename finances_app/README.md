# 💰 Money Sorter: Capitec statement classifier (v1)

Upload a Capitec bank statement (PDF) and see where your money goes. Every
transaction is sorted on three levels:

| Level | Question | Values |
|---|---|---|
| 1. Direction | Did money come in or go out? | **Credit** (in) / **Debit** (out) |
| 2. Group | What kind of money was it? | Out: **Needs**, **Wants**, **Savings**. In: **Income**, or **Savings** when money comes back from your savings |
| 3. Category | What was it for? | Groceries, Transport, Bank Fees, Alcohol, Gifts & Donations and 42 more |

The app then shows your spending against the **50/30/20 guide** (50% of income
on needs, 30% on wants, 20% saved), month-by-month trends, your biggest
categories and merchants, and a list of transactions it couldn't sort with
confidence, so you can sort them in a few clicks.

> Money Sorter is an independent tool and isn't affiliated with Capitec Bank.

## Run it

Needs Python 3.11 or newer.

```bash
cd finances_app
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Your browser opens at http://localhost:8501. Upload one or more statement PDFs
in the sidebar. Password-protected PDFs are supported.

### Or try it online (Streamlit Community Cloud, free)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Choose **Create app**, then **Deploy a public app from GitHub**.
3. Repository `luyandadhlamini2/luyandadhlamini2`, branch `finances-app-v1`
   (or `main` once merged), main file path `finances_app/app.py`.
4. Choose **Deploy**. The first start takes a few minutes while packages install.

When the app runs online, statements you upload are processed in memory on
Streamlit's servers rather than on your own computer.

## Using it

- **Overview**: money in and out, bank fees, spending on needs and wants, net
  savings, the 50/30/20 comparison, and month-by-month charts.
- **Categories**: spending, savings or income by category, with a drill-down
  into each category's merchants and transactions, and a category-by-month table.
- **Transactions**: every transaction with its three levels. Change a group or
  category in the table and it's saved. Download everything as CSV.
- **Review**: payments to people, cash and unknown shops, grouped by payee. Pick a
  category once per payee and it applies to all their transactions, in this
  statement and future ones.
- **Rules**: edit your rules, move a category to another group (say clothing is
  a need for you), and back up or restore your settings.

The sidebar filters (dates, credit or debit, group, category, search) apply to every tab.

## How classification works

For each transaction the first of these that applies wins:

1. **Your rules and edits.**
2. **Built-in keyword rules** for things Capitec labels loosely or inconsistently:
   savings transfers and Live Better round-ups, investments, insurers, medical aids,
   cellphone networks and ISPs, streaming, software, Uber vs Uber Eats, betting
   sites, rent and more (`finances/rules.py`, `STRONG_RULES`).
3. **Capitec's own category**, printed next to each transaction, when it's specific,
   e.g. *Groceries* (`finances/categories.py`, `CAPITEC_TO_CATEGORY`). These labels
   come from card merchant codes, or from the client's own choices in the Capitec
   app, so they're trusted over generic keyword guesses.
4. **Name matching** with the account holder's name from the statement: transfers
   to your own accounts at other banks (*Own Account Transfers*), and payments to
   people who share your surname (*Family Support*).
5. **Well-known South African merchants** (Pick n Pay, KFC, Engen, Mr Price...)
   for statements without Capitec's category.
6. **The payment type**: cash withdrawals, payments to people, debit orders.
7. Otherwise **Uncategorised** (money out) or **Other Income** (money in).

Choices worth knowing about:

- **Fees.** Capitec prints fees in their own column. Each fee becomes its own
  *Bank Fees* row, so category totals add up to exactly what left the account.
- **Savings are net.** Transfers into savings pockets, Live Better and investments
  are *Savings*; money moved back is a *Savings* credit. "Saved (net)" is the difference.
- **Income** excludes money coming back from savings, so it isn't counted twice.
- **Unclear spending is a Want until you say otherwise.** Cash withdrawals and
  payments to people can't be identified from a statement. They default to
  *Wants* and are flagged for review.
- **Accuracy check.** The parser adds up every amount it read and compares it to
  the running balance and closing balance printed on the statement. The app tells
  you whether they match, so a misread row can't go unnoticed.

## Privacy

- Statements are read in memory and never written to disk.
- What you teach the app (rules, edits, group choices) is saved to
  `~/.finances_app/preferences.json` so it's remembered next time, but only when
  you open the app on the same computer it runs on. Opened from anywhere else,
  for example once it's deployed online, settings last for the session only, so
  nobody's rules (which contain payee names) end up on a shared disk. Use
  **Download settings** in the Rules tab to keep them.
- `FINANCES_PREFS_FILE` overrides this: set it to a file path to always save
  there, or to `none` to never save.
- `.gitignore` keeps PDFs, CSV exports and settings files out of git.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The parser tests use synthetic word positions that mimic a real statement, so
no personal data lives in the repo. To also check the parser against a real
statement on your machine:

```bash
CAPITEC_STATEMENT=/path/to/statement.pdf python -m pytest
```

## Project layout

```
finances_app/
├── app.py                  Streamlit user interface
├── finances/
│   ├── parser.py           PDF → transactions (word positions, balance reconciliation)
│   ├── categories.py       The three levels, categories, Capitec category mapping
│   ├── rules.py            Keyword rules (strong, weak, fallback)
│   ├── classifier.py       Applies rules, user preferences, fee rows → DataFrame
│   ├── analysis.py         Summaries for the dashboard
│   ├── storage.py          Saving and loading preferences
│   └── models.py           Data classes
└── tests/
```

## Known limitations in v1

- Built for Capitec's current "Main Account Statement" layout (with the Category
  column). Older layouts without the Category column should parse, but haven't
  been tested on a real one.
- Business accounts and credit card statements aren't supported yet.
- Payments to people can only be sorted by you; the statement doesn't say what they were for.
