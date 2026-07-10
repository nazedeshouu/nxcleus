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
             cost: dict, units: list[dict], deliverable: dict | None) -> list[dict]:
    """Write the run's artifacts; returns [{kind, url}] for the API/SSE surface.

    ALWAYS writes both endpoint-backed artifacts (findings.csv + report.html): /export.csv and
    /report are fixed API surface, so a planner deliverable spec that names only one format — or
    an unexpected casing — must never 404 the other download (never-404, T2). `granularity` still
    shapes the report content; `formats` is advisory for future export kinds."""
    prefs = {**DEFAULT_DELIVERABLE, **(deliverable or {})}
    d = run_dir(run_id)
    _write_csv(d / "findings.csv", units)
    (d / "report.html").write_text(_report_html(
        run_id, process_name=process_name, goal=goal, corpus=corpus, stats=stats, cost=cost,
        units=units, granularity=prefs.get("granularity", "per_entity")), encoding="utf-8")
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
         font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .page { max-width: 780px; margin: 0 auto; padding: 56px 32px 80px; }
  header { border-bottom: 2px solid #1c1c1a; padding-bottom: 24px; margin-bottom: 8px; }
  .kicker { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: #8a8a82; margin: 0 0 10px; }
  h1 { font-size: 30px; line-height: 1.2; margin: 0 0 10px; letter-spacing: -.01em; }
  .goal { color: #55554e; margin: 0; max-width: 60ch; }
  .meta { display: flex; flex-wrap: wrap; gap: 28px; padding: 20px 0; border-bottom: 1px solid #e4e4de; }
  .meta div { min-width: 90px; }
  .meta .n { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .meta .n.flag { color: #b4231f; }
  .meta .l { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: #8a8a82; }
  .note { font-size: 13px; color: #8a8a82; margin: 14px 0 0; }
  section.case { margin-top: 40px; padding-top: 28px; border-top: 1px solid #e4e4de; }
  .case h2 { font-size: 17px; margin: 0 0 4px; }
  .case .ref { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
               color: #8a8a82; margin: 0 0 16px; }
  .sev { display: inline-block; font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
         padding: 2px 8px; border-radius: 3px; background: #f3e3e2; color: #b4231f; margin-left: 8px; }
  table.ev { width: 100%; border-collapse: collapse; margin: 8px 0 16px; font-size: 13.5px; }
  table.ev th { text-align: left; font-weight: 500; color: #8a8a82; width: 34%;
                padding: 6px 12px 6px 0; vertical-align: top; border-bottom: 1px solid #efefe9; }
  table.ev td { padding: 6px 0; border-bottom: 1px solid #efefe9;
                font-variant-numeric: tabular-nums; word-break: break-word; }
  .judgment { background: #f4f4ef; border-left: 3px solid #1c1c1a; padding: 12px 16px;
              font-size: 14px; }
  .judgment h3 { margin: 0 0 6px; font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
                 color: #8a8a82; font-weight: 600; }
  footer { margin-top: 56px; padding-top: 16px; border-top: 1px solid #e4e4de;
           font-size: 12px; color: #8a8a82; }
  @media print {
    body { background: #fff; }
    .page { max-width: none; padding: 0; }
    section.case { page-break-before: always; border-top: none; }
    section.case:first-of-type { page-break-before: auto; }
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


def _dl_table(row: dict) -> str:
    cells = []
    flat: dict = {}
    _flatten("", row, flat)
    for k, v in list(flat.items())[:24]:
        cells.append(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>")
    return f'<table class="ev">{"".join(cells)}</table>' if cells else ""


def _report_html(run_id: str, *, process_name: str, goal: str, corpus: str | None, stats: dict,
                 cost: dict, units: list[dict], granularity: str) -> str:
    flagged = _flagged_units(units)
    cases = []
    if granularity != "summary":
        for u in flagged:
            result = u.get("result") or {}
            evidence = result.get("candidate") if isinstance(result.get("candidate"), dict) else None
            judgments = {k: v for k, v in result.items() if k != "candidate"}
            severity = ""
            for step_out in result.values():
                if isinstance(step_out, dict) and step_out.get("severity"):
                    severity = str(step_out["severity"])
                    break
            sev_html = f'<span class="sev">{html.escape(severity)}</span>' if severity else ""
            judgment_html = ""
            if judgments:
                body = "".join(_dl_table(v) if isinstance(v, dict)
                               else f"<p>{html.escape(str(v))}</p>" for v in judgments.values())
                judgment_html = f'<div class="judgment"><h3>Judgment</h3>{body}</div>'
            cases.append(f"""
  <section class="case">
    <h2>Case — {html.escape(u.get('unit_ref', ''))}{sev_html}</h2>
    <p class="ref">{html.escape(u.get('id', ''))}</p>
    {_dl_table(evidence) if evidence else ""}
    {judgment_html}
  </section>""")

    per_unit = cost.get("cost_per_unit", 0.0)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(process_name or 'Run report')} — findings</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <header>
    <p class="kicker">Nxcleus run report</p>
    <h1>{html.escape(process_name or 'Process run')}</h1>
    <p class="goal">{html.escape(goal or '')}</p>
  </header>
  <div class="meta">
    <div><div class="n">{stats.get('units', 0)}</div><div class="l">Units</div></div>
    <div><div class="n">{stats.get('ok', 0)}</div><div class="l">Clear</div></div>
    <div><div class="n flag">{stats.get('needs_review', 0)}</div><div class="l">Flagged</div></div>
    <div><div class="n">{stats.get('error', 0)}</div><div class="l">Errors</div></div>
    <div><div class="n">${cost.get('total_usd', 0.0):.4f}</div><div class="l">Run cost</div></div>
    <div><div class="n">${per_unit:.5f}</div><div class="l">Per unit</div></div>
    <div><div class="n">{cost.get('frontier_calls', 0)}</div><div class="l">Frontier calls</div></div>
  </div>
  <p class="note">Corpus: {html.escape(corpus or 'n/a')} · Run {html.escape(run_id)} ·
     Generated {now_iso()} · All inference executed inside the boundary.</p>
  {''.join(cases) if cases else _no_findings_note(stats, goal)
    if granularity != 'summary' else ''}
  <footer>Nxcleus — adaptive sovereign process platform. This report was generated from run
  {html.escape(run_id)}; print this page for a PDF case file.</footer>
</div>
</body>
</html>"""
