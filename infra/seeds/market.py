"""Solano Marketplace seed kit (09 §2) — a net-new sandbox company: an e-commerce marketplace.

Six tables (~749k rows, bulk in orders + reviews) with real referential integrity, dates spread
2022–2026. Fixed local RNG (rng(14)) → regenerates byte-for-byte identical (rehearsal gate 09 §7).

Plants four fraud/abuse signals so good sandbox prompts find real things (never canned outputs):
  (a) review rings        — 10 sellers pumped by clusters of unverified 5-star buyer accounts
  (b) refund abusers       — ~60 buyers with >40% refund rate across 10+ orders, many sellers
  (c) counterfeit signals  — ~320 listings priced <40% of category median from <90-day-old sellers
  (d) brushing/self-orders — 15 sellers with order bursts from linked buyers sharing one ship
                             address hash, each order followed by an immediate 5-star review

Output: infra/seeds/out/market.db.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from ._gen import country, day_between, full_name, rng

OUT = Path(__file__).resolve().parent / "out"
START, END = date(2022, 1, 1), date(2026, 7, 1)

# Category -> base price. Listing prices spread around base; the DB median lands ~1.2x base
# (uniform 0.6–1.8), so a counterfeit at 0.15–0.35x base is safely under 0.4x median.
CATEGORIES = {
    "Electronics": 220.0, "Home & Kitchen": 55.0, "Fashion": 42.0, "Beauty": 26.0,
    "Toys & Games": 30.0, "Sports & Outdoors": 65.0, "Books": 16.0, "Garden": 48.0,
}
_CATS = list(CATEGORIES)
_SHOP_A = ["Nova", "Blue", "Peak", "Urban", "Willow", "Iron", "Solar", "Maple", "Cobalt", "Ember",
           "Harbor", "Vintage", "Alpine", "Coral", "Onyx", "Prairie", "Cedar", "Lunar"]
_SHOP_B = ["Goods", "Supply", "Trading", "Market", "Depot", "Emporium", "Bazaar", "Outfitters",
           "Collective", "Works", "Merchants", "Wholesale", "Boutique", "Traders"]
_REASONS = ["item_not_as_described", "damaged", "never_arrived", "changed_mind",
            "wrong_item", "late_delivery", "counterfeit_suspected"]
_COUNTERFEIT_TITLES = ["Designer Handbag — Authentic", "AirPods Pro (Genuine)", "Ray-Ban Aviators",
                       "Nike Air Max — Real", "Rolex-Style Watch", "Louis V Wallet",
                       "iPhone Charger OEM", "Gucci Belt Original"]

# Sensitive-field vocab for the masking/policy-distillation demo. All synthetic: emails on the
# reserved .example TLD, 555 fictional phone exchange, card networks + last-4 only (no PAN).
_CARD_NETWORKS = ["Visa", "Mastercard", "Amex", "Discover"]
_STREETS = ["Maple St", "Oak Ave", "Cedar Ln", "Pine Rd", "Elm Dr", "Birch Ct", "Willow Way",
            "Sunset Blvd", "Harbor St", "Lincoln Ave", "Market St", "Mission St"]
_CITIES = [("San Jose", "CA", "95112"), ("Oakland", "CA", "94607"), ("Fresno", "CA", "93721"),
           ("Sacramento", "CA", "95814"), ("Portland", "OR", "97205"), ("Reno", "NV", "89501"),
           ("Austin", "TX", "78701"), ("Denver", "CO", "80202")]

# ── review-narrative pools (unstructured scenario) ───────────────────────────────────────────────
# Every review gets free text. The tell is MEANING, not keywords: fake ring/brushing reviews always
# hit the SAME four-beat praise script (delight + fast shipping + a favourable comparison + a strong
# recommendation), each beat surface-reworded per member so exact/near-string-dedup underperforms.
# Organic reviews draw from the SAME beat pools but only ever complete 1–3 of the four beats (plus
# neutral/negative pools), so the four-beat conjunction is unique to coordinated fakes — yet each
# single anchor ("love" / "fast" / "better than" / "recommend") is common in organic text, so no
# lone keyword isolates the ring. Anchors intentionally shared so the four-beat AND is discoverable.
_BEAT_DELIGHT = ["love this {p} to bits", "absolutely love it", "love how well made it is",
                 "fell in love with this {p} straight away", "love that this one finally arrived",
                 "just love the whole thing", "love it more than expected", "really do love this {p}",
                 "love everything about this {p}", "loved it from the first minute",
                 "so easy to love this {p}", "you will love owning this {p}",
                 "cannot help but love the quality", "love the way this {p} looks",
                 "love the little details on this {p}", "genuinely love this {p}"]
_BEAT_SPEED = ["shipped incredibly fast", "arrived surprisingly fast", "fast delivery, right on time",
               "got to me fast with no waiting", "fast shipping from this store",
               "came fast, well before the estimate", "delivery was fast and painless",
               "reached my door fast", "packed and out the door fast", "such fast turnaround",
               "fast to arrive despite the distance", "impressively fast shipping",
               "fast handling from order to doorstep", "here fast, ahead of schedule",
               "fast and carefully packaged", "the fast delivery sealed it"]
_BEAT_COMPARE = ["way better than {c}", "so much better than {c}", "better than {c} by a mile",
                 "feels better than {c} honestly", "better than {c} in every way",
                 "quality better than {c}", "clearly better than {c}", "better than {c} and cheaper",
                 "runs better than {c}", "holds up better than {c}", "looks better than {c}",
                 "far better than {c} i had before", "noticeably better than {c}",
                 "better than {c} for half the fuss", "better than {c} without question",
                 "performs better than {c}"]
_BEAT_RECO = ["highly recommend to everyone", "would recommend without hesitation",
              "recommend it to anyone shopping around", "cannot recommend it enough",
              "happily recommend this one", "recommend grabbing one soon",
              "definitely recommend for the price", "recommend it to friends and family",
              "recommend this seller wholeheartedly", "would recommend again and again",
              "an easy one to recommend", "recommend picking one up today",
              "recommend it with zero reservations", "gladly recommend this {p}",
              "recommend it over anything else", "recommend, full stop"]
_BEATS = [_BEAT_DELIGHT, _BEAT_SPEED, _BEAT_COMPARE, _BEAT_RECO]
# neutral (3★) + negative (1–2★): NONE contain love/fast/"better than"/recommend, so organic
# non-glowing reviews carry zero anchors and never contaminate the four-beat evidence query.
_REVIEW_NEUTRAL = ["does the job, nothing to write home about", "pretty much what the listing said",
                   "fine for the price i paid", "average quality overall",
                   "it works, no strong feelings either way", "middle of the road for me",
                   "okay, though the box turned up a bit dented", "decent enough for occasional use",
                   "mixed bag, some good points some not", "reasonable, not remarkable",
                   "about what you'd expect at this tier", "serviceable but unexciting",
                   "gets used, never loved", "no real complaints, no real praise",
                   "adequate for light use", "meh, it is what it is"]
_REVIEW_NEGATIVE = ["arrived with a cracked corner and i'm annoyed", "stopped working within a week",
                    "not as described, quite disappointed", "cheaper feeling than the photos showed",
                    "shipping dragged and then it broke", "returning this, poor build quality",
                    "would not order from this store again", "smaller and flimsier than expected",
                    "parts were missing from the box", "regret buying this one",
                    "quality took a nosedive after two uses", "the seller ignored my messages",
                    "overpriced for what turns up", "packaging was a mess and so is the product",
                    "gave up on it after a day", "wish i'd read the other complaints first"]
_REVIEW_PROD = ["item", "buy", "gadget", "piece", "find", "thing", "product", "one"]
_REVIEW_COMPET = ["the big-box version", "the name-brand one", "the pricier options",
                  "the department-store pick", "the usual brands", "the premium label",
                  "the store-brand version", "the one i had before"]
_REVIEW_CONN = [", ", " — ", "; ", ", and ", ". "]


def _fill_beat(rt, pool: list[str]) -> str:
    s = rt.choice(pool)
    if "{p}" in s:
        s = s.replace("{p}", rt.choice(_REVIEW_PROD))
    if "{c}" in s:
        s = s.replace("{c}", rt.choice(_REVIEW_COMPET))
    return s


def _join_beats(rt, parts: list[str]) -> str:
    out = parts[0]
    for p in parts[1:]:
        out += rt.choice(_REVIEW_CONN) + p
    out = out[0].upper() + out[1:]
    return out if out.endswith(".") else out + "."


def _review_text(rt, rating: int, fake: bool) -> str:
    """Deterministic (rt only). fake ⇒ all four praise beats (coordinated near-duplicate); organic
    positive ⇒ 1–3 beats (never all four); 3★ ⇒ neutral; 1–2★ ⇒ negative."""
    if fake:
        parts = [_fill_beat(rt, b) for b in _BEATS]
        rt.shuffle(parts)
        return _join_beats(rt, parts)
    if rating >= 4:
        k = rt.choices([1, 2, 3], weights=[55, 35, 10])[0]
        beats = rt.sample(_BEATS, k)
        return _join_beats(rt, [_fill_beat(rt, b) for b in beats])
    if rating == 3:
        return _join_beats(rt, [rt.choice(_REVIEW_NEUTRAL)])
    return _join_beats(rt, [rt.choice(_REVIEW_NEGATIVE)])


def _email(name: str, i: int) -> str:
    return f"{name.lower().replace(' ', '.')}{i}@mail.example"


def _address_for(hash_: str) -> str:
    # Derived purely from the ship-address hash so a *shared* hash (brushing) → a *shared* street
    # address — the abuse signal stays visible in cleartext too. No RNG: byte-stable by construction.
    n = int(hash_.rsplit("_", 1)[1])
    street = _STREETS[n % len(_STREETS)]
    city, st, zc = _CITIES[(n // len(_STREETS)) % len(_CITIES)]
    return f"{100 + (n * 37) % 9800} {street}, {city}, {st} {zc}"


_TERMS = """# Terms of Sensitive Data Use

## Solano Marketplace, Inc.

Solano Marketplace operates a consumer e-commerce platform on which independent sellers list goods
and buyers place orders, pay, and leave reviews. In the course of that activity Solano collects
personal contact details, shipping locations, and payment instruments belonging to natural persons.
This document defines how that sensitive data may be used, and — critically — the limits that apply
whenever any of it would be transmitted to a system, model, or partner outside Solano-controlled
infrastructure. It exists to keep the platform aligned with consumer-privacy law (CCPA/CPRA and, for
EU/UK residents, the GDPR) and with the Payment Card Industry Data Security Standard (PCI DSS) as it
applies to cardholder data.

## Data classification

The following fields are classified as sensitive and are governed by the rules in this document.

- **buyers.name** — Personal data (identity). A buyer's real name.
- **buyers.email** — Personal data (contact). Direct electronic identifier of a natural person.
- **buyers.phone** — Personal data (contact). Direct telephone identifier of a natural person.
- **orders.ship_address** — Personal data (precise geolocation). Cleartext residential or delivery
  address tied to a specific order and buyer.
- **orders.ship_address_hash** — Pseudonymized data (linkage key). Salted digest of the shipping
  address; permits cross-order linkage without revealing the address itself.
- **orders.card_last4** — Cardholder data (PCI). The final four digits of the payment card used on
  an order. Solano stores no primary account number (PAN); only the last four are retained.
- **orders.card_network** — Cardholder data (PCI). The card scheme (for example Visa or Mastercard)
  associated with an order's payment.
- **sellers.country** — Business location data. Used to determine the residency rules that apply to a
  seller's payouts and records.

## Handling rules

- **Buyer contact identifiers must never leave Solano infrastructure in cleartext.** The values in
  buyers.email and buyers.phone must be masked before any external transmission — for example an
  email rendered as its local-part initial plus domain, and a phone reduced to its last two digits.
- **Buyer names may appear in external planning materials only in pseudonymized form.** No process
  that sends data to an external model may include buyers.name in plaintext; substitute a stable
  pseudonym or the buyer id.
- **Shipping addresses must never be transmitted externally.** orders.ship_address is precise
  geolocation data and may not appear in any brief, prompt, or export leaving Solano infrastructure;
  only the pseudonymized orders.ship_address_hash may be used to express cross-order linkage in
  external analysis.
- **Payment card data is handled strictly under PCI DSS.** Solano never stores a full PAN. Card
  numbers must always be masked to orders.card_last4 before any external transmission, and
  orders.card_last4 must never be combined with buyers.name or buyers.email in material sent outside
  Solano infrastructure.
- **Card network is reportable but not identifying alone.** orders.card_network may be shared in
  aggregate for fraud and settlement analysis, but never joined to an individual buyer's contact
  identifiers in external materials.
- **Data residency follows the buyer and seller.** Personal data of EU/UK residents must be
  processed and retained on infrastructure located in the EU/UK; seller records are governed by
  sellers.country, and payout and tax data for a seller must remain within that seller's jurisdiction.
- **Retention is bounded.** Order, review, and refund records are retained for seven years for
  financial-compliance purposes; buyers.email and buyers.phone are purged within thirty days of a
  verified account-closure request, subject only to open dispute or chargeback holds.
- **External planning is minimized by default.** Any brief prepared for an external frontier model
  must carry the smallest set of fields needed for the task, and must exclude every field in the Data
  classification section above unless this document expressly permits its masked form.

## Note

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation
boundary.
"""


def _write_terms() -> Path:
    path = OUT / "terms" / "market_terms.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_TERMS)
    return path


def _fresh_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return sqlite3.connect(str(path))


def _writer(con: sqlite3.Connection, sql: str, chunk: int = 50_000):
    """Buffered executemany so peak memory stays flat over ~450k rows (single commit at the end)."""
    buf: list[tuple] = []

    def add(row: tuple) -> None:
        buf.append(row)
        if len(buf) >= chunk:
            con.executemany(sql, buf)
            buf.clear()

    def done() -> None:
        if buf:
            con.executemany(sql, buf)
            buf.clear()

    return add, done


def gen_market() -> dict:
    r = rng(14)
    rs = rng(15)  # dedicated stream for sensitive PII/payment fields — keeps r's planted patterns byte-identical
    rt = rng(1410)  # dedicated stream for review narrative text — never touches r, so all floors stay byte-identical
    con = _fresh_db(OUT / "market.db")
    con.executescript(
        """
        CREATE TABLE sellers  (id INTEGER PRIMARY KEY, name TEXT, joined TEXT, country TEXT);
        CREATE TABLE listings (id INTEGER PRIMARY KEY, seller_id INTEGER, title TEXT, category TEXT,
            price_usd REAL, created TEXT);
        CREATE TABLE buyers   (id INTEGER PRIMARY KEY, name TEXT, joined TEXT, email TEXT, phone TEXT);
        CREATE TABLE orders   (id INTEGER PRIMARY KEY, listing_id INTEGER, buyer_id INTEGER, ts TEXT,
            qty INTEGER, total_usd REAL, ship_address_hash TEXT, ship_address TEXT,
            card_last4 TEXT, card_network TEXT);
        CREATE TABLE reviews  (id INTEGER PRIMARY KEY, listing_id INTEGER, buyer_id INTEGER,
            rating INTEGER, ts TEXT, verified_purchase INTEGER, review_text TEXT);
        CREATE TABLE refunds  (id INTEGER PRIMARY KEY, order_id INTEGER, ts TEXT, reason TEXT,
            amount_usd REAL);
        CREATE TABLE listing_price_history (listing_id INTEGER, ts TEXT, price_usd REAL);
        """
    )

    # ── sellers ──────────────────────────────────────────────────────────────────────────────
    N_SELLERS = 4000
    RING_SELLERS = list(range(501, 511))        # 10 pumped sellers
    BRUSHING_SELLERS = list(range(601, 616))    # 15 self-order sellers
    COUNTERFEIT_SELLERS = list(range(701, 741))  # 40 young sellers listing suspiciously cheap goods
    counterfeit_set = set(COUNTERFEIT_SELLERS)

    seller_joined: list[date] = [START]  # index 0 unused; seller ids are 1-based
    sellers = []
    for i in range(1, N_SELLERS + 1):
        # counterfeit sellers join recently so a <90-day listing still lands before END
        j = day_between(r, date(2024, 1, 1), date(2026, 3, 1)) if i in counterfeit_set \
            else day_between(r, START, date(2026, 6, 1))
        seller_joined.append(j)
        name = f"{r.choice(_SHOP_A)} {r.choice(_SHOP_B)}"
        sellers.append((i, name, j.isoformat(), country(r)))
    con.executemany("INSERT INTO sellers VALUES (?,?,?,?)", sellers)

    # ── listings ─────────────────────────────────────────────────────────────────────────────
    # Parallel arrays keyed by listing id (1-based) — needed to compute order ts/total downstream.
    l_seller: list[int] = [0]
    l_price: list[float] = [0.0]
    l_created: list[date] = [START]
    add_l, done_l = _writer(con, "INSERT INTO listings VALUES (?,?,?,?,?,?)")
    lid = 0

    def _emit_listing(seller: int, cat: str, price: float, created: date, title: str) -> int:
        nonlocal lid
        lid += 1
        add_l((lid, seller, title, cat, round(price, 2), created.isoformat()))
        l_seller.append(seller)
        l_price.append(round(price, 2))
        l_created.append(created)
        return lid

    # dedicated listings for ring sellers (5 each) — targets for the fake reviews
    ring_listings: dict[int, list[int]] = {}
    for s in RING_SELLERS:
        ids = []
        for _ in range(5):
            cat = r.choice(_CATS)
            created = day_between(r, seller_joined[s], END)
            ids.append(_emit_listing(s, cat, CATEGORIES[cat] * r.uniform(0.6, 1.8), created,
                                     f"{cat} item"))
        ring_listings[s] = ids

    # dedicated listings for brushing sellers (4 each) — targets for the self-orders
    brush_listings: dict[int, list[int]] = {}
    for s in BRUSHING_SELLERS:
        ids = []
        for _ in range(4):
            cat = r.choice(_CATS)
            created = day_between(r, seller_joined[s], END)
            ids.append(_emit_listing(s, cat, CATEGORIES[cat] * r.uniform(0.6, 1.8), created,
                                     f"{cat} item"))
        brush_listings[s] = ids

    # (c) counterfeit-signal listings: <40% of category median, seller joined <90d before creation
    counterfeit_listings = 0
    for s in COUNTERFEIT_SELLERS:
        for _ in range(r.randint(7, 9)):
            cat = r.choice(_CATS)
            created = seller_joined[s] + timedelta(days=r.randint(0, 89))
            price = CATEGORIES[cat] * r.uniform(0.15, 0.35)   # ~0.15–0.35x base < 0.4x median
            _emit_listing(s, cat, price, created, r.choice(_COUNTERFEIT_TITLES))
            counterfeit_listings += 1

    # normal listings fill the remainder to 50k
    while lid < 50_000:
        s = r.randint(1, N_SELLERS)
        cat = r.choice(_CATS)
        created = day_between(r, seller_joined[s], END)
        _emit_listing(s, cat, CATEGORIES[cat] * r.uniform(0.6, 1.8), created, f"{cat} item")
    done_l()
    N_LISTINGS = lid

    # ── buyers ───────────────────────────────────────────────────────────────────────────────
    # Reserved buyer-id blocks get ONLY their planted activity (kept out of normal orders/reviews),
    # so the refund-rate / ring / brushing math stays clean.
    N_BUYERS = 30_000
    NORMAL_LO = 3001                                     # normal actors draw from [3001, 30000]
    ring_buyer_cursor = 1                                # ring buyers  live in [1, ~300]
    ABUSER_BUYERS = list(range(1001, 1061))              # 60 refund abusers
    brush_buyer_cursor = 2001                            # brushing buyers live in [2001, ~2100]

    # Per-buyer card on file (last-4 + network only, never a PAN). 1-based, keyed by buyer id.
    buyer_card4: list[str] = [""]
    buyer_net: list[str] = [""]
    add_b, done_b = _writer(con, "INSERT INTO buyers VALUES (?,?,?,?,?)")
    for i in range(1, N_BUYERS + 1):
        name = full_name(r)  # r draws (name, joined) stay in the exact original order → plants unchanged
        joined = day_between(r, START, END).isoformat()
        buyer_card4.append(f"{rs.randint(0, 9999):04d}")
        buyer_net.append(rs.choice(_CARD_NETWORKS))
        add_b((i, name, joined, _email(name, i), f"+1-415-555-{rs.randint(1000, 9999)}"))
    done_b()

    # ── orders ───────────────────────────────────────────────────────────────────────────────
    add_o, done_o = _writer(con, "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)")
    oid = 0

    def _emit_order(listing: int, buyer: int, ts: date, hash_: str) -> int:
        nonlocal oid
        oid += 1
        qty = r.randint(1, 3)
        add_o((oid, listing, buyer, ts.isoformat(), qty, round(l_price[listing] * qty, 2), hash_,
               _address_for(hash_), buyer_card4[buyer], buyer_net[buyer]))
        return oid

    # normal orders (bulk). ship_address_hash unique per buyer → a shared hash is only ever planted.
    N_NORMAL_ORDERS = 448_000
    for _ in range(N_NORMAL_ORDERS):
        listing = r.randint(1, N_LISTINGS)
        buyer = r.randint(NORMAL_LO, N_BUYERS)
        ts = day_between(r, l_created[listing], END)
        _emit_order(listing, buyer, ts, f"addr_{buyer}")
    n_normal_orders = oid  # normal order ids are exactly 1..n_normal_orders

    # (b) refund abusers: 12–25 orders each across many sellers (random listings ⇒ distinct sellers)
    abuser_orders: dict[int, list[int]] = {}
    for buyer in ABUSER_BUYERS:
        ids = []
        for _ in range(r.randint(12, 25)):
            listing = r.randint(1, N_LISTINGS)
            ts = day_between(r, l_created[listing], END)
            ids.append(_emit_order(listing, buyer, ts, f"addr_{buyer}"))
        abuser_orders[buyer] = ids

    # (d) brushing: linked buyers share ONE hash per seller, burst-order the seller's own listings,
    #     each order immediately followed by a 5-star review (collected here, inserted below).
    brush_review_seed: list[tuple[int, int, date]] = []  # (listing, buyer, order_ts)
    for s in BRUSHING_SELLERS:
        linked = [brush_buyer_cursor + k for k in range(r.randint(3, 6))]
        brush_buyer_cursor += len(linked)
        shared_hash = f"brush_{s}"
        for buyer in linked:
            for _ in range(r.randint(4, 7)):
                listing = r.choice(brush_listings[s])
                ts = day_between(r, l_created[listing], END)
                _emit_order(listing, buyer, ts, shared_hash)
                brush_review_seed.append((listing, buyer, ts))
    done_o()

    # ── reviews ──────────────────────────────────────────────────────────────────────────────
    add_rv, done_rv = _writer(con, "INSERT INTO reviews VALUES (?,?,?,?,?,?,?)")
    rid = 0

    def _emit_review(listing: int, buyer: int, rating: int, ts: date, verified: int,
                     fake: bool = False) -> None:
        nonlocal rid
        rid += 1
        add_rv((rid, listing, buyer, rating, ts.isoformat(), verified,
                _review_text(rt, rating, fake)))

    # normal reviews (bulk): rating-5 heavy, ~90% verified purchases
    N_NORMAL_REVIEWS = 179_000
    for _ in range(N_NORMAL_REVIEWS):
        listing = r.randint(1, N_LISTINGS)
        buyer = r.randint(NORMAL_LO, N_BUYERS)
        rating = r.choices([5, 4, 3, 2, 1], weights=[50, 25, 12, 8, 5])[0]
        verified = 1 if r.random() < 0.9 else 0
        _emit_review(listing, buyer, rating, day_between(r, l_created[listing], END), verified)

    # (a) review rings: 8–20 buyer accounts per seller, 4 unverified 5-star reviews each, within
    #     a few days — a big cluster of verified_purchase=0 fives on one seller.
    ring_reviews = 0
    for s in RING_SELLERS:
        n_buyers = r.randint(8, 20)
        ring_buyers = list(range(ring_buyer_cursor, ring_buyer_cursor + n_buyers))
        ring_buyer_cursor += n_buyers
        base = day_between(r, date(2025, 1, 1), END)
        for buyer in ring_buyers:
            for _ in range(4):
                _emit_review(r.choice(ring_listings[s]), buyer, 5,
                             base + timedelta(days=r.randint(0, 4)), 0, fake=True)
                ring_reviews += 1

    # (d cont.) the immediate 5-star (verified) review that follows each brushing order — also written
    # to the coordinated four-beat praise script (reinforces the near-duplicate-sweep signal)
    for listing, buyer, ts in brush_review_seed:
        _emit_review(listing, buyer, 5, ts + timedelta(days=r.randint(0, 2)), 1, fake=True)
    done_rv()

    # ── refunds ──────────────────────────────────────────────────────────────────────────────
    add_rf, done_rf = _writer(con, "INSERT INTO refunds VALUES (?,?,?,?,?)")
    fid = 0

    def _emit_refund(order_id: int, reason: str | None = None) -> None:
        nonlocal fid
        fid += 1
        add_rf((fid, order_id, day_between(r, START, END).isoformat(),
                reason or r.choice(_REASONS), round(r.uniform(8, 240), 2)))

    # normal refunds: ~7.7% of normal orders (only normal order ids 1..n_normal_orders)
    n_normal_refunds = round(n_normal_orders * 0.077)
    for order_id in r.sample(range(1, n_normal_orders + 1), n_normal_refunds):
        _emit_refund(order_id)
    # abuser refunds: 55–70% of each abuser's orders ⇒ refund rate > 40%
    for buyer, ids in abuser_orders.items():
        k = round(len(ids) * r.uniform(0.55, 0.70))
        for order_id in r.sample(ids, k):
            _emit_refund(order_id, "changed_mind")
    done_rf()

    # ── (e) price-coordination cartels — new listing_price_history table (reasoning scenario) ────
    # Two cartels of 6 distinct sellers each, one per category. Each cartel shares ONE coordinated
    # move calendar: every member's flagship listing changes price on the same days, same direction
    # (magnitude jittered), timestamps hours apart — lockstep across months. A ~200-listing baseline
    # per category moves on its own random schedule. Detection needs ≥2 hops: derive per-listing
    # price-change direction (window LAG), self-join movers on same day+direction, then aggregate the
    # co-moves per same-category cross-seller pair — a single-table WHERE cannot see it. Uses existing
    # listings (FK-safe) + dedicated rng(1411) so r stays byte-identical and every floor holds.
    rc = rng(1411)
    add_ph, done_ph = _writer(con, "INSERT INTO listing_price_history VALUES (?,?,?)")

    def _emit_price(listing: int, d: date, hour: int, price: float) -> None:
        add_ph((listing, f"{d.isoformat()}T{hour:02d}:00:00", round(price, 2)))

    CARTEL_CATS = ["Electronics", "Fashion"]
    ph_start = date(2024, 1, 1)
    cartel_pairs = 0
    for cat in CARTEL_CATS:
        rows = con.execute(
            "SELECT id, seller_id, price_usd FROM listings WHERE category=? ORDER BY id", (cat,)
        ).fetchall()
        seen: set[int] = set()
        cartel: list[tuple[int, float]] = []
        for lid_, sid_, px_ in rows:
            if sid_ not in seen:
                seen.add(sid_)
                cartel.append((lid_, px_))
            if len(cartel) == 6:
                break
        cartel_ids = {c[0] for c in cartel}
        baseline = [(lid_, px_) for lid_, _sid, px_ in rows if lid_ not in cartel_ids][:200]

        # shared move calendar for this cartel (roughly monthly; same day + sign for every member)
        events: list[tuple[date, int]] = []
        d = ph_start
        for _ in range(24):
            d = d + timedelta(days=rc.randint(25, 40))
            if d >= END:
                break
            events.append((d, rc.choice([1, -1])))

        for idx, (lid_, base_px) in enumerate(cartel):
            px = base_px
            _emit_price(lid_, ph_start, 9, px)                  # seed price (dir=NULL, not a move)
            for ed, direction in events:
                px *= 1 + direction * rc.uniform(0.03, 0.12)    # same sign for all members
                _emit_price(lid_, ed, 9 + idx, px)              # within-hours offset per member
        cartel_pairs += len(cartel) * (len(cartel) - 1) // 2

        for lid_, base_px in baseline:                          # independent random-walk baseline
            px = base_px
            _emit_price(lid_, ph_start, 9, px)
            cur = ph_start
            for _ in range(rc.randint(8, 16)):
                cur = cur + timedelta(days=rc.randint(10, 90))
                if cur >= END:
                    break
                px *= 1 + rc.choice([1, -1]) * rc.uniform(0.03, 0.12)
                _emit_price(lid_, cur, rc.randint(8, 18), px)
    done_ph()

    # indexes (realistic + keep the sandbox's live queries and self-verification snappy)
    con.executescript(
        """
        CREATE INDEX ix_listings_seller ON listings(seller_id);
        CREATE INDEX ix_orders_listing  ON orders(listing_id);
        CREATE INDEX ix_orders_buyer    ON orders(buyer_id);
        CREATE INDEX ix_reviews_listing ON reviews(listing_id);
        CREATE INDEX ix_refunds_order   ON refunds(order_id);
        CREATE INDEX ix_price_listing   ON listing_price_history(listing_id);
        """
    )
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("sellers", "listings", "buyers", "orders", "reviews", "refunds",
                        "listing_price_history")}
    con.close()
    _write_terms()
    return {
        "db": "market.db",
        "counts": counts,
        "terms": "terms/market_terms.md",
        "planted": {
            "review_rings": len(RING_SELLERS),
            "review_ring_reviews": ring_reviews,
            "refund_abusers": len(ABUSER_BUYERS),
            "counterfeit_listings": counterfeit_listings,
            "brushing_sellers": len(BRUSHING_SELLERS),
            "brushing_orders": len(brush_review_seed),
            # (new) coordinated near-duplicate praise reviews carrying the full four-beat script
            "coordinated_review_texts": ring_reviews + len(brush_review_seed),
            "price_cartels": len(CARTEL_CATS),
            "price_cartel_pairs": cartel_pairs,
        },
    }


if __name__ == "__main__":  # ponytail: standalone self-check — regenerate + assert every plant fires
    import time

    t = time.time()
    res = gen_market()
    dt = time.time() - t
    print(res, f"{dt:.1f}s")
    assert dt < 60, f"too slow: {dt:.1f}s"
    con = sqlite3.connect(str(OUT / "market.db"))
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731
    rings = q("""SELECT l.seller_id FROM reviews rv JOIN listings l ON l.id=rv.listing_id
                 WHERE rv.rating=5 AND rv.verified_purchase=0
                 GROUP BY l.seller_id HAVING COUNT(DISTINCT rv.buyer_id)>=8 AND COUNT(*)>=30""")
    abusers = q("""SELECT o.buyer_id FROM orders o JOIN listings l ON l.id=o.listing_id
                   LEFT JOIN refunds rf ON rf.order_id=o.id GROUP BY o.buyer_id
                   HAVING COUNT(*)>=10 AND COUNT(rf.id)*1.0/COUNT(*)>0.4
                      AND COUNT(DISTINCT l.seller_id)>=5""")
    counterfeit = q("""WITH ranked AS (
            SELECT category, price_usd,
                   ROW_NUMBER() OVER (PARTITION BY category ORDER BY price_usd) AS rn,
                   COUNT(*)     OVER (PARTITION BY category) AS cnt
            FROM listings),
        med AS (SELECT category, price_usd AS median_price FROM ranked WHERE rn = cnt/2 + 1)
        SELECT li.id FROM listings li JOIN med ON med.category=li.category
        JOIN sellers s ON s.id=li.seller_id
        WHERE li.price_usd < 0.4*med.median_price
          AND julianday(li.created)-julianday(s.joined) BETWEEN 0 AND 89""")
    brushing = q("""SELECT l.seller_id FROM orders o JOIN listings l ON l.id=o.listing_id
                    GROUP BY l.seller_id, o.ship_address_hash
                    HAVING COUNT(*)>=10 AND COUNT(DISTINCT o.buyer_id) BETWEEN 2 AND 8""")
    print(f"rings={len(rings)} abusers={len(abusers)} counterfeit={len(counterfeit)} "
          f"brushing={len(brushing)}")
    assert len(rings) >= 10, rings
    assert len(abusers) >= 55, len(abusers)
    assert len(counterfeit) >= 250, len(counterfeit)
    assert len(brushing) >= 15, len(brushing)
    # sensitive-column audit: every buyer/order row carries its planted PII/payment fields
    assert q("SELECT COUNT(*) FROM buyers WHERE email LIKE '%@mail.example' AND phone LIKE '+1-415-555-%'")[0][0] \
        == q("SELECT COUNT(*) FROM buyers")[0][0]
    assert q("SELECT COUNT(*) FROM orders WHERE ship_address<>'' AND card_last4<>'' AND card_network<>''")[0][0] \
        == q("SELECT COUNT(*) FROM orders")[0][0]
    # brushing's shared ship_address_hash → one shared cleartext ship_address (abuse signal in the clear)
    assert q("SELECT COUNT(DISTINCT ship_address) FROM orders WHERE ship_address_hash='brush_601'")[0][0] == 1
    # (a-new) every review carries narrative text; the four-beat conjunction isolates coordinated fakes
    assert q("SELECT COUNT(*) FROM reviews WHERE review_text IS NULL OR review_text=''")[0][0] == 0
    quad = q("""SELECT COUNT(*) FROM reviews WHERE review_text LIKE '%love%'
                AND review_text LIKE '%fast%' AND review_text LIKE '%better than%'
                AND review_text LIKE '%recommend%'""")[0][0]
    print(f"four_beat_reviews={quad}")
    assert quad >= 500, quad
    # no single anchor may isolate the fakes (each must be common in organic text too)
    for kw in ("love", "fast", "better than", "recommend"):
        organic = q(f"SELECT COUNT(*) FROM reviews WHERE review_text LIKE '%{kw}%'")[0][0]
        assert organic > quad * 3, (kw, organic, quad)
    # (e-new) price-coordination cartels: same-category cross-seller pairs moving in lockstep
    cartels = q("""WITH moves AS (SELECT listing_id, date(ts) AS d,
              CASE WHEN price_usd > LAG(price_usd) OVER (PARTITION BY listing_id ORDER BY ts) THEN 1
                   WHEN price_usd < LAG(price_usd) OVER (PARTITION BY listing_id ORDER BY ts) THEN -1
                   ELSE 0 END AS dir FROM listing_price_history),
          m AS (SELECT listing_id, d, dir FROM moves WHERE dir<>0)
        SELECT a.listing_id, b.listing_id, COUNT(*) c FROM m a
        JOIN m b ON a.d=b.d AND a.dir=b.dir AND a.listing_id<b.listing_id
        JOIN listings la ON la.id=a.listing_id JOIN listings lb ON lb.id=b.listing_id
        WHERE la.category=lb.category AND la.seller_id<>lb.seller_id
        GROUP BY a.listing_id, b.listing_id HAVING COUNT(*)>=8""")
    print(f"cartel_pairs={len(cartels)}")
    assert len(cartels) >= 20, len(cartels)
    con.close()
    terms = _write_terms().read_text()
    assert all(c in terms for c in ("buyers.email", "buyers.phone", "orders.ship_address",
                                    "orders.card_last4", "orders.card_network"))
    print("all plants fire ✓  sensitive fields + terms ✓")
