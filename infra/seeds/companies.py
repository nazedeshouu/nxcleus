"""Judge-sandbox datasets: three synthetic companies (09 §2), each a read-only SQLite file plus,
for the law firm, a `contracts/*.txt` corpus. Volumes are tuned so fan-out is *visible* (a 200-unit
contract sweep animates well) yet regenerate in seconds. Every dataset plants the patterns listed in
09 §2 so the suggested prompts find real things — the outputs are always computed live, never canned
(track rule anchor).

Run via `scripts/seed.py`. Output: `infra/seeds/out/{bank,clinic,lawfirm}.db` + `out/contracts/`.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from ._gen import SANCTIONS_ADJACENT, country, day_between, dob, full_name, rng

OUT = Path(__file__).resolve().parent / "out"


# ── Synthetic sensitive-field generators (masking-demo fodder). All draw from a passed-in local rng
# so a regenerate reproduces byte-for-byte. Formats are realistic-shaped but fully fake. Each
# generator uses a DEDICATED rng(salt) for these so the existing planted patterns and the contracts/
# corpus (which consume the primary stream) stay byte-identical to before this wave.
_STREETS = ["Alder", "Birch", "Cedar", "Marquam", "Hawthorne", "Willamette", "Powell", "Belmont",
            "Killingsworth", "Burnside", "Fremont", "Glisan"]
_CITIES = ["Portland", "Beaverton", "Gresham", "Hillsboro", "Tigard", "Milwaukie"]
# ICD-10-shaped diagnosis codes (chronic-care mix an Aurora Clinic would carry). Fake but well-formed.
_ICD10 = ["E11.9", "I10", "J45.909", "N18.3", "E78.5", "I25.10", "Z79.4", "F32.9", "M54.50",
          "E11.65", "N18.4", "I48.91", "J44.9", "K21.9"]
_NARRATIVES = [
    "Reviewed privileged client correspondence and drafted memo re: litigation strategy.",
    "Attorney-client conference regarding settlement posture and exposure.",
    "Prepared work-product analysis of counterparty's breach allegations.",
    "Revised confidential deal terms and privileged risk memorandum.",
    "Telephone conference with client re: privileged discovery strategy.",
    "Drafted privileged opinion letter on regulatory exposure.",
]

# ─────────────────────────────────────────────────────────────────────────── narrative corpora
# Wave-3 unstructured/reasoning layers (09 §2). Every template is slot-filled from a dedicated
# rng(1500+) stream so the existing planted-pattern streams stay byte-identical. The planted SIGNAL is
# always MEANING (a contradiction / semantic mismatch), never a keyword: benign and planted rows draw
# from the SAME skeleton pools, so no single LIKE/grep isolates the plant.

# ── Bank transaction memos (transactions.memo). >=15 skeletons across purpose categories. Benign rows
# draw a purpose that fits the transaction kind; planted structuring/layering rows draw MUTUALLY
# CONTRADICTORY purposes for the SAME counterparty (a script reading the numbers can't see it — only
# reading the memos reveals the same party financed as payroll, a car sale, and a wedding gift in a week).
_MEMO_CO = ["Beacon", "Cascade", "Sterling", "Harbor", "Ridgeline", "Meadow", "Copper", "Anchor",
            "Vantage", "Brightwater", "Foxglove", "Ironwood", "Larkspur", "Quill"]
_MEMO_CO2 = ["Trading", "Holdings", "Logistics", "Consulting", "Imports", "Builders", "Media",
             "Produce", "Freight", "Interiors"]
_MEMO_MON = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]
_MEMO: dict[str, list[str]] = {
    "payroll": ["Payroll run {mon} — {co} staff wages", "Bi-weekly salary disbursement, {co}",
                "{mon} wages for {co} employees", "Net pay {mon}, {co} payroll cycle"],
    "rent": ["Rent {mon} — unit {u}", "Monthly lease payment, suite {u}",
             "{mon} rent remittance for {co} premises"],
    "invoice": ["Settlement of invoice #{inv} — {co}", "Payment against {co} invoice #{inv}",
                "Invoice #{inv} paid in full, {co}"],
    "support": ["Monthly family support to {person}", "{mon} allowance for {person}",
                "Household support transfer, {person}"],
    "loan": ["Loan repayment {mon} — facility #{inv}", "Installment on note #{inv}",
             "{mon} principal-and-interest payment, {co}"],
    "goods": ["Purchase of used vehicle from {co}", "Proceeds from sale of equipment, {co}",
              "Payment for materials — {co}", "Boat sale settlement, {co}"],
    "services": ["Consulting retainer — {co}", "Contractor payment {mon}, {co}",
                 "Professional services fee, {co}"],
    "gift": ["Wedding gift from {person}", "Holiday gift from family", "{mon} birthday gift, {person}"],
}  # 26 skeletons
_MEMO_KIND_CATS = {
    "deposit": ["payroll", "invoice", "support", "loan", "services", "goods", "gift"],
    "withdrawal": ["rent", "goods", "services", "loan", "invoice", "support"],
    "transfer": ["invoice", "loan", "services", "goods", "support"],
    "card": ["goods", "services", "gift"],
}
# purposes rotated across a structuring account's deposits — mutually unrelated by construction
_MEMO_CONTRA = ["payroll", "goods", "gift", "support", "loan", "services", "invoice"]


def _fill_memo(m, tmpl: str, co: str) -> str:
    return tmpl.format(mon=m.choice(_MEMO_MON), co=co, inv=m.randint(1000, 9999),
                       person=full_name(m), u=m.randint(1, 40))


def _memo_co(m) -> str:
    return f"{m.choice(_MEMO_CO)} {m.choice(_MEMO_CO2)} LLC"


def _benign_memo(m, kind: str) -> str:
    cat = m.choice(_MEMO_KIND_CATS.get(kind, ["services"]))
    return _fill_memo(m, m.choice(_MEMO[cat]), _memo_co(m))


def _contra_memos(m, n: int) -> tuple[str, list[str]]:
    """A shared counterparty + n memos each describing an UNRELATED purpose (the semantic tell)."""
    co = _memo_co(m)
    memos = [_fill_memo(m, m.choice(_MEMO[_MEMO_CONTRA[k % len(_MEMO_CONTRA)]]), co) for k in range(n)]
    return co, memos


# ── Clinic CPT catalog + visit notes. Upcoding = a HIGH-complexity billed code whose note describes a
# brief routine visit. Brief-note pool is shared by legitimate low/moderate visits AND upcoded ones, so
# no keyword separates them — only reading note-vs-catalog-complexity does.
_CPT_CATALOG = [
    ("99211", "Office visit, minimal, established patient", "low"),
    ("99212", "Office visit, low complexity, established patient", "low"),
    ("99202", "New patient, straightforward", "low"),
    ("93000", "Electrocardiogram, routine", "low"),
    ("99213", "Office visit, low-to-moderate complexity", "moderate"),
    ("99214", "Office visit, moderate complexity", "moderate"),
    ("99203", "New patient, low complexity", "moderate"),
    ("99204", "New patient, moderate complexity", "moderate"),
    ("99284", "Emergency department visit, moderate complexity", "moderate"),
    ("99396", "Preventive visit, established patient", "moderate"),
    ("99215", "Office visit, high complexity, extended", "high"),
    ("99205", "New patient, high complexity, comprehensive", "high"),
    ("99285", "Emergency department visit, high complexity", "high"),
    ("99417", "Prolonged service, high complexity add-on", "high"),
]
_CPT_LOW = [c for c, _, lv in _CPT_CATALOG if lv == "low"]
_CPT_MOD = [c for c, _, lv in _CPT_CATALOG if lv == "moderate"]
_CPT_HIGH = [c for c, _, lv in _CPT_CATALOG if lv == "high"]
_COND = ["hypertension", "type 2 diabetes", "asthma", "hyperlipidemia", "atrial fibrillation",
         "chronic kidney disease", "COPD", "hypothyroidism", "GERD", "osteoarthritis"]
_VAC = ["influenza vaccine", "tetanus booster", "pneumococcal vaccine", "shingles vaccine"]
_NOTE_BRIEF = [   # describe a light/uncomplicated visit by MEANING; keyword-thin on purpose
    "Follow-up visit; patient stable, no new complaints.",
    "Medication refill visit; vitals within normal limits.",
    "Recheck of {cond}; doing well, continue current plan.",
    "Nurse visit for {vac}; no issues, patient in good spirits.",
    "Established-patient visit; {cond} controlled, no changes.",
    "Uncomplicated visit for {cond} review; reassured and discharged.",
    "Follow-up for stable {cond}; labs reviewed, plan unchanged.",
    "Blood-pressure check; asymptomatic, medications continued.",
    "Visit to renew prescription for {cond}; nothing further.",
    "Wellness check; no acute concerns reported today.",
    "Dressing change; wound healing well.",
    "Suture removal; site clean, no signs of infection.",
    "Counseling on {cond}; patient understands the plan.",
    "Reviewed home readings for {cond}; within target.",
    "Established patient, minor concern, resolved same day.",
    "Recheck; {cond} stable, next visit in three months.",
]  # 16 skeletons
_NOTE_COMPLEX = [
    "Extended evaluation of multiple active problems including {cond} and {cond2}; detailed exam.",
    "Comprehensive new-patient workup for {cond}; multi-system review and extensive counseling.",
    "Prolonged visit managing decompensated {cond} with medication overhaul and coordination.",
    "High-complexity assessment of worsening {cond}; further workup and specialist referral ordered.",
    "Detailed evaluation of acute {cond} with several comorbidities; extended decision-making.",
    "Complex care conference regarding {cond} and {cond2}; multiple options weighed.",
    "Extensive review of new symptoms; broad differential for {cond} explored in depth.",
    "Prolonged encounter for poorly-controlled {cond}; therapy titrated with safety-netting.",
    "Comprehensive assessment following abnormal results for {cond}; escalation planned.",
    "High-acuity evaluation of {cond} with unstable vitals; close monitoring arranged.",
    "Detailed multi-problem visit addressing {cond}, {cond2}, and polypharmacy.",
    "Extended shared decision-making for {cond}; risks and alternatives reviewed at length.",
    "Complex follow-up of {cond} with new complications; care plan substantially revised.",
    "Thorough evaluation of {cond} requiring extensive counseling and coordination of care.",
    "Prolonged assessment of {cond}; multiple diagnostics reviewed and interpreted.",
]  # 15 skeletons


def _fill_note(k, tmpl: str) -> str:
    return tmpl.format(cond=k.choice(_COND), cond2=k.choice(_COND), vac=k.choice(_VAC))


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ── Law-firm contract clauses (injected into the corpus, mirrored in NO db column). Every contract
# carries a liability clause AND an indemnity clause. Benign contracts pair them consistently
# (both capped OR both uncapped); planted contracts pair a CAPPED liability with an UNCAPPED indemnity
# that overrides it — an internal contradiction only reading both clauses reveals. >=15 skeletons each.
_LIAB_CAPPED = [
    "Each party's aggregate liability under this Agreement shall not exceed the total fees paid in the twelve months preceding the claim.",
    "Neither party's total liability shall exceed the Fee Cap set forth in Section 2.",
    "The maximum aggregate liability of either party is limited to the fees actually paid under this Agreement.",
    "In no event shall either party's cumulative liability exceed USD {lcap}.",
    "Each party's liability for any and all claims is capped at the amounts paid or payable in the prior twelve (12) months.",
    "Liability of the parties is limited to direct damages not exceeding the fees paid hereunder.",
    "Total liability under this Agreement shall be limited to USD {lcap} in the aggregate.",
    "Under no circumstances shall either party be liable beyond the fees received under this Agreement.",
]
_LIAB_UNCAPPED = [
    "Each party shall remain fully liable for all damages arising under this Agreement, without any monetary cap.",
    "The parties agree that no limitation of liability shall apply to obligations under this Agreement.",
    "Liability under this Agreement is unlimited and shall not be subject to any cap.",
    "Each party accepts full and uncapped liability for losses caused by its breach.",
    "No cap or limitation shall restrict either party's liability hereunder.",
    "The parties expressly disclaim any limitation on liability for damages under this Agreement.",
    "Liability shall extend to the full measure of damages, without ceiling or limitation.",
]
_INDEM_BOUNDED = [
    "Each party shall indemnify the other for third-party claims, subject to the limitation of liability in Section 4.",
    "Each party's indemnification obligations are capped at, and subject to, the liability limit above.",
    "Indemnification hereunder shall not exceed the aggregate liability cap set forth in Section 4.",
    "Each party shall indemnify the other solely up to the amounts permitted under the limitation of liability.",
    "The indemnity provided herein is bounded by, and shall not exceed, the liability cap in this Agreement.",
    "Each party indemnifies the other for third-party claims, but only to the extent of the capped liability above.",
    "Indemnity obligations are expressly limited by the limitation-of-liability provision of Section 4.",
]
_INDEM_UNBOUNDED = [
    "Each party shall indemnify and hold the other harmless from any and all losses without limitation and notwithstanding any other provision of this Agreement.",
    "Each party's indemnity obligation is unlimited and shall survive termination, regardless of any cap stated elsewhere.",
    "Each party shall fully indemnify the other for the entirety of any loss, without regard to any limitation of liability.",
    "Indemnification under this Section applies in full and is not subject to any cap or ceiling.",
    "Each party shall indemnify the other for all losses in their entirety, notwithstanding anything to the contrary herein.",
    "The indemnifying party shall be responsible without limit for all claims, damages, and expenses.",
    "Each party's duty to indemnify is uncapped and overrides any conflicting limitation in this Agreement.",
    "Each party shall indemnify the other without cap and irrespective of any other provision.",
]

# ── Law-firm amendments. Amendment bodies are shared by benign and planted; the plant is that two
# amendments to one contract give conflicting terms on the SAME clause and the LATER is SILENT on
# precedence — unresolvable without reading base + both amendments. Benign single amendments are also
# often silent (nothing to resolve), so silence alone does not isolate the plant.
_AMEND_TMPL = """AMENDMENT NO. {no} TO MASTER SERVICES AGREEMENT

This Amendment is entered into as of {eff} and amends the Master Services Agreement identified as
matter {matter} between the parties (the "Agreement").

{body}

{precedence}"""
_AMEND_BODY = [
    "Section 2 (Fees) is amended so that the Fee Cap shall be USD {v}.",
    "The Fee Cap under Section 2 is increased to USD {v}.",
    "The Fee Cap under Section 2 is reduced to USD {v}.",
    "The notice period for non-renewal in Section 1 is amended to {d} days.",
    "The notice period in Section 1 is extended to {d} days.",
    "The notice period in Section 1 is shortened to {d} days.",
    "The initial term set out in Section 1 is amended to {t} months.",
    "Section 4 (Limitation of Liability) is amended so that aggregate liability shall not exceed USD {v}.",
    "The liability cap in Section 4 is removed; liability shall be uncapped.",
    "Section 1 is amended so that the Agreement shall not automatically renew.",
    "Section 1 is amended so that the Agreement shall automatically renew for successive {t}-month terms.",
    "Section 6 (Termination) is amended to require {d} days' written notice for termination.",
    "Section 2 is amended to change the monthly invoicing cadence to quarterly invoicing.",
    "The governing law in Section 7 is amended to the State of New York.",
    "The parties' notice addresses are updated as set forth in Schedule A.",
    "A data-processing addendum is incorporated by reference as Schedule C.",
]  # 16 skeletons
_AMEND_PREC = [
    "All other terms of the Agreement remain in full force and effect. In the event of any conflict, this Amendment controls.",
    "Except as expressly amended herein, the Agreement is unchanged; this Amendment supersedes any conflicting prior term.",
    "This Amendment prevails over any inconsistent provision of the Agreement or prior amendments.",
]
_AMEND_SILENT = "The remaining provisions of the Agreement continue to apply."
# conflicting (bodyA, bodyB) pairs on the SAME clause — drawn from the shared _AMEND_BODY wordings
_AMEND_CONFLICT = [
    ("The Fee Cap under Section 2 is increased to USD {vA}.",
     "The Fee Cap under Section 2 is reduced to USD {vB}."),
    ("The notice period in Section 1 is extended to 90 days.",
     "The notice period in Section 1 is shortened to 15 days."),
    ("The initial term set out in Section 1 is amended to 12 months.",
     "The initial term set out in Section 1 is amended to 36 months."),
    ("Section 4 (Limitation of Liability) is amended so that aggregate liability shall not exceed USD {vA}.",
     "The liability cap in Section 4 is removed; liability shall be uncapped."),
    ("Section 1 is amended so that the Agreement shall not automatically renew.",
     "Section 1 is amended so that the Agreement shall automatically renew for successive 24-month terms."),
]


def _amend_body(am) -> str:
    return am.choice(_AMEND_BODY).format(v=f"{am.randint(1, 9) * 50_000:,}",
                                         d=am.choice([15, 30, 45, 60, 90]), t=am.choice([12, 24, 36]))


def _ssn(r) -> str:  # US SSN-shaped, area 100-899 excl. 666
    area = r.randint(100, 899)
    if area == 666:
        area = 667
    return f"{area:03d}-{r.randint(10, 99):02d}-{r.randint(1000, 9999):04d}"


def _phone(r, area: int) -> str:  # +1-<area>-555-01xx reserved-exchange style
    return f"+1-{area}-555-{r.randint(100, 199):04d}"


def _email(name: str, r) -> str:  # name-derived personal address on a synthetic domain
    parts = "".join(ch if ch.isalnum() or ch == " " else " " for ch in name).lower().split()
    stem = ".".join([parts[0], parts[-1]]) if len(parts) >= 2 else (parts[0] if parts else "user")
    return f"{stem}{r.randint(1, 999)}@example.com"


def _iban(r) -> str:  # GB IBAN shape (22 chars): GB kk MERI + 14 digits
    return f"GB{r.randint(10, 99):02d}MERI{r.randint(0, 10**14 - 1):014d}"


def _acct_no(r) -> str:  # domestic account number, masked-to-last-4 in the demo
    return f"{r.randint(1000, 9999)}-{r.randint(1000000, 9999999)}"


def _address(r) -> str:
    return (f"{r.randint(100, 9999)} {r.choice(_STREETS)} "
            f"{r.choice(['Ave', 'St', 'Blvd', 'Ln', 'Dr'])}, {r.choice(_CITIES)}, OR "
            f"{r.randint(97001, 97299):05d}")


def _tax_id(name: str, r) -> str:  # EIN for entities (…LLC), SSN-shaped for individuals
    if "LLC" in name:
        return f"{r.randint(10, 99):02d}-{r.randint(1000000, 9999999):07d}"
    return _ssn(r)


def _fresh_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return sqlite3.connect(str(path))


# ── "Terms of Sensitive Data Use" corpus (one per company, in its regulatory voice). Static — no
# randomness. Stage 0 distills these into RedactionPolicy rules that fire on the columns above.
# Minimal markdown only (#/## headings, paragraphs, "- " lists, **bold**) for the light viewer.
_TERMS: dict[str, str] = {
    "bank": """# Terms of Sensitive Data Use — Meridian Bank

Meridian Bank, N.A. ("Meridian", "the Bank") maintains this policy to govern how customer nonpublic \
personal information and Bank Secrecy Act records are classified, handled, and permitted to leave \
Bank infrastructure. It gives effect to the Bank's obligations under the Gramm-Leach-Bliley Act \
(GLBA) Safeguards Rule, the Bank Secrecy Act, and its anti-money-laundering (BSA/AML) program. Any \
automated or external processing of Bank data — including planning or analysis performed by a \
third-party or frontier model — is bound by these terms.

## Data classification

The following fields in the Bank's customer and account systems are designated sensitive and carry \
the sensitivity class shown.

- **customers.national_id** — customer government identifier (SSN / national ID). Class: RESTRICTED.
- **customers.name** — customer legal name. Class: CONFIDENTIAL.
- **customers.dob** — customer date of birth. Class: CONFIDENTIAL.
- **customers.email** — customer contact email. Class: CONFIDENTIAL.
- **customers.phone** — customer contact telephone number. Class: CONFIDENTIAL.
- **accounts.account_number** — deposit account number. Class: RESTRICTED.
- **accounts.iban** — international bank account number. Class: RESTRICTED.
- **accounts.balance_usd** — account balance. Class: CONFIDENTIAL.
- **transactions.counterparty** — transaction counterparty name. Class: CONFIDENTIAL.

## Handling rules

- Customer national identifiers in **customers.national_id** must never leave Meridian infrastructure \
in any form, masked or unmasked, and must never appear in materials sent to an external model.
- Deposit account numbers in **accounts.account_number** and **accounts.iban** must be masked to the \
last four digits before any external transmission.
- Customer names in **customers.name** may appear in external planning materials only in \
pseudonymized form; the mapping from pseudonym to real identity remains inside the Bank.
- Customer contact details in **customers.email** and **customers.phone** must be masked before \
external transmission; an email domain may be retained but its local-part must not.
- Account balances in **accounts.balance_usd** must be banded or aggregated before inclusion in any \
external planning brief; individual balances must not be transmitted.
- Counterparty names in **transactions.counterparty** must be pseudonymized before external \
transmission, except where a name is screened against a lawful sanctions list.
- All records governed by the Bank Secrecy Act, including customer identity and transaction detail, \
must remain resident on Bank-controlled infrastructure within the United States; cross-border \
transfer of BSA records is prohibited.
- Suspicious-activity analysis — structuring and dormant-account reactivation review — must run on \
de-identified data only; customer identity is re-associated exclusively inside Bank systems.
- Sensitive customer and account records must be retained for at least five years per BSA \
recordkeeping requirements and then securely destroyed.

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation \
boundary.
""",
    "clinic": """# Terms of Sensitive Data Use — Aurora Clinic

Aurora Clinic ("Aurora", "the Clinic") is a covered entity under the Health Insurance Portability \
and Accountability Act (HIPAA). This policy governs how protected health information (PHI) held in \
the Clinic's systems is classified, handled, and permitted to leave Clinic infrastructure. It binds \
all automated and external processing of Clinic data — including planning or analysis performed by a \
third-party or frontier model — to the HIPAA Privacy and Security Rules and the minimum-necessary \
standard.

## Data classification

The following fields are designated protected health information and carry the sensitivity class \
shown.

- **patients.name** — patient full name. Class: PHI (direct identifier).
- **patients.mrn** — medical record number. Class: PHI (direct identifier).
- **patients.dob** — patient date of birth. Class: PHI.
- **patients.phone** — patient telephone number. Class: PHI (direct identifier).
- **patients.address** — patient home address. Class: PHI (direct identifier).
- **encounters.icd10** — encounter diagnosis code. Class: PHI (clinical).
- **encounters.provider** — treating provider name. Class: CONFIDENTIAL.
- **prescriptions.drug** — prescribed medication. Class: PHI (clinical).

## Handling rules

- Medical record numbers in **patients.mrn** are direct identifiers and must never leave Clinic \
infrastructure in any form.
- Patient names in **patients.name** may appear in external planning materials only in pseudonymized \
form; the re-identification key remains inside the Clinic.
- Patient contact identifiers in **patients.phone** and **patients.address** must be removed before \
any external transmission and must never be sent to an external model.
- Patient dates of birth in **patients.dob** must be generalized to year of birth before external \
transmission; full dates must not leave the Clinic.
- Diagnosis codes in **encounters.icd10** and medications in **prescriptions.drug** may be included \
in external planning materials only after removal of all direct patient identifiers, consistent with \
the minimum-necessary standard.
- Any external analysis — duplicate-billing review or data-quality checks on vitals — must operate \
on a de-identified data set; re-association with patient identity occurs only inside Clinic systems.
- PHI must remain resident on Clinic-controlled infrastructure within the United States; transfer of \
identifiable PHI outside that boundary is prohibited absent a Business Associate Agreement.
- PHI must be retained for at least six years as required by HIPAA and then securely destroyed.

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation \
boundary.
""",
    "lawfirm": """# Terms of Sensitive Data Use — Hale & Ostrom LLP

Hale & Ostrom LLP ("the Firm") holds client information subject to the attorney-client privilege, \
the work-product doctrine, and the Firm's professional duty of confidentiality. This policy governs \
how privileged and confidential client data is classified, handled, and permitted to leave Firm \
infrastructure, and it binds all automated and external processing — including planning or analysis \
performed by a third-party or frontier model.

## Data classification

The following fields carry the sensitivity class shown.

- **parties.name** — client and counterparty legal name. Class: CONFIDENTIAL.
- **parties.tax_id** — client tax identifier (SSN / EIN). Class: RESTRICTED.
- **parties.contact** — client contact email. Class: CONFIDENTIAL.
- **parties.phone** — client telephone number. Class: CONFIDENTIAL.
- **contracts.matter_number** — internal matter identifier. Class: PRIVILEGED.
- **contracts.privilege** — privilege classification of the record. Class: CONTROL.
- **billing_entries.narrative** — timekeeper work description. Class: PRIVILEGED.
- **billing_entries.timekeeper** — attorney or timekeeper name. Class: CONFIDENTIAL.

## Handling rules

- Billing narratives in **billing_entries.narrative** are attorney-client privileged work product \
and must never leave Firm infrastructure or appear in materials sent to an external model, masked or \
unmasked.
- Matter identifiers in **contracts.matter_number** must never leave Firm infrastructure; external \
planning materials must reference a matter only by an opaque handle assigned inside the Firm.
- Client tax identifiers in **parties.tax_id** are restricted and must never be transmitted \
externally in any form.
- Client and counterparty names in **parties.name** may appear in external planning materials only \
in pseudonymized form; the mapping to real identity remains inside the Firm.
- Client contact details in **parties.contact** and **parties.phone** must be masked before any \
external transmission.
- Any record whose **contracts.privilege** classification is "attorney-client" or "work-product" \
must be excluded from external transmission unless privilege has been expressly waived in writing by \
the client.
- Timekeeper identities in **billing_entries.timekeeper** must be pseudonymized before external \
transmission.
- Contract review, renewal-window analysis, and fee-cap auditing may be performed on de-identified \
extracts only; privileged narrative content is never included in an external brief.
- Privileged and confidential client records must remain resident on Firm-controlled infrastructure \
and be retained per the Firm's records-retention schedule, then securely destroyed.

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation \
boundary.
""",
}


def _write_terms(cid: str) -> str:
    d = OUT / "terms"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{cid}_terms.md"
    p.write_text(_TERMS[cid], encoding="utf-8")
    return f"terms/{cid}_terms.md"


# ─────────────────────────────────────────────────────────── Meridian Bank
def gen_bank() -> dict:
    r = rng(1)
    s = rng(11)  # dedicated stream for sensitive columns — leaves the planted-pattern stream untouched
    con = _fresh_db(OUT / "bank.db")
    con.executescript(
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, dob TEXT, country TEXT,
            onboarded TEXT, pep INTEGER, national_id TEXT, email TEXT, phone TEXT);
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, customer_id INTEGER, kind TEXT,
            opened TEXT, last_active TEXT, status TEXT, balance_usd REAL,
            account_number TEXT, iban TEXT);
        CREATE TABLE transactions (id INTEGER PRIMARY KEY, account_id INTEGER, ts TEXT,
            amount_usd REAL, direction TEXT, kind TEXT, counterparty TEXT,
            memo TEXT, counterparty_account_id INTEGER);
        """
    )
    m = rng(1501)   # transaction-memo stream
    c = rng(1502)   # layering-chain stream
    start, end = date(2019, 1, 1), date(2026, 7, 1)
    # 800 customers; a handful carry sanctions-adjacent names (planted screening hits)
    customers = []
    for i in range(1, 801):
        name = SANCTIONS_ADJACENT[i % len(SANCTIONS_ADJACENT)] if i <= len(SANCTIONS_ADJACENT) else full_name(r)
        customers.append((i, name, dob(r), country(r), day_between(r, start, end).isoformat(),
                          1 if r.random() < 0.03 else 0,
                          _ssn(s), _email(name, s), _phone(s, 415)))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?)", customers)

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
                         last_active.isoformat(), status, round(r.uniform(0, 250_000), 2),
                         _acct_no(s), _iban(s)))
    con.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?)", accounts)

    # 8,000 transactions. Plant: (a) sudden reactivation on ~15 dormant accounts (a large recent
    # deposit long after last_active); (b) structuring runs — clusters of deposits just under $10k.
    txns, tid = [], 1
    react_ids = dormant_ids[:15]
    structuring_accts = r.sample(range(1, 1201), 12)
    for _ in range(7600):
        acct = r.randint(1, 1200)
        ts = day_between(r, start, end)
        amt = round(r.uniform(20, 8_000), 2)
        direction = r.choice(["credit", "debit"])
        kind = r.choice(["deposit", "withdrawal", "transfer", "card"])
        cp = full_name(r) if r.random() < 0.3 else ""
        cpa = m.randint(1, 1200) if kind == "transfer" and m.random() < 0.4 else None
        if cpa == acct:
            cpa = None
        txns.append((tid, acct, ts.isoformat(), amt, direction, kind, cp, _benign_memo(m, kind), cpa))
        tid += 1
    for acct in react_ids:  # sudden reactivation: big deposit in 2026 on a dormant account
        txns.append((tid, acct, date(2026, 6, r.randint(1, 28)).isoformat(),
                     round(r.uniform(40_000, 180_000), 2), "credit", "deposit", full_name(r),
                     _benign_memo(m, "deposit"), None))
        tid += 1
    for acct in structuring_accts:  # structuring: 8-14 deposits of $9,000-$9,900 within days
        base = day_between(r, date(2026, 1, 1), date(2026, 6, 1))
        n = r.randint(8, 14)
        co, memos = _contra_memos(m, n)  # one shady counterparty, mutually contradictory purposes
        for k in range(n):
            d = base.isoformat() if k == 0 else day_between(r, base, date(2026, 6, 20)).isoformat()
            amt = round(r.uniform(9_000, 9_900), 2)
            txns.append((tid, acct, d, amt, "credit", "deposit", co, memos[k], None))
            tid += 1
    # Benign large internal transfers (treasury sweeps, big settlements) — same magnitude and internal
    # shape as the layering hops below, so no amount/kind threshold isolates the chains; only the
    # decaying multi-hop PATH does.
    for _ in range(160):
        src, dst = m.randint(1, 1200), m.randint(1, 1200)
        if dst == src:
            dst = dst % 1200 + 1
        d = day_between(m, date(2026, 1, 1), date(2026, 6, 20)).isoformat()
        txns.append((tid, src, d, round(m.uniform(40_000, 120_000), 2), "debit", "transfer",
                     _memo_co(m), _benign_memo(m, "transfer"), dst))
        tid += 1
    # Layering chains: A->B->C->D... internal transfers within days, amount decaying 1-3% per hop,
    # terminating in an external outbound (counterparty_account_id NULL). Detection needs a recursive
    # walk (2+ hops) — a single WHERE can't distinguish these from ordinary internal transfers.
    layering_chains = 0
    for _ in range(12):
        accts = c.sample(range(1, 1201), c.choice([5, 6]))
        d = day_between(c, date(2026, 2, 1), date(2026, 5, 1))
        amt = round(c.uniform(40_000, 120_000), 2)
        for i in range(len(accts) - 1):  # internal hops
            co = _memo_co(c)
            memo = _fill_memo(m, m.choice(_MEMO[m.choice(["invoice", "loan", "services", "goods"])]), co)
            txns.append((tid, accts[i], d.isoformat(), amt, "debit", "transfer", co, memo, accts[i + 1]))
            tid += 1
            d += timedelta(days=c.randint(1, 3))
            amt = round(amt * (1 - c.uniform(0.01, 0.03)), 2)
        memo = _fill_memo(m, m.choice(_MEMO["goods"]), _memo_co(c))  # terminal external cash-out
        txns.append((tid, accts[-1], d.isoformat(), amt, "debit", "transfer", full_name(c), memo, None))
        tid += 1
        layering_chains += 1
    con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?)", txns)
    con.commit()
    counts = _counts(con, ["customers", "accounts", "transactions"])
    con.close()
    return {"db": "bank.db", "counts": counts, "terms": _write_terms("bank"),
            "planted": {"reactivation_accounts": len(react_ids), "structuring_accounts": len(structuring_accts),
                        "sanctions_adjacent_names": len(SANCTIONS_ADJACENT),
                        "contradictory_memo_accounts": len(structuring_accts),
                        "layering_chains": layering_chains}}


# ─────────────────────────────────────────────────────────── Aurora Clinic
def gen_clinic() -> dict:
    r = rng(2)
    s = rng(12)  # dedicated stream for PHI columns — leaves the planted-pattern stream untouched
    con = _fresh_db(OUT / "clinic.db")
    con.executescript(
        """
        CREATE TABLE patients (id INTEGER PRIMARY KEY, name TEXT, dob TEXT, sex TEXT,
            last_screening TEXT, mrn TEXT, phone TEXT, address TEXT);
        CREATE TABLE encounters (id INTEGER PRIMARY KEY, patient_id INTEGER, date TEXT,
            provider TEXT, department TEXT, billing_code TEXT, icd10 TEXT,
            visit_note TEXT, start_time TEXT, end_time TEXT);
        CREATE TABLE lab_results (id INTEGER PRIMARY KEY, encounter_id INTEGER, test TEXT,
            value REAL, unit TEXT, flag TEXT);
        CREATE TABLE prescriptions (id INTEGER PRIMARY KEY, encounter_id INTEGER, drug TEXT,
            dose_mg REAL, days INTEGER);
        CREATE TABLE cpt_catalog (code TEXT PRIMARY KEY, short_description TEXT, complexity_level TEXT);
        """
    )
    con.executemany("INSERT INTO cpt_catalog VALUES (?,?,?)", _CPT_CATALOG)
    k = rng(1503)   # visit-note + appointment-time stream
    depts = ["Cardiology", "Primary Care", "Endocrinology", "Oncology", "Nephrology"]
    provs = [f"Dr. {full_name(r).split()[1]}" for _ in range(20)]
    start, end = date(2024, 1, 1), date(2026, 7, 1)
    # 500 patients; ~12% overdue-screening cohort (last_screening > 2y or null)
    patients = []
    for i in range(1, 501):
        overdue = r.random() < 0.12
        last_scr = "" if overdue and r.random() < 0.4 else day_between(
            r, date(2021, 1, 1) if overdue else date(2025, 1, 1), end).isoformat()
        patients.append((i, full_name(r), dob(r, 1, 95), r.choice(["F", "M"]), last_scr,
                         f"AUR-{s.randint(100000, 999999):06d}", _phone(s, 503), _address(s)))
    con.executemany("INSERT INTO patients VALUES (?,?,?,?,?,?,?,?)", patients)

    # 2,500 encounters; plant duplicate-billing shapes (same patient+date+code twice) on ~40. Codes
    # now draw from cpt_catalog so complexity is joinable; every encounter carries a visit_note whose
    # register (brief vs complex) matches its billed complexity — except the planted upcoding block.
    _tier = {"low": _CPT_LOW, "moderate": _CPT_MOD, "high": _CPT_HIGH}

    def _benign_code_note():
        tier = r.choices(["low", "moderate", "high"], weights=[45, 40, 15])[0]
        pool = _NOTE_COMPLEX if tier == "high" else _NOTE_BRIEF
        return r.choice(_tier[tier]), _fill_note(k, k.choice(pool))

    encounters, eid = [], 1
    for _ in range(2460):
        pid = r.randint(1, 500)
        d = day_between(r, start, end).isoformat()
        prov, dept = r.choice(provs), r.choice(depts)
        code, note = _benign_code_note()
        st = k.choice(range(8 * 60, 16 * 60 + 1, 15))
        encounters.append((eid, pid, d, prov, dept, code, s.choice(_ICD10), note,
                           _hhmm(st), _hhmm(st + k.choice([15, 20, 30, 45]))))
        eid += 1
    dup_pairs = 0
    for _ in range(40):  # duplicate billing: identical (patient, date, code) on two encounters
        pid, d = r.randint(1, 500), day_between(r, start, end).isoformat()
        tier = r.choices(["low", "moderate", "high"], weights=[45, 40, 15])[0]
        code = r.choice(_tier[tier])
        pool = _NOTE_COMPLEX if tier == "high" else _NOTE_BRIEF
        for _ in range(2):
            st = k.choice(range(8 * 60, 16 * 60 + 1, 15))
            encounters.append((eid, pid, d, r.choice(provs), r.choice(depts), code, s.choice(_ICD10),
                               _fill_note(k, k.choice(pool)), _hhmm(st), _hhmm(st + k.choice([15, 20, 30, 45]))))
            eid += 1
        dup_pairs += 1
    # Provider double-booking: 25 pairs where one provider has OVERLAPPING encounters in two different
    # departments on the same date. Detection needs a temporal-overlap self-join, not a single scan.
    double_booking_pairs = 0
    for _ in range(25):
        prov = r.choice(provs)
        d = day_between(r, start, end).isoformat()
        d1, d2 = r.sample(depts, 2)
        s1 = k.choice(range(9 * 60, 15 * 60, 15))
        e1 = s1 + k.choice([30, 45, 60])
        s2 = s1 + k.choice([10, 15, 20])                 # starts inside the first window → overlap
        e2 = s2 + k.choice([30, 45, 60])
        for dept, ss, ee in [(d1, s1, e1), (d2, s2, e2)]:
            tier = r.choices(["low", "moderate"], weights=[6, 4])[0]
            encounters.append((eid, r.randint(1, 500), d, prov, dept, r.choice(_tier[tier]),
                               s.choice(_ICD10), _fill_note(k, k.choice(_NOTE_BRIEF)), _hhmm(ss), _hhmm(ee)))
            eid += 1
        double_booking_pairs += 1
    # Upcoding (APPENDED LAST so the block is the trailing 60 encounter ids): each is billed a
    # HIGH-complexity code but the visit_note describes a brief, routine visit. The mismatch lives only
    # in the note's meaning — a script comparing structured fields cannot see it.
    upcoding_encounters = 0
    for _ in range(60):
        st = k.choice(range(8 * 60, 16 * 60 + 1, 15))
        encounters.append((eid, r.randint(1, 500), day_between(r, start, end).isoformat(),
                           r.choice(provs), r.choice(depts), r.choice(_CPT_HIGH), s.choice(_ICD10),
                           _fill_note(k, k.choice(_NOTE_BRIEF)), _hhmm(st), _hhmm(st + k.choice([15, 20, 30, 45]))))
        eid += 1
        upcoding_encounters += 1
    con.executemany("INSERT INTO encounters VALUES (?,?,?,?,?,?,?,?,?,?)", encounters)

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
    counts = _counts(con, ["patients", "encounters", "lab_results", "prescriptions", "cpt_catalog"])
    con.close()
    return {"db": "clinic.db", "counts": counts, "terms": _write_terms("clinic"),
            "planted": {"duplicate_billing_pairs": dup_pairs, "impossible_vitals": impossible,
                        "upcoding_encounters": upcoding_encounters,
                        "provider_double_booking_pairs": double_booking_pairs}}


# ─────────────────────────────────────────────────────────── Hale & Ostrom (law firm)
_CONTRACT_TMPL = """MASTER SERVICES AGREEMENT

This Agreement ("Agreement") is entered into as of {eff} by and between {a} ("Client") and
{b} ("Provider").

1. TERM. The initial term of this Agreement is {term} months, commencing on the Effective Date.
{renewal}

2. FEES. Provider shall invoice Client monthly. {feecap}

3. CONFIDENTIALITY. Each party shall protect the other's Confidential Information and shall not
disclose it to any third party without prior written consent.

4. LIMITATION OF LIABILITY. {liability}

5. INDEMNIFICATION. {indemnity}

6. TERMINATION. Either party may terminate for material breach upon 30 days' written notice if the
breach remains uncured.

7. GOVERNING LAW. This Agreement is governed by the laws of the State of Delaware.

{signature}
"""


def gen_lawfirm() -> dict:
    r = rng(3)
    s = rng(13)  # dedicated stream for privilege/PII columns — leaves the contracts stream untouched
    con = _fresh_db(OUT / "lawfirm.db")
    con.executescript(
        """
        CREATE TABLE parties (id INTEGER PRIMARY KEY, name TEXT, kind TEXT, contact TEXT,
            tax_id TEXT, phone TEXT);
        CREATE TABLE contracts (id INTEGER PRIMARY KEY, title TEXT, party_a INTEGER, party_b INTEGER,
            effective_date TEXT, term_months INTEGER, auto_renew INTEGER, notice_days INTEGER,
            fee_cap_usd REAL, text_ref TEXT, matter_number TEXT, privilege TEXT);
        CREATE TABLE billing_entries (id INTEGER PRIMARY KEY, contract_id INTEGER, date TEXT,
            hours REAL, rate_usd REAL, amount_usd REAL, timekeeper TEXT, narrative TEXT);
        CREATE TABLE amendments (id INTEGER PRIMARY KEY, contract_id INTEGER, effective_date TEXT,
            text_ref TEXT);
        """
    )
    lc = rng(1505)   # liability/indemnity clause stream (corpus-only, mirrored in no db column)
    am = rng(1506)   # amendment stream
    parties = []
    for i in range(1, 351):
        name = (full_name(r) if r.random() < 0.5 else
                f"{r.choice(['Nexa', 'Orbit', 'Vertex', 'Lumen', 'Kestrel'])} "
                f"{r.choice(['Holdings', 'Systems', 'Labs', 'Partners', 'Group'])} LLC")
        parties.append((i, name, r.choice(["client", "counterparty"]), f"legal@example{i}.com",
                        _tax_id(name, s), _phone(s, 212)))
    con.executemany("INSERT INTO parties VALUES (?,?,?,?,?,?)", parties)

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
        # Liability/indemnity clause pair — planted contracts (id % 8 == 3) pair a CAPPED liability with
        # an UNCAPPED indemnity that overrides it (internal contradiction); benign contracts pair them
        # consistently. Corpus text only — deliberately NOT recorded in any db column.
        if i % 8 == 3:
            liability, indemnity = lc.choice(_LIAB_CAPPED), lc.choice(_INDEM_UNBOUNDED)
        elif lc.random() < 0.5:
            liability, indemnity = lc.choice(_LIAB_CAPPED), lc.choice(_INDEM_BOUNDED)
        else:
            liability, indemnity = lc.choice(_LIAB_UNCAPPED), lc.choice(_INDEM_UNBOUNDED)
        liability = liability.format(lcap=f"{lc.randint(1, 10) * 100_000:,}")
        title = f"MSA {parties[a-1][1]} / {parties[b-1][1]}"
        text = _CONTRACT_TMPL.format(eff=eff.isoformat(), a=parties[a-1][1], b=parties[b-1][1],
                                     term=term, renewal=renewal, feecap=feecap, signature=signature,
                                     liability=liability, indemnity=indemnity)
        ref = f"contracts/contract_{i:03d}.txt"
        (contracts_dir / f"contract_{i:03d}.txt").write_text(text, encoding="utf-8")
        matter = f"H&O-{s.choice([2022, 2023, 2024, 2025])}-{s.randint(1000, 9999):04d}"
        privilege = s.choice(["attorney-client", "work-product", "confidential"])
        rows.append((i, title, a, b, eff.isoformat(), term, auto_renew, notice, fee_cap, ref,
                     matter, privilege))
        if auto_renew and notice < 60:
            planted["auto_renew_short_notice"] += 1
        if missing_sig:
            planted["missing_signature"] += 1
    con.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    # 2,000 billing entries; plant fee-cap breaches on ~15 contracts (sum of amount > fee_cap)
    entries, bid = [], 1
    for _ in range(1900):
        cid = r.randint(1, 200)
        hours = round(r.uniform(0.5, 8), 1)
        rate = r.choice([250, 400, 550, 700])
        entries.append((bid, cid, day_between(r, start, date(2026, 7, 1)).isoformat(), hours, rate,
                        round(hours * rate, 2), full_name(s), s.choice(_NARRATIVES)))
        bid += 1
    breach_contracts = r.sample(range(1, 201), 15)
    for cid in breach_contracts:  # pile enough hours to exceed the fee cap
        cap = rows[cid-1][8]
        piled = 0.0
        while piled < cap * 1.2:
            amt = round(700 * 8, 2)
            entries.append((bid, cid, day_between(r, date(2026, 1, 1), date(2026, 7, 1)).isoformat(),
                            8.0, 700, amt, full_name(s), s.choice(_NARRATIVES)))
            piled += amt
            bid += 1
    con.executemany("INSERT INTO billing_entries VALUES (?,?,?,?,?,?,?,?)", entries)

    # Amendments (~40 files). Planted: 12 contracts (ids 10,20,...,120) each get two amendments with
    # CONTRADICTORY terms on the same clause where the LATER is SILENT on precedence — resolvable only
    # by reading base + both amendments. Benign contracts get 1-2 non-conflicting amendments; benign
    # singles are also silent, so silence alone does not isolate the plant.
    amend_rows, aid = [], 1

    def _write_amend(cid: int, no: int, eff_date: str, body: str, precedence: str) -> None:
        nonlocal aid
        ref = f"contracts/amendment_{aid:03d}.txt"
        (contracts_dir / f"amendment_{aid:03d}.txt").write_text(
            _AMEND_TMPL.format(no=no, eff=eff_date, matter=rows[cid - 1][10], body=body,
                               precedence=precedence),
            encoding="utf-8")
        amend_rows.append((aid, cid, eff_date, ref))
        aid += 1

    amendment_conflicts = list(range(10, 121, 10))   # 12 planted contracts
    for cid in amendment_conflicts:
        pa, pb = am.choice(_AMEND_CONFLICT)
        vals = {"vA": f"{am.randint(2, 9) * 100_000:,}", "vB": f"{am.randint(1, 4) * 50_000:,}"}
        d1 = day_between(am, date(2024, 1, 1), date(2025, 1, 1)).isoformat()
        d2 = day_between(am, date(2025, 2, 1), date(2026, 6, 1)).isoformat()   # strictly later
        _write_amend(cid, 1, d1, pa.format(**vals), am.choice(_AMEND_PREC))
        _write_amend(cid, 2, d2, pb.format(**vals), _AMEND_SILENT)             # later one: silent
    for cid in [5, 15, 25, 35]:      # benign: two non-conflicting amendments, both cite precedence
        d1 = day_between(am, date(2024, 1, 1), date(2025, 1, 1)).isoformat()
        d2 = day_between(am, date(2025, 2, 1), date(2026, 6, 1)).isoformat()
        _write_amend(cid, 1, d1, _amend_body(am), am.choice(_AMEND_PREC))
        _write_amend(cid, 2, d2, _amend_body(am), am.choice(_AMEND_PREC))
    for cid in [45, 55, 65, 75, 85, 95, 105, 115]:   # benign singles, silent (nothing to resolve)
        d1 = day_between(am, date(2024, 1, 1), date(2026, 6, 1)).isoformat()
        _write_amend(cid, 1, d1, _amend_body(am), _AMEND_SILENT)
    con.executemany("INSERT INTO amendments VALUES (?,?,?,?)", amend_rows)
    con.commit()
    counts = _counts(con, ["parties", "contracts", "billing_entries", "amendments"])
    con.close()
    planted["fee_cap_breaches"] = len(breach_contracts)
    planted["contract_text_contradictions"] = sum(1 for i in range(1, 201) if i % 8 == 3)
    planted["amendment_conflicts"] = len(amendment_conflicts)
    planted["amendments_total"] = len(amend_rows)
    return {"db": "lawfirm.db", "counts": counts, "planted": planted, "contracts_txt": 200,
            "amendments_txt": len(amend_rows), "terms": _write_terms("lawfirm")}


def _counts(con: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def generate_all() -> dict:
    return {"bank": gen_bank(), "clinic": gen_clinic(), "lawfirm": gen_lawfirm()}
