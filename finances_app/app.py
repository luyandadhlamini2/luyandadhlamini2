"""Money Sorter: upload a Capitec bank statement and see where your money goes.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from finances import analysis, storage
from finances import categories as cats
from finances.categories import CREDIT, DEBIT, INCOME, NEEDS, SAVINGS, WANTS
from finances.classifier import Classifier, Preferences, UserRule
from finances.parser import StatementParseError, parse_statement

st.set_page_config(page_title="Money Sorter", page_icon="💰", layout="wide")

# Group colours, validated for colour-blind separation on light and dark surfaces
GROUP_COLORS = {
    "light": {NEEDS: "#2a78d6", WANTS: "#eb6834", SAVINGS: "#1baf7a", INCOME: "#4a3aa7"},
    "dark": {NEEDS: "#3987e5", WANTS: "#d95926", SAVINGS: "#199e70", INCOME: "#9085e9"},
}
SURFACE = {"light": "#ffffff", "dark": "#0e1117"}
MUTED = "#898781"
# Totals use thousands separators ("accounting" shows negatives in brackets)
MONEY = st.column_config.NumberColumn(format="accounting")


def money_column(label: str) -> st.column_config.NumberColumn:
    return st.column_config.NumberColumn(f"{label} (R)", format="accounting")


# --- helpers -----------------------------------------------------------------


def theme() -> str:
    return "dark" if getattr(st.context.theme, "type", None) == "dark" else "light"


def colors() -> dict[str, str]:
    return GROUP_COLORS[theme()]


def rands(value: float, signed: bool = False, cents: bool = True) -> str:
    """R12 345.67 (Capitec uses a space as the thousands separator)."""
    text = f"R{abs(value):,.{2 if cents else 0}f}".replace(",", " ")
    if value < 0:
        return "-" + text
    return ("+" + text) if signed and value > 0 else text


def month_label(month: str) -> str:
    return pd.Period(month).strftime("%b %Y")


def percent(value: float) -> str:
    return f"{value:.0%}"


@st.cache_data(show_spinner=False, max_entries=10)
def read_statement(data: bytes, password: str):
    return parse_statement(io.BytesIO(data), password=password or None)


class PasswordNeeded(Exception):
    pass


def load_statement(data: bytes, password: str):
    try:
        return read_statement(data, password)
    except StatementParseError:
        raise
    except Exception as error:  # pdfminer raises a few different types here
        if "password" in repr(error).lower() or "encrypt" in repr(error).lower():
            raise PasswordNeeded() from error
        raise StatementParseError(
            "We couldn't read this PDF. Please upload the statement exactly as "
            "downloaded from Capitec (not a photo or scan)."
        ) from error


def prefs() -> Preferences:
    if "prefs" not in st.session_state:
        st.session_state.prefs = storage.load(storage.preferences_path())
    return st.session_state.prefs


def save_prefs(message: str) -> None:
    storage.save(prefs(), storage.preferences_path())
    # New widget keys so editors don't re-apply their old edits to the new data
    st.session_state.version = st.session_state.get("version", 0) + 1
    st.session_state.toast = message
    st.rerun()


def version() -> int:
    return st.session_state.get("version", 0)


def editor_key(name: str, keys: pd.Series) -> str:
    """A widget key that changes whenever the rows shown change.

    Streamlit applies pending table edits by row position, so a table whose
    rows change (new filters, a save) must start fresh.
    """
    return f"{name}_{version()}_{pd.util.hash_pandas_object(keys, index=False).sum()}"


def chart_layout(fig: go.Figure, height: int, **extra) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                    traceorder="normal"),
        hoverlabel=dict(namelength=-1),
        bargap=0.25,
        **extra,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridwidth=1)
    return fig


# --- landing page --------------------------------------------------------------


def landing() -> None:
    st.title("💰 Money Sorter")
    st.markdown(
        "#### See where your money goes, straight from your Capitec bank statement.\n"
        "Upload a statement PDF in the sidebar and every transaction is sorted on three levels:"
    )
    one, two, three = st.columns(3)
    with one, st.container(border=True):
        st.markdown("**1 · In or out**")
        st.markdown("**Credit**: money that came into your account.  \n**Debit**: money that left it.")
    with two, st.container(border=True):
        st.markdown("**2 · Group**")
        st.markdown(
            "**Needs**: essentials like groceries, rent, transport.  \n"
            "**Wants**: nice-to-haves like takeaways and clothes.  \n"
            "**Savings**: money you put away.  \n"
            "Money in is **Income** (or **Savings** coming back to you)."
        )
    with three, st.container(border=True):
        st.markdown("**3 · Category**")
        st.markdown("What it was for: groceries, transport, fees, alcohol, gifts and "
                    f"{len(cats.CATEGORIES) - 5} more.")
    st.markdown(
        "**How to get your statement:** download a PDF statement from the Capitec app or "
        "online banking. Longer periods (3 to 12 months) give a better picture. You can "
        "upload several statements at once.\n\n"
        "**Your privacy:** the statement is read in memory on the computer running this app "
        "and is never stored. Only the categories you teach the app are saved."
    )
    st.caption("Money Sorter is an independent tool and isn't affiliated with Capitec Bank.")


# --- sidebar -------------------------------------------------------------------


def sidebar_upload():
    with st.sidebar:
        st.subheader("Your statement")
        files = st.file_uploader(
            "Capitec statement (PDF)",
            type="pdf",
            accept_multiple_files=True,
            help="Upload one or more statements. Overlapping periods are fine; duplicates are removed.",
        )
        with st.expander("Is the PDF password-protected?"):
            password = st.text_input("PDF password", type="password", help="Often your ID number.")
        st.caption("🔒 Read in memory, never stored.")
    return files, password


def sidebar_filters(frame: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.divider()
        st.subheader("Filters")
        first, last = frame["date"].min().date(), frame["date"].max().date()
        picked = st.date_input("Dates", value=(first, last), min_value=first, max_value=last, format="DD/MM/YYYY")
        start, end = (picked if isinstance(picked, (tuple, list)) and len(picked) == 2 else (first, last))
        directions = st.pills("Money", [CREDIT, DEBIT], selection_mode="multi", default=[CREDIT, DEBIT],
                              format_func=lambda d: "In (credit)" if d == CREDIT else "Out (debit)")
        groups = st.pills("Group", list(cats.ALL_GROUPS), selection_mode="multi", default=list(cats.ALL_GROUPS))
        chosen = st.multiselect("Categories", sorted(frame["category"].unique()), placeholder="All categories",
                                format_func=cats.label)
        search = st.text_input("Search descriptions", placeholder="e.g. Checkers")

    mask = frame["date"].dt.date.between(start, end)
    mask &= frame["direction"].isin(directions or [CREDIT, DEBIT])
    mask &= frame["group"].isin(groups or list(cats.ALL_GROUPS))
    if chosen:
        mask &= frame["category"].isin(chosen)
    if search:
        mask &= frame["description"].str.contains(search, case=False, regex=False)
    return frame[mask]


# --- tabs ----------------------------------------------------------------------


def overview(view: pd.DataFrame) -> None:
    totals = analysis.summary(view)
    income = totals["income"]
    months = totals["months"]

    first_row = st.columns(3)
    first_row[0].metric("Money in (credits)", rands(totals["money_in"], cents=False), border=True,
                        help="Everything that came in, including money moved back from your savings.")
    first_row[1].metric("Money out (debits)", rands(totals["money_out"], cents=False), border=True,
                        help="Everything that left, including transfers into savings.")
    first_row[2].metric("Bank fees", rands(totals["fees"]), f"{rands(totals['fees'] / months)} a month",
                        delta_color="off", delta_arrow="off", border=True)
    second_row = st.columns(3)
    for tile, group in zip(second_row, (NEEDS, WANTS, SAVINGS)):
        share = totals[group] / income if income else 0
        name = "Saved (net of withdrawals)" if group == SAVINGS else f"Spent on {group.lower()}"
        tile.metric(name, rands(totals[group], cents=False), f"{percent(share)} of income", delta_color="off",
                    delta_arrow="off", border=True)

    left, right = st.columns([5, 4], gap="large")
    with left:
        st.subheader("Where your income went")
        st.caption(f"Income this period: **{rands(income)}** (salary and other money in, "
                   "not counting money moved back from savings).")
        split = analysis.income_split(view)
        st.plotly_chart(income_split_chart(split), width="stretch", config={"displayModeBar": False})
        for line in income_insights(split, months):
            st.markdown(line)
    with right:
        st.subheader("Biggest spending categories")
        table = analysis.by_category(view, DEBIT)
        table = table[table["group"].isin([NEEDS, WANTS])].head(8)
        if table.empty:
            st.info("No spending in this selection.")
        else:
            st.dataframe(
                table.assign(category=table["category"].map(cats.label))[["category", "group", "total", "per_month"]],
                hide_index=True, width="stretch",
                column_config={"category": "Category", "group": "Group",
                               "total": money_column("Total"), "per_month": money_column("Per month")},
            )
        if totals["to_review"]:
            st.info(f"🔍 **{totals['to_review']} transactions** need a quick check (mostly payments to "
                    "people and cash). Sorting them in the **Review** tab makes these numbers sharper.")

    st.subheader("Month by month")
    table = analysis.monthly(view)
    if len(table) < 1:
        return
    st.plotly_chart(monthly_chart(table), width="stretch", config={"displayModeBar": False})
    st.caption("Saved (net) is what went into savings and investments minus what came back out. "
               "Below zero means you used more savings than you put away that month.")
    st.plotly_chart(savings_chart(table), width="stretch", config={"displayModeBar": False})
    with st.expander("Table view"):
        shown = table.copy()
        shown.index = [month_label(m) for m in shown.index]
        st.dataframe(shown.rename(columns={SAVINGS: "Saved (net)"}), width="stretch",
                     column_config={c: MONEY for c in shown.columns})


def income_split_chart(split: pd.DataFrame) -> go.Figure:
    palette = colors()
    fig = go.Figure()
    for _, row in split.iterrows():
        group = row["group"]
        values = [row["guide"] * 100, row["share"] * 100]
        fig.add_bar(
            y=["50/30/20 guide", "You"],
            x=values,
            name=group,
            orientation="h",
            marker=dict(color=palette[group], line=dict(color=SURFACE[theme()], width=2)),
            text=[f"{group} {v:.0f}%" if v >= 9 else "" for v in values],
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(color="#ffffff"),
            hovertemplate="%{y} · " + group + ": %{x:.1f}% of income<extra></extra>",
        )
    fig.update_layout(barmode="stack")
    fig.update_xaxes(ticksuffix="%", rangemode="tozero")
    return chart_layout(fig, 220)


def income_insights(split: pd.DataFrame, months: float) -> list[str]:
    lines = []
    for _, row in split.iterrows():
        group, share, guide = row["group"], row["share"], row["guide"]
        if group == SAVINGS:
            verdict = "on track" if share >= guide else "below the guide"
            lines.append(f"- **Savings:** you put away **{percent(share)}** of income after withdrawals "
                         f"(guide {percent(guide)}): {verdict}.")
        else:
            diff = share - guide
            if diff > 0.02:
                verdict = f"{percent(diff)} above the guide"
            elif diff < -0.02:
                verdict = f"{percent(-diff)} below the guide"
            else:
                verdict = "right on the guide"
            per_month = rands(row["amount"] / months)
            lines.append(f"- **{group}:** **{percent(share)}** of income, about {per_month} a month "
                         f"(guide {percent(guide)}): {verdict}.")
    return lines


def monthly_chart(table: pd.DataFrame) -> go.Figure:
    palette = colors()
    labels = [month_label(m) for m in table.index]
    fig = go.Figure()
    for group in (NEEDS, WANTS):
        fig.add_bar(x=labels, y=table[group], name=group,
                    marker=dict(color=palette[group], line=dict(color=SURFACE[theme()], width=2)),
                    hovertemplate="%{x} · " + group + ": R%{y:,.2f}<extra></extra>")
    fig.add_scatter(x=labels, y=table[INCOME], name="Income", mode="lines+markers",
                    line=dict(color=palette[INCOME], width=2), marker=dict(size=8),
                    hovertemplate="%{x} · Income: R%{y:,.2f}<extra></extra>")
    fig.update_layout(barmode="relative", hovermode="x unified")
    fig.update_yaxes(tickprefix="R", separatethousands=True)
    return chart_layout(fig, 340)


def savings_chart(table: pd.DataFrame) -> go.Figure:
    labels = [month_label(m) for m in table.index]
    fig = go.Figure()
    fig.add_bar(x=labels, y=table[SAVINGS], name="Saved (net)",
                marker=dict(color=colors()[SAVINGS], line=dict(color=SURFACE[theme()], width=2)),
                hovertemplate="%{x} · Saved (net): R%{y:,.2f}<extra></extra>")
    fig.update_yaxes(tickprefix="R", separatethousands=True, zeroline=True, zerolinecolor=MUTED)
    fig.update_layout(showlegend=False)
    return chart_layout(fig, 220)


def categories_tab(view: pd.DataFrame) -> None:
    show = st.segmented_control(
        "Show", ["Spending", SAVINGS, INCOME], default="Spending", key="cat_view",
        format_func=lambda v: {"Spending": "Spending (needs & wants)", SAVINGS: "Savings", INCOME: "Money in"}[v],
    ) or "Spending"
    table = analysis.by_category(view, CREDIT if show == INCOME else DEBIT)
    if show == "Spending":
        table = table[table["group"].isin([NEEDS, WANTS])]
    elif show == SAVINGS:
        table = table[table["group"] == SAVINGS]
        st.caption("Net amounts: what went into savings minus what came back out to your main account.")
    if table.empty:
        st.info("Nothing to show for this selection.")
        return
    total = table["total"].sum()
    table = table.assign(share=table["total"] / total if total else 0.0)
    left, right = st.columns([2, 3], gap="large")
    with left:
        st.plotly_chart(category_chart(table), width="stretch", config={"displayModeBar": False})
    with right:
        st.dataframe(
            table.assign(category=table["category"].map(cats.label))[
                ["category", "group", "total", "per_month", "share"]],
            hide_index=True, width="stretch", height=38 + 35 * len(table),
            column_config={
                "category": st.column_config.TextColumn("Category", width="medium"),
                "group": st.column_config.TextColumn("Group", width="small"),
                "total": money_column("Total"),
                "per_month": money_column("Per month"),
                "share": st.column_config.ProgressColumn("Share", format="percent", min_value=0, max_value=1,
                                                         width="small"),
            },
        )

    st.subheader("Look inside a category")
    category = st.selectbox("Category", table["category"], format_func=cats.label, key=f"drill_{show}")
    rows = view[view["category"] == category]
    info = cats.get(category)
    st.caption(f"{info.help}. Group: **{rows['group'].mode().iat[0] if not rows.empty else info.group}**.")
    # Show spending and saving as positive amounts; refunds then show as negatives
    sign, heading = (1, "Received") if show == INCOME else (-1, "Spent" if show == "Spending" else "Saved")
    places, items = st.columns([2, 3], gap="large")
    with places:
        merchants = (rows.groupby("merchant")["amount"].agg(["sum", "size"]).reset_index()
                     .rename(columns={"merchant": "Merchant / payee", "sum": "total", "size": "Count"}))
        merchants["total"] *= sign
        merchants = merchants.sort_values("total", ascending=False)
        st.dataframe(merchants, hide_index=True, width="stretch", column_config={"total": money_column(heading)})
    with items:
        st.dataframe(
            rows.assign(amount=rows["amount"] * sign)[["date", "description", "amount"]]
            .sort_values("date", ascending=False),
            hide_index=True, width="stretch",
            column_config={"date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                           "description": "Description", "amount": money_column(heading)},
        )

    st.subheader("Category by month")
    pivot = analysis.category_by_month(view, CREDIT if show == INCOME else DEBIT)
    pivot = pivot[pivot.index.isin(table["category"])]
    pivot.columns = [month_label(c) if c != "Total" else c for c in pivot.columns]
    pivot.index = [cats.label(c) for c in pivot.index]
    st.dataframe(pivot, width="stretch", column_config={c: MONEY for c in pivot.columns})


def category_chart(table: pd.DataFrame) -> go.Figure:
    palette = colors()
    fig = go.Figure()
    for group in cats.ALL_GROUPS:
        part = table[table["group"] == group]
        if part.empty:
            continue
        fig.add_bar(
            y=part["category"].map(cats.label), x=part["total"], name=group, orientation="h",
            marker=dict(color=palette[group], line=dict(color=SURFACE[theme()], width=2)),
            customdata=part[["count"]],
            hovertemplate="%{y}: R%{x:,.2f} · %{customdata[0]} transactions<extra>" + group + "</extra>",
        )
    order = list(table["category"].map(cats.label))
    fig.update_yaxes(categoryorder="array", categoryarray=order[::-1])
    fig.update_xaxes(tickprefix="R", separatethousands=True, showgrid=True)
    fig.update_layout(barmode="overlay")
    return chart_layout(fig, 60 + 26 * len(table))


def transactions_tab(view: pd.DataFrame) -> None:
    st.markdown("Change a transaction's **group** or **category** right in the table; it's saved straight away. "
                "To sort every transaction from the same payee at once, use the **Review** tab or add a rule.")
    show_fees = st.toggle("Show fee rows", value=False,
                          help="Capitec charges many transactions a small fee. They're counted under Bank Fees.")
    rows = view if show_fees else view[~view["is_fee"]]
    rows = rows.sort_values("date", ascending=False)
    columns = ["date", "description", "amount", "direction", "group", "category", "source", "needs_review"]
    edited = st.data_editor(
        rows.set_index("key")[columns],
        key=editor_key("tx_editor", rows["key"]),
        hide_index=True,
        width="stretch",
        height=560,
        disabled=["date", "description", "amount", "direction", "source", "needs_review"],
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "amount": st.column_config.NumberColumn("Amount", format="R %.2f"),
            "direction": st.column_config.TextColumn("1 · In/out"),
            "group": st.column_config.SelectboxColumn("2 · Group", options=list(cats.ALL_GROUPS), required=True),
            "category": st.column_config.SelectboxColumn("3 · Category", options=[c.name for c in cats.CATEGORIES],
                                                         required=True),
            "source": st.column_config.TextColumn("Why", help="What decided the category"),
            "needs_review": st.column_config.CheckboxColumn("Check?"),
        },
    )
    original = rows.set_index("key")
    changed = (edited["category"] != original["category"]) | (edited["group"] != original["group"])
    changes = {}
    for key in edited.index[changed]:
        edit = {}
        for column in ("category", "group"):
            if edited.at[key, column] != original.at[key, column]:
                edit[column] = edited.at[key, column]
        changes[key] = {**prefs().edits.get(key, {}), **edit}
    if changes:
        prefs().edits.update(changes)
        save_prefs(f"Saved {len(changes)} change(s).")

    csv = view.drop(columns=["key"]).to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download as CSV", csv, file_name="classified_transactions.csv", mime="text/csv")


def review_tab(view: pd.DataFrame) -> None:
    queue = analysis.review_queue(view)
    st.subheader(f"{int(view['needs_review'].sum())} transactions to check")
    if queue.empty:
        st.success("Nothing to review: every transaction in this selection has a clear category. 🎉")
        return
    st.markdown(
        "We couldn't tell what these were for, usually because they're payments to people, cash, "
        "or shops we don't know. **Pick a category once per payee** and every transaction with that "
        "payee (now and in future statements) is sorted the same way. Leave a row blank to skip it."
    )
    queue = queue.assign(new_category=None, new_group=None)
    edited = st.data_editor(
        queue,
        placeholder="",
        key=editor_key("review_editor", queue["merchant"] + queue["category"]),
        hide_index=True,
        width="stretch",
        height=min(38 + 35 * len(queue), 600),
        disabled=["merchant", "direction", "category", "count", "total"],
        column_config={
            "merchant": st.column_config.TextColumn("Payee / merchant", width="medium"),
            "direction": "In/out",
            "category": "Currently",
            "count": st.column_config.NumberColumn("Transactions"),
            "total": money_column("Total"),
            "new_category": st.column_config.SelectboxColumn(
                "New category", options=[c.name for c in cats.CATEGORIES], width="medium"),
            "new_group": st.column_config.SelectboxColumn(
                "Group (optional)", options=list(cats.ALL_GROUPS),
                help="Leave blank to use the category's usual group"),
        },
    )
    chosen = edited[edited["new_category"].notna()]
    if st.button(f"Save {len(chosen)} choice(s)", type="primary", disabled=chosen.empty):
        for _, row in chosen.iterrows():
            prefs().rules.append(UserRule(match=row["merchant"], category=row["new_category"],
                                          group=row["new_group"] if pd.notna(row["new_group"]) else None))
        save_prefs(f"Saved {len(chosen)} rule(s).")


def rules_tab() -> None:
    preferences = prefs()
    st.subheader("Your rules")
    st.caption("A rule applies when the description contains the text (or the payee name matches it). "
               "Your rules always win over the built-in ones. The first matching rule is used.")
    rules = pd.DataFrame([vars(r) for r in preferences.rules], columns=["match", "category", "group"])
    edited = st.data_editor(
        rules, key=f"rules_editor_{version()}", num_rows="dynamic", hide_index=True, width="stretch",
        column_config={
            "match": st.column_config.TextColumn("Description contains", required=True),
            "category": st.column_config.SelectboxColumn("Category", options=[c.name for c in cats.CATEGORIES],
                                                         required=True),
            "group": st.column_config.SelectboxColumn("Group (optional)", options=list(cats.ALL_GROUPS)),
        },
    )
    if st.button("Save rules"):
        clean = edited.dropna(subset=["match", "category"])
        preferences.rules = [UserRule(match=str(r["match"]), category=r["category"],
                                      group=r["group"] if pd.notna(r["group"]) else None)
                             for _, r in clean.iterrows() if str(r["match"]).strip()]
        save_prefs("Rules saved.")

    st.subheader("Which group each category belongs to")
    st.caption("Disagree with a default? For example, if clothing is a need for you, move it to Needs.")
    groups = pd.DataFrame([
        {"category": c.name, "default": c.group, "group": preferences.category_groups.get(c.name, c.group)}
        for c in cats.CATEGORIES
    ])
    edited_groups = st.data_editor(
        groups, key=f"groups_editor_{version()}", hide_index=True, width="stretch", height=400,
        disabled=["category", "default"],
        column_config={"category": "Category", "default": "Default group",
                       "group": st.column_config.SelectboxColumn("Your group", options=list(cats.ALL_GROUPS),
                                                                 required=True)},
    )
    if st.button("Save groups"):
        preferences.category_groups = {r["category"]: r["group"] for _, r in edited_groups.iterrows()
                                       if r["group"] != r["default"]}
        save_prefs("Groups saved.")

    st.subheader("Back up or move your settings")
    path = storage.preferences_path()
    st.caption(f"Saved automatically to `{path}`." if path else
               "Settings last for this session only. Download them to keep them.")
    left, right = st.columns(2)
    with left:
        st.download_button("⬇️ Download settings", storage.dumps(preferences),
                           file_name="money_sorter_settings.json", mime="application/json")
        if preferences.edits and st.button(f"Clear {len(preferences.edits)} single-transaction edit(s)"):
            preferences.edits = {}
            save_prefs("Single-transaction edits cleared.")
    with right:
        uploaded = st.file_uploader("Restore settings", type="json", key=f"settings_upload_{version()}")
        if uploaded is not None:
            try:
                st.session_state.prefs = storage.loads(uploaded.getvalue().decode("utf-8"))
            except (ValueError, TypeError, KeyError):
                st.error("That file doesn't look like Money Sorter settings.")
            else:
                save_prefs("Settings restored.")

    with st.expander("How transactions are classified"):
        st.markdown(
            "1. **Your rules and edits** always come first.\n"
            "2. **Built-in keyword rules** for things Capitec labels loosely: savings transfers, "
            "insurers, cellphone networks, streaming services, Uber, betting sites and more.\n"
            "3. **Capitec's own category** printed on the statement, when it's specific "
            "(e.g. *Groceries*).\n"
            "4. **Name matching**: payments to your own accounts at other banks, and payments to people "
            "who share your surname (treated as family support).\n"
            "5. **Well-known merchants** (Pick n Pay, KFC, Engen, ...).\n"
            "6. **The payment type**: cash withdrawals, payments to people, debit orders.\n\n"
            "Capitec's fees (the *Fee* column) are split into their own **Bank Fees** rows, so every "
            "rand that left your account is counted exactly once."
        )


# --- main --------------------------------------------------------------------


def main() -> None:
    if message := st.session_state.pop("toast", None):
        st.toast(message, icon="✅")

    files, password = sidebar_upload()
    if not files:
        landing()
        return

    statements = []
    for file in files:
        try:
            with st.spinner(f"Reading {file.name}...", show_time=True):
                statements.append(load_statement(file.getvalue(), password))
        except PasswordNeeded:
            if password:
                st.warning(f"🔐 That password didn't open **{file.name}**. Please check it and try again.")
            else:
                st.warning(f"🔐 **{file.name}** is password-protected. Enter its password in the sidebar.")
        except StatementParseError as error:
            st.error(f"**{file.name}**: {error}")
    if not statements:
        return

    holder = next((s.account_holder for s in statements if s.account_holder), "")
    frame = Classifier(prefs(), account_holder=holder).to_frame(statements)
    if frame.empty:
        st.warning("No money moved in these statements.")
        return

    accounts = sorted({s.masked_account for s in statements if s.account_number})
    starts = [s.from_date for s in statements if s.from_date] or [frame["date"].min().date()]
    ends = [s.to_date for s in statements if s.to_date] or [frame["date"].max().date()]
    st.title("💰 Money Sorter")
    st.markdown(f"**Account {', '.join(accounts) or ''}** · {fmt_date(min(starts))} to {fmt_date(max(ends))} · "
                f"{(~frame['is_fee']).sum():,} transactions".replace(",", " "))
    for statement in statements:
        if statement.reconciled:
            continue
        first = statement.balance_mismatches[0] if statement.balance_mismatches else None
        where = (f" from {fmt_date(statement.transactions[first[0]].date)}" if first else "")
        st.warning(f"⚠️ Some amounts{where} don't add up to the balances printed on the statement, "
                   "so a few transactions may have been misread. Totals could be slightly off.")
    if all(s.reconciled for s in statements):
        st.caption("✅ Every amount we read adds up exactly to the balances printed on your statement.")

    view = sidebar_filters(frame)
    if view.empty:
        st.info("No transactions match your filters.")
        return

    # Stable labels and a key keep you on the same tab when saving reruns the app
    tabs = st.tabs(["📊 Overview", "🗂️ Categories", "📄 Transactions", "🔍 Review", "⚙️ Rules"], key="main_tabs")
    with tabs[0]:
        overview(view)
    with tabs[1]:
        categories_tab(view)
    with tabs[2]:
        transactions_tab(view)
    with tabs[3]:
        review_tab(view)
    with tabs[4]:
        rules_tab()


def fmt_date(value: date) -> str:
    return value.strftime("%d %b %Y").lstrip("0")


main()
