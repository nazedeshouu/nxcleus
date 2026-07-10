"""Judge sandbox router (06 §2, 09). Three synthetic companies with suggested prompts; a run enters
the FIFO queue and streams the standard Build view. Company datasets are read-only SQLite files under
infra/seeds/out/ (generated in the seeds zone); until seeded, table browsing returns empty.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import client_hash, sandbox_session
from app.config import REPO_ROOT
from app.db import dao
from app.sandbox.queue import sandbox_queue

router = APIRouter(tags=["sandbox"])

_SEEDS_DIR = REPO_ROOT / "infra" / "seeds" / "out"

COMPANIES = [
    {"id": "bank", "name": "Meridian Bank", "industry": "Retail banking",
     "prompts": ["Flag dormant accounts with unusual reactivation patterns and rank by risk",
                 "Detect structuring-shaped deposit runs across transactions",
                 "Screen customers against the sanctions-adjacent name list",
                 "Read the memo on every deposit and flag any account whose cluster of small repeated deposits carries mutually contradictory stated purposes for the same counterparty - e.g. one payer described as payroll, then a vehicle sale, then a wedding gift within a single week.",
                 "Trace money through internal account-to-account transfers and flag layering chains: a run of at least four hops within a few days each, where the amount shrinks a little at every hop before the funds leave the bank as an external outbound."]},
    {"id": "clinic", "name": "Aurora Clinic", "industry": "Healthcare",
     "prompts": ["Find duplicate-billing shapes across encounters",
                 "Flag impossible vitals as data-quality issues",
                 "List overdue-screening cohorts by patient",
                 "Read each visit note and weigh what it describes against the complexity level of its billed CPT code in the catalog; flag encounters whose note plainly describes a brief, routine visit yet are billed a high-complexity code.",
                 "Reconcile each provider's schedule from the start and end times and flag impossible double-bookings - the same provider recorded in two different departments at overlapping times on the same day."]},
    {"id": "lawfirm", "name": "Hale & Ostrom", "industry": "Legal services",
     "prompts": ["Extract renewal dates and auto-renew clauses across all contracts; flag notice windows under 60 days",
                 "Find contracts missing signature blocks",
                 "Detect fee-cap breaches in billing entries",
                 "Read each contract in full and flag documents that contradict themselves - for example a clause capping each party's total liability while a later indemnity clause promises to cover all losses without limit and to override any cap in the agreement.",
                 "For every contract, read the base agreement together with all of its amendments in effective-date order and flag contracts where two amendments set conflicting terms on the same clause and the later amendment is silent on which one controls."]},
    {"id": "exchange", "name": "Ashford Mercantile Exchange",
     "industry": "Futures & commodities exchange",
     "prompts": ["Detect spoofing: bursts of large same-side orders placed and cancelled within seconds, followed by an opposite-side fill",
                 "Flag wash trades: matched buy and sell fills of the same instrument, quantity and price within seconds across two accounts held by the same owner, ranked by owner",
                 "Review marking-the-close: aggressive buy fills concentrated in the final minutes of month-end sessions at escalating prices",
                 "Report position-limit breaches: accounts whose cumulative net filled quantity in one instrument exceeds its position limit",
                 "Read the desk-chat messages in the comms table alongside the order blotter. For each spoofing burst (an account firing >=6 large same-side orders it cancels within seconds), read the messages that account exchanged with any counterparty in the minutes just before the burst, and flag the bursts that were preceded by chatter whose MEANING signals intent to post orders they always meant to pull -- faking book pressure while the real trade goes the other way. Do not flag ordinary fill reports, liquidity colour, risk-limit or lunch chatter.",
                 "Treat each shared clearing_ref prefix as a possible concert party of separately-owned accounts. For every (prefix, instrument), reconcile the group's COMBINED net filled position against that instrument's position limit. Flag the prefixes where four or more different owners each individually sit under the per-account cap, yet their combined net long position breaches the instrument limit -- a single large position deliberately split across nominee accounts to stay under the line."]},
    {"id": "insurer", "name": "Cascadia Mutual", "industry": "Auto & property insurance",
     "prompts": ["Flag duplicate claims filed against the same policy for one incident — same incident date, amounts within 5%, different claim IDs",
                 "Detect staged-accident rings where unrelated policies funnel claims through one repair shop and claimant phone inside a tight window",
                 "Audit claims whose total payments exceed the policy's coverage limit",
                 "Rank adjusters by approval rate and average payout to flag those rubber-stamping claims above the peer mean",
                 "Read the first-notice-of-loss narrative (claims.fnol_narrative) on each claim and flag any claim whose described mechanism or point of impact contradicts the structured claims.damage_area - for example a story about being struck from behind or the lower level flooding on a claim coded to front or exterior damage. Also call out any set of near-identical loss narratives filed by supposedly unrelated policyholders.",
                 "Resolve claimant identities that appear across different policies under varied name spellings (initials, nicknames, transliterations) but share a residence and an overlapping phone, then order each resolved person's policies by time and flag anyone who repeatedly opened a fresh policy within weeks of their previous claim paying out."]},
    {"id": "ledger", "name": "Aldgate Holdings plc", "industry": "Multinational group finance",
     "prompts": ["Reconcile intercompany receivable and payable balances across all entity pairs and flag mismatches above materiality",
                 "Find journal lines booked to expense-class accounts whose memos clearly describe sales revenue",
                 "List counterparties with material ledger activity but a missing or malformed LEI",
                 "Audit journal batches where total debits do not equal total credits",
                 "Read the memo on every journal line that is a credit to an expense account and flag the ones whose narrative describes revenue earned from a customer (a retainer, subscription, licence, royalty, advisory, hosting, support or service fee we billed and collected) rather than a legitimate cost recovery such as a supplier refund, rebate, credit note or accrual release. The narrative contradicts the account: money we earned from a client has been posted to a cost account instead of a revenue account.",
                 "Treat every intra-group service billing between subsidiaries as a directed edge (the entity booking the revenue points at the entity it billed) and follow the edges to find any closed loop that returns to its origin (A bills B, B bills C, C bills A). Flag those rings: each recognises revenue for the same value chased around the loop, inflating consolidated group revenue while every member's cash nets to zero, so the revenue must eliminate on consolidation."]},
    {"id": "freight", "name": "Northgate Freight", "industry": "Freight & logistics",
     "prompts": ["Flag invoices billed more than 15% over their matching purchase order",
                 "Find fully-paid invoices with no delivered shipment and no customs clearance",
                 "Screen customs declaration consignees against the sanctions-adjacent watchlist",
                 "Rank origin-to-destination lanes whose deliveries chronically run past ETA",
                 "Read the free-text goods description on every customs declaration and flag any line where the plain-language goods actually describe a different commodity family than the declared HS code implies — e.g. knitted pullovers or silver ingots moving under a machinery or cocoa code. The words and the tariff code must agree; flag the ones that contradict.",
                 "Trace cargo that shares a container across two shipment legs: find moves whose first leg terminates at an innocuous intermediate port (Dubai, Singapore, Jebel Ali) and whose second leg continues from that same port to a final destination consigned to a party matching the sanctions watchlist under a slightly altered name. Link the legs by container, then screen the final leg's consignee."]},
    {"id": "market", "name": "Solano Marketplace", "industry": "E-commerce marketplace",
     "prompts": ["Surface sellers boosted by review rings — clusters of buyer accounts posting unverified 5-star reviews on the same seller within days",
                 "Flag buyers with abnormal refund rates — over 40% of 10+ orders refunded across many different sellers",
                 "Triage likely-counterfeit listings priced under 40% of their category median from sellers that joined less than 90 days before listing",
                 "Detect brushing sellers — order bursts on a seller's own listings from a small set of linked buyer accounts sharing one ship address, each followed by a 5-star review",
                 "Read the review text across each seller's listings and flag sellers whose five-star reviews are meaning-level near-duplicates of one another — every review following the same praise script (delight with the item, unusually fast shipping, a favourable comparison to a name brand, and a strong recommendation) even though the exact wording is swapped around per reviewer. That reused praise skeleton is the fingerprint of a coordinated review ring; report the sellers and the review clusters, not just individual keywords.",
                 "Reconstruct each listing's price-change timeline from the price history and surface groups of sellers within the same category whose flagship listings move price in lockstep — the same direction within hours of each other, repeatedly over many months — and separate them from the category's independently-moving baseline. Report the coordinated seller groups, not one-off matching prices."]},
]
_COMPANY_IDS = {c["id"] for c in COMPANIES}


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


def _window_expired(created_at: str | None) -> bool:
    from datetime import datetime, timedelta
    try:
        start = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(UTC) - start > timedelta(hours=1)


@router.get("/sandbox/companies")
async def companies() -> dict:
    """All datasets: the builtin seed companies plus custom BYOD datasets (uploads/connectors/
    codebases). Builtins gain origin:'builtin', kind:'rows'; custom entries carry their origin+kind
    and schema-aware suggested prompts. Additive over the wave-1 shape (nothing renamed)."""
    from app.sandbox import seeds
    out = []
    for c in COMPANIES:
        schema = seeds.company_schema(c["id"])
        out.append({**c, "origin": "builtin", "kind": "rows",
                    "suggested_prompts": c["prompts"],
                    "tables": [{"table": s["table"], "row_count": s["row_count"]} for s in schema],
                    "seeded": bool(schema)})
    for d in await dao.list_datasets():
        meta = d.get("meta") or {}
        out.append({"id": d["id"], "name": d["name"], "industry": d.get("blurb") or "",
                    "blurb": d.get("blurb") or "", "origin": d["origin"], "kind": d["kind"],
                    "prompts": meta.get("suggested_prompts", []),
                    "suggested_prompts": meta.get("suggested_prompts", []),
                    "tables": [{"table": t["name"], "row_count": t["rows"]}
                               for t in meta.get("tables", [])],
                    "seeded": bool(meta.get("tables"))})
    return {"companies": out}


@router.get("/sandbox/companies/{company_id}/tables")
async def company_tables(company_id: str) -> dict:
    from app.sandbox import seeds
    db_path = seeds.seed_db_path(company_id)      # resolves builtins AND custom BYOD datasets
    if db_path is None:
        return {"tables": [], "seeded": False}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    finally:
        con.close()
    return {"tables": [r[0] for r in rows], "seeded": True}


@router.get("/sandbox/companies/{company_id}/terms")
async def company_terms(company_id: str) -> dict:
    """Terms of Sensitive Data Use markdown for the company. Known-but-unseeded returns
    {"markdown": "", "seeded": false} (no 404); unknown ids are rejected."""
    if company_id not in _COMPANY_IDS:
        raise _err(400, "unknown company")
    from app.sandbox.seeds import company_terms as read_terms
    text = read_terms(company_id)
    return {"markdown": text or "", "seeded": text is not None}


@router.get("/sandbox/companies/{company_id}/tables/{table}")
async def browse_table(company_id: str, table: str, page: int = 0, page_size: int = 50) -> dict:
    from app.sandbox import seeds
    db_path = seeds.seed_db_path(company_id)      # resolves builtins AND custom BYOD datasets
    if db_path is None:
        return {"rows": [], "seeded": False}
    if not table.isidentifier():
        raise _err(400, "invalid table name")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(f'SELECT * FROM "{table}" LIMIT ? OFFSET ?', (page_size, page * page_size))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        con.close()
    return {"rows": rows}


@router.post("/sandbox/runs", status_code=202)
async def sandbox_run(body: dict, request: Request, response: Response,
                      session_id: str = Depends(sandbox_session)) -> dict:
    company = body.get("company")
    prompt = body.get("prompt", "")
    if company not in _COMPANY_IDS:
        raise _err(400, "unknown company")
    if not prompt:
        raise _err(400, "prompt is required")
    # per-session rate limit: 3 runs/hour, rolling window on the session row (09 §4)
    session = await dao.get_sandbox_session(session_id)
    if session is None:
        await dao.create_sandbox_session(company=company, client_hash=client_hash(request),
                                         session_id=session_id)
    else:
        if _window_expired(session.get("created_at")):
            await dao.reset_sandbox_window(session_id)
        elif (session.get("runs_used") or 0) >= 3:
            raise _err(429, "sandbox limit reached (3 runs/hour) — completed runs and replays "
                            "stay available in the gallery")
    job_id, position = await sandbox_queue.enqueue(company=company, prompt=prompt, session_id=session_id)
    await dao.incr_sandbox_runs(session_id)
    return {"job_id": job_id, "queue_position": position}


@router.get("/sandbox/queue")
async def sandbox_queue_state() -> dict:
    return sandbox_queue.queue_state()
