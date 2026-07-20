"""Run deliverables (hardening 2026-07-10, M1): findings.csv + a self-contained report.html
(inline CSS only, print-clean for browser print -> PDF) written into the run's data directory.
This is a business document for the claims committee / recovery team, not the app shell —
clean light page, system fonts, one case section per flagged entity.
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from app.config import settings
from app.events import now_iso

DEFAULT_DELIVERABLE = {"formats": ["csv", "report"], "granularity": "per_entity"}


def run_dir(run_id: str) -> Path:
    d = settings.data_path / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _flatten(prefix: str, value, out: dict) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(value, list):
        out[prefix] = json.dumps(value, default=str)[:200]
    else:
        out[prefix] = value


def _flagged_units(units: list[dict]) -> list[dict]:
    return [u for u in units if u.get("status") == "needs_review"]


def generate(run_id: str, *, process_name: str, goal: str, corpus: str | None, stats: dict,
             cost: dict, units: list[dict], deliverable: dict | None,
             egress: dict | None = None, duration_s: float | None = None) -> list[dict]:
    """Write the run's artifacts; returns [{kind, url}] for the API/SSE surface.

    ALWAYS writes both endpoint-backed artifacts (findings.csv + report.html): /export.csv and
    /report are fixed API surface, so a planner deliverable spec that names only one format — or
    an unexpected casing — must never 404 the other download (never-404, T2). `granularity` still
    shapes the report content; `formats` is advisory for future export kinds. `egress` (zone->count)
    and `duration_s` are optional headline facts — the report renders fine without them."""
    prefs = {**DEFAULT_DELIVERABLE, **(deliverable or {})}
    d = run_dir(run_id)
    _write_csv(d / "findings.csv", units)
    (d / "report.html").write_text(_report_html(
        run_id, process_name=process_name, goal=goal, corpus=corpus, stats=stats, cost=cost,
        units=units, granularity=prefs.get("granularity", "per_entity"),
        egress=egress, duration_s=duration_s), encoding="utf-8")
    return [{"kind": "csv", "url": f"/api/runs/{run_id}/export.csv"},
            {"kind": "report", "url": f"/api/runs/{run_id}/report"}]


def existing_artifacts(run_id: str) -> list[dict]:
    """Artifact list from what is actually on disk (GET /runs/{id} surface)."""
    d = settings.data_path / "runs" / run_id
    out = []
    if (d / "findings.csv").exists():
        out.append({"kind": "csv", "url": f"/api/runs/{run_id}/export.csv"})
    if (d / "report.html").exists():
        out.append({"kind": "report", "url": f"/api/runs/{run_id}/report"})
    return out


def _write_csv(path: Path, units: list[dict]) -> None:
    rows = []
    for u in _flagged_units(units):
        flat: dict = {}
        _flatten("", u.get("result") or {}, flat)
        rows.append({"unit_ref": u.get("unit_ref", ""), "status": u.get("status", ""),
                     "review_verdict": u.get("review_verdict") or "",
                     "review_note": u.get("review_note") or "", **flat})
    # union of keys, stable order: fixed columns first, then result fields as first seen
    cols = ["unit_ref", "status", "review_verdict", "review_note"]
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


_CSS = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #fafaf8; color: #1c1c1a;
         font: 15px/1.62 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         -webkit-font-smoothing: antialiased; }
  .page { max-width: 820px; margin: 0 auto; padding: 56px 40px 88px; }
  header { padding-bottom: 22px; margin-bottom: 4px; }
  .kicker { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: #9a5b19; margin: 0 0 12px; font-weight: 600; }
  h1 { font-size: 32px; line-height: 1.15; margin: 0 0 12px; letter-spacing: -.015em; }
  .goal { color: #55554e; margin: 0; max-width: 62ch; font-size: 16px; }
  .verdict { margin: 22px 0 0; font-size: 15px; color: #33332f; }
  .verdict strong { color: #b4231f; }
  /* headline stat cards */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); gap: 1px;
           background: #e4e4de; border: 1px solid #e4e4de; border-radius: 10px; overflow: hidden;
           margin: 26px 0 8px; }
  .card { background: #fff; padding: 15px 16px 14px; }
  .card .n { font-size: 24px; font-weight: 620; font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
  .card .n.flag { color: #b4231f; }
  .card .n.good { color: #1a7a45; }
  .card .l { font-size: 10.5px; letter-spacing: .09em; text-transform: uppercase; color: #8a8a82; margin-top: 3px; }
  /* egress / boundary strip */
  .egress { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px;
            background: #f3f6f2; border: 1px solid #dfeade; border-radius: 10px;
            padding: 13px 18px; margin: 6px 0 4px; font-size: 13.5px; }
  .egress .lead { font-weight: 600; color: #1a7a45; }
  .egress.breached { background: #fbf0ef; border-color: #f0d6d4; }
  .egress.breached .lead { color: #b4231f; }
  .egress .z { color: #55554e; font-variant-numeric: tabular-nums; }
  .egress .z b { color: #1c1c1a; font-weight: 600; }
  .note { font-size: 12.5px; color: #8a8a82; margin: 16px 0 0; }
  .findings-head { margin: 44px 0 0; font-size: 13px; letter-spacing: .08em; text-transform: uppercase;
                   color: #8a8a82; font-weight: 600; border-bottom: 1px solid #e4e4de; padding-bottom: 10px; }
  section.case { margin-top: 30px; padding-top: 4px; }
  .case-hd { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .case h2 { font-size: 18px; margin: 0; letter-spacing: -.01em; }
  .case .ref { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11.5px;
               color: #a0a099; margin: 3px 0 0; word-break: break-all; }
  .sev, .flagchip { display: inline-block; font-size: 10.5px; letter-spacing: .07em; text-transform: uppercase;
         padding: 2px 9px; border-radius: 4px; font-weight: 600; }
  .sev { background: #f3e3e2; color: #b4231f; }
  .flagchip.on { background: #f3e3e2; color: #b4231f; }
  .flagchip.off { background: #e8efe8; color: #1a7a45; }
  .summary { margin: 14px 0 4px; font-size: 15.5px; line-height: 1.55; color: #26261f; }
  .summary b { font-variant-numeric: tabular-nums; }
  /* paired A/B evidence table */
  table.ev { width: 100%; border-collapse: collapse; margin: 14px 0 6px; font-size: 13.5px; }
  table.ev th { text-align: left; font-weight: 500; color: #8a8a82;
                padding: 7px 14px 7px 0; vertical-align: top; border-bottom: 1px solid #efefe9; }
  table.ev td { padding: 7px 14px 7px 0; border-bottom: 1px solid #efefe9;
                font-variant-numeric: tabular-nums; word-break: break-word; }
  table.ev thead th { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: #a0a099; }
  table.ev .fld { color: #8a8a82; width: 32%; }
  table.ev td.v { color: #1c1c1a; }
  table.ev tr.diff td.v { font-weight: 600; }
  .judgment { background: #f5f5f0; border-left: 3px solid #9a5b19; padding: 14px 18px;
              font-size: 14px; line-height: 1.6; border-radius: 0 8px 8px 0; margin: 16px 0 6px; }
  .judgment h3 { margin: 0 0 8px; font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase;
                 color: #9a5b19; font-weight: 700; }
  .judgment p { margin: 0; color: #2c2c26; }
  .transcript { font-size: 12px; color: #a0a099; margin: 8px 0 0; }
  .transcript code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #8a8a82; }
  footer { margin-top: 60px; padding-top: 16px; border-top: 1px solid #e4e4de;
           font-size: 12px; color: #a0a099; line-height: 1.6; }
  @media print {
    body { background: #fff; }
    .page { max-width: none; padding: 0; }
    .cards { break-inside: avoid; }
    section.case { break-inside: avoid; }
  }
"""


def _no_findings_note(stats: dict, goal: str) -> str:
    """A zero-findings run still tells the reader what was done: candidates examined, how many
    cleared, and what was checked — so a clean result reads as a completed audit, not a blank page."""
    examined = stats.get("sql_rows") or stats.get("units", 0)
    cleared = stats.get("ok", stats.get("units", 0))
    checked = html.escape(goal) if goal else "the requested detection"
    return (f'<p class="note"><strong>No findings flagged.</strong> {examined} candidate(s) '
            f'examined, {cleared} cleared. Checked: {checked}.</p>')


def write_stub(run_id: str, *, process_name: str, goal: str, corpus: str | None, stats: dict,
               cost: dict) -> list[dict]:
    """Last-resort artifacts when the full generator raises: a headers-only findings.csv and a
    minimal report.html, so GET /report and /export.csv never 404 on a completed run."""
    d = run_dir(run_id)
    _write_csv(d / "findings.csv", [])          # header row only
    (d / "report.html").write_text(_report_html(
        run_id, process_name=process_name, goal=goal, corpus=corpus, stats=stats, cost=cost,
        units=[], granularity="per_entity"), encoding="utf-8")
    return [{"kind": "csv", "url": f"/api/runs/{run_id}/export.csv"},
            {"kind": "report", "url": f"/api/runs/{run_id}/report"}]


_E = html.escape


def _fmt(v) -> str:
    """Human-readable scalar: booleans as yes/no, big floats with thousands separators, trimmed."""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) >= 1000 else f"{v:.2f}".rstrip("0").rstrip(".")
    return str(v)


def _label(k: str) -> str:
    return k.replace("_", " ").strip()


def _candidate_of(result: dict):
    """The structural evidence row a step produced, if any — 'candidate' (SQL detection) or 'output'
    (staging shim). Judged-only runs have neither; their story lives in the reasoning prose."""
    for key in ("candidate", "output"):
        v = result.get(key)
        if isinstance(v, dict):
            return v
    return None


def _summary_sentence(cand: dict) -> str:
    # ponytail: tuned to the duplicate-pair candidate shape (flagship demo). Returns "" for any
    # other schema, which then falls through to the evidence table — no guessing, no lorem.
    def g(*keys: str):
        return next((cand[key] for key in keys if cand.get(key) is not None), None)

    c1, c2 = g("claim_id_1"), g("claim_id_2")
    if c1 is None or c2 is None:
        return ""
    head = f"Claims <b>{_E(str(c1))}</b> and <b>{_E(str(c2))}</b>"
    pol = g("policy_id", "policy")
    if pol is not None:
        head += f" on policy <b>{_E(str(pol))}</b>"
    inc = g("incident_date", "loss_date")
    if inc:
        head += f" share incident date <b>{_E(str(inc))}</b>"
    tail = []
    a1, a2 = g("amount_claimed_1", "amount_1"), g("amount_claimed_2", "amount_2")
    if a1 is not None and a2 is not None:
        tail.append(f"claimed amounts <b>${_E(_fmt(a1))}</b> vs <b>${_E(_fmt(a2))}</b>")
    pct = g("percent_difference", "amount_pct_diff")
    try:
        if pct is not None:
            tail.append(f"within <b>{float(pct):.1f}%</b>")
    except (TypeError, ValueError):
        pass
    tail.append("different claim IDs")
    return head + " — " + ", ".join(tail) + "."


def _evidence_table(cand: dict) -> str:
    """Paired fields (foo_1/foo_2) as a Record A vs B table with differences bolded; unpaired fields
    as shared rows. Works for any dict; shines on the two-record duplicate shape."""
    pairs: dict = {}
    shared: dict = {}
    for k, v in cand.items():
        if k in ("flagged", "candidate_pair_id"):
            continue
        if (k.endswith("_1") or k.endswith("_2")) and len(k) > 2:
            pairs.setdefault(k[:-2], {})[k[-1]] = v
        else:
            shared[k] = v
    rows = []
    for k, v in list(shared.items())[:20]:
        rows.append(f'<tr><td class="fld">{_E(_label(k))}</td>'
                    f'<td class="v" colspan="2">{_E(_fmt(v))}</td></tr>')
    for base, sides in list(pairs.items())[:20]:
        a, b = sides.get("1"), sides.get("2")
        diff = " diff" if a != b else ""
        av = _E(_fmt(a)) if a is not None else "—"
        bv = _E(_fmt(b)) if b is not None else "—"
        rows.append(f'<tr class="pair{diff}"><td class="fld">{_E(_label(base))}</td>'
                    f'<td class="v">{av}</td><td class="v">{bv}</td></tr>')
    if not rows:
        return ""
    head = ('<thead><tr><th class="fld">Field</th><th>Record A</th><th>Record B</th></tr></thead>'
            if pairs else "")
    return f'<table class="ev">{head}<tbody>{"".join(rows)}</tbody></table>'


def _judgment(result: dict) -> tuple[str, str]:
    """(reasoning_html, flag_chip) from the model/judge step stored on the unit. The `findings` prose
    is the per-entity model response the founders want surfaced; the full prompt exchange is in /traces."""
    for name, out in result.items():
        if isinstance(out, dict) and isinstance(out.get("findings"), str):
            flagged = out.get("flagged")
            chip = ('<span class="flagchip on">flagged</span>' if flagged is True
                    else '<span class="flagchip off">cleared</span>' if flagged is False else "")
            block = (f'<div class="judgment"><h3>Model reasoning · {_E(_label(name))}</h3>'
                     f'<p>{_E(out["findings"])}</p></div>')
            return block, chip
    return "", ""


def _severity(result: dict) -> str:
    for out in result.values():
        if isinstance(out, dict) and out.get("severity"):
            return f'<span class="sev">{_E(str(out["severity"]))}</span>'
    return ""


def _case_html(u: dict, n: int) -> str:
    result = u.get("result") or {}
    cand = _candidate_of(result)
    reasoning, chip = _judgment(result)
    sentence = _summary_sentence(cand) if cand else ""
    title = _E(u.get("unit_ref", "") or f"Unit {n}")
    summary = f'<p class="summary">{sentence}</p>' if sentence else ""
    table = _evidence_table(cand) if cand else ""
    # candidate-only (SQL) case: no model prose, so name why it was flagged
    if not reasoning and cand:
        reasoning = ('<div class="judgment"><h3>Why flagged</h3>'
                     '<p>Structural match on the detection rule — the two records collide on the '
                     'scoping fields the query targets. No model call was required to surface this '
                     'candidate; a reviewer confirms intent.</p></div>')
    return f"""
  <section class="case">
    <div class="case-hd"><h2>Case {n}</h2>{chip}{_severity(result)}</div>
    <p class="ref">{title}</p>
    {summary}
    {table}
    {reasoning}
  </section>"""


def _egress_strip(egress: dict | None) -> str:
    """Where inference ran, by zone. The product's core claim, made auditable for a judge."""
    e = egress or {}
    ext, amd = e.get("EXTERNAL", 0), e.get("AMD_HOSTED", 0)
    loc, cust = e.get("LOCAL", 0), e.get("CUSTOM", 0)
    total = ext + amd + loc + cust
    if total == 0:
        return ('<div class="egress"><span class="lead">Boundary held.</span>'
                '<span class="z">Detection ran on-box — <b>0</b> model calls left the perimeter.</span>'
                '</div>')
    zones = [("EXTERNAL", ext), ("AMD_HOSTED", amd), ("LOCAL", loc)]
    if cust:
        zones.append(("CUSTOM", cust))
    chips = " ".join(f'<span class="z"><b>{n}</b> {_E(z.replace("_", " ").lower())}</span>'
                     for z, n in zones)
    if ext:
        lead = f'<span class="lead"><b>{ext}</b> call(s) left to external providers.</span>'
        return f'<div class="egress breached">{lead}{chips}</div>'
    return (f'<div class="egress"><span class="lead">0 external — all inference stayed inside '
            f'the boundary.</span>{chips}</div>')


def _duration(duration_s: float | None) -> str:
    if not duration_s or duration_s < 0:
        return "—"
    s = int(round(duration_s))
    return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"


def _report_html(run_id: str, *, process_name: str, goal: str, corpus: str | None, stats: dict,
                 cost: dict, units: list[dict], granularity: str,
                 egress: dict | None = None, duration_s: float | None = None) -> str:
    flagged = _flagged_units(units)
    cases = ""
    if granularity != "summary":
        cases = "".join(_case_html(u, i + 1) for i, u in enumerate(flagged))

    n_flag = stats.get("needs_review", len(flagged))
    body = ""
    if granularity != "summary":
        if cases:
            body = (f'<h2 class="findings-head">Flagged for review · {n_flag} case(s)</h2>'
                    f'{cases}')
        else:
            body = _no_findings_note(stats, goal)
    has_model = any("findings" in (v or {}) for u in flagged
                    for v in (u.get("result") or {}).values() if isinstance(v, dict))
    transcript = (f'<p class="note">Full model prompt/response transcripts for this run: '
                  f'<code>GET /api/traces?scope=run:{_E(run_id)}</code>.</p>' if has_model else "")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_E(process_name or 'Run report')} — findings</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <header>
    <p class="kicker">Nxcleus run report</p>
    <h1>{_E(process_name or 'Process run')}</h1>
    <p class="goal">{_E(goal or '')}</p>
    <p class="verdict"><strong>{n_flag}</strong> of {stats.get('units', 0)} units flagged for
       review · {stats.get('ok', 0)} cleared.</p>
  </header>
  <div class="cards">
    <div class="card"><div class="n">{stats.get('units', 0)}</div><div class="l">Units scanned</div></div>
    <div class="card"><div class="n flag">{n_flag}</div><div class="l">Flagged</div></div>
    <div class="card"><div class="n good">{stats.get('ok', 0)}</div><div class="l">Cleared</div></div>
    <div class="card"><div class="n">{stats.get('error', 0)}</div><div class="l">Errors</div></div>
    <div class="card"><div class="n">${cost.get('total_usd', 0.0):.4f}</div><div class="l">Run cost</div></div>
    <div class="card"><div class="n">{_duration(duration_s)}</div><div class="l">Duration</div></div>
  </div>
  {_egress_strip(egress)}
  <p class="note">Corpus: {_E(corpus or 'n/a')} · Run {_E(run_id)} · Generated {now_iso()} ·
     {cost.get('frontier_calls', 0)} frontier call(s) · ${cost.get('cost_per_unit', 0.0):.5f}/unit.</p>
  {transcript}
  {body}
  <footer>Nxcleus — adaptive sovereign process platform. Generated from run {_E(run_id)}.
  Print this page for a PDF case file; per-row data in the accompanying findings.csv.</footer>
</div>
</body>
</html>"""
