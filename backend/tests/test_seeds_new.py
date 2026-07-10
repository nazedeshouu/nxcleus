"""Evidence check for the eight judge-sandbox datasets (09 §2), including the unstructured
(semantic-reading) + reasoning (multi-hop structural) layer added to every company.

Each generator plants patterns so the suggested prompts find real things (track rule anchor:
outputs are computed live, never canned). This test opens each already-generated read-only DB and
runs the exact evidence SQL behind every use case, asserting it returns at least the expected number
of planted hits. If a DB has not been generated (infra/seeds/out/<id>.db missing) its cases skip —
regenerate with `uv run --project backend python scripts/seed.py`.

Plain sqlite3 + pytest, no fixtures. The evidence SQL and expected minimums are literal data below.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.api.sandbox import COMPANIES
from app.boundary.intake import resolve_policy_sources
from app.sandbox.seeds import company_terms

_OUT = Path(__file__).resolve().parents[2] / "infra" / "seeds" / "out"
_NAMES = {c["id"]: c["name"] for c in COMPANIES}

# dataset id -> list of (use-case title, evidence SQL, expected minimum planted hits)
EVIDENCE: dict[str, list[tuple[str, str, int]]] = {
    "bank": [
        ("contradictory-memos",
         "SELECT account_id, COUNT(*) AS deposits, COUNT(DISTINCT memo) AS distinct_purposes FROM transactions WHERE amount_usd BETWEEN 9000 AND 9900 AND kind='deposit' GROUP BY account_id HAVING COUNT(*) >= 6 AND COUNT(DISTINCT memo) >= 4",
         10),
        ("layering-chains",
         "WITH RECURSIVE hop(head, acct_next, depth, amt, ts) AS (SELECT id, counterparty_account_id, 1, amount_usd, ts FROM transactions WHERE kind='transfer' AND counterparty_account_id IS NOT NULL UNION ALL SELECT h.head, t.counterparty_account_id, h.depth+1, t.amount_usd, t.ts FROM transactions t JOIN hop h ON t.account_id=h.acct_next AND t.kind='transfer' AND t.counterparty_account_id IS NOT NULL AND julianday(t.ts) BETWEEN julianday(h.ts) AND julianday(h.ts)+4 AND t.amount_usd BETWEEN h.amt*0.95 AND h.amt*0.999) SELECT head, MAX(depth) AS chain_depth FROM hop GROUP BY head HAVING MAX(depth) >= 4",
         12),
    ],
    "clinic": [
        ("upcoding",
         "SELECT e.id, e.billing_code, cat.complexity_level, e.visit_note FROM encounters e JOIN cpt_catalog cat ON cat.code = e.billing_code WHERE cat.complexity_level = 'high' AND e.id > (SELECT MAX(id) FROM encounters) - 60",
         55),
        ("provider-double-booking",
         "SELECT a.id AS enc_a, b.id AS enc_b, a.provider, a.date, a.department AS dept_a, b.department AS dept_b, a.start_time, a.end_time, b.start_time, b.end_time FROM encounters a JOIN encounters b ON a.provider=b.provider AND a.date=b.date AND a.id<b.id AND a.department<>b.department AND a.start_time < b.end_time AND b.start_time < a.end_time",
         25),
    ],
    "lawfirm": [
        ("contract-contradictions",
         "SELECT id, title FROM contracts WHERE id IN (3,11,19,27,35,43,51,59,67,75,83,91,99,107,115,123,131,139,147,155,163,171,179,187,195)",
         25),
        ("amendment-conflicts",
         "SELECT a.contract_id, COUNT(*) AS amendments, c.title FROM amendments a JOIN contracts c ON c.id = a.contract_id WHERE a.contract_id IN (10,20,30,40,50,60,70,80,90,100,110,120) GROUP BY a.contract_id HAVING COUNT(*) >= 2",
         12),
    ],
    "exchange": [
        ("spoofing",
         "SELECT account_id, instrument_id, side, date(ts) AS trade_day, COUNT(*) AS cancelled_burst, MAX(qty) AS largest_qty FROM orders WHERE status='cancelled' AND (julianday(cancel_ts)-julianday(ts))*86400 <= 6 AND qty >= 20000 GROUP BY account_id, instrument_id, side, date(ts) HAVING COUNT(*) >= 6 ORDER BY cancelled_burst DESC",
         40),
        ("wash-trade",
         "SELECT ab.owner_name, ab.firm, b.instrument_id, b.qty, b.price, b.id AS buy_order_id, s.id AS sell_order_id FROM orders b JOIN accounts ab ON b.account_id=ab.id JOIN orders s ON s.instrument_id=b.instrument_id AND s.price=b.price AND s.qty=b.qty AND s.side='sell' AND s.status='filled' JOIN accounts asel ON s.account_id=asel.id JOIN executions eb ON eb.order_id=b.id JOIN executions es ON es.order_id=s.id WHERE b.side='buy' AND b.status='filled' AND ab.owner_name=asel.owner_name AND ab.id<>asel.id AND ABS(julianday(es.ts)-julianday(eb.ts))*86400 <= 6 ORDER BY ab.owner_name",
         60),
        ("marking-the-close",
         "SELECT o.account_id, strftime('%Y-%m', e.ts) AS session_month, COUNT(*) AS closing_buys, MIN(e.price) AS first_px, MAX(e.price) AS last_px FROM executions e JOIN orders o ON e.order_id=o.id WHERE o.side='buy' AND time(e.ts) >= '15:55:00' AND strftime('%d', date(e.ts,'+1 day'))='01' GROUP BY o.account_id, session_month HAVING COUNT(*) >= 5 ORDER BY closing_buys DESC",
         15),
        ("position-limit-breach",
         "SELECT o.account_id, o.instrument_id, SUM(CASE WHEN o.side='buy' THEN e.qty ELSE -e.qty END) AS net_position, pl.max_net_qty FROM executions e JOIN orders o ON e.order_id=o.id JOIN position_limits pl ON pl.instrument_id=o.instrument_id GROUP BY o.account_id, o.instrument_id HAVING net_position > pl.max_net_qty ORDER BY net_position - pl.max_net_qty DESC",
         12),
        ("spoof-intent-comms",
         "SELECT c.id, c.ts, c.from_account_id, c.to_account_id, burst.first_ts, c.body FROM comms c JOIN (SELECT account_id, instrument_id, side, date(ts) d, MIN(ts) first_ts FROM orders WHERE status='cancelled' AND (julianday(cancel_ts)-julianday(ts))*86400 <= 6 AND qty >= 20000 GROUP BY account_id, instrument_id, side, date(ts) HAVING COUNT(*) >= 6) burst ON (c.from_account_id=burst.account_id OR c.to_account_id=burst.account_id) AND date(c.ts)=burst.d AND c.ts < burst.first_ts AND (julianday(burst.first_ts)-julianday(c.ts))*86400 <= 900 ORDER BY burst.first_ts, c.ts",
         60),
        ("concert-party",
         "WITH acct_net AS (SELECT o.account_id, o.instrument_id, SUM(CASE WHEN o.side='buy' THEN e.qty ELSE -e.qty END) AS net FROM executions e JOIN orders o ON e.order_id=o.id GROUP BY o.account_id, o.instrument_id), grp AS (SELECT substr(a.clearing_ref,1,4) AS pfx, an.instrument_id, COUNT(DISTINCT a.owner_name) AS owners, COUNT(DISTINCT a.id) AS members, SUM(an.net) AS group_net, MAX(an.net) AS top_member_net FROM acct_net an JOIN accounts a ON a.id=an.account_id GROUP BY substr(a.clearing_ref,1,4), an.instrument_id) SELECT g.pfx, g.instrument_id, g.owners, g.members, g.group_net, pl.max_net_qty FROM grp g JOIN position_limits pl ON pl.instrument_id=g.instrument_id WHERE g.owners >= 4 AND g.group_net > pl.max_net_qty AND g.top_member_net <= pl.max_net_qty ORDER BY g.group_net - pl.max_net_qty DESC",
         3),
    ],
    "insurer": [
        ("duplicate-claim",
         "SELECT a.id AS claim_a, b.id AS claim_b, a.policy_id, a.incident_date, a.amount_claimed AS amount_a, b.amount_claimed AS amount_b FROM claims a JOIN claims b ON a.policy_id = b.policy_id AND a.incident_date = b.incident_date AND a.id < b.id WHERE ABS(a.amount_claimed - b.amount_claimed) <= 0.05 * a.amount_claimed ORDER BY a.policy_id",
         120),
        ("fraud-ring",
         "SELECT repair_shop_id, claimant_phone, COUNT(*) AS ring_claims, COUNT(DISTINCT policy_id) AS distinct_policies, MIN(incident_date) AS first_incident, MAX(incident_date) AS last_incident FROM claims WHERE repair_shop_id IS NOT NULL GROUP BY repair_shop_id, claimant_phone HAVING COUNT(*) >= 6 AND COUNT(DISTINCT policy_id) >= 6 ORDER BY ring_claims DESC",
         8),
        ("coverage-breach",
         "SELECT c.id AS claim_id, c.policy_id, p.coverage_limit_usd, SUM(cp.amount) AS total_paid FROM claims c JOIN policies p ON p.id = c.policy_id JOIN claim_payments cp ON cp.claim_id = c.id GROUP BY c.id HAVING SUM(cp.amount) > p.coverage_limit_usd ORDER BY total_paid - p.coverage_limit_usd DESC",
         200),
        ("adjuster-conduct",
         "SELECT c.adjuster_id, a.name, SUM(c.status = 'approved') AS approved, SUM(c.status IN ('approved','denied')) AS decided, ROUND(1.0 * SUM(c.status = 'approved') / SUM(c.status IN ('approved','denied')), 3) AS approval_rate, ROUND(AVG(CASE WHEN c.status = 'approved' THEN c.amount_approved END), 0) AS avg_approved FROM claims c JOIN adjusters a ON a.id = c.adjuster_id GROUP BY c.adjuster_id HAVING decided > 50 AND approval_rate > 0.98 AND avg_approved > (SELECT AVG(amount_approved) FROM claims WHERE status = 'approved') ORDER BY approval_rate DESC",
         6),
        ("fnol-narrative-consistency",
         "SELECT c.id, c.kind, c.damage_area, c.fnol_narrative FROM claims c JOIN (SELECT repair_shop_id, claimant_phone FROM claims WHERE repair_shop_id IS NOT NULL GROUP BY repair_shop_id, claimant_phone HAVING COUNT(*) >= 6 AND COUNT(DISTINCT policy_id) >= 6) ring ON c.repair_shop_id = ring.repair_shop_id AND c.claimant_phone = ring.claimant_phone ORDER BY c.repair_shop_id, c.claimant_phone",
         48),
        ("serial-reenrollment",
         "WITH payouts AS MATERIALIZED (SELECT ci.policy_id, MAX(cp.date) AS last_payout FROM claims ci JOIN claim_payments cp ON cp.claim_id = ci.id GROUP BY ci.policy_id), pol AS MATERIALIZED (SELECT p.id, p.holder_name, p.start_date, substr(p.policyholder_address, instr(p.policyholder_address,' ')+1) AS residence, po.last_payout FROM policies p LEFT JOIN payouts po ON po.policy_id = p.id), multi AS (SELECT residence FROM pol GROUP BY residence HAVING COUNT(*) >= 2), links AS (SELECT a.residence, a.id AS prior_policy, a.holder_name AS prior_name, b.id AS next_policy, b.holder_name AS next_name FROM pol a JOIN pol b ON a.residence = b.residence AND a.id <> b.id WHERE a.residence IN (SELECT residence FROM multi) AND a.last_payout IS NOT NULL AND b.start_date > a.last_payout AND julianday(b.start_date) - julianday(a.last_payout) BETWEEN 0 AND 60 AND a.holder_name <> b.holder_name) SELECT residence, COUNT(*) AS serial_reenrollments, GROUP_CONCAT(DISTINCT prior_name) AS name_variants_seen FROM links GROUP BY residence HAVING COUNT(*) >= 2 ORDER BY serial_reenrollments DESC",
         8),
    ],
    "ledger": [
        ("intercompany-reconciliation",
         "SELECT a.entity_id AS entity_a, b.entity_id AS entity_b, a.recv AS receivable, b.pay AS payable, ROUND(a.recv - b.pay, 2) AS diff FROM (SELECT entity_id, intercompany_entity_id, SUM(CASE WHEN side='dr' THEN amount ELSE -amount END) AS recv FROM gl_entries WHERE account_code='1010' GROUP BY entity_id, intercompany_entity_id) a JOIN (SELECT entity_id, intercompany_entity_id, SUM(CASE WHEN side='cr' THEN amount ELSE -amount END) AS pay FROM gl_entries WHERE account_code='2010' GROUP BY entity_id, intercompany_entity_id) b ON a.entity_id = b.intercompany_entity_id AND a.intercompany_entity_id = b.entity_id WHERE ABS(a.recv - b.pay) > 1000",
         30),
        ("revenue-misclassification",
         "SELECT g.id, g.entity_id, g.account_code, a.name AS account_name, a.class AS account_class, g.amount, g.memo FROM gl_entries g JOIN chart_of_accounts a ON g.account_code = a.code WHERE a.class = 'expense' AND g.memo LIKE '%Sales revenue%'",
         500),
        ("lei-remediation",
         "SELECT cp.id, cp.name, cp.country, cp.lei, COUNT(*) AS gl_lines, ROUND(SUM(g.amount), 2) AS total_amount FROM counterparties cp JOIN gl_entries g ON g.counterparty_id = cp.id WHERE cp.lei IS NULL OR LENGTH(cp.lei) <> 20 GROUP BY cp.id HAVING SUM(g.amount) > 100000 ORDER BY total_amount DESC",
         80),
        ("batch-integrity",
         "SELECT batch_id, ROUND(SUM(CASE WHEN side='dr' THEN amount ELSE 0 END), 2) AS total_dr, ROUND(SUM(CASE WHEN side='cr' THEN amount ELSE 0 END), 2) AS total_cr, ROUND(SUM(CASE WHEN side='dr' THEN amount ELSE -amount END), 2) AS imbalance FROM gl_entries GROUP BY batch_id HAVING ABS(SUM(CASE WHEN side='dr' THEN amount ELSE 0 END) - SUM(CASE WHEN side='cr' THEN amount ELSE 0 END)) > 0.01",
         25),
        ("misfiled-revenue-memos",
         "SELECT g.id, g.entity_id, g.account_code, a.name AS account_name, g.side, g.amount, g.memo FROM gl_entries g JOIN chart_of_accounts a ON g.account_code = a.code WHERE a.class = 'expense' AND g.side = 'cr' AND (lower(g.memo) LIKE '%retainer%' OR lower(g.memo) LIKE '%subscription%' OR lower(g.memo) LIKE '%membership dues%' OR lower(g.memo) LIKE '%royalty%' OR lower(g.memo) LIKE '%advisory fee%' OR lower(g.memo) LIKE '%managed service%' OR lower(g.memo) LIKE '%hosting plan%' OR lower(g.memo) LIKE '%seat licence%' OR lower(g.memo) LIKE '%onboarding fee%' OR lower(g.memo) LIKE '%data feed%' OR lower(g.memo) LIKE '%support plan%' OR lower(g.memo) LIKE '%overage%' OR lower(g.memo) LIKE '%setup fee%' OR lower(g.memo) LIKE '%renewal uplift%' OR lower(g.memo) LIKE '%consulting engagement%' OR lower(g.memo) LIKE '%maintenance plan%')",
         500),
        ("circular-intercompany-rings",
         "WITH RECURSIVE edges AS (SELECT DISTINCT g.entity_id AS src, g.intercompany_entity_id AS dst FROM gl_entries g JOIN chart_of_accounts a ON g.account_code = a.code WHERE a.class = 'revenue' AND g.intercompany_entity_id IS NOT NULL), walk(start, node, hops, path, closed) AS (SELECT src, dst, 1, '|'||src||'|'||dst||'|', CASE WHEN dst = src THEN 1 ELSE 0 END FROM edges UNION ALL SELECT w.start, e.dst, w.hops + 1, w.path||e.dst||'|', CASE WHEN e.dst = w.start THEN 1 ELSE 0 END FROM walk w JOIN edges e ON e.src = w.node WHERE w.closed = 0 AND w.hops < 12 AND (e.dst = w.start OR (e.dst > w.start AND instr(w.path, '|'||e.dst||'|') = 0))) SELECT start AS cycle_min_entity, hops AS cycle_length, path AS ring_path FROM walk WHERE closed = 1 ORDER BY start",
         3),
    ],
    "freight": [
        ("three-way-match",
         "SELECT i.id AS invoice_id, i.po_id, i.amount_usd AS invoiced, p.amount_usd AS po_amount, ROUND(i.amount_usd / p.amount_usd, 2) AS ratio FROM invoices i JOIN purchase_orders p ON p.id = i.po_id WHERE i.amount_usd > p.amount_usd * 1.15 ORDER BY ratio DESC",
         400),
        ("ghost-shipment",
         "SELECT i.id AS invoice_id, i.amount_usd, i.paid, i.shipment_id FROM invoices i LEFT JOIN shipments s ON s.id = i.shipment_id WHERE i.paid IS NOT NULL AND (i.shipment_id IS NULL OR (s.delivered_ts IS NULL AND NOT EXISTS (SELECT 1 FROM customs_declarations c WHERE c.shipment_id = s.id)))",
         150),
        ("denied-party",
         "SELECT id AS declaration_id, shipment_id, consignee_name, hs_code, declared_value_usd, country FROM customs_declarations WHERE consignee_name IN ('Viktor Sokolov','Ivan Petrov','Sergei Volkov','Nadia Popova','Andrei Marchenko','Pavel Ivanov') ORDER BY declared_value_usd DESC",
         30),
        ("lane-performance",
         "SELECT origin, destination, COUNT(*) AS shipments, ROUND(AVG(julianday(delivered_ts) - julianday(eta)), 1) AS avg_days_late FROM shipments WHERE delivered_ts IS NOT NULL GROUP BY origin, destination HAVING avg_days_late >= 5 AND shipments >= 50 ORDER BY avg_days_late DESC",
         5),
        ("hs-misdeclaration",
         "WITH tagged AS (SELECT c.id AS declaration_id, c.hs_code, substr(c.hs_code,1,2) AS declared_chapter, c.goods_description, (SELECT h.chapter FROM hs_catalog h WHERE c.goods_description LIKE '%'||h.keyword||'%' LIMIT 1) AS described_chapter FROM customs_declarations c) SELECT declaration_id, hs_code, declared_chapter, described_chapter, goods_description FROM tagged WHERE described_chapter IS NOT NULL AND described_chapter <> declared_chapter ORDER BY declaration_id",
         90),
        ("transshipment-watchlist",
         "WITH watch(surname) AS (VALUES ('Sokolov'),('Petrov'),('Volkov'),('Popova'),('Marchenko'),('Ivanov')) SELECT s1.container_id, s1.id AS leg1_id, s2.id AS leg2_id, s1.origin AS leg1_origin, s1.destination AS transship_via, s2.destination AS final_dest, s2.consignee_name FROM shipments s1 JOIN shipments s2 ON s1.container_id=s2.container_id AND s1.id<s2.id AND s1.destination=s2.origin JOIN watch w ON s2.consignee_name LIKE '%'||w.surname||'%' WHERE s1.destination IN ('Dubai','Singapore','Jebel Ali') ORDER BY s1.container_id",
         18),
    ],
    "market": [
        ("review-ring",
         "SELECT l.seller_id, COUNT(DISTINCT rv.buyer_id) AS ring_buyers, COUNT(*) AS fake_five_stars FROM reviews rv JOIN listings l ON l.id = rv.listing_id WHERE rv.rating = 5 AND rv.verified_purchase = 0 GROUP BY l.seller_id HAVING COUNT(DISTINCT rv.buyer_id) >= 8 AND COUNT(*) >= 30 ORDER BY fake_five_stars DESC",
         10),
        ("refund-abuse",
         "SELECT o.buyer_id, COUNT(*) AS orders, COUNT(rf.id) AS refunds, ROUND(COUNT(rf.id)*1.0/COUNT(*), 2) AS refund_rate, COUNT(DISTINCT l.seller_id) AS distinct_sellers FROM orders o JOIN listings l ON l.id = o.listing_id LEFT JOIN refunds rf ON rf.order_id = o.id GROUP BY o.buyer_id HAVING COUNT(*) >= 10 AND COUNT(rf.id)*1.0/COUNT(*) > 0.4 AND COUNT(DISTINCT l.seller_id) >= 5 ORDER BY refund_rate DESC",
         55),
        ("counterfeit-triage",
         "WITH ranked AS (SELECT category, price_usd, ROW_NUMBER() OVER (PARTITION BY category ORDER BY price_usd) AS rn, COUNT(*) OVER (PARTITION BY category) AS cnt FROM listings), med AS (SELECT category, price_usd AS median_price FROM ranked WHERE rn = cnt/2 + 1) SELECT li.id, li.seller_id, li.category, li.price_usd, med.median_price, s.joined, li.created FROM listings li JOIN med ON med.category = li.category JOIN sellers s ON s.id = li.seller_id WHERE li.price_usd < 0.4*med.median_price AND julianday(li.created) - julianday(s.joined) BETWEEN 0 AND 89 ORDER BY li.price_usd/med.median_price",
         250),
        ("brushing",
         "SELECT l.seller_id, o.ship_address_hash, COUNT(*) AS burst_orders, COUNT(DISTINCT o.buyer_id) AS linked_buyers FROM orders o JOIN listings l ON l.id = o.listing_id GROUP BY l.seller_id, o.ship_address_hash HAVING COUNT(*) >= 10 AND COUNT(DISTINCT o.buyer_id) BETWEEN 2 AND 8 ORDER BY burst_orders DESC",
         15),
        ("review-near-duplicate",
         "SELECT rv.id AS review_id, l.seller_id, rv.verified_purchase FROM reviews rv JOIN listings l ON l.id = rv.listing_id WHERE rv.review_text LIKE '%love%' AND rv.review_text LIKE '%fast%' AND rv.review_text LIKE '%better than%' AND rv.review_text LIKE '%recommend%'",
         500),
        ("price-coordination",
         "WITH moves AS (SELECT listing_id, date(ts) AS d, CASE WHEN price_usd > LAG(price_usd) OVER (PARTITION BY listing_id ORDER BY ts) THEN 1 WHEN price_usd < LAG(price_usd) OVER (PARTITION BY listing_id ORDER BY ts) THEN -1 ELSE 0 END AS dir FROM listing_price_history), m AS (SELECT listing_id, d, dir FROM moves WHERE dir <> 0) SELECT a.listing_id AS l1, b.listing_id AS l2, la.seller_id AS s1, lb.seller_id AS s2, la.category, COUNT(*) AS co_moves FROM m a JOIN m b ON a.d = b.d AND a.dir = b.dir AND a.listing_id < b.listing_id JOIN listings la ON la.id = a.listing_id JOIN listings lb ON lb.id = b.listing_id WHERE la.category = lb.category AND la.seller_id <> lb.seller_id GROUP BY a.listing_id, b.listing_id HAVING COUNT(*) >= 8 ORDER BY co_moves DESC",
         20),
    ],
}


@pytest.mark.parametrize("cid", sorted(_NAMES))
def test_company_terms_present(cid: str) -> None:
    """Every sandbox company emits a Terms of Sensitive Data Use file that names the company and
    reads like a policy (≥500 chars, at least one 'must' directive)."""
    if not (_OUT / "terms" / f"{cid}_terms.md").exists():
        pytest.skip(f"terms/{cid}_terms.md not generated — run scripts/seed.py {cid}")
    text = company_terms(cid)
    assert text and len(text) >= 500, f"{cid} terms too short"
    assert _NAMES[cid] in text, f"{cid} terms do not name the company"
    assert any("must" in ln.lower() for ln in text.splitlines()), f"{cid} terms have no directive line"


def test_intake_defaults_policy_sources_to_company_terms() -> None:
    """Stage-0 guard: a sandbox job with a company but no explicit policy defaults its policy sources
    to that company's terms; an explicit policy always wins."""
    if company_terms("bank") is None:
        pytest.skip("bank terms not generated — run scripts/seed.py bank")
    src = resolve_policy_sources({"spec": {"request": "flag dormant accounts", "company": "bank"},
                                  "policy": None})
    assert len(src) == 1 and src[0]["kind"] == "doc"
    assert src[0]["ref"] == "terms/bank_terms.md"
    assert len(src[0]["text"]) >= 500 and "Meridian Bank" in src[0]["text"]
    # explicit policy wins — no company default injected
    explicit = [{"kind": "text", "ref": "typed"}]
    assert resolve_policy_sources({"spec": {"company": "bank"},
                                   "policy": {"sources": explicit}}) == explicit
    # no company → no default
    assert resolve_policy_sources({"spec": {"request": "x"}, "policy": None}) == []


@pytest.mark.parametrize("dataset", sorted(EVIDENCE))
def test_planted_patterns_fire(dataset: str) -> None:
    db_path = _OUT / f"{dataset}.db"
    if not db_path.exists():
        pytest.skip(f"{db_path} not generated — run scripts/seed.py {dataset}")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for title, sql, expected in EVIDENCE[dataset]:
            hits = len(con.execute(sql).fetchall())
            assert hits >= expected, f"{dataset}/{title}: got {hits} hits, expected >= {expected}"
    finally:
        con.close()
