"""Keyword rules that map a transaction description to a category.

Rules are regular expressions matched (case-insensitively) against the
description printed on the statement.

* STRONG rules run before Capitec's own category is considered. They cover
  transaction types Capitec labels generically ("Transfer", "Digital
  Payments") and merchants Capitec labels inconsistently (the same insurer
  shows up as "Pets" one month and "Vehicle Insurance" the next).
* WEAK rules only run when Capitec's category is generic or missing, e.g.
  older statements without a category column, so they don't override a label
  that came from the card's merchant code or that the client set in the app.
* FALLBACK rules recognise the payment type (cash, transfer to a person,
  debit order) when nothing says what the money was for.

The first matching rule in each list wins, so put specific rules first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .categories import CREDIT, DEBIT


@dataclass(frozen=True)
class Rule:
    category: str
    pattern: str
    direction: str | None = None  # None matches both credits and debits
    regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "regex", re.compile(self.pattern, re.IGNORECASE))

    def matches(self, description: str, direction: str) -> bool:
        if self.direction and self.direction != direction:
            return False
        return bool(self.regex.search(description))


DEBIT_ORDER = r"(debit order|debicheck)"

STRONG_RULES: tuple[Rule, ...] = (
    # Bank charges booked as their own line, e.g. "Adjustment: Fee Netflix Purchase"
    Rule("Bank Fees", r"^adjustment: fee\b|\bfee$|\bfee:", DEBIT),
    Rule("Refunds & Reversals", r"\b(refund|reversal|reversed|correction|chargeback)\b", CREDIT),
    # Capitec savings: round-ups, interest sweeps and moves between your own accounts
    Rule("Savings", r"live better (round-up|interest sweep)|^banking app transfer to ", DEBIT),
    Rule("Savings", r"^banking app transfer (received )?from |live better savings", CREDIT),
    Rule("Interest", r"^interest received|\binterest\b", CREDIT),
    Rule("Salary", r"\b(salary|salaries|wages?|payroll|stipend)\b", CREDIT),
    Rule("Rental Income", r"\brent\b", CREDIT),
    Rule("Loans", r"\bloan\b", CREDIT),
    Rule("Cash Deposits", r"\bcash dep", CREDIT),
    Rule(
        "Investments",
        r"\b(invest\w*|inve$|equit(y|ies)|easyequities|stokvel|unit trusts?|satrix|etfs?|"
        r"allan gray|coronation|sygnia|10x|retirement annuity|capital)\b",
        DEBIT,
    ),
    Rule(
        "Health & Medical",
        r"\b(medical aid|discovery health|dischemmi|dis-chem medical|bonitas|medshield|"
        r"bestmed|fedhealth|unity h|keyhealth|medihelp|sizwe|profmed|polmed|gems)\b",
        DEBIT,
    ),
    Rule(
        "Insurance",
        r"\b(dotsure|legalwise|accprotect|outsurance|miway|king price|hollard|clientele|"
        r"assupol|avbob|1life|budget insurance|first for women|dialdirect|"
        r"insurance|assurance|funeral)\b",
        DEBIT,
    ),
    Rule(
        "Insurance",
        DEBIT_ORDER + r".*\b(sanlam|sl-debits|old mutual|liberty|momentum|metropolitan|"
        r"discovery|santam|pps)\b",
        DEBIT,
    ),
    Rule("Utilities", r"prepaid purchase: electricity|\beskom\b|municipal|(payment|debit order).*\bcity of\b", DEBIT),
    Rule(
        "Cellphone & Internet",
        r"\b(afrihost|telkom\w*|vodacom|mtn|cell c|rain|webafrica|vox|openserve|mweb|"
        r"cool ideas|herotel|vumatel|airtime)\b",
        DEBIT,
    ),
    Rule("Housing", r"\brent(?!okil|al car|-a-)|\bbond\b|home loan|levies|body corporate|real estate|estate agent", DEBIT),
    Rule("Takeaways & Coffee", r"\buber ?eats\b|\bmr ?d food\b|\bmr delivery\b|\bnando'?s\b", DEBIT),
    Rule(
        "Transport",
        r"\b(uber|bolt|indriver|taxify|didi|myciti|gautrain|metrorail|prasa|putco|"
        r"golden arrow|greyhound|intercape|translux|rea vaya|areyeng)\b",
        DEBIT,
    ),
    Rule(
        "Subscriptions",
        r"\b(netflix|showmax|dstv|multichoice|spotify|youtube\w*|apple\.com|icloud|"
        r"disney|prime video|deezer|google(?! cloud))\b",
        DEBIT,
    ),
    Rule(
        "Software & Tech",
        r"\b(github|openrouter|anthropic|openai|chatgpt|pythonanywhere|rapidapi|google cloud|"
        r"aws|amazon web services|microsoft|adobe|canva|digitalocean|heroku|vercel|netlify|"
        r"cloudflare|jetbrains|dropbox|zoom\.us|steam games|playstation|xbox|nintendo)\b",
        DEBIT,
    ),
    Rule(
        "Gambling",
        r"\b(4racing|betway|hollywood ?bets|supabets|sportingbet|lottostar|lotto|gbets|"
        r"easybet|playa ?bets|world sports betting|sunbet|yesplay|betxchange|10bet|ithuba|casino)\b",
        DEBIT,
    ),
    Rule("Tobacco & Vaping", r"\b(canna\w*|vape\w*|vapour|tobacco|twisp|hubbly|shisa)\b", DEBIT),
    Rule(
        "Travel & Holidays",
        r"\b(flysafai\w*|airlink|lift airline|kulula|british airways|emirates|qatar airways|"
        r"booking\.com|airbnb|travelstart|city lodge|protea hotel|avis|hertz|europcar|"
        r"tempest car|first car rental)\b",
        DEBIT,
    ),
    Rule("Legal & Professional", r"\b(lawyers?|attorneys?|advocate|inc attorneys)\b", DEBIT),
    Rule("Sport & Hobbies", r"\b(gym|fitness|virgin active|planet fitness)\b", DEBIT),
    Rule("Personal Care", r"\b(salon|barber\w*|hair ?cut|nails)\b", DEBIT),
    Rule("Shopping", r"\b(jewell?ery|jewellers?)\b", DEBIT),
)

WEAK_RULES: tuple[Rule, ...] = (
    Rule(
        "Groceries",
        r"\b(pick ?n ?pay|pnp|checkers|shoprite|spar|kwikspar|superspar|boxer|usave|"
        r"food lover'?s|fruit ?& ?veg|ok (foods|minimark|grocer)|cambridge food|save ?mor|"
        r"woolworths food|butcher\w*|meats?|super ?store|supermarket|superette|spaza|general (store|dealer)|bakery)\b",
        DEBIT,
    ),
    Rule(
        "Takeaways & Coffee",
        r"\b(kfc|mcdonald'?s|steers|debonairs|chicken licken|wimpy|burger king|roman'?s pizza|"
        r"fishaways|pedros|hungry lion|galitos|king pie|simply asia|pizza\w*|starbucks|vida e|"
        r"seattle coffee|bootlegger|coffee|fish ?(and|&) ?chips)\b",
        DEBIT,
    ),
    Rule(
        "Restaurants",
        r"\b(spur|ocean basket|mugg ?& ?bean|panarottis|rocomamas|hussar grill|cattle baron|"
        r"john dory'?s|restaurant|grill|bistro|sushi|eatery)\b",
        DEBIT,
    ),
    Rule(
        "Alcohol",
        r"\b(liquor\w*|tops|bottle ?store|tavern|pub|bar|brewery|brewing|cellars|distillery|"
        r"ultra liquors|norman goodfellows)\b",
        DEBIT,
    ),
    Rule("Fuel", r"\b(engen|shell|bp|sasol|caltex|total(energies)?|astron|garage|service station)\b", DEBIT),
    Rule("Parking & Tolls", r"\b(parking|parkade|parkin|parki|street wallet|tolls?|sanral|e-toll)\b", DEBIT),
    Rule(
        "Home & Furniture",
        r"\b(builders|cashbuild|leroy merlin|lewis|ok furniture|bradlows|russells|coricraft|"
        r"@home|mr price home|pep home|sheet street|hifi corp|furniture)\b",
        DEBIT,
    ),
    Rule(
        "Clothing & Shoes",
        r"\b(mr ?price|pep|ackermans|jet|edgars|truworths|foschini|markham|totalsports|"
        r"sportscene|h ?& ?m|zara|cotton on|identity|legit|jam clothing|studio 88|"
        r"superbalist|shein|shoes?|clothing|fashion)\b",
        DEBIT,
    ),
    Rule(
        "Health & Medical",
        r"\b(clicks|dis-?chem|pharmacy|pharm\w*|medirite|spec-?savers|netcare|mediclinic|"
        r"pathcare|lancet|ampath|dr\.?|doctor|dentist|optometrist|physio\w*|hospital|clinic)\b",
        DEBIT,
    ),
    Rule(
        "Debt Repayments",
        r"\b(pay ?just ?now|payflex|happy ?pay|mobicred|rcs|credit card|repayment|wonga|"
        r"capfin|african bank|account payment)\b",
        DEBIT,
    ),
    Rule("Home Maintenance", r"\b(hardware|plumb\w*|electrician|handyman|locksmith|pest control)\b", DEBIT),
    Rule(
        "Shopping",
        r"\b(takealot|amazon|temu|aliexpress|makro|game|incredible connection|istore|"
        r"cna|wikideals|bash)\b",
        DEBIT,
    ),
    Rule(
        "Entertainment",
        r"\b(ster kinekor|nu metro|cinema|webtickets|computicket|quicket|howler|ticketpro|"
        r"concert|festival|museum|aquarium|cableway)\b",
        DEBIT,
    ),
    Rule(
        "Vehicle Costs",
        r"\b(tyres?|supa quick|tiger wheel|midas|autozone|motor spares|masterparts|car wash|"
        r"licen[cs]e|rtmc|natis|testing cent(re|er)|traffic)\b",
        DEBIT,
    ),
    Rule(
        "Education",
        r"\b(school|college|university|unisa|tuition|creche|daycare|educare|academy|tvet|"
        r"udemy|coursera|stationery)\b",
        DEBIT,
    ),
    Rule("Pets", r"\b(vet|veterinary|pet ?shop|petstock|absolute pets)\b", DEBIT),
    Rule("Gifts & Donations", r"\b(donation|church|tithe|offering|charity|npo|nicro|gift\w*)\b", DEBIT),
    Rule(
        "Family Support",
        r"\b(mom|mother|mum|mama|dad|father|papa|gogo|granny|grandma|parents?|family|"
        r"support|allowance|pocket money)\b",
        DEBIT,
    ),
    Rule("Travel & Holidays", r"\b(booking|hotel|lodge|guest ?house|holiday)\b", DEBIT),
)

FALLBACK_RULES: tuple[Rule, ...] = (
    Rule("Cash Withdrawals", r"cash sent|cash withdrawal|\batm\b", DEBIT),
    Rule("Other Bills", DEBIT_ORDER, DEBIT),
    Rule(
        "Payments to People",
        r"(immediate|payshap|external|recurring) (business )?payment|^recurring payment",
        DEBIT,
    ),
    Rule("Money Received", r"payment received|received from|\breceived\b", CREDIT),
)
