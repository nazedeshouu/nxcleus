"""Judge-sandbox datasets: three synthetic companies (09 §2), each a read-only SQLite file plus,
for the law firm, a `contracts/*.txt` corpus. Volumes are tuned so fan-out is *visible* (a 200-unit
contract sweep animates well) yet regenerate in seconds. Every dataset plants the patterns listed in
09 §2 so the suggested prompts find real things — the outputs are always computed live, never canned
(track rule anchor).

Run via `scripts/seed.py`. Output: `infra/seeds/out/{bank,clinic,lawfirm}.db` + `out/contracts/`.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from ._gen import SANCTIONS_ADJACENT, country, day_between, dob, full_name, rng

OUT = Path(__file__).resolve().parent / "out"


def _fresh_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return sqlite3.connect(str(path))


# ─────────────────────────────────────────────────────────── Meridian Bank
def gen_bank() -> dict:
    r = rng(1)
    con = _fresh_db(OUT / "bank.db")
    con.executescript(
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, dob TEXT, country TEXT,
            onboarded TEXT, pep INTEGER);
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, customer_id INTEGER, kind TEXT,
            opened TEXT, last_active TEXT, status TEXT, balance_usd REAL);
        CREATE TABLE transactions (id INTEGER PRIMARY KEY, account_id INTEGER, ts TEXT,
            amount_usd REAL, direction TEXT, kind TEXT, counterparty TEXT);
        """
    )
    start, end = date(2019, 1, 1), date(2026, 7, 1)
    # 800 customers; a handful carry sanctions-adjacent names (planted screening hits)
    customers = []
    for i in range(1, 801):
        name = SANCTIONS_ADJACENT[i % len(SANCTIONS_ADJACENT)] if i <= len(SANCTIONS_ADJACENT) else full_name(r)
        customers.append((i, name, dob(r), country(r), day_between(r, start, end).isoformat(),
                          1 if r.random() < 0.03 else 0))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", customers)

    # 1,200 accounts; ~8% dormant (last_active > 2y ago) — a subset get a planted reactivation below
    accounts, dormant_ids = [], []
    for i in range(1, 1201):
        cust = r.randint(1, 800)
        dormant = r.random() < 0.08
        if dormant:  # opened early, went quiet before mid-2023
            opened = day_between(r, start, date(2021, 6, 1))
            last_active = day_between(r, opened, date(2023, 6, 1))
            status = "dormant"
            dormant_ids.append(i)
        else:
            opened = day_between(r, start, date(2024, 1, 1))
            last_active = day_between(r, opened, end)
            status = "active"
        accounts.append((i, cust, r.choice(["checking", "savings", "business"]), opened.isoformat(),
                         last_active.isoformat(), status, round(r.uniform(0, 250_000), 2)))
    con.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?)", accounts)

    # 8,000 transactions. Plant: (a) sudden reactivation on ~15 dormant accounts (a large recent
    # deposit long after last_active); (b) structuring runs — clusters of deposits just under $10k.
    txns, tid = [], 1
    react_ids = dormant_ids[:15]
    structuring_accts = r.sample(range(1, 1201), 12)
    for _ in range(7600):
        acct = r.randint(1, 1200)
        ts = day_between(r, start, end)
        amt = round(r.uniform(20, 8_000), 2)
        txns.append((tid, acct, ts.isoformat(), amt, r.choice(["credit", "debit"]),
                     r.choice(["deposit", "withdrawal", "transfer", "card"]),
                     full_name(r) if r.random() < 0.3 else ""))
        tid += 1
    for acct in react_ids:  # sudden reactivation: big deposit in 2026 on a dormant account
        txns.append((tid, acct, date(2026, 6, r.randint(1, 28)).isoformat(),
                     round(r.uniform(40_000, 180_000), 2), "credit", "deposit", full_name(r)))
        tid += 1
    for acct in structuring_accts:  # structuring: 8-14 deposits of $9,000-$9,900 within days
        base = day_between(r, date(2026, 1, 1), date(2026, 6, 1))
        for k in range(r.randint(8, 14)):
            txns.append((tid, acct, (base).isoformat() if k == 0 else
                         day_between(r, base, date(2026, 6, 20)).isoformat(),
                         round(r.uniform(9_000, 9_900), 2), "credit", "deposit", ""))
            tid += 1
    con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?)", txns)
    con.commit()
    counts = _counts(con, ["customers", "accounts", "transactions"])
    con.close()
    return {"db": "bank.db", "counts": counts,
            "planted": {"reactivation_accounts": len(react_ids), "structuring_accounts": len(structuring_accts),
                        "sanctions_adjacent_names": len(SANCTIONS_ADJACENT)}}


# ─────────────────────────────────────────────────────────── Aurora Clinic
def gen_clinic() -> dict:
    r = rng(2)
    con = _fresh_db(OUT / "clinic.db")
    con.executescript(
        """
        CREATE TABLE patients (id INTEGER PRIMARY KEY, name TEXT, dob TEXT, sex TEXT,
            last_screening TEXT);
        CREATE TABLE encounters (id INTEGER PRIMARY KEY, patient_id INTEGER, date TEXT,
            provider TEXT, department TEXT, billing_code TEXT);
        CREATE TABLE lab_results (id INTEGER PRIMARY KEY, encounter_id INTEGER, test TEXT,
            value REAL, unit TEXT, flag TEXT);
        CREATE TABLE prescriptions (id INTEGER PRIMARY KEY, encounter_id INTEGER, drug TEXT,
            dose_mg REAL, days INTEGER);
        """
    )
    depts = ["Cardiology", "Primary Care", "Endocrinology", "Oncology", "Nephrology"]
    provs = [f"Dr. {full_name(r).split()[1]}" for _ in range(20)]
    start, end = date(2024, 1, 1), date(2026, 7, 1)
    # 500 patients; ~12% overdue-screening cohort (last_screening > 2y or null)
    patients = []
    for i in range(1, 501):
        overdue = r.random() < 0.12
        last_scr = "" if overdue and r.random() < 0.4 else day_between(
            r, date(2021, 1, 1) if overdue else date(2025, 1, 1), end).isoformat()
        patients.append((i, full_name(r), dob(r, 1, 95), r.choice(["F", "M"]), last_scr))
    con.executemany("INSERT INTO patients VALUES (?,?,?,?,?)", patients)

    # 2,500 encounters; plant duplicate-billing shapes (same patient+date+code twice) on ~40
    encounters, eid = [], 1
    for _ in range(2460):
        pid = r.randint(1, 500)
        encounters.append((eid, pid, day_between(r, start, end).isoformat(), r.choice(provs),
                           r.choice(depts), f"CPT{r.randint(10000, 99999)}"))
        eid += 1
    dup_pairs = 0
    for _ in range(40):  # duplicate billing: identical (patient, date, code) on two encounters
        pid, d, code = r.randint(1, 500), day_between(r, start, end).isoformat(), f"CPT{r.randint(10000, 99999)}"
        for _ in range(2):
            encounters.append((eid, pid, d, r.choice(provs), r.choice(depts), code))
            eid += 1
        dup_pairs += 1
    con.executemany("INSERT INTO encounters VALUES (?,?,?,?,?,?)", encounters)

    # 4,000 lab results; plant impossible vitals (data-quality finds) on ~30
    tests = [("Heart Rate", "bpm", 50, 100), ("Temperature", "C", 36.0, 38.0),
             ("Systolic BP", "mmHg", 90, 140), ("Glucose", "mg/dL", 70, 140), ("SpO2", "%", 94, 100)]
    labs, lid = [], 1
    n_enc = len(encounters)
    for _ in range(3970):
        t = r.choice(tests)
        val = round(r.uniform(t[2], t[3]), 1)
        flag = "normal" if t[2] <= val <= t[3] else "abnormal"
        labs.append((lid, r.randint(1, n_enc), t[0], val, t[1], flag))
        lid += 1
    impossible = 0
    for _ in range(30):  # impossible: HR 300+, Temp 45+, SpO2 130 — physiologically impossible
        t = r.choice(tests)
        val = {"Heart Rate": 340.0, "Temperature": 47.0, "Systolic BP": 400.0,
               "Glucose": 2000.0, "SpO2": 130.0}[t[0]]
        labs.append((lid, r.randint(1, n_enc), t[0], val, t[1], "abnormal"))
        lid += 1
        impossible += 1
    con.executemany("INSERT INTO lab_results VALUES (?,?,?,?,?,?)", labs)

    drugs = ["Metformin", "Atorvastatin", "Lisinopril", "Amoxicillin", "Warfarin", "Insulin"]
    rx = [(i, r.randint(1, n_enc), r.choice(drugs), r.choice([5, 10, 20, 40, 500]), r.choice([7, 14, 30, 90]))
          for i in range(1, 1501)]
    con.executemany("INSERT INTO prescriptions VALUES (?,?,?,?,?)", rx)
    con.commit()
    counts = _counts(con, ["patients", "encounters", "lab_results", "prescriptions"])
    con.close()
    return {"db": "clinic.db", "counts": counts,
            "planted": {"duplicate_billing_pairs": dup_pairs, "impossible_vitals": impossible}}


# ─────────────────────────────────────────────────────────── Hale & Ostrom (law firm)
_CONTRACT_TMPL = """MASTER SERVICES AGREEMENT

This Agreement ("Agreement") is entered into as of {eff} by and between {a} ("Client") and
{b} ("Provider").

1. TERM. The initial term of this Agreement is {term} months, commencing on the Effective Date.
{renewal}

2. FEES. Provider shall invoice Client monthly. {feecap}

3. CONFIDENTIALITY. Each party shall protect the other's Confidential Information and shall not
disclose it to any third party without prior written consent.

4. TERMINATION. Either party may terminate for material breach upon 30 days' written notice if the
breach remains uncured.

5. GOVERNING LAW. This Agreement is governed by the laws of the State of Delaware.

{signature}
"""


def gen_lawfirm() -> dict:
    r = rng(3)
    con = _fresh_db(OUT / "lawfirm.db")
    con.executescript(
        """
        CREATE TABLE parties (id INTEGER PRIMARY KEY, name TEXT, kind TEXT, contact TEXT);
        CREATE TABLE contracts (id INTEGER PRIMARY KEY, title TEXT, party_a INTEGER, party_b INTEGER,
            effective_date TEXT, term_months INTEGER, auto_renew INTEGER, notice_days INTEGER,
            fee_cap_usd REAL, text_ref TEXT);
        CREATE TABLE billing_entries (id INTEGER PRIMARY KEY, contract_id INTEGER, date TEXT,
            hours REAL, rate_usd REAL, amount_usd REAL);
        """
    )
    parties = [(i, full_name(r) if r.random() < 0.5 else f"{r.choice(['Nexa','Orbit','Vertex','Lumen','Kestrel'])} "
                f"{r.choice(['Holdings','Systems','Labs','Partners','Group'])} LLC",
                r.choice(["client", "counterparty"]), f"legal@example{i}.com") for i in range(1, 351)]
    con.executemany("INSERT INTO parties VALUES (?,?,?,?)", parties)

    contracts_dir = OUT / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    for old in contracts_dir.glob("*.txt"):
        old.unlink()

    rows, planted = [], {"auto_renew_short_notice": 0, "missing_signature": 0}
    start = date(2022, 1, 1)
    for i in range(1, 201):
        a, b = r.randint(1, 350), r.randint(1, 350)
        eff = day_between(r, start, date(2025, 6, 1))
        term = r.choice([12, 24, 36])
        auto_renew = 1 if r.random() < 0.5 else 0
        # plant: ~25% of auto-renew contracts carry a <60-day notice window (the thing to flag)
        notice = r.choice([15, 30, 45]) if (auto_renew and r.random() < 0.5) else r.choice([60, 90])
        fee_cap = round(r.uniform(50_000, 400_000), 2)
        renewal = (f"Upon expiry, this Agreement automatically renews for successive {term}-month "
                   f"terms unless either party gives written notice of non-renewal at least "
                   f"{notice} days before the end of the then-current term."
                   if auto_renew else "This Agreement does not renew automatically and expires at "
                   "the end of the initial term.")
        feecap = f"Total fees under this Agreement shall not exceed USD {fee_cap:,.0f} (the 'Fee Cap')."
        missing_sig = r.random() < 0.10  # plant: 10% missing signature block
        signature = ("" if missing_sig else
                     "IN WITNESS WHEREOF, the parties have executed this Agreement.\n\n"
                     "_________________________        _________________________\n"
                     "Client                            Provider")
        title = f"MSA {parties[a-1][1]} / {parties[b-1][1]}"
        text = _CONTRACT_TMPL.format(eff=eff.isoformat(), a=parties[a-1][1], b=parties[b-1][1],
                                     term=term, renewal=renewal, feecap=feecap, signature=signature)
        ref = f"contracts/contract_{i:03d}.txt"
        (contracts_dir / f"contract_{i:03d}.txt").write_text(text)
        rows.append((i, title, a, b, eff.isoformat(), term, auto_renew, notice, fee_cap, ref))
        if auto_renew and notice < 60:
            planted["auto_renew_short_notice"] += 1
        if missing_sig:
            planted["missing_signature"] += 1
    con.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    # 2,000 billing entries; plant fee-cap breaches on ~15 contracts (sum of amount > fee_cap)
    entries, bid = [], 1
    for _ in range(1900):
        cid = r.randint(1, 200)
        hours = round(r.uniform(0.5, 8), 1)
        rate = r.choice([250, 400, 550, 700])
        entries.append((bid, cid, day_between(r, start, date(2026, 7, 1)).isoformat(), hours, rate,
                        round(hours * rate, 2)))
        bid += 1
    breach_contracts = r.sample(range(1, 201), 15)
    for cid in breach_contracts:  # pile enough hours to exceed the fee cap
        cap = rows[cid-1][8]
        piled = 0.0
        while piled < cap * 1.2:
            amt = round(700 * 8, 2)
            entries.append((bid, cid, day_between(r, date(2026, 1, 1), date(2026, 7, 1)).isoformat(),
                            8.0, 700, amt))
            piled += amt
            bid += 1
    con.executemany("INSERT INTO billing_entries VALUES (?,?,?,?,?,?)", entries)
    con.commit()
    counts = _counts(con, ["parties", "contracts", "billing_entries"])
    con.close()
    planted["fee_cap_breaches"] = len(breach_contracts)
    return {"db": "lawfirm.db", "counts": counts, "planted": planted, "contracts_txt": 200}


def _counts(con: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def generate_all() -> dict:
    return {"bank": gen_bank(), "clinic": gen_clinic(), "lawfirm": gen_lawfirm()}
