"""Ashford Mercantile Exchange — Demo 2 (Sovereign Surveillance) seed kit (09 §5).

A mid-size securities venue: instruments + trader accounts (some owners hold multiple accounts, so
wash trades are real), position limits, and a large order/execution blotter. Planted market-abuse
sequences fire *deterministically* under plain SQL so the surveillance prompts always find real
things — never canned outputs, only planted inputs (track rule anchor). Fixed RNG seed (rng(10)) →
regenerate byte-for-byte (rehearsal gate 09 §7).

Planted: (a) spoofing bursts, (b) wash-trade pairs (same owner, two accounts), (c) marking-the-close
month-end ramps, (d) position-limit breaches. Each is discoverable with the matching evidence query.

Run via scripts/seed.py (or standalone). Output: infra/seeds/out/exchange.db.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from ._gen import full_name, rng

OUT = Path(__file__).resolve().parent / "out"

_ASSET_CLASSES = ["equity", "etf", "bond", "future", "option"]
_TICKS = [0.01, 0.05, 0.1, 0.25]
_LOTS = [1, 10, 100]
_FIRMS = ["Northwind Capital", "Aldergate Securities", "Bramwell & Co", "Calderon Partners",
          "Drayton Markets", "Everstone Trading", "Fenwick Global", "Granby Asset Mgmt",
          "Holloway Brokers", "Ironwood Capital", "Juniper Securities", "Kestrel Trading",
          "Larkspur Partners", "Marlowe & Finch", "Oakhurst Capital", "Pemberton Markets"]
_CORP = ["Holdings", "Industries", "Resources", "Technologies", "Financial", "Energy", "Materials",
         "Pharma", "Logistics", "Networks"]

# Sensitive-field vocab for the masking/policy-distillation demo (Terms of Sensitive Data Use).
# All synthetic: national-ID/tax-ID shaped strings, 555 fictional phone exchange, .example emails,
# GB-shaped IBANs (never real routable numbers). Drawn from a *dedicated* stream (rs = rng(16)) so
# the market-abuse plants on the main r stream stay byte-identical.
_AREAS = ["212", "415", "312", "617", "305", "206", "713", "202", "646", "628"]
_IBAN_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def _firm_slug(firm: str) -> str:
    return firm.lower().replace(" & ", "-").replace(" ", "-")


def _pii(rr, owner: str, firm: str) -> tuple[str, str, str, str]:
    """(owner_tax_id, contact_email, contact_phone, settlement_iban) — one identity per owner."""
    tax = f"{rr.randint(100, 899):03d}-{rr.randint(10, 99):02d}-{rr.randint(1000, 9999):04d}"
    email = f"{owner.lower().replace(' ', '.')}@{_firm_slug(firm)}.example"
    phone = f"+1-{rr.choice(_AREAS)}-555-{rr.randint(1000, 9999)}"
    bank = "".join(rr.choice(_IBAN_LETTERS) for _ in range(4))
    iban = f"GB{rr.randint(10, 99):02d}{bank}{rr.randint(0, 99_999_999_999_999):014d}"
    return tax, email, phone, iban


_TERMS = """# Ashford Mercantile Exchange — Terms of Sensitive Data Use

Ashford Mercantile Exchange ("Ashford", "the Exchange") operates a regulated multi-asset trading \
venue. This document sets out the mandatory controls governing sensitive data held in the Exchange's \
account and surveillance systems. Its purpose is to protect **account-owner identity** and the \
confidentiality of pre-trade and in-flight **order flow**, and to ensure that no material \
non-public information (MNPI) or personally identifying account data is disclosed outside \
Exchange-controlled infrastructure without the masking and authorization that market-abuse \
regulation requires.

The Exchange is subject to market-abuse and market-conduct obligations (MAR-equivalent and \
CFTC/Dodd-Frank supervisory regimes). Account-owner identifiers, contact details, settlement \
instructions, and un-anonymized order and execution flow are all regulated sensitive data. Any \
external processing — including automated planning, drafting, or model-assisted analysis — must \
operate on masked or pseudonymized inputs unless a documented, residency-bound exception applies.

## Data classification

The following fields are classified sensitive and are subject to the handling rules below.

- **accounts.owner_name** — Legal name of the account owner. Class: Confidential — personal identifier.
- **accounts.owner_tax_id** — National tax / identification number of the beneficial owner. Class: \
Restricted — national identifier.
- **accounts.contact_email** — Owner contact email. Class: Confidential — personal contact.
- **accounts.contact_phone** — Owner contact telephone number. Class: Confidential — personal contact.
- **accounts.settlement_iban** — Settlement account number (IBAN) for the trading account. Class: \
Restricted — financial account number.
- **accounts.firm** — Clearing / introducing firm affiliation. Class: Internal — commercially sensitive.
- **orders.account_id** — Links order flow to an identified account owner. Class: Restricted when \
joined to owner identity — MNPI / order-flow confidentiality.
- **orders.price**, **orders.qty**, **orders.ts** — Terms and timing of a working order. Class: \
Confidential — order-flow / MNPI while the order is live.

## Handling rules

- Account-owner national identifiers in **accounts.owner_tax_id** must never leave Exchange \
infrastructure, in whole or in part, and must not appear in any external planning brief, prompt, or \
model context.
- Settlement account numbers in **accounts.settlement_iban** must be masked to the last four \
characters before any external transmission; the full IBAN may be processed only inside \
Exchange-controlled systems.
- Owner contact details in **accounts.contact_email** and **accounts.contact_phone** must be \
redacted from any material shared with an external processor; where a contact reference is \
unavoidable it must be pseudonymized.
- Account-owner names in **accounts.owner_name** may appear in external surveillance or planning \
materials only in pseudonymized form (for example a stable owner token), never as the cleartext \
legal name.
- Order-flow terms in **orders.price**, **orders.qty** and **orders.ts** for any working or \
unexecuted order constitute material non-public information and must not be transmitted outside the \
Exchange until the order is filled, cancelled, or otherwise public.
- Any linkage of **orders.account_id** to account-owner identity is MNPI and must be broken — owner \
fields dropped or tokenized — before order or execution data is sent to an external model.
- All sensitive fields in the **accounts** table must remain resident on Exchange-controlled \
infrastructure within the venue's home jurisdiction; cross-border replication of owner identity or \
settlement data is prohibited without a documented residency exception.
- Sensitive account-owner and order-flow records must be retained only for the statutory \
market-abuse record-keeping period and then securely destroyed; no external copy may be retained \
beyond the life of the specific authorized task.
- Surveillance findings derived from sensitive data (spoofing, wash-trade, marking-the-close and \
position-limit results) must reference accounts by pseudonymized owner token, not by \
**accounts.owner_name** or **accounts.owner_tax_id**, when shared outside the surveillance team.

## Note

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation \
boundary.
"""


def _write_terms() -> None:
    d = OUT / "terms"
    d.mkdir(parents=True, exist_ok=True)
    (d / "exchange_terms.md").write_text(_TERMS)


def _fresh_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return sqlite3.connect(str(path))


def _round_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 4)


def _month_ends(start: date, end: date) -> list[tuple[int, str]]:
    """(day_offset, 'YYYY-MM') for the last calendar day of every month inside [start, end]."""
    out, y, m = [], start.year, start.month
    while True:
        nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        last = nxt - timedelta(days=1)
        if last > end:
            break
        if last >= start:
            out.append(((last - start).days, f"{y:04d}-{m:02d}"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# ── clearing references + concert-party groups (reasoning scenario) ────────────────────────────────
# Every account carries a clearing_ref "<PFX>-<serial>"; a PFX identifies a clearing member / omnibus
# and is shared by a handful of accounts, so shared prefixes (even across different owners) are
# ordinary. Three planted concert-party groups share a PFX like any other — the ONLY tell is that
# their COMBINED net position in one instrument breaches the cap while each member sits under it.
_PFX_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1 — looks like a real clearing code


def _assign_clearing(accounts: list[tuple], limits: dict[int, int]) -> tuple[dict[int, str], list]:
    """Return (account_id -> clearing_ref, concert_groups). Uses a dedicated rng(1012) stream so the
    r/rs market-abuse plants stay byte-identical. concert_groups = [(pfx, instrument_id, [member_ids],
    per_member_net)]."""
    rc = rng(1012)

    def mk_pfx() -> str:
        return "".join(rc.choice(_PFX_CHARS) for _ in range(4))

    seen: set[str] = set()
    prefixes: list[str] = []
    while len(prefixes) < 280:  # ~5 accounts share each PFX → shared prefixes are the norm, not a tell
        p = mk_pfx()
        if p not in seen:
            seen.add(p)
            prefixes.append(p)
    ref = {row[0]: f"{rc.choice(prefixes)}-{rc.randint(100000, 999999):06d}" for row in accounts}

    owner_by_id = {row[0]: row[1] for row in accounts}
    pool = [row[0] for row in accounts if row[0] >= 130]  # avoid wash-paired ids 1..120
    rc.shuffle(pool)
    cursor, used_ins, concert_groups = 0, set(), []
    for size, mult in ((4, 2.3), (5, 2.6), (6, 2.8)):  # each member < cap; group net = mult x cap
        members, owners = [], set()
        while len(members) < size and cursor < len(pool):
            aid = pool[cursor]
            cursor += 1
            if owner_by_id[aid] not in owners:  # distinct owners → real concert party, not one person
                owners.add(owner_by_id[aid])
                members.append(aid)
        while True:
            ins = rc.randint(1, 300)
            if ins not in used_ins:
                used_ins.add(ins)
                break
        per_member = int(mult * limits[ins] / size)  # <= 0.575 x cap → every member stays under
        while True:
            p = mk_pfx()
            if p not in seen:  # fresh PFX, indistinguishable from the benign pool
                seen.add(p)
                break
        for aid in members:
            ref[aid] = f"{p}-{rc.randint(100000, 999999):06d}"
        concert_groups.append((p, ins, members, per_member))
    return ref, concert_groups


# ── desk chatter (unstructured scenario) ───────────────────────────────────────────────────────────
# Benign and coordination messages draw from overlapping lexicons (size/show/depth/wall/heavy/look/
# bid/pull/lean/book/floor/print/stack/build/flash/chase...) so no keyword isolates the planted set.
# The planted signal is MEANING: intent to post orders they will cancel to fake book pressure while
# the real trade is the other way — never surveillance vocabulary ("spoof"/"fake"/"manipulate").
_BENIGN = [
    "done {qty} {sym} on the {side}, good print",
    "got filled {qty} in {sym}, {side} side cleared clean",
    "had to pull my {side} in {sym}, got done elsewhere",
    "{sym} printed at {px}, took {qty} on the {side}",
    "working {qty} {sym}, only half done so far",
    "pulled the {side} order in {sym}, price ran away from me",
    "showing a bid in {sym}, real interest, {qty} to buy",
    "put up {qty} on the {side} in {sym}, genuine size looking to trade",
    "stacked some real {side} in {sym}, {qty} that wants to trade",
    "building a position in {sym} on the {side}, adding slowly",
    "{sym} feels thin up here, not much depth on the {side}",
    "book's two-sided in {sym}, plenty of size both ways",
    "there's a wall of {side} in {sym}, real supply sitting there",
    "{sym} looks heavy on the {side}, someone's a genuine seller",
    "who's showing size in {sym}? need to get a block done",
    "{sym} is bid well, buyers leaning in on real size",
    "how does {sym} look to you, deep enough to work a block?",
    "market's leaning {side} in {sym}, decent paper around",
    "quick flash of size hit {sym} then it settled, all real flow",
    "buyers chasing {sym} higher, genuine demand up here",
    "floor's holding in {sym}, buyers keep stepping up for real",
    "watch the limit on {sym}, we're close to the cap on the {side}",
    "trimmed {sym} to stay under the line before close",
    "risk wants us flatter on {sym} by the bell",
    "we're near the position cap in {sym}, ease off the {side}",
    "squared up {sym}, back under the cap now",
    "{sym} moved my way, took size on the {side}",
    "had to step off {sym}, book got too thin to work",
    "{sym} a bit one-sided today, all buyers up here",
    "that {side} in {sym} wasn't meant to fill so fast, oh well",
    "sold my {sym} before it turned, lucky timing",
    "took the {side} in {sym} before it ran, decent entry",
    "offered {sym} but none of it traded, quiet out there",
    "left a {side} in {sym}, not carrying any of it overnight",
    "grabbing lunch, back around {t}",
    "coffee run — want anything from downstairs?",
    "stepping out for {t}, cover my {sym} order?",
    "who's in tomorrow, need someone on the {sym} book",
    # Innocent chatter that deliberately reuses the coordination lexicon PHRASE-for-phrase, so no
    # single keyword/LIKE isolates the planted set — the tell is meaning-in-context, not any phrase.
    "{sym} finally ticks my way, glad I sat on the {side}",
    "{sym} reads busy today, decent two-way paper on the {side}",
    "left a small {side} in {sym}, won't sit long at this level",
    "half the board in {sym} is just quotes for show pre-open",
    "phantom depth in {sym} on the print, none of it's real down here",
    "that block in {sym} was meant to trade at the open, missed the window",
    "took {qty} {sym} and it came straight back off, choppy tape",
    "had to step off the moment {sym} gapped, couldn't get filled",
    "grab {sym} before it prints higher, momentum on the {side}",
    "lift {sym} before it trades through the {side}, offers thinning out",
    "cancel anything in {sym} you don't want done before the auction",
    "the real one on the {side} in {sym} finally filled, good size",
    "refresh our {sym} quote before they hit the stale one",
    "solid {sym} numbers, that'll get them leaning our way",
    "don't lean on the book in {sym}, too thin to trust up here",
    "pull your {side} in {sym} before the auction, re-enter after",
    "pull it once you're done in {sym}, don't leave it working",
    "pull the lot in {sym} at the bell, going flat overnight",
    "clear it before the close in {sym}, risk wants us square",
    "that floor in {sym} isn't really there, just resting bids thinning",
]
_INTENT = [
    "put some size up top on {sym}, let them lean in — none of it's meant to trade, I'll pull before it does",
    "show depth on the {side} in {sym} for a minute, then pull it once they start to move",
    "let's make {sym} look heavy on the {side}, none of it's real, we're not doing any of it",
    "stack a few big {side} orders in {sym} to move them — my real interest is the {opp}",
    "hold the {side} up in {sym} so it ticks my way, pull the lot before it prints",
    "give {sym} a floor that isn't really there, step off the moment it fills",
    "show the {side} in {sym} big to get them leaning, pull it before they hit",
    "build a wall on {sym} for show — I'm actually working the {opp} the whole time",
    "lean on the book in {sym} with size you don't want done, then lift the {opp}",
    "keep {sym} looking bid, pull it the second real size shows up",
    "put up a couple of big {side} orders in {sym}, they're coming straight back off",
    "let {sym} look bid into the print, I'm not carrying any of it",
    "make the {side} in {sym} look deep, we're out before it trades through",
    "show them a bid in {sym} that won't sit, I do the real one on the {opp}",
    "size up the {side} in {sym} so it reads busy, then clear it before anyone hits",
    "keep {sym} one-sided for a minute, the real order goes the {opp} way",
    "flash some size on the {side} in {sym}, pull it once they chase",
]
_OPEN = ["", "", "", "hey — ", "quick one, ", "when you get a sec, ", "listen, ", "fyi ", "ok so "]
_CLOSE = ["", "", "", " cheers", " ok?", " ping me", " you good?", " lmk", " thx"]


def _slots(rr, sym: str, side: str | None = None) -> dict:
    s = side if side is not None else rr.choice(["bid", "offer"])
    return {"sym": sym, "side": s, "opp": "offer" if s == "bid" else "bid",
            "qty": rr.choice([f"{rr.randint(2, 40)}k", f"{rr.randint(1, 9)} lot",
                              f"{rr.randint(2, 25)}00"]),
            "px": f"{rr.randint(5, 500)}.{rr.randint(0, 99):02d}",
            "t": rr.choice(["1", "half an hour", "20", "2", "10 min", "1.30"])}


def _wrap(rr, core: str) -> str:
    return f"{rr.choice(_OPEN)}{core}{rr.choice(_CLOSE)}"


def _benign_body(rr, syms: list[str]) -> str:
    return _wrap(rr, rr.choice(_BENIGN).format(**_slots(rr, rr.choice(syms))))


def _intent_body(rr, sym: str, order_side: str) -> str:
    side = "bid" if order_side == "buy" else "offer"
    return _wrap(rr, rr.choice(_INTENT).format(**_slots(rr, sym, side)))


def gen_exchange() -> dict:
    r = rng(10)
    rs = rng(16)  # dedicated stream for sensitive owner-identity fields — keeps r's plants byte-identical
    con = _fresh_db(OUT / "exchange.db")
    _write_terms()
    con.executescript(
        """
        CREATE TABLE instruments (id INTEGER PRIMARY KEY, symbol TEXT, name TEXT,
            asset_class TEXT, tick_size REAL, lot_size INTEGER);
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, owner_name TEXT, firm TEXT,
            owner_tax_id TEXT, contact_email TEXT, contact_phone TEXT, settlement_iban TEXT,
            clearing_ref TEXT);
        CREATE TABLE position_limits (id INTEGER PRIMARY KEY, instrument_id INTEGER,
            max_net_qty INTEGER);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, ts TEXT, account_id INTEGER,
            instrument_id INTEGER, side TEXT, price REAL, qty INTEGER, status TEXT,
            cancel_ts TEXT);
        CREATE TABLE executions (id INTEGER PRIMARY KEY, order_id INTEGER, ts TEXT,
            price REAL, qty INTEGER);
        CREATE TABLE comms (id INTEGER PRIMARY KEY, ts TEXT, from_account_id INTEGER,
            to_account_id INTEGER, body TEXT);
        """
    )

    start, end_d = date(2022, 1, 1), date(2026, 6, 30)
    total_days = (end_d - start).days
    day_strs = [(start + timedelta(days=k)).isoformat() for k in range(total_days + 1)]

    def fmt(day_idx: int, secs: int) -> str:  # secs may run a little past 16:00 (cancel latency)
        return f"{day_strs[day_idx]} {secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"

    # ── instruments (300): each carries an in-memory (base_price, tick) + a position limit
    instr_px: dict[int, tuple[float, float]] = {}
    limits: dict[int, int] = {}
    instruments, seen_sym = [], set()
    vowels, cons = "AEIOU", "BCDFGHJKLMNPRSTVWXZ"
    for i in range(1, 301):
        while True:
            sym = r.choice(cons) + r.choice(vowels) + r.choice(cons) + (r.choice(cons) if r.random() < 0.5 else "")
            if sym not in seen_sym:
                seen_sym.add(sym)
                break
        tick = r.choice(_TICKS)
        lot = r.choice(_LOTS)
        base = round(r.uniform(5, 500), 2)
        instr_px[i] = (base, tick)
        limits[i] = r.choice([50_000, 80_000, 120_000, 200_000])
        instruments.append((i, sym, f"{sym} {r.choice(_CORP)}", r.choice(_ASSET_CLASSES), tick, lot))
    con.executemany("INSERT INTO instruments VALUES (?,?,?,?,?,?)", instruments)
    con.executemany("INSERT INTO position_limits VALUES (?,?,?)",
                    [(i, i, limits[i]) for i in range(1, 301)])

    # ── accounts (1500): first 60 owners each hold TWO accounts (1..120) → real wash-trade linkage;
    #     remaining accounts get individual owners. Each carries synthetic owner-identity PII
    #     (tax id, email, phone, settlement IBAN) for the masking demo; a paired owner's two accounts
    #     share ONE identity — the beneficial-owner link a wash trader would try to hide.
    accounts = []
    for k in range(60):
        owner, firm = full_name(r), r.choice(_FIRMS)
        pii = _pii(rs, owner, firm)
        accounts.append((2 * k + 1, owner, firm, *pii))
        accounts.append((2 * k + 2, owner, firm, *pii))
    for i in range(121, 1501):
        owner, firm = full_name(r), r.choice(_FIRMS)
        accounts.append((i, owner, firm, *_pii(rs, owner, firm)))
    clearing_ref, concert_groups = _assign_clearing(accounts, limits)
    con.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?)",
                    [row + (clearing_ref[row[0]],) for row in accounts])

    # ── orders / executions: stream in 50k batches, single commit at the end (memory-sane)
    order_rows: list[tuple] = []
    exec_rows: list[tuple] = []
    oid = eid = 0

    def add_order(ts, acc, ins, side, price, qty, status, cancel_ts) -> int:
        nonlocal oid
        oid += 1
        order_rows.append((oid, ts, acc, ins, side, price, qty, status, cancel_ts))
        if len(order_rows) >= 50_000:
            con.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)", order_rows)
            order_rows.clear()
        return oid

    def add_exec(order_id, ts, price, qty) -> None:
        nonlocal eid
        eid += 1
        exec_rows.append((eid, order_id, ts, price, qty))
        if len(exec_rows) >= 50_000:
            con.executemany("INSERT INTO executions VALUES (?,?,?,?,?)", exec_rows)
            exec_rows.clear()

    # Noise blotter: ~549k orders. High cancel ratio (realistic for an electronic venue); noise qty
    # tops out at 4,000 and cancel latency is 30s-1h, so NONE of it trips the abuse signatures below.
    NOISE = 549_000
    for _ in range(NOISE):
        acc = r.randint(1, 1500)
        ins = r.randint(1, 300)
        base, tick = instr_px[ins]
        side = "buy" if r.random() < 0.5 else "sell"
        price = _round_tick(base * (1 + r.uniform(-0.05, 0.05)), tick)
        qty = r.randint(1, 40) * 100
        day_idx = r.randint(0, total_days)
        secs = r.randint(34_200, 57_599)  # 09:30:00 .. 15:59:59
        ts = fmt(day_idx, secs)
        x = r.random()
        if x < 0.30:  # filled
            oid_ = add_order(ts, acc, ins, side, price, qty, "filled", None)
            add_exec(oid_, ts, price, qty)
        elif x < 0.33:  # partial fill
            oid_ = add_order(ts, acc, ins, side, price, qty, "partial", None)
            add_exec(oid_, ts, price, max(qty // 2, 100))
        else:  # cancelled (slow, benign cancel)
            add_order(ts, acc, ins, side, price, qty, "cancelled", fmt(day_idx, secs + r.randint(30, 3600)))

    # (a) SPOOFING — 40 episodes: 6-15 LARGE same-side orders placed & cancelled within seconds,
    #     then a smaller opposite-side fill on the same instrument/account. Signature = a burst of
    #     >=6 rapidly-cancelled (<=6s) large (qty>=20k) same-side orders in one account/instrument/day.
    spoof_used: set = set()
    spoof_episodes: list[tuple] = []  # (acc, ins, side, day_idx, first_secs) — for the comms plant
    made = 0
    while made < 40:
        acc, ins = r.randint(200, 1500), r.randint(1, 300)
        side = "buy" if r.random() < 0.5 else "sell"
        day_idx = r.randint(0, total_days)
        key = (acc, ins, side, day_idx)
        if key in spoof_used:
            continue
        spoof_used.add(key)
        base, tick = instr_px[ins]
        secs = r.randint(34_200, 56_800)
        spoof_episodes.append((acc, ins, side, day_idx, secs))
        for k in range(r.randint(6, 15)):
            s = secs + k
            add_order(fmt(day_idx, s), acc, ins, side,
                      _round_tick(base * (1 + r.uniform(-0.02, 0.02)), tick),
                      r.randint(20_000, 80_000), "cancelled", fmt(day_idx, s + r.randint(1, 5)))
        opp = "sell" if side == "buy" else "buy"
        fs = secs + 20
        fprice = _round_tick(base * (1 + r.uniform(-0.02, 0.02)), tick)
        fqty = r.randint(100, 1000)
        fid = add_order(fmt(day_idx, fs), acc, ins, opp, fprice, fqty, "filled", None)
        add_exec(fid, fmt(day_idx, fs), fprice, fqty)
        made += 1

    # (b) WASH TRADES — 60 matched pairs: a buy and a sell on the same instrument, same qty, same
    #     price, executed within seconds, across two accounts owned by the SAME person. Per-pair qty
    #     (503+7k, never a round-100 like the noise) + price make cross-pair/noise matches impossible.
    for k in range(60):
        a1, a2 = 2 * k + 1, 2 * k + 2  # accounts 1..120: share an owner by construction
        ins = r.randint(1, 300)
        base, tick = instr_px[ins]
        price = _round_tick(base, tick) + tick * (k % 5)
        qty = 503 + 7 * k
        day_idx = r.randint(0, total_days)
        secs = r.randint(34_200, 57_000)
        bid = add_order(fmt(day_idx, secs), a1, ins, "buy", price, qty, "filled", None)
        add_exec(bid, fmt(day_idx, secs), price, qty)
        s2 = secs + r.randint(1, 4)
        sid = add_order(fmt(day_idx, s2), a2, ins, "sell", price, qty, "filled", None)
        add_exec(sid, fmt(day_idx, s2), price, qty)

    # (c) MARKING THE CLOSE — 15 account/month-end combos: 6-10 aggressive buy fills concentrated in
    #     the final minutes (15:55-16:00) of a month-end session at escalating prices.
    me_days = _month_ends(start, end_d)
    mc_used: set = set()
    made = 0
    while made < 15:
        acc = r.randint(200, 1500)
        day_idx, _ym = r.choice(me_days)
        if (acc, day_idx) in mc_used:
            continue
        mc_used.add((acc, day_idx))
        ins = r.randint(1, 300)
        base, tick = instr_px[ins]
        p = _round_tick(base, tick)
        for j in range(r.randint(6, 10)):
            secs = 57_300 + j * 30  # 15:55:00 onward, still < 15:59:59
            p = _round_tick(p + tick, tick)  # escalating
            qty = r.randint(200, 600)
            mid = add_order(fmt(day_idx, secs), acc, ins, "buy", p, qty, "filled", None)
            add_exec(mid, fmt(day_idx, secs), p, qty)
        made += 1

    # (d) POSITION-LIMIT BREACHES — 12 account/instrument combos whose cumulative net FILLED qty
    #     exceeds the instrument's position_limits.max_net_qty (piled to ~1.15x, margin far above any
    #     benign noise a shared cell could contribute).
    br_used: set = set()
    made = 0
    while made < 12:
        acc, ins = r.randint(200, 1500), r.randint(1, 300)
        if (acc, ins) in br_used:
            continue
        br_used.add((acc, ins))
        base, tick = instr_px[ins]
        cap = limits[ins]
        piled = 0
        while piled < cap * 1.15:
            q = r.randint(int(cap * 0.15), int(cap * 0.30))
            day_idx = r.randint(0, total_days)
            secs = r.randint(34_200, 55_000)
            price = _round_tick(base, tick)
            bid = add_order(fmt(day_idx, secs), acc, ins, "buy", price, q, "filled", None)
            add_exec(bid, fmt(day_idx, secs), price, q)
            piled += q
        made += 1

    # (e) CONCERT-PARTY ACCUMULATION — 3 groups of distinct-owner accounts sharing a clearing_ref
    #     prefix. Each member's net FILLED long stays under the instrument cap; the group's COMBINED
    #     net runs 2.3-2.8x the cap — a per-account limit evaded by splitting across nominees. Only a
    #     prefix-group aggregate finds it; no single-account query can. (rng(1011): own stream.)
    rcp = rng(1011)
    for _pfx, ins, members, per_member in concert_groups:
        base, tick = instr_px[ins]
        price = _round_tick(base, tick)
        for aid in members:
            legs = 3
            for j in range(legs):
                q = per_member // legs if j < legs - 1 else per_member - (per_member // legs) * (legs - 1)
                day_idx = rcp.randint(0, total_days)
                secs = rcp.randint(34_200, 55_000)  # never the 15:55+ close window (won't trip mark)
                cid = add_order(fmt(day_idx, secs), aid, ins, "buy", price, q, "filled", None)
                add_exec(cid, fmt(day_idx, secs), price, q)

    # ── desk-chat comms (unstructured layer): ~20k benign messages + coordination threads planted in
    #    the 90s-13min before the first 25 of the 40 spoofing bursts. (rng(1010): own stream.)
    rcm = rng(1010)
    syms = [row[1] for row in instruments]
    instr_sym = {row[0]: row[1] for row in instruments}
    comms_rows: list[tuple] = []
    cmid = 0
    for _ in range(20_000):
        frm = rcm.randint(1, 1500)
        to = rcm.randint(1, 1500)
        while to == frm:
            to = rcm.randint(1, 1500)
        secs = rcm.randint(30_600, 60_000)
        cmid += 1
        comms_rows.append((cmid, fmt(rcm.randint(0, total_days), secs), frm, to, _benign_body(rcm, syms)))
    for acc, ins, side, day_idx, first_secs in spoof_episodes[:25]:
        partner = rcm.randint(1, 1500)
        while partner == acc:
            partner = rcm.randint(1, 1500)
        parties = [(acc, partner), (partner, acc), (acc, partner)]  # a short back-and-forth
        for off, (frm, to) in zip(sorted(rcm.sample(range(90, 780), 3), reverse=True), parties):
            cmid += 1
            comms_rows.append((cmid, fmt(day_idx, first_secs - off), frm, to,
                               _intent_body(rcm, instr_sym[ins], side)))
    con.executemany("INSERT INTO comms VALUES (?,?,?,?,?)", comms_rows)
    con.execute("CREATE INDEX ix_comms_from ON comms (from_account_id)")
    con.execute("CREATE INDEX ix_comms_to ON comms (to_account_id)")

    if order_rows:
        con.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)", order_rows)
    if exec_rows:
        con.executemany("INSERT INTO executions VALUES (?,?,?,?,?)", exec_rows)

    # indexes after bulk load (surveillance joins: order lookup, price/qty match for wash detection)
    con.executescript(
        """
        CREATE INDEX ix_orders_acct_instr ON orders (account_id, instrument_id);
        CREATE INDEX ix_orders_match ON orders (instrument_id, price, qty);
        CREATE INDEX ix_exec_order ON executions (order_id);
        """
    )
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("instruments", "accounts", "position_limits", "orders", "executions", "comms")}
    con.close()
    return {"db": "exchange.db", "counts": counts,
            "planted": {"spoofing_episodes": 40, "wash_trade_pairs": 60,
                        "marking_close_combos": 15, "position_limit_breaches": 12,
                        "concert_party_groups": 3, "spoof_intent_comms_episodes": 25}}


if __name__ == "__main__":  # ponytail: standalone self-check — regenerate + assert every plant fires
    import time
    t = time.time()
    res = gen_exchange()
    print(res, f"{time.time() - t:.1f}s")
    c = sqlite3.connect(str(OUT / "exchange.db"))
    spoof = c.execute("""SELECT COUNT(*) FROM (SELECT 1 FROM orders WHERE status='cancelled'
        AND (julianday(cancel_ts)-julianday(ts))*86400 <= 6 AND qty >= 20000
        GROUP BY account_id, instrument_id, side, date(ts) HAVING COUNT(*) >= 6)""").fetchone()[0]
    wash = c.execute("""SELECT COUNT(*) FROM orders b JOIN accounts ab ON b.account_id=ab.id
        JOIN orders s ON s.instrument_id=b.instrument_id AND s.price=b.price AND s.qty=b.qty
            AND s.side='sell' AND s.status='filled'
        JOIN accounts asel ON s.account_id=asel.id
        JOIN executions eb ON eb.order_id=b.id JOIN executions es ON es.order_id=s.id
        WHERE b.side='buy' AND b.status='filled' AND ab.owner_name=asel.owner_name AND ab.id<>asel.id
            AND ABS(julianday(es.ts)-julianday(eb.ts))*86400 <= 6""").fetchone()[0]
    mark = c.execute("""SELECT COUNT(*) FROM (SELECT 1 FROM executions e JOIN orders o ON e.order_id=o.id
        WHERE o.side='buy' AND time(e.ts) >= '15:55:00'
            AND strftime('%d', date(e.ts,'+1 day'))='01'
        GROUP BY o.account_id, strftime('%Y-%m', e.ts) HAVING COUNT(*) >= 5)""").fetchone()[0]
    breach = c.execute("""SELECT COUNT(*) FROM (SELECT 1 FROM executions e JOIN orders o ON e.order_id=o.id
        JOIN position_limits pl ON pl.instrument_id=o.instrument_id
        GROUP BY o.account_id, o.instrument_id
        HAVING SUM(CASE WHEN o.side='buy' THEN e.qty ELSE -e.qty END) > pl.max_net_qty)""").fetchone()[0]
    print("spoof", spoof, "wash", wash, "mark", mark, "breach", breach)
    assert spoof == 40 and wash == 60 and mark == 15 and breach == 12, (spoof, wash, mark, breach)
    concert = c.execute("""WITH acct_net AS (SELECT o.account_id, o.instrument_id,
            SUM(CASE WHEN o.side='buy' THEN e.qty ELSE -e.qty END) AS net
            FROM executions e JOIN orders o ON e.order_id=o.id GROUP BY o.account_id, o.instrument_id),
        grp AS (SELECT substr(a.clearing_ref,1,4) AS pfx, an.instrument_id,
            COUNT(DISTINCT a.owner_name) AS owners, SUM(an.net) AS group_net, MAX(an.net) AS top_net
            FROM acct_net an JOIN accounts a ON a.id=an.account_id
            GROUP BY substr(a.clearing_ref,1,4), an.instrument_id)
        SELECT COUNT(*) FROM grp g JOIN position_limits pl ON pl.instrument_id=g.instrument_id
        WHERE g.owners >= 4 AND g.group_net > pl.max_net_qty
            AND g.top_net <= pl.max_net_qty""").fetchone()[0]
    comms_hits = c.execute("""SELECT COUNT(*) FROM comms c JOIN
        (SELECT account_id, instrument_id, side, date(ts) d, MIN(ts) first_ts FROM orders
         WHERE status='cancelled' AND (julianday(cancel_ts)-julianday(ts))*86400 <= 6 AND qty >= 20000
         GROUP BY account_id, instrument_id, side, date(ts) HAVING COUNT(*) >= 6) burst
        ON (c.from_account_id=burst.account_id OR c.to_account_id=burst.account_id)
        AND date(c.ts)=burst.d AND c.ts < burst.first_ts
        AND (julianday(burst.first_ts)-julianday(c.ts))*86400 <= 900""").fetchone()[0]
    print("concert", concert, "comms_hits", comms_hits)
    assert concert == 3, concert
    assert comms_hits >= 70, comms_hits
    c.close()
    print("OK")
