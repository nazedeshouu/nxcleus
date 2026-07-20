"""Ledger seed kit — Aldgate Holdings plc group finance (09 §5 Demo 3, Regulatory Report Factory).

Mock source systems + synthetic financials for a 20-subsidiary holding company: a double-entry
general ledger (~640k journal lines) plus its reference data (entities, chart of accounts,
counterparties, daily FX). Six patterns are planted so the suggested prompts find real things
(track rule anchor 09 §3): intercompany balance mismatches, revenue misclassified to expense
accounts, counterparty LEI gaps, unbalanced journal batches, revenue receipts misfiled onto expense
credits (detectable only by reading the memo narrative, not any keyword), and circular intercompany
revenue rings that inflate group revenue while netting to zero. All outputs computed live.

Deterministic: local random.Random(SEED + salt) only (09 §7). Run via scripts/seed.py or standalone.
Output: infra/seeds/out/ledger.db
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from ._gen import country, day_between, full_name, rng

OUT = Path(__file__).resolve().parent / "out"

# Special account codes referenced by the planted patterns (all live in the ranges below).
CASH = "1000"       # asset  — Cash and Cash Equivalents (offsetting leg everywhere)
IC_RECV = "1010"    # asset  — Intercompany Receivable (A-side of an IC loan)
IC_PAY = "2010"     # liab.  — Intercompany Payable    (B-side of an IC loan)

_ENTITIES = [
    ("Aldgate Capital Partners Ltd", "GB", "GBP"), ("Aldgate Manufacturing GmbH", "DE", "EUR"),
    ("Aldgate Logistics SA", "FR", "EUR"), ("Aldgate Retail UK Ltd", "GB", "GBP"),
    ("Aldgate Technologies Inc", "US", "USD"), ("Aldgate Energy Trading LLC", "US", "USD"),
    ("Aldgate Pharma KK", "JP", "JPY"), ("Aldgate Real Estate Ltd", "GB", "GBP"),
    ("Aldgate Insurance Ltd", "US", "USD"), ("Aldgate Media Group Inc", "US", "USD"),
    ("Aldgate Foods Pty", "AU", "AUD"), ("Aldgate Mining Corp", "CA", "CAD"),
    ("Aldgate Financial Services AG", "DE", "EUR"), ("Aldgate Aviation Ltd", "GB", "GBP"),
    ("Aldgate Chemicals BV", "DE", "EUR"), ("Aldgate Telecom SAS", "FR", "EUR"),
    ("Aldgate Automotive GmbH", "DE", "EUR"), ("Aldgate Ventures LP", "US", "USD"),
    ("Aldgate Shipping Ltd", "CA", "CAD"), ("Aldgate Treasury Centre Inc", "US", "USD"),
]  # 20 subsidiaries

_CP_A = ["Northwind", "Silverline", "Baytree", "Crestford", "Halcyon", "Ironclad", "Cobalt",
         "Redwood", "Kestrel", "Marlow", "Brightwater", "Oakfield", "Sterling", "Vantage",
         "Amberline", "Fairhaven", "Granite", "Larkspur", "Pinecrest", "Thornbury"]
_CP_B = ["Trading", "Industries", "Supplies", "Logistics", "Consulting", "Components", "Metals",
         "Energy", "Systems", "Freight", "Chemicals", "Textiles", "Foods", "Services", "Partners"]
_CP_C = ["Ltd", "GmbH", "Inc", "SA", "LLC", "BV", "Pty", "AG", "SAS", "Corp"]
_LEI_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_EXP_MEMOS = ["Vendor payment", "Payroll run", "Office lease", "Utilities", "Professional fees",
              "Depreciation charge", "Travel and expenses", "Insurance premium", "IT services"]

# ── Narrative memo pools (rng 1210+). Journal memos become slot-filled prose drawn from these
#    skeletons so no single keyword names a pattern. The planted signal is MEANING: a revenue-
#    earning receipt narrative (INFLOW) sitting as a *credit to an expense account*, hidden among
#    thousands of legitimate expense credits (REFUND) that share the exact same journal structure.
#    INFLOW anchors are disjoint from every REFUND/OUTFLOW skeleton so the ground-truth oracle stays
#    precise, yet each anchor also floods the (benign) revenue accounts, so a lone LIKE cannot isolate.
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]
_PERIODS = ["Q1 FY2024", "Q2 FY2024", "Q3 FY2024", "Q4 FY2024", "Q1 FY2025", "Q2 FY2025",
            "Q3 FY2025", "H1 2025", "H2 2025", "FY2024", "FY2025", "the current period"]
_YEARWORDS = ["one", "two", "three", "four", "five"]
_ACCR_CATS = ["Accrued expense", "Provision charge", "Accrued liability", "Provision top-up", "Accrual"]

# INFLOW — money EARNED from a customer (belongs on a revenue account). 16 skeletons, each carrying
# exactly one anchor from _INFLOW_ANCHORS.
_INFLOW = [
    "Client retainer for {period} settled by {cp}, engagement {ref}",
    "Annual platform subscription renewed by {cp}, year {n}, account {ref}",
    "Membership dues collected from {cp} for {period}, ref {ref}",
    "Royalty statement {ref} received from {cp} covering {period}",
    "Advisory fee billed to {cp} and cleared, mandate {ref}",
    "Managed service charge to {cp} invoiced in {month}, order {ref}",
    "Hosting plan {ref} renewed by {cp}, billed {month}",
    "Seat licence expansion invoiced to {cp}, order {ref}",
    "Onboarding fee received from {cp}, project {ref}",
    "Data feed subscription {ref} renewed by {cp} for {period}",
    "Support plan {ref} billed to {cp} and receipted in {month}",
    "Usage overage charged to {cp}, statement {ref} for {period}",
    "Setup fee invoiced to {cp} for engagement {ref}",
    "Renewal uplift applied to {cp} contract {ref} for {period}",
    "Consulting engagement {ref} delivered to {cp} and invoiced",
    "Annual maintenance plan {ref} renewed by {cp} for {period}",
]
_INFLOW_ANCHORS = ["retainer", "subscription", "membership dues", "royalty", "advisory fee",
                   "managed service", "hosting plan", "seat licence", "onboarding fee", "data feed",
                   "support plan", "overage", "setup fee", "renewal uplift", "consulting engagement",
                   "maintenance plan"]

# REFUND — money coming back FROM a supplier we paid (legitimately reduces a cost; a real expense
# credit). Same journal shape as a misfiled revenue receipt; only the meaning differs. 16 skeletons.
_REFUND = [
    "Vendor refund credited against invoice {ref} from {cp}",
    "Supplier rebate applied for {period}, agreement {ref}",
    "Credit note {ref} received from {cp} in {month}",
    "Accrual release for {period}, provision {ref}",
    "Overpayment recovered from {cp}, ref {ref}",
    "Duplicate payment reversed, invoice {ref}",
    "Returned goods credited, order {ref} from {cp}",
    "Volume rebate posted for {period}, contract {ref}",
    "Warranty credit received from {cp}, claim {ref}",
    "Price adjustment credited on invoice {ref}",
    "Chargeback recovered from {cp}, case {ref}",
    "Unused deposit returned by {cp}, ref {ref}",
    "Expense reversal posted for {period}, journal {ref}",
    "Prepayment release for {period}, schedule {ref}",
    "Settlement discount taken on invoice {ref} from {cp}",
    "Reclassified accrual credited for {period}, ref {ref}",
]

# OUTFLOW — ordinary expense paid out (background sea; carries no planted signal). 15 skeletons, {cat}
# slotted from the expense/accrual category so the same pool serves both cash and accrued expenses.
_OUTFLOW = [
    "{cat} to {cp} settled, invoice {ref} in {month}",
    "{cat} paid for {period}, account {ref}",
    "{cat} remitted to {cp}, ref {ref}",
    "{cat} cleared for {month}, PO {ref}",
    "{cat} disbursed to {cp} for {period}",
    "{cat} for {period} paid, invoice {ref}",
    "{cat} to {cp} processed, batch {ref}",
    "{cat} settled in {month}, reference {ref}",
    "{cat} paid to {cp} against PO {ref}",
    "{cat} for {month} cleared, voucher {ref}",
    "{cat} remitted for {period}, doc {ref}",
    "{cat} to {cp} paid down, invoice {ref}",
    "{cat} booked and paid, {period}, ref {ref}",
    "{cat} outflow to {cp}, settlement {ref}",
    "{cat} charge for {period} paid, account {ref}",
]

# Reasoning scenario: entity id sets. Cycle members carry ONLY their ring's intra-group edges (so a
# recursive walk finds exactly 3 cycles); every other entity carries the acyclic camouflage DAG.
_CYCLES = [(2, 3, 4), (7, 8, 9), (13, 14, 15)]
_NONCYC = [1, 5, 6, 10, 11, 12, 16, 17, 18, 19, 20]


def _narrate(rt, pool: list, ref, cat: str = "") -> str:
    """Slot-fill one memo skeleton. Always draws the SAME 7 values in the SAME order from ``rt`` so
    the stream stays deterministic regardless of which skeleton is chosen. ``ref`` reuses a caller's
    reference number (keeps the main rng byte-identical) or None to draw a fresh one."""
    cp = f"{rt.choice(_CP_A)} {rt.choice(_CP_B)}"
    month, period, n = rt.choice(_MONTHS), rt.choice(_PERIODS), rt.choice(_YEARWORDS)
    ref2 = rt.randint(100000, 999999)
    sk = rt.choice(pool)
    return sk.format(cp=cp, ref=(ref2 if ref is None else ref), month=month, period=period, n=n, cat=cat)


# ── synthetic sensitive identifiers (demo-factor masking targets, drawn from a dedicated rng
#    stream so existing counterparty/entity values stay byte-identical) ──
def _iban(r, cty: str) -> str:  # e.g. GB29NWBK6016133192 — matches the boundary IBAN mask
    bank = "".join(r.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(4))
    body = "".join(str(r.randint(0, 9)) for _ in range(14))
    return f"{cty}{r.randint(10, 99)}{bank}{body}"


def _tax_id(r, cty: str) -> str:
    if cty == "US":
        return f"{r.randint(10, 99)}-{r.randint(1000000, 9999999)}"        # EIN NN-NNNNNNN
    return f"{r.randint(100, 999)}-{r.randint(10, 99)}-{r.randint(1000, 9999)}"  # national-ID shape -> GOV_ID mask


def _vat_no(r, cty: str) -> str:
    return f"{cty}{r.randint(100000000, 999999999)}"                         # cty + 9 digits


def _contact_email(r, company_name: str) -> str:
    fn, ln = full_name(r).split()
    return f"{fn}.{ln}@{company_name.split()[0]}.example".lower()            # person-derived finance contact


_TERMS = """# Aldgate Holdings plc — Terms of Sensitive Data Use

## Purpose

Aldgate Holdings plc operates the group general ledger and consolidation systems for its twenty
subsidiaries. As a dual-listed group, Aldgate is subject to Sarbanes-Oxley section 302 and 404
attestation, market-abuse controls over material non-public financial information, and counterparty
data-protection obligations. These Terms govern how the sensitive fields held in the group ledger
may be processed, and in particular what may be distilled into any brief transmitted to an external
planning model outside Aldgate infrastructure.

## Data classification

The following fields carry a sensitivity class. External-transmission rules in the next section are
keyed to these classes.

- **counterparties.tax_id** — Restricted. Counterparty national tax identifier.
- **counterparties.iban** — Restricted. Counterparty settlement bank account number.
- **counterparties.vat_no** — Confidential. Counterparty VAT registration number.
- **counterparties.contact_email** — Confidential. Counterparty finance-contact personal email.
- **counterparties.lei** — Public. ISO 17442 Legal Entity Identifier.
- **counterparties.name**, **counterparties.country** — Internal. Counterparty master reference.
- **entities.officer_name**, **entities.officer_email** — Confidential. Subsidiary attestation signatory identity.
- **entities.name**, **entities.country**, **entities.currency** — Internal. Subsidiary reference data.
- **gl_entries.memo** — Confidential. Journal narrative that may embed counterparty identifiers.
- **gl_entries.amount** — Restricted before filing. Material non-public financial data.
- **chart_of_accounts.code**, **chart_of_accounts.class** — Internal. Ledger structure.

## Handling rules

- Counterparty national tax identifiers (**counterparties.tax_id**) must never leave Aldgate
  infrastructure and must be fully masked before any brief is sent to an external planning model.
- Counterparty bank account numbers (**counterparties.iban**) must be masked to the last four
  characters before any external transmission.
- Counterparty VAT registration numbers (**counterparties.vat_no**) may not appear in materials
  transmitted outside the group finance perimeter.
- Counterparty finance-contact email addresses (**counterparties.contact_email**) must be redacted
  before external transmission and must never be paired externally with the counterparty legal name.
- Subsidiary attestation officer identities (**entities.officer_name**, **entities.officer_email**)
  may appear in external planning materials only in pseudonymized form.
- Journal narrative memos (**gl_entries.memo**) frequently embed counterparty names, invoice numbers
  and account details; any such identifier in a memo must be masked before external transmission.
- Pre-close ledger amounts (**gl_entries.amount**) aggregated by subsidiary (**gl_entries.entity_id**)
  constitute material non-public information and must not be transmitted outside Aldgate infrastructure
  before the corresponding results are publicly filed.
- Legal Entity Identifiers (**counterparties.lei**) are public reference data and may be transmitted,
  but must never be transmitted alongside the same counterparty's **counterparties.tax_id** or
  **counterparties.iban**.
- Records for subsidiaries domiciled in the European Union (**entities.country** of DE or FR) and their
  related counterparty data must be processed only within EU/EEA infrastructure.
- Counterparty identifiers (**counterparties.tax_id**, **counterparties.iban**, **counterparties.vat_no**)
  are retained no longer than seven years after the last related entry in **gl_entries**, then destroyed.

## Closing note

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation
boundary.
"""


def _write_terms() -> Path:
    d = OUT / "terms"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "ledger_terms.md"
    p.write_text(_TERMS, encoding="utf-8")
    return p


def gen_ledger() -> dict:
    r = rng(12)          # main stream: entities, COA, ledger, intercompany
    r_cp = rng(1201)     # counterparties + LEI
    r_fx = rng(1202)     # FX rates
    r_id = rng(1203)     # synthetic sensitive identifiers (tax id, VAT, IBAN, contact/officer emails)
    r_txt = rng(1210)    # narrative memos (benign + planted share the same skeleton pools)
    r_new = rng(1211)    # new planted misfilings + benign expense-credit camouflage
    r_cyc = rng(1212)    # circular + acyclic intercompany revenue edges

    con = _fresh_db(OUT / "ledger.db")
    con.executescript(
        """
        CREATE TABLE entities (id INTEGER PRIMARY KEY, name TEXT, country TEXT, currency TEXT,
            officer_name TEXT, officer_email TEXT);
        CREATE TABLE chart_of_accounts (id INTEGER PRIMARY KEY, code TEXT, name TEXT, class TEXT);
        CREATE TABLE counterparties (id INTEGER PRIMARY KEY, name TEXT, country TEXT, lei TEXT,
            tax_id TEXT, vat_no TEXT, iban TEXT, contact_email TEXT);
        CREATE TABLE fx_rates (id INTEGER PRIMARY KEY, date TEXT, currency TEXT, rate_to_usd REAL);
        CREATE TABLE gl_entries (id INTEGER PRIMARY KEY, entity_id INTEGER, account_code TEXT,
            batch_id TEXT, date TEXT, side TEXT, amount REAL, currency TEXT,
            counterparty_id INTEGER, intercompany_entity_id INTEGER, memo TEXT);
        """
    )

    # ── entities (20 subsidiaries) — each carries its SOX attestation signatory (person PII) ──
    ent_rows = []
    for i, (n, c, cur) in enumerate(_ENTITIES):
        officer = full_name(r_id)
        fn, ln = officer.split()
        ent_rows.append((i + 1, n, c, cur, officer, f"{fn}.{ln}@aldgate.example".lower()))
    con.executemany("INSERT INTO entities VALUES (?,?,?,?,?,?)", ent_rows)
    ent_cur = {i + 1: cur for i, (_, _, cur) in enumerate(_ENTITIES)}

    # ── chart of accounts (400) — 1xxx asset, 2xxx liability, 3xxx equity, 4xxx revenue, 5xxx expense ──
    coa, ranges = [], [("asset", 1000, 100), ("liability", 2000, 80), ("equity", 3000, 40),
                       ("revenue", 4000, 80), ("expense", 5000, 100)]
    special = {CASH: ("Cash and Cash Equivalents", "asset"),
               IC_RECV: ("Intercompany Receivable", "asset"),
               IC_PAY: ("Intercompany Payable", "liability")}
    cid = 0
    for cls, base, n in ranges:
        for k in range(n):
            code = str(base + k)
            name, klass = special.get(code, (f"{cls.title()} account {code}", cls))
            cid += 1
            coa.append((cid, code, name, klass))
    con.executemany("INSERT INTO chart_of_accounts VALUES (?,?,?,?)", coa)
    expense_codes = [str(5000 + k) for k in range(100)]
    revenue_codes = [str(4000 + k) for k in range(80)]
    liability_codes = [str(2000 + k) for k in range(80) if str(2000 + k) != IC_PAY]
    asset_other = [str(1000 + k) for k in range(100) if str(1000 + k) not in (CASH, IC_RECV)]

    # ── counterparties (2500). Plant (c): 80 with NULL/malformed LEI (wrong length) — all others
    # get a valid 20-char LEI, so a "LEI gap" query returns exactly the planted set. ──
    lei_gap_ids = sorted(r_cp.sample(range(1, 2501), 80))
    cps = []
    for i in range(1, 2501):
        name = f"{r_cp.choice(_CP_A)} {r_cp.choice(_CP_B)} {r_cp.choice(_CP_C)}"
        cty = country(r_cp)
        if i in lei_gap_ids:  # planted gap: NULL or wrong-length (not 20) LEI
            lei = None if r_cp.random() < 0.5 else "".join(
                r_cp.choice(_LEI_CHARS) for _ in range(r_cp.choice([18, 19, 21, 22])))
        else:
            lei = "".join(r_cp.choice(_LEI_CHARS) for _ in range(20))  # well-formed
        # sensitive identifiers from r_id (independent stream): tax id, VAT, IBAN, finance-contact email
        cps.append((i, name, cty, lei, _tax_id(r_id, cty), _vat_no(r_id, cty),
                    _iban(r_id, cty), _contact_email(r_id, name)))
    con.executemany("INSERT INTO counterparties VALUES (?,?,?,?,?,?,?,?)", cps)

    # ── fx_rates: daily 2024-01-01 .. 2026-12-31 for 5 currencies vs USD ──
    fx, fid, day = [], 0, date(2024, 1, 1)
    fx_base = {"EUR": 1.08, "GBP": 1.27, "JPY": 0.0067, "CAD": 0.74, "AUD": 0.66}
    while day <= date(2026, 12, 31):
        for cur, b0 in fx_base.items():
            fid += 1
            fx.append((fid, day.isoformat(), cur, round(b0 * (1 + r_fx.uniform(-0.05, 0.05)), 6)))
        day += timedelta(days=1)
    con.executemany("INSERT INTO fx_rates VALUES (?,?,?,?)", fx)

    # ── gl_entries: streamed insert (buffer flush @50k, single commit at end) ──
    buf: list[tuple] = []
    state = {"gid": 0, "bid": 0}

    def emit(ent, code, batch, d, side, amt, cur, cp, ic, memo):
        state["gid"] += 1
        buf.append((state["gid"], ent, code, batch, d, side, round(amt, 2), cur, cp, ic, memo))
        if len(buf) >= 50000:
            con.executemany("INSERT INTO gl_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)", buf)
            buf.clear()

    def new_batch():
        state["bid"] += 1
        return f"B{state['bid']:07d}"

    g_start, g_end = date(2022, 1, 1), date(2026, 12, 31)

    # Bulk operational ledger: ~320k balanced single-transaction batches (each dr==cr, so they
    # never trip the unbalanced-batch check). Four realistic journal shapes.
    for _ in range(320000):
        ent = r.randint(1, 20)
        cur, d, b = ent_cur[ent], day_between(r, g_start, g_end).isoformat(), new_batch()
        x = round(r.uniform(50, 400000), 2)
        cp = r.randint(1, 2500) if r.random() < 0.6 else None
        s = r.random()
        if s < 0.40:                                   # expense paid in cash
            cat = r.choice(_EXP_MEMOS)                  # (r draw preserved) category slot
            m = _narrate(r_txt, _OUTFLOW, None, cat)    # outflow narrative on the expense (dr) leg
            emit(ent, r.choice(expense_codes), b, d, "dr", x, cur, cp, None, m)
            emit(ent, CASH, b, d, "cr", x, cur, None, None, f"Cash disbursement ref {b}")
        elif s < 0.70:                                 # sales revenue (correctly on a revenue acct)
            inv = r.randint(100000, 999999)            # (r draw preserved) invoice ref → narrative slot
            m = _narrate(r_txt, _INFLOW, inv)          # inflow narrative on the revenue (cr) leg
            emit(ent, CASH, b, d, "dr", x, cur, cp, None, f"Customer receipt ref {inv}")
            emit(ent, r.choice(revenue_codes), b, d, "cr", x, cur, cp, None, m)
        elif s < 0.85:                                 # accrued payable
            m = _narrate(r_txt, _OUTFLOW, None, r_txt.choice(_ACCR_CATS))
            emit(ent, r.choice(expense_codes), b, d, "dr", x, cur, cp, None, m)
            emit(ent, r.choice(liability_codes), b, d, "cr", x, cur, None, None, "Accrual carried to balance sheet")
        else:                                          # capital asset purchase
            emit(ent, r.choice(asset_other), b, d, "dr", x, cur, cp, None, "Asset acquisition")
            emit(ent, CASH, b, d, "cr", x, cur, None, None, "Asset acquisition")

    # Plant (a) INTERCOMPANY MISMATCHES: 60 directed entity pairs carry IC loans (A lends to B:
    # A dr IC_RECV / cr Cash ; B dr Cash / cr IC_PAY). For 30 of them the B-side payable is
    # overstated by a material delta on one transaction, so A's receivable != B's payable.
    pairs = [(a, b) for a in range(1, 21) for b in range(a + 1, 21)]
    active = r.sample(pairs, 60)
    for idx, (a, b) in enumerate(active):
        is_mis = idx < 30
        m = r.randint(4, 10)
        bad_k = r.randint(0, m - 1) if is_mis else -1
        delta = round(r.uniform(5000, 50000), 2)
        for k in range(m):
            x = round(r.uniform(10000, 500000), 2)
            d = day_between(r, date(2024, 1, 1), date(2026, 6, 30)).isoformat()
            ba = new_batch()
            emit(a, IC_RECV, ba, d, "dr", x, "USD", None, b, f"Intercompany loan to entity {b}")
            emit(a, CASH, ba, d, "cr", x, "USD", None, b, f"Intercompany funding to entity {b}")
            y = x + (delta if k == bad_k else 0)       # mismatched leg: overstated payable
            bb = new_batch()
            emit(b, CASH, bb, d, "dr", y, "USD", None, a, f"Intercompany drawdown from entity {a}")
            emit(b, IC_PAY, bb, d, "cr", y, "USD", None, a, f"Intercompany payable to entity {a}")

    # Plant (b) MISCLASSIFICATIONS: 500 lines whose memo clearly says revenue but are booked to an
    # expense-class account (credit to a 5xxx). Detect: class='expense' AND memo LIKE '%Sales revenue%'.
    for _ in range(500):
        ent = r.randint(1, 20)
        cur, d, b = ent_cur[ent], day_between(r, g_start, g_end).isoformat(), new_batch()
        x, cp = round(r.uniform(1000, 200000), 2), r.randint(1, 2500)
        memo = f"Sales revenue - customer invoice #{r.randint(100000, 999999)}"
        emit(ent, CASH, b, d, "dr", x, cur, cp, None, memo)
        emit(ent, r.choice(expense_codes), b, d, "cr", x, cur, cp, None, memo)  # misbooked leg

    # Plant (d) UNBALANCED BATCHES: 25 batches with one extra unposted dr line so sum(dr) != sum(cr).
    for _ in range(25):
        ent = r.randint(1, 20)
        cur, d, b = ent_cur[ent], day_between(r, g_start, g_end).isoformat(), new_batch()
        for _ in range(r.randint(2, 4)):               # balanced pairs
            x = round(r.uniform(500, 80000), 2)
            emit(ent, r.choice(expense_codes), b, d, "dr", x, cur, r.randint(1, 2500), None, "Vendor payment")
            emit(ent, CASH, b, d, "cr", x, cur, None, None, "Vendor payment")
        emit(ent, r.choice(expense_codes), b, d, "dr", round(r.uniform(5000, 60000), 2),
             cur, None, None, "Unposted accrual - review")   # dangling debit

    # Ensure plant (c) counterparties have MATERIAL activity (so the LEI-gap report is about real
    # exposure, not dormant records): dedicated high-value vendor payments against each.
    for cp in lei_gap_ids:
        for _ in range(r.randint(3, 6)):
            ent = r.randint(1, 20)
            cur, d, b = ent_cur[ent], day_between(r, g_start, g_end).isoformat(), new_batch()
            x = round(r.uniform(40000, 200000), 2)
            emit(ent, r.choice(expense_codes), b, d, "dr", x, cur, cp, None, "Vendor payment")
            emit(ent, CASH, b, d, "cr", x, cur, None, None, "Vendor payment")

    # ── (A) MISFILED REVENUE (unstructured, meaning-only) ──────────────────────────────────────────
    # 540 credits to expense accounts whose memo describes a customer *revenue* receipt (retainer,
    # subscription, royalty, …) — revenue-earning prose sitting on a cost account. Hidden among 5,000
    # LEGITIMATE expense credits (vendor refunds, rebates, accrual releases) with the identical
    # dr-CASH / cr-expense structure. No keyword names the pattern: the inflow phrases also flood the
    # revenue accounts (benign), and the credit-to-expense structure is dominated by real refunds —
    # only reading the memo tells a misfiled sale from a genuine cost recovery.
    for _ in range(540):
        ent = r_new.randint(1, 20)
        cur, d, b = ent_cur[ent], day_between(r_new, date(2024, 1, 1), date(2026, 6, 30)).isoformat(), new_batch()
        x, cp = round(r_new.uniform(2000, 250000), 2), r_new.randint(1, 2500)
        emit(ent, CASH, b, d, "dr", x, cur, cp, None, f"Receipt ref {b}")
        emit(ent, r_new.choice(expense_codes), b, d, "cr", x, cur, cp, None,
             _narrate(r_txt, _INFLOW, None))            # revenue narrative misfiled to an expense credit
    for _ in range(5000):                               # benign camouflage: real cost recoveries
        ent = r_new.randint(1, 20)
        cur, d, b = ent_cur[ent], day_between(r_new, g_start, g_end).isoformat(), new_batch()
        x, cp = round(r_new.uniform(500, 120000), 2), r_new.randint(1, 2500)
        emit(ent, CASH, b, d, "dr", x, cur, cp, None, f"Credit receipt ref {b}")
        emit(ent, r_new.choice(expense_codes), b, d, "cr", x, cur, cp, None,
             _narrate(r_txt, _REFUND, None))

    # ── (B) CIRCULAR INTERCOMPANY REVENUE (reasoning, recursive-CTE cycle detection) ────────────────
    # 3 rings (A→B→C→A) of intra-group service billings: each edge books revenue in the seller and an
    # equal expense in the buyer, so consolidated revenue is inflated by 3×M per ring while every
    # entity's cash nets to ~zero — round-tripping that must eliminate on consolidation. Camouflaged
    # by 30 ACYCLIC intra-group edges arranged as a DAG in a shuffled topological order, so neither a
    # flat listing nor a "backward-edge" filter isolates the rings; only path-following does.
    def _ic_edge(src, dst, amt):
        d = day_between(r_cyc, date(2024, 1, 1), date(2026, 6, 30)).isoformat()
        b1 = new_batch()
        emit(src, CASH, b1, d, "dr", amt, "USD", None, dst, f"Intra-group services rendered to entity {dst}")
        emit(src, r_cyc.choice(revenue_codes), b1, d, "cr", amt, "USD", None, dst,
             f"Intra-group services rendered to entity {dst}")
        b2 = new_batch()
        emit(dst, r_cyc.choice(expense_codes), b2, d, "dr", amt, "USD", None, src,
             f"Intra-group services from entity {src}")
        emit(dst, CASH, b2, d, "cr", amt, "USD", None, src, f"Intra-group services from entity {src}")

    for a3, b3, c3 in _CYCLES:                           # equal M around each ring → nets to ~zero
        m_cyc = round(r_cyc.uniform(300000, 900000), 2)
        for src, dst in ((a3, b3), (b3, c3), (c3, a3)):
            _ic_edge(src, dst, m_cyc)
    topo = _NONCYC[:]                                    # acyclic camouflage: edges low-rank → high-rank
    r_cyc.shuffle(topo)
    rank = {e: i for i, e in enumerate(topo)}
    dag_pairs = [(u, v) for u in _NONCYC for v in _NONCYC if u != v and rank[u] < rank[v]]
    for src, dst in r_cyc.sample(dag_pairs, 30):
        for _ in range(r_cyc.randint(1, 3)):
            _ic_edge(src, dst, round(r_cyc.uniform(50000, 700000), 2))

    if buf:
        con.executemany("INSERT INTO gl_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)", buf)
    con.commit()

    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["entities", "chart_of_accounts", "counterparties", "fx_rates", "gl_entries"]}
    con.close()
    _write_terms()
    return {"db": "ledger.db", "counts": counts,
            "planted": {"intercompany_mismatches": 30, "misclassifications": 500,
                        "lei_gaps": 80, "unbalanced_batches": 25,
                        "misfiled_revenue_narratives": 540, "intercompany_cycles": 3},
            "terms": "terms/ledger_terms.md"}


def _fresh_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return sqlite3.connect(str(path))


if __name__ == "__main__":  # ponytail: self-check — regenerate + assert every planted count is findable
    import time
    t = time.time()
    rep = gen_ledger()
    print(rep, f"{time.time() - t:.1f}s")
    c = sqlite3.connect(str(OUT / "ledger.db"))
    ic = c.execute("""
        SELECT COUNT(*) FROM
          (SELECT entity_id ae, intercompany_entity_id be,
                  SUM(CASE WHEN side='dr' THEN amount ELSE -amount END) recv
           FROM gl_entries WHERE account_code='1010' GROUP BY entity_id, intercompany_entity_id) a
        JOIN (SELECT entity_id be, intercompany_entity_id ae,
                  SUM(CASE WHEN side='cr' THEN amount ELSE -amount END) pay
              FROM gl_entries WHERE account_code='2010' GROUP BY entity_id, intercompany_entity_id) b
          ON a.ae=b.ae AND a.be=b.be
        WHERE ABS(a.recv-b.pay) > 1000""").fetchone()[0]
    mis = c.execute("""SELECT COUNT(*) FROM gl_entries g JOIN chart_of_accounts a ON g.account_code=a.code
                       WHERE a.class='expense' AND g.memo LIKE '%Sales revenue%'""").fetchone()[0]
    lei = c.execute("""SELECT COUNT(*) FROM (SELECT cp.id FROM counterparties cp
                       JOIN gl_entries g ON g.counterparty_id=cp.id
                       WHERE cp.lei IS NULL OR LENGTH(cp.lei)!=20
                       GROUP BY cp.id HAVING SUM(g.amount) > 100000)""").fetchone()[0]
    unb = c.execute("""SELECT COUNT(*) FROM (SELECT batch_id FROM gl_entries GROUP BY batch_id
                       HAVING ABS(SUM(CASE WHEN side='dr' THEN amount ELSE 0 END)
                                - SUM(CASE WHEN side='cr' THEN amount ELSE 0 END)) > 0.01)""").fetchone()[0]
    # (A) misfiled-revenue oracle: revenue narrative on an expense credit (meaning, not keyword)
    _anchors = " OR ".join(f"lower(g.memo) LIKE '%{a}%'" for a in _INFLOW_ANCHORS)
    misf = c.execute(f"""SELECT COUNT(*) FROM gl_entries g JOIN chart_of_accounts a ON g.account_code=a.code
                         WHERE a.class='expense' AND g.side='cr' AND ({_anchors})""").fetchone()[0]
    # (B) circular-intercompany oracle: recursive-CTE cycle detection over intercompany_entity_id
    cyc = c.execute("""WITH RECURSIVE edges AS (
            SELECT DISTINCT g.entity_id AS src, g.intercompany_entity_id AS dst
            FROM gl_entries g JOIN chart_of_accounts a ON g.account_code=a.code
            WHERE a.class='revenue' AND g.intercompany_entity_id IS NOT NULL),
          walk(start,node,hops,path,closed) AS (
            SELECT src,dst,1,'|'||src||'|'||dst||'|',CASE WHEN dst=src THEN 1 ELSE 0 END FROM edges
            UNION ALL
            SELECT w.start,e.dst,w.hops+1,w.path||e.dst||'|',CASE WHEN e.dst=w.start THEN 1 ELSE 0 END
            FROM walk w JOIN edges e ON e.src=w.node
            WHERE w.closed=0 AND w.hops<12
              AND (e.dst=w.start OR (e.dst>w.start AND instr(w.path,'|'||e.dst||'|')=0)))
          SELECT COUNT(*) FROM walk WHERE closed=1""").fetchone()[0]
    # attack-resistance: neither a lone inflow keyword nor the credit-to-expense structure isolates
    leak_kw = c.execute("SELECT COUNT(*) FROM gl_entries WHERE lower(memo) LIKE '%retainer%'").fetchone()[0]
    leak_struct = c.execute("""SELECT COUNT(*) FROM gl_entries g JOIN chart_of_accounts a
                               ON g.account_code=a.code WHERE a.class='expense' AND g.side='cr'""").fetchone()[0]
    cp_pii = c.execute("SELECT tax_id, vat_no, iban, contact_email FROM counterparties WHERE id=1").fetchone()
    ent_pii = c.execute("SELECT officer_name, officer_email FROM entities WHERE id=1").fetchone()
    c.close()
    assert ic == 30, ic
    assert mis == 500, mis
    assert lei == 80, lei
    assert unb == 25, unb
    assert misf == 540, misf              # every planted misfiling found by the semantic oracle
    assert cyc == 3, cyc                  # exactly 3 intercompany cycles, one row per ring (min entity)
    assert leak_kw > misf * 3, (leak_kw, misf)        # 'retainer' floods benign revenue accounts
    assert leak_struct > misf * 3, (leak_struct, misf)  # credit-to-expense floods benign refunds
    assert all(cp_pii), cp_pii            # sensitive counterparty identifiers populated
    assert all(ent_pii), ent_pii          # subsidiary attestation signatory populated
    assert (OUT / "terms" / "ledger_terms.md").exists()
    print("planted OK:", ic, mis, lei, unb, "| misfiled", misf, "cycles", cyc,
          "| leaks(kw/struct)", leak_kw, leak_struct, "| pii+terms OK")
