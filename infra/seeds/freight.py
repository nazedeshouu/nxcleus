"""Northgate Freight — synthetic freight-forwarding / logistics sandbox company (09 §2).

Net-new judge-sandbox dataset, same conventions as companies.py: one local seeded
random.Random, a fresh read-only SQLite in out/, planted patterns so good prompts find real
things. Regenerating from scratch reproduces identical counts + planted dict (09 §7 rehearsal
gate — "no hand-tuned state"). Single deterministic rng stream (rng(13)); generation order is
fixed, so two runs are byte-for-byte identical.

Plants:
 (a) ghost shipments    — 150 fully-paid invoices with no real delivery/customs trail
 (b) 3-way-match breaks — 400 invoices billed >15% over their purchase order
 (c) denied-party hits  — 30 customs declarations consigned to sanctions-adjacent names
 (d) chronically late lanes — 5 origin->destination pairs that blow past ETA by 5-15 days

Also carries synthetic sensitive-data columns for the masking demo — shipper contact + remit IBAN on
purchase_orders, consignee EORI/tax-id + contact on customs_declarations — and writes a static
"Terms of Sensitive Data Use" doc to out/terms/freight_terms.md that stage 0 distills into rules that
fire on exactly those columns.
"""
from __future__ import annotations

import sqlite3
import string
from datetime import date, timedelta
from pathlib import Path

from ._gen import SANCTIONS_ADJACENT, country, day_between, full_name, rng

OUT = Path(__file__).resolve().parent / "out"

_CO_PREFIX = ["Nexa", "Orbit", "Vertex", "Lumen", "Kestrel", "Atlas", "Cobalt", "Harbor",
              "Summit", "Pioneer", "Onyx", "Crown", "Sable", "Aurora", "Granite", "Meridian"]
_CO_SUFFIX = ["Holdings", "Systems", "Trading", "Imports", "Industries", "Global",
              "Distribution", "Wholesale", "Manufacturing", "Group"]
_CARRIER_KIND = ["Freight", "Lines", "Cargo", "Logistics", "Shipping", "Transport"]
_CURRENCIES = ["USD", "EUR", "GBP", "CNY", "AED", "JPY"]
_HS_CODES = ["8471.30", "8517.12", "2709.00", "3004.90", "6109.10", "8703.23", "9403.60",
             "0901.21", "7108.13", "8542.31", "4011.10", "1806.31"]

# ordinary lane endpoints — the planted late-lane origins below are deliberately NOT in here,
# so a chronically-late (origin,destination) pair can never collide with a normal lane.
_PORTS = ["Shanghai", "Singapore", "Rotterdam", "Hamburg", "Los Angeles", "Newark", "Dubai",
          "Mumbai", "Santos", "Antwerp", "Busan", "Hong Kong", "Felixstowe", "Valencia",
          "Genoa", "Piraeus", "Jebel Ali", "Long Beach", "Savannah", "Houston", "Ningbo",
          "Shenzhen", "Qingdao", "Colombo", "Durban", "Veracruz", "Callao", "Gdansk"]

# (d) 5 planted chronically-late lanes; unique origins guarantee these pairs don't appear elsewhere.
_LATE_LANES = [("Lagos", "Southampton"), ("Karachi", "Le Havre"), ("Chittagong", "Barcelona"),
               ("Manila", "Oakland"), ("Mombasa", "Bremen")]


# Synthetic sensitive-data formats for the masking demo. All values drawn ONLY from the local rng
# so a regenerate reproduces them byte-for-byte. These are the fields the terms doc (below) names.
_EMAIL_DOM = ["freightmail.example", "trade.example", "shipco.example", "cargonet.example"]
_AREA = [212, 415, 646, 305, 713, 206, 312, 404]


def _contact(r):  # shipper-side named individual: name + name-derived email + phone
    name = full_name(r)
    first, last = name.lower().split()
    return (name, f"{first}.{last}@{r.choice(_EMAIL_DOM)}",
            f"+1-{r.choice(_AREA)}-555-01{r.randint(0, 99):02d}")


def _entity_contact(r, entity_name):  # consignee ops mailbox + phone, slugged from the entity name
    slug = entity_name.lower().replace(" ", "").replace(".", "")
    return (f"{r.choice(['ops', 'customs', 'trade', 'clearing'])}@{slug}.example",
            f"+1-{r.choice(_AREA)}-555-01{r.randint(0, 99):02d}")


def _iban(r, cc):  # GB29NWBK60161331926819-shaped: cc + 2 check + 4 bank letters + 14 digits
    bank = "".join(r.choice(string.ascii_uppercase) for _ in range(4))
    return f"{cc}{r.randint(10, 99)}{bank}{r.randint(10**13, 10**14 - 1)}"


def _eori(r, cc):
    return f"{cc}{r.randint(10**11, 10**12 - 1)}"   # customs EORI: country + 12 digits


def _tax_id(r, cc):
    return f"{cc}{r.randint(10**8, 10**9 - 1)}"     # VAT/tax registration: country + 9 digits


def _company(r) -> str:
    return f"{r.choice(_CO_PREFIX)} {r.choice(_CO_SUFFIX)}"


# ── narrative + structural streams (rng(1310+)) — kept OFF the main rng(13) stream so every existing
#    planted count/value stays byte-for-byte identical; these only ADD a free-text column, an hs
#    reference table, a container id and 20 transshipment shipment pairs.

# (A) semantic-mismatch layer. hs_catalog maps an HS chapter (first 2 digits of the code) to what it
# actually covers, plus representative commodity phrases. A benign customs line's goods_description
# names a commodity from its OWN declared chapter; a planted line names a commodity from a DIFFERENT
# chapter — the code says one thing, the words mean another. Phrases are the join keys for the
# oracle; the LLM has to KNOW that "knitted cotton pullover" is chapter 61, not 84. No shared marker
# token: benign and planted draw the same skeletons and the same commodity vocabulary.
HS_CHAPTERS = {
    "84": ("Machinery, mechanical appliances and boilers",
           ["laptop", "notebook computer", "hydraulic pump", "industrial gearbox", "lathe",
            "conveyor roller", "turbine blade"]),
    "85": ("Electrical machinery, telecom apparatus and electronics",
           ["smartphone handset", "integrated circuit", "semiconductor wafer", "network switch",
            "copper transformer", "LED module"]),
    "27": ("Mineral fuels, mineral oils and bituminous substances",
           ["crude petroleum", "diesel gasoil", "lubricating oil", "bitumen", "liquefied propane"]),
    "30": ("Pharmaceutical products",
           ["antibiotic tablets", "insulin vials", "vaccine doses", "paracetamol capsules",
            "surgical antiseptic"]),
    "61": ("Apparel and clothing accessories, knitted or crocheted",
           ["knitted cotton pullover", "wool sweater", "knit polo shirt", "jersey cardigan",
            "knitted baby romper"]),
    "87": ("Vehicles other than railway, and parts thereof",
           ["passenger sedan", "brake caliper", "car alternator", "tyre rim assembly",
            "gearbox housing"]),
    "94": ("Furniture, bedding, lamps and lighting fittings",
           ["office swivel chair", "oak dining table", "upholstered sofa", "desk lamp",
            "bookshelf unit"]),
    "09": ("Coffee, tea, mate and spices",
           ["arabica coffee beans", "black tea leaves", "ground cinnamon", "whole peppercorns",
            "cardamom pods"]),
    "71": ("Pearls, precious stones and metals, jewellery",
           ["gold bullion bars", "loose diamonds", "silver ingots", "platinum granules",
            "gemstone necklace"]),
    "40": ("Rubber and articles of rubber",
           ["natural rubber sheet", "pneumatic tyre", "rubber gasket", "latex glove",
            "conveyor belt rubber"]),
    "18": ("Cocoa and cocoa preparations",
           ["cocoa butter", "chocolate confectionery", "cocoa powder", "cacao nibs",
            "chocolate couverture"]),
}

# >=15 paraphrase skeletons; the commodity is a slot, so a keyword search hits benign + planted alike.
_GOODS_SKELETONS = [
    "{q} pallets of {g}, commercial grade.",
    "Consignment of {g}; {q} cartons, {cond}.",
    "Container load: {g} ({q} units), {inc}.",
    "{g} packed in {q} crates for export.",
    "Mixed shipment comprising {g}, approx {q} pallets.",
    "{q}x cartons {g}, stowed and secured below deck.",
    "Bulk {g} — {q} pallets, {cond}.",
    "Full container of {g}; {q} boxes declared to customs.",
    "{g}, assorted, {q} cases, {inc}.",
    "Freight manifest: {g}. Quantity {q} pallets. {cond}.",
    "{q} crates {g}, palletised and shrink-wrapped.",
    "Shipment of {g} loaded loose, {q} bundles total.",
    "General cargo — {g}, {q} cartons on skids.",
    "{g} for wholesale distribution, {q} units.",
    "Declared goods: {g}; total {q} packages, {cond}.",
    "Palletised {g}, {q} skids, {inc}.",
    "{q} boxes of {g}, commercial invoice attached.",
    "Ocean freight of {g}; {q} pallets, gross weight noted.",
]
_GOODS_COND = ["condition on arrival to be inspected", "new and unused", "refurbished stock",
               "first quality", "subject to survey at destination", "standard export packing"]
_GOODS_INC = ["CIF terms", "FOB origin", "DAP destination", "EXW warehouse", "CFR named port"]


def _goods_desc(r, chapter):  # slot-fill one paraphrase skeleton with a commodity from `chapter`
    return r.choice(_GOODS_SKELETONS).format(
        g=r.choice(HS_CHAPTERS[chapter][1]), q=r.randint(1, 40),
        cond=r.choice(_GOODS_COND), inc=r.choice(_GOODS_INC))


# (B) transshipment layer. Leg 2's consignee is a sanctions-adjacent name with the SURNAME preserved
# but the full string altered (corp suffix / initial / swapped forename) so the exact denied-party
# screen on customs misses it — you only catch it by linking the two legs on the shared container and
# screening the FINAL leg's consignee against the watchlist surnames.
_TRANSSHIP_VIA = ["Dubai", "Singapore", "Jebel Ali"]          # innocuous intermediates (in _PORTS)
_HIGH_RISK_ORIGIN = ["Bandar Abbas", "Novorossiysk", "Latakia", "Vladivostok"]
_CORP_SUFFIX = ["Trading LLC", "Holdings", "Import Export", "Global Logistics", "& Co", "Distribution"]
_FIRST_ALT = ["Boris", "Igor", "Dmitri", "Yuri", "Katya", "Oleg", "Vera"]
_WATCH_SURNAMES = [n.split(" ", 1)[1] for n in SANCTIONS_ADJACENT]  # Sokolov, Petrov, ... Ivanov


def _alter_name(r, canonical):  # keep surname exact, mutate the rest so IN(...) exact-screen misses
    first, surname = canonical.split(" ", 1)
    style = r.randint(0, 3)
    if style == 0:
        return f"{surname} {r.choice(_CORP_SUFFIX)}"
    if style == 1:
        return f"{first[0]}. {surname}"
    if style == 2:
        return f"{first} {surname} {r.choice(_CORP_SUFFIX)}"
    return f"{r.choice(_FIRST_ALT)} {surname}"


def _insert(con, sql, rows, chunk=50000):
    for i in range(0, len(rows), chunk):
        con.executemany(sql, rows[i:i + chunk])


_TERMS = """# Northgate Freight — Terms of Sensitive Data Use

**Northgate Freight Ltd.** operates as a licensed freight forwarder and customs broker. In the course
of arranging carriage and clearing goods, we hold commercially sensitive and personal data belonging
to shippers, consignees and their authorised representatives. This document governs how that data is
classified, masked, transmitted and retained, and in particular what may cross Northgate's
infrastructure boundary into any external planning, analytics or model-assisted workflow. It is
issued under our obligations as a registered economic operator under the Union Customs Code and under
applicable data-protection and export-control law.

## Purpose

These terms exist so that trade-compliance analysis, exception review and lane reporting can be
performed on our shipment records without exposing the identifying details of the parties to a
transaction. The controlling principle is data minimisation: a party's identity, fiscal identifiers
and contact details are handled on a strict need-to-know basis and are masked or withheld before any
record leaves company-controlled systems.

## Data classification

The following fields carry elevated sensitivity and are subject to the handling rules below.

- **customs_declarations.consignee_name** — party identity on the customs entry; restricted.
- **customs_declarations.consignee_eori** — customs registration identifier (EORI); restricted, regulated identifier.
- **customs_declarations.consignee_tax_id** — national VAT / tax registration; restricted, regulated identifier.
- **customs_declarations.consignee_email** — consignee contact; personal data.
- **customs_declarations.consignee_phone** — consignee contact; personal data.
- **shipments.consignee_name** — party identity on the movement record; restricted.
- **purchase_orders.shipper_contact** — named individual acting for the shipper; personal data.
- **purchase_orders.shipper_email** — shipper contact; personal data.
- **purchase_orders.shipper_phone** — shipper contact; personal data.
- **purchase_orders.remit_iban** — supplier settlement account number; confidential financial data.

## Handling rules

- Customs and fiscal identifiers in **customs_declarations.consignee_eori** and **customs_declarations.consignee_tax_id** are regulated identifiers and must never leave Northgate infrastructure; they may not appear in any external planning brief.
- Party names in **customs_declarations.consignee_name** and **shipments.consignee_name** may appear in external planning materials only in pseudonymised form; the underlying name must be withheld or replaced with a stable reference token.
- Settlement account numbers in **purchase_orders.remit_iban** must be masked to the last four characters before any external transmission; the full account number is never disclosed outside the finance function.
- Contact details in **customs_declarations.consignee_email**, **customs_declarations.consignee_phone**, **purchase_orders.shipper_email** and **purchase_orders.shipper_phone** are personal data and must be redacted from any dataset shared with an external processor unless a lawful basis and a data-processing agreement are in place.
- Named shipper representatives in **purchase_orders.shipper_contact** must be minimised: external planning references a role or reference token, never the individual's name.
- Denied-party and sanctions screening against **customs_declarations.consignee_name** must be carried out inside Northgate's environment; consignee identity may be sent to an external screening provider only under contract and only for that purpose.
- The personal and fiscal data described above must be processed and stored within the EU/EEA; onward transfer to a third country requires an approved transfer mechanism.
- Records carrying the identifiers and contact details above are retained no longer than required for customs and audit obligations and are then deleted or irreversibly anonymised.
- Any external analytics or model-assisted review must operate only on records from which the restricted identifiers have been removed or masked in accordance with the rules above.

## Note

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation boundary.
"""


def gen_freight() -> dict:
    r = rng(13)
    path = OUT / "freight.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(str(path))
    con.executescript(
        """
        CREATE TABLE carriers (id INTEGER PRIMARY KEY, name TEXT, mode TEXT, home_country TEXT);
        CREATE TABLE purchase_orders (id INTEGER PRIMARY KEY, buyer TEXT, supplier TEXT,
            shipper_contact TEXT, shipper_email TEXT, shipper_phone TEXT, remit_iban TEXT,
            amount_usd REAL, currency TEXT, created TEXT);
        CREATE TABLE shipments (id INTEGER PRIMARY KEY, po_id INTEGER, carrier_id INTEGER,
            origin TEXT, destination TEXT, ship_ts TEXT, eta TEXT, delivered_ts TEXT,
            consignee_name TEXT, weight_kg REAL, container_id TEXT);
        CREATE TABLE invoices (id INTEGER PRIMARY KEY, po_id INTEGER, shipment_id INTEGER,
            amount_usd REAL, issued TEXT, paid TEXT);
        CREATE TABLE customs_declarations (id INTEGER PRIMARY KEY, shipment_id INTEGER,
            consignee_name TEXT, consignee_eori TEXT, consignee_tax_id TEXT,
            consignee_email TEXT, consignee_phone TEXT,
            hs_code TEXT, declared_value_usd REAL, country TEXT, goods_description TEXT);
        CREATE TABLE hs_catalog (chapter TEXT, description TEXT, keyword TEXT);
        """
    )

    # additive streams (rng(1310+)) — narrative text, mismatch picks, consignee noise, transshipment,
    # container ids — all independent of rng(13) so existing plants are byte-for-byte unchanged.
    r_txt, r_cons, r_pp, r_cont = rng(1310), rng(1311), rng(1313), rng(1314)

    # hs_catalog: chapter -> what it covers + representative commodity keywords (the oracle's lexicon)
    _insert(con, "INSERT INTO hs_catalog VALUES (?,?,?)",
            [(ch, title, kw) for ch, (title, kws) in HS_CHAPTERS.items() for kw in kws])

    # ── carriers (250)
    carriers = [(i, f"{r.choice(_CO_PREFIX)} {r.choice(_CARRIER_KIND)}",
                 r.choice(["road", "sea", "air"]), country(r)) for i in range(1, 251)]
    _insert(con, "INSERT INTO carriers VALUES (?,?,?,?)", carriers)

    # ── purchase_orders (70k); keep USD amounts for 3-way match + invoice sizing
    N_PO = 70000
    po_start, po_end = date(2022, 1, 1), date(2026, 6, 1)
    po_amount = [0.0] * (N_PO + 1)
    pos = []
    for i in range(1, N_PO + 1):
        amt = round(r.uniform(2_000, 480_000), 2)
        po_amount[i] = amt
        s_name, s_email, s_phone = _contact(r)         # shipper-side contact PII
        pos.append((i, _company(r), _company(r), s_name, s_email, s_phone, _iban(r, country(r)),
                    amt, r.choice(_CURRENCIES), day_between(r, po_start, po_end).isoformat()))
    _insert(con, "INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?,?,?,?)", pos)
    del pos

    # ── shipments: normal, then planted late lanes, then the ghost block LAST (contiguous ids so
    #    customs can reference every non-ghost id and never touch a ghost — that "no customs" gap
    #    is exactly what plant (a) keys on).
    s_start, s_end = date(2022, 1, 1), date(2026, 6, 1)
    N_NORMAL = 238000
    delivered = []            # (ship_id, po_id) — only delivered shipments back real invoices
    ships = []
    sid = 1
    for _ in range(N_NORMAL):
        po = r.randint(1, N_PO)
        origin, dest = r.sample(_PORTS, 2)
        ship_ts = day_between(r, s_start, s_end)
        eta = ship_ts + timedelta(days=r.randint(3, 45))
        if r.random() < 0.80:                       # 80% delivered, on/around ETA (avg lateness ~0)
            dts_s = (eta + timedelta(days=r.randint(-3, 3))).isoformat()
            delivered.append((sid, po))
        else:
            dts_s = None                            # 20% still in transit
        carrier = r.randint(1, 250)                 # (rng13 order preserved: carrier, consignee, wt)
        cons = _company(r)
        weight = round(r.uniform(20, 26000), 1)
        if r_cons.random() < 0.02:                  # ~2% person consignees (some carry watchlist
            cons = full_name(r_cons)                # surnames) — so a name screen alone is imprecise
        ships.append((sid, po, carrier, origin, dest, ship_ts.isoformat(),
                      eta.isoformat(), dts_s, cons, weight))
        sid += 1

    # (d) chronically late lanes — 300 shipments/lane, each delivered 5-15 days past ETA
    for origin, dest in _LATE_LANES:
        for _ in range(300):
            po = r.randint(1, N_PO)
            ship_ts = day_between(r, s_start, s_end)
            eta = ship_ts + timedelta(days=r.randint(10, 40))
            dts = eta + timedelta(days=r.randint(5, 15))
            delivered.append((sid, po))
            ships.append((sid, po, r.randint(1, 250), origin, dest, ship_ts.isoformat(),
                          eta.isoformat(), dts.isoformat(), _company(r), round(r.uniform(20, 26000), 1)))
            sid += 1
    n_non_ghost = sid - 1     # customs_declarations only ever reference ids <= this

    # (a) ghost shipments — never delivered, never customs-cleared; each gets one paid invoice below
    ghost_ships = []          # (ship_id, po_id)
    for _ in range(100):
        po = r.randint(1, N_PO)
        ship_ts = day_between(r, date(2025, 6, 1), s_end)
        eta = ship_ts + timedelta(days=r.randint(3, 45))
        ghost_ships.append((sid, po))
        ships.append((sid, po, r.randint(1, 250), r.choice(_PORTS), r.choice(_PORTS),
                      ship_ts.isoformat(), eta.isoformat(), None, _company(r),
                      round(r.uniform(20, 26000), 1)))
        sid += 1

    # (e) two-leg transshipment — 20 shipment PAIRS sharing a container (assigned below). Leg 1 ends
    #     at an innocuous intermediate; leg 2 continues from there to a final destination consigned to
    #     an altered sanctions-adjacent name. Appended after n_non_ghost, so no customs/invoice ever
    #     references them — the risk lives only in the container link + a final-leg name screen.
    transship_pairs = []                                    # (leg1_id, leg2_id)
    for k in range(20):
        via = r_pp.choice(_TRANSSHIP_VIA)
        st1 = day_between(r_pp, s_start, s_end)
        e1 = st1 + timedelta(days=r_pp.randint(5, 20))
        d1 = (e1 + timedelta(days=r_pp.randint(-2, 2))).isoformat()
        ships.append((sid, r_pp.randint(1, N_PO), r_pp.randint(1, 250), r_pp.choice(_HIGH_RISK_ORIGIN),
                      via, st1.isoformat(), e1.isoformat(), d1, _company(r_pp),
                      round(r_pp.uniform(20, 26000), 1)))
        leg1 = sid; sid += 1
        st2 = e1 + timedelta(days=r_pp.randint(1, 6))
        e2 = st2 + timedelta(days=r_pp.randint(5, 20))
        d2 = (e2 + timedelta(days=r_pp.randint(-2, 2))).isoformat()
        ships.append((sid, r_pp.randint(1, N_PO), r_pp.randint(1, 250), via, r_pp.choice(_PORTS),
                      st2.isoformat(), e2.isoformat(), d2,
                      _alter_name(r_pp, SANCTIONS_ADJACENT[k % len(SANCTIONS_ADJACENT)]),
                      round(r_pp.uniform(20, 26000), 1)))
        leg2 = sid; sid += 1
        transship_pairs.append((leg1, leg2))

    # container ids: ~2500 benign shared pairs (join noise) + unique ids for the rest; the 20 planted
    # legs share their own ids. Benign pairs almost never satisfy the leg1.dest==leg2.origin continuity
    # filter, so the self-join stays precise.
    planted_sids = {s for pair in transship_pairs for s in pair}
    pool = [row[0] for row in ships if row[0] not in planted_sids]
    r_cont.shuffle(pool)
    cmap = {}
    for i in range(0, 5000, 2):
        cmap[pool[i]] = cmap[pool[i + 1]] = f"CTN-{i // 2:06d}"
    for s in pool[5000:]:
        cmap[s] = f"CTN-U{s:07d}"
    for k, (leg1, leg2) in enumerate(transship_pairs):
        cmap[leg1] = cmap[leg2] = f"CTN-X{k:04d}"
    _insert(con, "INSERT INTO shipments VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [row + (cmap[row[0]],) for row in ships])
    del ships

    # ── invoices (80k)
    i_end = date(2026, 7, 1)

    def _issue_paid(pay: bool):
        issued = day_between(r, po_start, date(2026, 6, 15))
        paid = day_between(r, issued, i_end).isoformat() if pay else None
        return issued.isoformat(), paid

    inv = []
    iid = 1
    for _ in range(79450):                          # normal: billed 0.85-1.10x PO -> never a break
        s_id, po = r.choice(delivered)
        amt = round(po_amount[po] * r.uniform(0.85, 1.10), 2)
        issued, paid = _issue_paid(r.random() < 0.7)
        inv.append((iid, po, s_id, amt, issued, paid)); iid += 1

    for _ in range(400):                            # (b) 3-way-match breaks: billed 1.20-1.80x PO
        s_id, po = r.choice(delivered)
        amt = round(po_amount[po] * r.uniform(1.20, 1.80), 2)
        issued, paid = _issue_paid(True)
        inv.append((iid, po, s_id, amt, issued, paid)); iid += 1

    for s_id, po in ghost_ships:                    # (a) 100 ghosts pointing at undelivered/no-customs
        amt = round(po_amount[po] * r.uniform(0.90, 1.05), 2)
        issued, paid = _issue_paid(True)
        inv.append((iid, po, s_id, amt, issued, paid)); iid += 1
    for _ in range(50):                             # (a) 50 ghosts with no shipment at all, still paid
        po = r.randint(1, N_PO)
        amt = round(po_amount[po] * r.uniform(0.90, 1.05), 2)
        issued, paid = _issue_paid(True)
        inv.append((iid, po, None, amt, issued, paid)); iid += 1
    _insert(con, "INSERT INTO invoices VALUES (?,?,?,?,?,?)", inv)
    del inv

    # ── customs_declarations (40k) — reference non-ghost shipments only. Every row now carries a
    #    free-text goods_description; (f) 100 scattered rows describe a commodity from a DIFFERENT
    #    chapter than their declared hs_code — a semantic contradiction, not a keyword.
    mism_idx = set(rng(1312).sample(range(39970), 100))
    cust = []
    cid = 1
    for j in range(39970):                          # normal consignees are companies (never a person)
        cc, name = country(r), _company(r)
        email, phone = _entity_contact(r, name)
        row = (cid, r.randint(1, n_non_ghost), name, _eori(r, cc), _tax_id(r, cc),
               email, phone, r.choice(_HS_CODES), round(r.uniform(500, 500_000), 2), cc)
        decl_ch = row[7][:2]
        ch = r_txt.choice([c for c in HS_CHAPTERS if c != decl_ch]) if j in mism_idx else decl_ch
        cust.append(row + (_goods_desc(r_txt, ch),)); cid += 1
    for k in range(30):                             # (c) denied-party consignees (sanctions-adjacent)
        cc = country(r)
        name = SANCTIONS_ADJACENT[k % len(SANCTIONS_ADJACENT)]
        email, phone = _entity_contact(r, name)
        row = (cid, r.randint(1, n_non_ghost), name, _eori(r, cc), _tax_id(r, cc),
               email, phone, r.choice(_HS_CODES), round(r.uniform(500, 500_000), 2), cc)
        cust.append(row + (_goods_desc(r_txt, row[7][:2]),)); cid += 1
    _insert(con, "INSERT INTO customs_declarations VALUES (?,?,?,?,?,?,?,?,?,?,?)", cust)
    del cust
    con.execute("CREATE INDEX idx_ship_container ON shipments(container_id)")  # self-join on legs

    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("carriers", "purchase_orders", "shipments", "invoices",
                        "customs_declarations", "hs_catalog")}
    con.close()

    terms_dir = OUT / "terms"
    terms_dir.mkdir(parents=True, exist_ok=True)
    (terms_dir / "freight_terms.md").write_text(_TERMS, encoding="utf-8")

    return {"db": "freight.db", "counts": counts, "terms": "terms/freight_terms.md",
            "planted": {"ghost_shipment_invoices": 150, "three_way_match_breaks": 400,
                        "denied_party_customs": 30, "chronically_late_lanes": 5,
                        "hs_code_mismatch_declarations": 100, "transshipment_pairs": 20}}


_EV_MISMATCH = """
WITH tagged AS (
  SELECT c.id AS declaration_id, c.hs_code, substr(c.hs_code,1,2) AS declared_chapter,
         c.goods_description,
         (SELECT h.chapter FROM hs_catalog h
          WHERE c.goods_description LIKE '%'||h.keyword||'%' LIMIT 1) AS described_chapter
  FROM customs_declarations c)
SELECT declaration_id, hs_code, declared_chapter, described_chapter, goods_description
FROM tagged
WHERE described_chapter IS NOT NULL AND described_chapter <> declared_chapter
ORDER BY declaration_id
"""
_EV_TRANSSHIP = """
WITH watch(surname) AS (VALUES ('Sokolov'),('Petrov'),('Volkov'),('Popova'),('Marchenko'),('Ivanov'))
SELECT s1.container_id, s1.id AS leg1_id, s2.id AS leg2_id, s1.origin AS leg1_origin,
       s1.destination AS transship_via, s2.destination AS final_dest, s2.consignee_name
FROM shipments s1
JOIN shipments s2 ON s1.container_id = s2.container_id AND s1.id < s2.id
                 AND s1.destination = s2.origin
JOIN watch w ON s2.consignee_name LIKE '%'||w.surname||'%'
WHERE s1.destination IN ('Dubai','Singapore','Jebel Ali')
ORDER BY s1.container_id
"""


def _selfcheck():  # ponytail: one runnable check — regen + both oracles + keyword-collision guard
    import itertools
    kws = [(ch, kw) for ch, (_, kws) in HS_CHAPTERS.items() for kw in kws]
    for (ca, a), (cb, b) in itertools.permutations(kws, 2):  # no cross-chapter substring collisions
        assert not (ca != cb and a in b), f"keyword collision: {a!r}({ca}) inside {b!r}({cb})"
    con = sqlite3.connect(str(OUT / "freight.db"))
    mis = len(con.execute(_EV_MISMATCH).fetchall())
    tr = len(con.execute(_EV_TRANSSHIP).fetchall())
    con.close()
    assert mis >= 90, f"hs mismatch oracle got {mis}"
    assert tr >= 18, f"transshipment oracle got {tr}"
    print(f"selfcheck OK — hs_mismatch={mis}, transshipment={tr}")


if __name__ == "__main__":
    import time
    t = time.time()
    print(gen_freight())
    print(f"{time.time() - t:.1f}s")
    _selfcheck()
