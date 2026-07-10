"""Insurer seed kit — Cascadia Mutual, a P&C carrier (09 §5, Demo 5 Claims, at scale).

One read-only SQLite (`out/insurer.db`) with policies / adjusters / repair_shops / claims /
claim_payments. Plants four claims-fraud shapes so the suggested prompts find real things — every
output is computed live, never canned (09 track rule). Fixed RNG seed (rng salt 11) → regenerates
byte-for-byte (rehearsal gate 09 §7: "regenerated from scratch proves no hand-tuned state").

Planted (all discoverable with plain SQL over the final DB):
  (a) duplicate claims        — 120 pairs: same policy + same incident_date, amounts within 5%
  (b) staged-accident rings   — 8 rings: distinct policies sharing one repair_shop + one claimant
                                phone within a short window
  (c) over-coverage payouts   — 200 claims whose claim_payments sum exceeds the policy coverage limit
  (d) adjuster anomaly        — 6 adjusters approving >98% (peers ~80%) at approved amounts well above
                                the peer mean

Sensitive PII (masking targets for the stage-0 boundary demo; decorated on rng salts 12/13 so the
plant rng stream `r` stays byte-identical): policies carry policyholder_national_id / _email /
_address / premium_bank_account; claims carry claimant_phone + injury_code. out/terms/insurer_terms.md
distills into rules that bite these columns.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from ._gen import full_name, rng

OUT = __import__("pathlib").Path(__file__).resolve().parent / "out"

_CITIES = ["Seattle", "Portland", "Tacoma", "Bellevue", "Spokane", "Eugene", "Salem", "Bend",
           "Olympia", "Vancouver", "Boise", "Yakima", "Redmond", "Everett", "Gresham"]
_SHOP_TYPES = ["Auto Body", "Collision Center", "Body Works", "Auto Repair", "Motors", "Garage"]
_SHOP_NAMES = ["Cascade", "Summit", "Rainier", "Harbor", "Evergreen", "Pioneer", "Coastal",
               "Cedar", "Northwest", "Meridian", "Union", "Falcon", "Granite", "Willamette"]
_REGIONS = ["North", "South", "Coastal", "Interior", "Metro"]
_SENIORITY = ["Junior", "Adjuster", "Senior", "Lead", "Principal"]
# coverage limit range by policy kind (a claim is normally a small fraction of this)
_COVERAGE = {"auto": (50_000, 150_000), "home": (200_000, 800_000),
             "commercial": (750_000, 6_000_000)}
_SHOP_PROB = {"auto": 0.75, "home": 0.15, "commercial": 0.25}


def _phone(r) -> str:
    return f"+1-{r.randint(200, 989)}-{r.randint(200, 989)}-{r.randint(1000, 9999)}"


# ── synthetic policyholder / claimant PII (fully fake; drawn ONLY from a caller-supplied rng) ──
_STREETS = ["Cascade Ave", "Rainier St", "Willamette Blvd", "Pioneer Way", "Harbor Dr",
            "Cedar Ln", "Meridian Ave", "Union St", "Alder St", "Marine Dr"]
_STATES = ["WA", "OR"]  # Cascadia Mutual writes P&C in the Pacific Northwest only
# ICD-10-style bodily-injury codes (auto/commercial liability) — the claims-file medical class
_ICD10 = ["S72.001A", "S82.101A", "S42.001A", "S52.501A", "M54.5", "S06.0X0A",
          "S13.4XXA", "T14.90XA", "S93.401A", "S43.006A", "S32.010A", "S22.020A"]


def _national_id(r) -> str:  # SSN-shaped, fully synthetic (never a real number)
    return f"{r.randint(100, 899):03d}-{r.randint(10, 99):02d}-{r.randint(1000, 9999):04d}"


def _email(r, name: str) -> str:  # name-derived, e.g. "mary.silva4821@example.com"
    first, _, last = name.partition(" ")
    return f"{first}.{last}{r.randint(1, 9999)}@example.com".lower()


def _address(r) -> str:
    return (f"{r.randint(100, 9999)} {r.choice(_STREETS)}, {r.choice(_CITIES)}, "
            f"{r.choice(_STATES)} {r.randint(97000, 99499):05d}")


def _bank_account(r) -> str:  # 12-digit premium-draft account number (mask-to-last-4 target)
    return f"{r.randint(10 ** 11, 10 ** 12 - 1)}"


def _injury(r, kind: str) -> str:  # bodily-injury codes ride auto/commercial liability claims only
    hit = r.random() < 0.5  # draw every row so the rng stream is kind-independent within salt 13
    return r.choice(_ICD10) if hit and kind in ("auto", "commercial") else ""


# ── FNOL narrative corpus (unstructured layer, rng salt 1110) ──────────────────────────────────
# A first-notice-of-loss free-text description rides EVERY claim, alongside a structured
# claims.damage_area (the point of impact / affected area). Benign narratives AGREE with damage_area.
# The 8 staged-accident rings get copy-adjacent narratives (shared skeleton, swapped make slot) whose
# described point of impact CONTRADICTS damage_area — front-vs-rear, roof-vs-basement. There is no
# keyword tell: directional / collision vocabulary ("behind", "ahead", "left", "rear", "struck") is
# scattered through the scene + aftermath of every narrative regardless of damage_area, so the signal
# is MEANING (which sentence is the operative impact, and does its direction match the field) — only a
# reader can decide it, never a LIKE/regex.
_VEH_AREAS = ["front", "rear", "driver_side", "passenger_side", "roof"]
_PROP_AREAS = ["roof", "kitchen", "basement", "garage", "exterior"]

_VEH_IMPACTS = [  # (implied damage_area, operative impact clause)
    ("front", "as I entered the junction the other car cut across and I caught it head-on"),
    ("front", "traffic stopped fast and I could not brake in time, catching the vehicle ahead"),
    ("front", "a car pulled out of the lot and I ran into it as I came forward"),
    ("rear", "I was stationary at the crossing when a following vehicle rolled into the back of mine"),
    ("rear", "waiting to turn, I felt a jolt as the van behind me failed to stop"),
    ("rear", "at the toll the pickup behind did not slow and pushed into my tailgate"),
    ("driver_side", "a car ran the sign and clipped me along the driver door as I crossed"),
    ("driver_side", "merging traffic came across and caught the left of my vehicle"),
    ("driver_side", "someone drifted out of their lane on my left and scraped down the driver door"),
    ("passenger_side", "turning right, another vehicle came through and struck the far door"),
    ("passenger_side", "a car reversing out of a bay caught the right flank of my vehicle"),
    ("passenger_side", "at the roundabout a van cut in and hit the passenger panel"),
    ("roof", "on the icy bend the car slid, went over and came to rest upside down"),
    ("roof", "a large branch came down in the storm and caved the top in"),
    ("roof", "the vehicle rolled on the embankment and took the impact up top"),
]
_PROP_IMPACTS = [
    ("roof", "wind lifted shingles overnight and water started coming through the ceiling upstairs"),
    ("roof", "a falling limb punched through overhead and opened the attic to the rain"),
    ("roof", "hail battered the decking above the bedrooms and cracked it through"),
    ("kitchen", "a supply line under the sink let go and flooded the cooking area before we noticed"),
    ("kitchen", "a pan fire spread to the cabinets and scorched the wall by the stove"),
    ("kitchen", "the dishwasher overflowed and soaked the flooring where we cook"),
    ("basement", "heavy rain backed up the drain and the lower level took several inches of water"),
    ("basement", "the sump pump failed during the storm and the lower level flooded"),
    ("basement", "a cracked foundation wall let groundwater seep in below grade"),
    ("garage", "an electrical fault by the parking bay started a fire that damaged the near wall"),
    ("garage", "the overhead door mechanism failed and came down on the parked car"),
    ("garage", "a vehicle rolled forward in the bay and went through the back wall"),
    ("exterior", "a storm brought a fence and part of the siding down along the outside"),
    ("exterior", "a neighbouring tree fell against the outside wall and cracked the render"),
    ("exterior", "flood water rose against the outside and undermined the cladding"),
]
_VEH_SCENE = [  # scene-setting; each mentions some direction so directional words flood every area
    "It was a wet evening and traffic was heavy.",
    "Visibility was poor with a delivery van close behind me.",
    "I was on my usual commute with a sedan slowing ahead.",
    "The lot was busy and cars were backing out on both sides.",
    "Conditions were fine but the road ahead was congested.",
    "There was a car tailgating me for most of the trip.",
    "The junction was blind with traffic crossing from the left.",
    "I had just left home and the streets were quiet.",
    "Rain had made the surface slick near the bend.",
    "A cyclist was to my right and I was watching my mirrors.",
    "Someone was riding my bumper the whole way in.",
    "It happened late at night with little traffic around.",
    "The car ahead braked hard for a light.",
    "A truck was merging on my left as I approached.",
    "The road curved and the sun was low behind me.",
]
_PROP_SCENE = [
    "The property looked fine when I left that morning.",
    "The neighbours were away and the street was empty.",
    "Everything seemed normal until the noise started.",
    "We had been away for the weekend.",
    "The storm had been building all afternoon.",
    "It was the coldest night of the winter.",
    "We were asleep when it happened.",
    "The tenants called it in first thing.",
    "Work had just finished on the other side of the house.",
    "The gutters had been cleared the week before.",
    "There had been heavy rain for three days.",
    "The alarm went off just after midnight.",
    "We were home but did not hear anything at first.",
    "It was quiet until water started coming down.",
    "Nothing seemed wrong from the front of the house.",
]
_VEH_AFTER = [
    "I pulled over to the right and we exchanged details.",
    "The other driver stopped a few lengths ahead.",
    "We moved onto the shoulder and called it in.",
    "Nobody appeared hurt and both cars were driveable.",
    "The car behind stayed until police arrived.",
    "I took photos of the damage and the other plates.",
    "Traffic backed up behind us while we waited.",
    "The vehicle was towed from the near side.",
]
_PROP_AFTER = [
    "We shut the water off at the main and called a contractor.",
    "The damage was contained to that part of the house.",
    "We moved what we could into a dry room.",
    "A neighbour helped board up the opening.",
    "We got the power isolated before anything spread.",
    "The loss adjuster was booked for the next day.",
]
_MAKES = ["Honda Civic", "Toyota Corolla", "Ford F-150", "Subaru Outback", "Nissan Altima",
          "Chevrolet Malibu", "Hyundai Elantra", "Jeep Cherokee", "Mazda CX-5", "Kia Sportage",
          "Ram 1500", "Volkswagen Jetta"]

# name-variant machinery for the serial re-enrollment plant (rng salt 1111)
_NICK = {"James": "Jim", "Mary": "Mae", "Ivan": "Vanya", "Sofia": "Sonia", "Elena": "Lena",
         "Sergei": "Serge", "Andrei": "Andrey", "Pavel": "Pasha", "Anna": "Annie", "Diego": "Dieg",
         "Priya": "Pri", "Tomas": "Tom", "Mateo": "Teo", "Iryna": "Ira", "Omar": "Omi", "Zara": "Zar"}


def _translit(last: str) -> str:  # plausible transliteration variant of a surname
    for a, b in (("kov", "koff"), ("ova", "ovna"), ("ov", "off"), ("ev", "eff"),
                 ("sky", "ski"), ("in", "ine"), ("ez", "es")):
        if last.endswith(a):
            return last[:-len(a)] + b
    return last + "s"


def _name_variants(first: str, last: str) -> list[str]:
    """Up to four linkable spellings of one person (canonical / initial / transliterated / nickname)."""
    out: list[str] = []
    for x in (f"{first} {last}", f"{first[0]}. {last}", f"{first} {_translit(last)}",
              f"{_NICK.get(first, first[:3])} {last}"):
        if x not in out:
            out.append(x)
    return out


def _split(r, total: float, k: int) -> list[float]:
    """k installment amounts summing (to cents) to total."""
    if k == 1:
        return [round(total, 2)]
    cuts = sorted(r.random() for _ in range(k - 1)) + [1.0]
    parts, prev = [], 0.0
    for c in cuts:
        parts.append(c - prev)
        prev = c
    amts = [round(total * p, 2) for p in parts]
    amts[-1] = round(total - sum(amts[:-1]), 2)
    return amts


def _chunked(con: sqlite3.Connection, sql: str, rows: list, size: int = 50_000) -> None:
    for i in range(0, len(rows), size):
        con.executemany(sql, rows[i:i + size])


# Static "Terms of Sensitive Data Use" — stage 0 distills this into a RedactionPolicy whose rules
# bite the real policies.* / claims.* columns above. Markdown limited to #/## + paragraphs + "- " +
# **bold** (minimal viewer). References >= 4 real table.column names by design.
_TERMS = """# Cascadia Mutual — Terms of Sensitive Data Use

Cascadia Mutual is a policyholder-owned property and casualty carrier writing auto, home, and
commercial lines across Washington and Oregon. As a mutual, our first duty runs to our members. This
document states how policyholder and claimant information held in our claims and policy systems is
classified and handled whenever any part of it is prepared for processing outside Cascadia Mutual
infrastructure. It gives effect to our obligations under the state insurance codes (RCW Title 48 and
the parallel Oregon Insurance Code), the NAIC Insurance Data Security Model Law, the Gramm-Leach-Bliley
Act safeguards for nonpublic personal financial information, and the health-adjacent protections that
attach to bodily-injury data in a claims file. **Sensitive fields must never cross the external
boundary in a form that identifies, or helps re-identify, a member or claimant.**

## Data classification

- **policies.holder_name** — Policyholder identity. Nonpublic personal information (**Confidential**).
- **policies.policyholder_national_id** — Member national identifier / SSN. Government identifier (**Restricted**).
- **policies.policyholder_email** — Member contact email. Nonpublic personal information (**Confidential**).
- **policies.policyholder_address** — Member residential address. Nonpublic personal information (**Confidential**).
- **policies.premium_bank_account** — Premium-draft bank account number. Financial account data under GLBA (**Restricted**).
- **claims.claimant_phone** — Claimant contact telephone. Nonpublic personal information (**Confidential**).
- **claims.injury_code** — Bodily-injury diagnosis code on the claim. Health-adjacent data (**Restricted**).
- **adjusters.name** — Adjuster identity. Internal personnel data (**Internal**).
- **repair_shops.phone** — Repair-shop business contact. Business contact data (**Internal**).

## Handling rules

- Member national identifiers in **policies.policyholder_national_id** must never leave Cascadia Mutual infrastructure, in whole or in part, under any circumstance.
- Bank account numbers in **policies.premium_bank_account** must be masked to their last four digits before any external transmission; the full number is never exported.
- Bodily-injury codes in **claims.injury_code** are health-adjacent and may appear in external planning materials only in pseudonymized form, generalized to injury category rather than the specific diagnosis code.
- Claimant telephone numbers in **claims.claimant_phone** must be masked before external transmission; at most the area code may be retained for staged-ring pattern analysis.
- Policyholder email addresses in **policies.policyholder_email** may appear externally as the domain portion only, never the full mailbox.
- Policyholder residential addresses in **policies.policyholder_address** may be generalized to city and state for external planning; street lines must be dropped.
- Policyholder names in **policies.holder_name** and adjuster names in **adjusters.name** may appear in external planning briefs only in pseudonymized form.
- All records containing the fields above must remain resident on infrastructure located within the United States; no sensitive claims or policy data may be stored or processed in another jurisdiction.
- Claim files carrying **claims.injury_code** and **claims.claimant_phone** are retained no longer than seven years after claim closure, after which the sensitive fields are irreversibly purged.
- No combination of masked or generalized fields may be transmitted externally if, taken together, they would re-identify a member or claimant.

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation boundary.
"""


def gen_insurer() -> dict:
    r = rng(11)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "terms").mkdir(parents=True, exist_ok=True)
    (OUT / "terms" / "insurer_terms.md").write_text(_TERMS)  # fresh overwrite each regen
    path = OUT / "insurer.db"
    if path.exists():
        path.unlink()
    con = sqlite3.connect(str(path))
    con.executescript(
        """
        CREATE TABLE policies (id INTEGER PRIMARY KEY, holder_name TEXT, kind TEXT,
            coverage_limit_usd REAL, start_date TEXT, end_date TEXT, premium_usd REAL,
            policyholder_national_id TEXT, policyholder_email TEXT, policyholder_address TEXT,
            premium_bank_account TEXT);
        CREATE TABLE adjusters (id INTEGER PRIMARY KEY, name TEXT, hire_date TEXT,
            region TEXT, seniority TEXT);
        CREATE TABLE repair_shops (id INTEGER PRIMARY KEY, name TEXT, city TEXT, phone TEXT);
        CREATE TABLE claims (id INTEGER PRIMARY KEY, policy_id INTEGER, incident_date TEXT,
            filed_date TEXT, kind TEXT, amount_claimed REAL, amount_approved REAL, status TEXT,
            adjuster_id INTEGER, repair_shop_id INTEGER, claimant_phone TEXT, injury_code TEXT,
            damage_area TEXT, fnol_narrative TEXT);
        CREATE TABLE claim_payments (id INTEGER PRIMARY KEY, claim_id INTEGER, date TEXT,
            amount REAL);
        """
    )

    # ── policies (50k) ── keep per-policy kind/coverage/dates in parallel arrays for FK-clean claims
    N_POL = 50_000
    pol_kind, pol_cov = [None] * (N_POL + 1), [0.0] * (N_POL + 1)
    pol_start, pol_end = [None] * (N_POL + 1), [None] * (N_POL + 1)
    policies = []
    for i in range(1, N_POL + 1):
        kind = "auto" if r.random() < 0.55 else "home" if r.random() < 0.78 else "commercial"
        lo, hi = _COVERAGE[kind]
        cov = round(r.uniform(lo, hi), 2)
        start = date(2022, 1, 1) + timedelta(days=r.randint(0, (date(2025, 6, 1) - date(2022, 1, 1)).days))
        end = start + timedelta(days=r.choice([12, 24, 36]) * 30)
        prem = round(cov * {"auto": r.uniform(0.02, 0.05), "home": r.uniform(0.003, 0.01),
                            "commercial": r.uniform(0.005, 0.02)}[kind], 2)
        pol_kind[i], pol_cov[i], pol_start[i], pol_end[i] = kind, cov, start, end
        policies.append((i, full_name(r), kind, cov, start.isoformat(), end.isoformat(), prem))
    # decorate policyholder PII on a *separate* rng (salt 12) so the plant rng stream `r` is never
    # touched — every planted-fraud pattern regenerates byte-identical, only new columns are added.
    r2 = rng(12)
    policies = [row + (_national_id(r2), _email(r2, row[1]), _address(r2), _bank_account(r2))
                for row in policies]
    _chunked(con, "INSERT INTO policies VALUES (?,?,?,?,?,?,?,?,?,?,?)", policies)

    # ── adjusters (150) ── 6 are anomalous: they approve ~99.5% (peers 75-85%) at full payout.
    # The anomaly is behavioural (provable from `claims`), so it is NOT flagged in this table.
    anomalous = set(r.sample(range(1, 151), 6))
    adj_rate = {}
    adjusters = []
    for i in range(1, 151):
        adj_rate[i] = 0.995 if i in anomalous else round(r.uniform(0.75, 0.85), 3)
        hire = date(2015, 1, 1) + timedelta(days=r.randint(0, (date(2024, 1, 1) - date(2015, 1, 1)).days))
        adjusters.append((i, full_name(r), hire.isoformat(), r.choice(_REGIONS), r.choice(_SENIORITY)))
    con.executemany("INSERT INTO adjusters VALUES (?,?,?,?,?)", adjusters)

    # ── repair_shops (600) ──
    shops = [(i, f"{r.choice(_SHOP_NAMES)} {r.choice(_SHOP_TYPES)}", r.choice(_CITIES), _phone(r))
             for i in range(1, 601)]
    con.executemany("INSERT INTO repair_shops VALUES (?,?,?,?)", shops)

    claims: list = []
    approved_rows: list = []  # (claim_id, filed_date, approved_amt, coverage) for payment planning
    cid = 0

    def add_claim(policy_id, incident, filed, amount_claimed, adjuster_id, shop_id, phone,
                  *, approve: bool):
        """Append one decided claim. Coupling approve/amount to the adjuster is what makes the
        adjuster anomaly (d) fall out live: anomalous adjusters approve at full, peers haircut."""
        nonlocal cid
        cid += 1
        if approve:
            status = "approved"
            approved = (amount_claimed if adjuster_id in anomalous
                        else round(amount_claimed * r.uniform(0.6, 0.9), 2))
            approved_rows.append((cid, filed, approved, pol_cov[policy_id]))
        else:
            status, approved = "denied", 0.0
        claims.append((cid, policy_id, incident.isoformat(), filed.isoformat(), pol_kind[policy_id],
                       amount_claimed, approved, status, adjuster_id, shop_id, phone))

    # ── base claims (~140k) ──
    N_BASE = 140_000
    for _ in range(N_BASE):
        pid = r.randint(1, N_POL)
        kind = pol_kind[pid]
        adjuster = r.randint(1, 150)
        anom = adjuster in anomalous
        # incident within the policy's active window, capped at "today"
        hi = min(pol_end[pid], date(2026, 6, 30))
        if hi <= pol_start[pid]:
            hi = pol_start[pid] + timedelta(days=30)
        incident = pol_start[pid] + timedelta(days=r.randint(0, (hi - pol_start[pid]).days))
        filed = incident + timedelta(days=r.randint(0, 20))
        # anomalous adjusters ride inflated claims (~0.45-0.68 of the limit); peers file small ones
        frac = r.uniform(0.45, 0.68) if anom else r.uniform(0.02, 0.28)
        amount = round(pol_cov[pid] * frac, 2)
        shop = r.randint(1, 600) if r.random() < _SHOP_PROB[kind] else None
        # explicit 8% "open" (undecided) slice, else let the adjuster rate decide
        if r.random() < 0.08:
            cid += 1
            claims.append((cid, pid, incident.isoformat(), filed.isoformat(), kind, amount,
                           None, "open", adjuster, shop, _phone(r)))
        else:
            add_claim(pid, incident, filed, amount, adjuster, shop, _phone(r),
                      approve=(r.random() < adj_rate[adjuster]))

    # ── plant (a): 120 duplicate pairs — same policy + incident_date, amounts within 5% ──
    dup_pairs = 120
    base_adjusters = [a for a in range(1, 151) if a not in anomalous]
    for _ in range(dup_pairs):
        pid = r.randint(1, N_POL)
        hi = min(pol_end[pid], date(2026, 6, 30))
        if hi <= pol_start[pid]:
            hi = pol_start[pid] + timedelta(days=30)
        incident = pol_start[pid] + timedelta(days=r.randint(0, (hi - pol_start[pid]).days))
        amount = round(pol_cov[pid] * r.uniform(0.05, 0.2), 2)
        amt2 = round(amount * r.uniform(0.96, 1.04), 2)  # within 5%
        shop = r.randint(1, 600)
        for amt in (amount, amt2):
            add_claim(pid, incident, incident + timedelta(days=r.randint(0, 5)), amt,
                      r.choice(base_adjusters), shop, _phone(r), approve=True)

    # ── plant (b): 8 staged-accident rings — distinct policies sharing shop + phone in a window ──
    # rings_members[i] = the claim ids of ring i, so the narrative layer below can hang mutually
    # copy-adjacent, structurally-contradictory FNOL stories on exactly these claims (plant a-narr).
    n_rings, ring_claims = 8, 0
    rings_members: list[list[int]] = []
    for _ in range(n_rings):
        shop = r.randint(1, 600)
        phone = _phone(r)  # one shared claimant phone for the whole ring
        anchor = date(2024, 1, 1) + timedelta(days=r.randint(0, 600))
        pids = r.sample(range(1, N_POL + 1), r.randint(6, 12))  # unrelated policies
        members: list[int] = []
        for pid in pids:
            incident = anchor + timedelta(days=r.randint(0, 21))  # tight window
            amount = round(pol_cov[pid] * r.uniform(0.03, 0.15), 2)
            add_claim(pid, incident, incident + timedelta(days=r.randint(0, 7)), amount,
                      r.choice(base_adjusters), shop, phone, approve=True)
            members.append(cid)
            ring_claims += 1
        rings_members.append(members)

    # ── plant (c): 200 over-coverage payouts — total payments exceed the policy coverage limit ──
    over_n = 200
    over_ids = set(r.sample([row[0] for row in approved_rows], over_n))

    # ── claim_payments (~170k) ── approved claims pay in installments summing to amount_approved,
    # except the 200 planted claims whose installments overshoot the coverage limit (plant c).
    payments, pid_seq = [], 0
    for claim_id, filed, approved, cov in approved_rows:
        if claim_id in over_ids:
            total = round(cov * r.uniform(1.05, 1.4), 2)  # breach the coverage limit
            k = r.randint(2, 4)
        else:
            total = approved
            x = r.random()
            k = 1 if x < 0.55 else 2 if x < 0.85 else 3
        for j, amt in enumerate(_split(r, total, k)):
            pid_seq += 1
            payments.append((pid_seq, claim_id, (filed + timedelta(days=30 * j + r.randint(0, 10)))
                             .isoformat(), amt))

    # ── plant (e): serial re-enrollment — ~10 identities recurring across unrelated policies under
    # name VARIANTS (transliteration / initials / nickname) with ONE shared residence + a partially
    # overlapping claimant phone, each new policy opened shortly after the prior claim paid out.
    # Detecting it needs fuzzy entity resolution AND timeline ordering — reconcile policies↔claims↔
    # claim_payments across time, not a single-table filter. rng salt 1111 (isolated from stream r).
    rr = rng(1111)
    reenroll_chains, reenroll_policies, reenroll_claims = 10, 0, 0
    chain_pol: list = []
    pol_id = N_POL  # chain policies take ids N_POL+1 .. (no existing claim references them)
    for _ in range(reenroll_chains):
        bf, _, bl = full_name(rr).partition(" ")
        variants = _name_variants(bf, bl)
        street, city, state = rr.choice(_STREETS), rr.choice(_CITIES), rr.choice(_STATES)
        zc, area, last4 = rr.randint(97000, 99499), rr.randint(200, 989), rr.randint(1000, 9999)
        start = date(2022, 1, 1) + timedelta(days=rr.randint(0, 500))
        for leg in range(rr.choice([3, 4])):
            pol_id += 1
            cov = round(rr.uniform(*_COVERAGE["auto"]), 2)
            end = start + timedelta(days=rr.choice([12, 24, 36]) * 30)
            prem = round(cov * rr.uniform(0.02, 0.05), 2)
            addr = f"{rr.randint(100, 9999)} {street}, {city}, {state} {zc:05d}"  # shared residence
            name = variants[leg % len(variants)]
            chain_pol.append((pol_id, name, "auto", cov, start.isoformat(), end.isoformat(), prem,
                              _national_id(rr), _email(rr, name), addr, _bank_account(rr)))
            reenroll_policies += 1
            cid += 1  # one approved, paid claim per chain policy
            incident = start + timedelta(days=rr.randint(3, 20))
            filed = incident + timedelta(days=rr.randint(0, 10))
            amount = round(cov * rr.uniform(0.1, 0.4), 2)
            approved = round(amount * rr.uniform(0.7, 0.95), 2)
            phone = f"+1-{area}-{rr.randint(200, 989)}-{last4}"  # partial overlap across the chain
            claims.append((cid, pol_id, incident.isoformat(), filed.isoformat(), "auto", amount,
                           approved, "approved", rr.choice(base_adjusters), rr.randint(1, 600), phone))
            reenroll_claims += 1
            pay0 = filed + timedelta(days=rr.randint(15, 40))
            if rr.choice([1, 2]) == 1:
                pays = [(pay0, approved)]
            else:
                a0 = round(approved * rr.uniform(0.4, 0.6), 2)
                pays = [(pay0, a0), (pay0 + timedelta(days=rr.randint(20, 40)), round(approved - a0, 2))]
            for d, amt in pays:
                pid_seq += 1
                payments.append((pid_seq, cid, d.isoformat(), amt))
            start = pays[-1][0] + timedelta(days=rr.randint(5, 45))  # next policy opens after payout
    _chunked(con, "INSERT INTO policies VALUES (?,?,?,?,?,?,?,?,?,?,?)", chain_pol)

    # decorate claim injury codes on rng salt 13 (same isolation rationale as policies above)
    rc = rng(13)
    claims = [row + (_injury(rc, row[4]),) for row in claims]

    # ── unstructured layer: first-notice-of-loss narrative + structured damage_area on EVERY claim.
    # Benign narratives agree with damage_area; the 8 rings carry copy-adjacent narratives (shared
    # skeleton, per-member make slot) whose described impact CONTRADICTS damage_area. rng salt 1110.
    nr = rng(1110)
    ring_of = {c: ri for ri, mem in enumerate(rings_members) for c in mem}
    ring_sig = [(nr.randrange(15), nr.randint(1, 4)) for _ in rings_members]  # (skeleton, area shift)
    narrated: list = []
    for row in claims:
        cid_, kind = row[0], row[4]
        prop = kind == "home" or (kind == "commercial" and nr.random() < 0.5)
        areas, imps = (_PROP_AREAS, _PROP_IMPACTS) if prop else (_VEH_AREAS, _VEH_IMPACTS)
        scenes, afters = (_PROP_SCENE, _PROP_AFTER) if prop else (_VEH_SCENE, _VEH_AFTER)
        if cid_ in ring_of:
            slot, shift = ring_sig[ring_of[cid_]]
            imp_area, imp_sent = imps[slot % len(imps)]
            dmg_area = areas[(areas.index(imp_area) + shift) % len(areas)]  # != imp_area (contradiction)
            scene, after = scenes[slot % len(scenes)], afters[slot % len(afters)]  # shared per ring
        else:
            imp_area, imp_sent = imps[nr.randrange(len(imps))]
            dmg_area = imp_area  # benign: narrative agrees with the structured field
            scene, after = nr.choice(scenes), nr.choice(afters)
        make = nr.choice(_MAKES)
        narr = (f"{scene} {imp_sent}; {after}" if prop
                else f"{make}. {scene} {imp_sent}; {after}")
        narrated.append(row + (dmg_area, narr))
    _chunked(con, "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", narrated)
    _chunked(con, "INSERT INTO claim_payments VALUES (?,?,?,?)", payments)
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("policies", "adjusters", "repair_shops", "claims", "claim_payments")}
    con.close()
    return {"db": "insurer.db", "counts": counts,
            "planted": {"duplicate_claim_pairs": dup_pairs, "staged_accident_rings": n_rings,
                        "staged_ring_claims": ring_claims, "over_coverage_payouts": over_n,
                        "anomalous_adjusters": len(anomalous),
                        "ring_narrative_claims": ring_claims,  # rings' FNOLs contradict damage_area
                        "reenrollment_chains": reenroll_chains,
                        "reenrollment_policies": reenroll_policies,
                        "reenrollment_claims": reenroll_claims}}


if __name__ == "__main__":  # ponytail: standalone self-check — regenerate + assert every plant fires
    import time
    t = time.time()
    rep = gen_insurer()
    print(rep, f"{time.time() - t:.1f}s")
    c = sqlite3.connect(str(OUT / "insurer.db"))
    dup = c.execute("""SELECT COUNT(*) FROM claims a JOIN claims b
        ON a.policy_id=b.policy_id AND a.incident_date=b.incident_date AND a.id<b.id
        WHERE ABS(a.amount_claimed-b.amount_claimed) <= 0.05*a.amount_claimed""").fetchone()[0]
    rings = c.execute("""SELECT COUNT(*) FROM (SELECT repair_shop_id,claimant_phone
        FROM claims WHERE repair_shop_id IS NOT NULL
        GROUP BY repair_shop_id,claimant_phone
        HAVING COUNT(*)>=6 AND COUNT(DISTINCT policy_id)>=6)""").fetchone()[0]
    over = c.execute("""SELECT COUNT(*) FROM (SELECT c.id FROM claims c
        JOIN policies p ON p.id=c.policy_id JOIN claim_payments cp ON cp.claim_id=c.id
        GROUP BY c.id HAVING SUM(cp.amount) > p.coverage_limit_usd)""").fetchone()[0]
    adj = c.execute("""SELECT COUNT(*) FROM (SELECT adjuster_id,
        1.0*SUM(status='approved')/SUM(status IN ('approved','denied')) AS ar
        FROM claims GROUP BY adjuster_id
        HAVING SUM(status IN ('approved','denied'))>50 AND ar>0.98)""").fetchone()[0]
    print("dup>=120:", dup, "rings==8:", rings, "over>=200:", over, "adj==6:", adj)
    assert dup >= 120 and rings == 8 and over >= 200 and adj == 6
    # new sensitive columns populated + terms authored and biting >= 4 real columns
    n_id = c.execute("SELECT COUNT(*) FROM policies WHERE policyholder_national_id LIKE '___-__-____'").fetchone()[0]
    n_inj = c.execute("SELECT COUNT(*) FROM claims WHERE injury_code <> ''").fetchone()[0]
    terms = (OUT / "terms" / "insurer_terms.md").read_text()
    refs = sum(col in terms for col in
               ("policies.policyholder_national_id", "policies.premium_bank_account",
                "policies.policyholder_email", "claims.claimant_phone", "claims.injury_code"))
    print("policies w/ nat_id:", n_id, "claims w/ injury:", n_inj, "terms col refs:", refs)
    assert n_id >= 50_000 and n_inj > 0 and refs >= 4
    # new unstructured layer: FNOL narrative + damage_area on every claim; rings carry contradictions
    narr_all = c.execute("SELECT COUNT(*) FROM claims WHERE fnol_narrative <> '' AND damage_area <> ''").fetchone()[0]
    ring_narr = c.execute("""SELECT COUNT(*) FROM claims c JOIN (SELECT repair_shop_id,claimant_phone
        FROM claims WHERE repair_shop_id IS NOT NULL GROUP BY repair_shop_id,claimant_phone
        HAVING COUNT(*)>=6 AND COUNT(DISTINCT policy_id)>=6) g
        ON c.repair_shop_id=g.repair_shop_id AND c.claimant_phone=g.claimant_phone""").fetchone()[0]
    # new reasoning layer: serial re-enrollment — residences with >=2 serial links, each a new policy
    # opened <=60d after the prior policy's payout under a DIFFERENT holder-name spelling (fuzzy
    # identity resolution + timeline reconciliation across policies↔claims↔payments, a self-join)
    reenroll = c.execute("""WITH payouts AS MATERIALIZED (
        SELECT ci.policy_id, MAX(cp.date) AS last_payout FROM claims ci
        JOIN claim_payments cp ON cp.claim_id=ci.id GROUP BY ci.policy_id),
      pol AS MATERIALIZED (SELECT p.id, p.holder_name, p.start_date,
        substr(p.policyholder_address, instr(p.policyholder_address,' ')+1) AS residence, po.last_payout
        FROM policies p LEFT JOIN payouts po ON po.policy_id=p.id),
      multi AS (SELECT residence FROM pol GROUP BY residence HAVING COUNT(*)>=2),
      links AS (SELECT a.residence FROM pol a JOIN pol b ON a.residence=b.residence AND a.id<>b.id
        WHERE a.residence IN (SELECT residence FROM multi) AND a.last_payout IS NOT NULL
          AND b.start_date > a.last_payout
          AND julianday(b.start_date)-julianday(a.last_payout) BETWEEN 0 AND 60
          AND a.holder_name<>b.holder_name)
      SELECT COUNT(*) FROM (SELECT residence FROM links GROUP BY residence HAVING COUNT(*)>=2)""").fetchone()[0]
    print("narrated claims:", narr_all, "ring-narrative claims:", ring_narr, "reenroll chains:", reenroll)
    assert narr_all == c.execute("SELECT COUNT(*) FROM claims").fetchone()[0] and ring_narr >= 48
    assert reenroll >= 8
    c.close()
    c.close()
