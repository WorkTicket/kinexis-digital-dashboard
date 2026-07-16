"""HTML rendering and download filenames for success reports."""
from __future__ import annotations

from app.success_report.branding import (
    FOCUS_CYAN,
    INK_GRAPHITE,
    MOMENTUM_CORAL,
    PROOF_GREEN,
    RISK_ROSE,
    SIGNAL_AMBER,
    _esc,
    resolve_report_accent,
)
from app.success_report.narrative import _render_narrative_html
from app.success_report.metrics import change_is_favorable


def _change_cls(key: str, ch) -> str:
    if ch is None:
        return "flat"
    fav = change_is_favorable(key, ch)
    if fav is True:
        return "up"
    if fav is False:
        return "down"
    return "flat"

def _fmt_kpi_value(key: str, val: object) -> str:
    key_l = (key or "").lower()
    if not isinstance(val, (int, float)):
        return str(val)
    if "ctr" in key_l and "cvr" not in key_l:
        # GSC ctr often stored as fraction
        display = val * 100 if val <= 1 else val
        return f"{display:.2f}%"
    if "cvr" in key_l:
        return f"{val:.2f}%"
    if "revenue" in key_l or "cost" in key_l or "conversion_value" in key_l or "cpc" in key_l:
        return f"${val:,.2f}" if abs(val) < 100 else f"${val:,.0f}"
    if isinstance(val, float) and val >= 10:
        return f"{val:,.0f}"
    if isinstance(val, float):
        return f"{val:,.1f}"
    return f"{val:,}"


def _table_rows(headers: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table class='data'><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def render_success_report_html(report: dict) -> str:
    """Printable light-theme HTML success report — cover + loop narrative."""
    client = report["client"]
    agency = report.get("agency") or {}
    agency_name = agency.get("name") or "Kinexis"
    brand = agency.get("accent") or resolve_report_accent(
        "", client.get("brand_color") or ""
    )
    logo_url = (agency.get("logo_url") or "").strip()
    is_wl = bool(agency.get("is_white_label"))
    period = report["period"]
    is_monthly = period.get("mode") == "monthly"
    title_period = (
        f"{period.get('month_name', '')} {period.get('year', '')}".strip()
        if is_monthly
        else f"{period['start']} → {period['end']}"
    )
    kind = report.get("report_kind") or "success"
    kind_label = "Diagnostic Report" if kind == "diagnostic" else "Success Report"
    doc_title = f"{client['name']} — {title_period} {kind_label}"
    industry = client.get("industry") or "Digital performance"
    generated = report.get("generated_at") or ""

    kpi_blocks = []
    for k in report["kpis"]:
        ch = k.get("change_pct")
        ch_str = f"{ch:+.1f}%" if ch is not None else "—"
        cls = _change_cls(k.get("key") or "", ch)
        display = _fmt_kpi_value(k["key"], k["current"])
        kpi_blocks.append(
            f'<div class="kpi"><div class="kpi-label">{_esc(k["label"])}</div>'
            f'<div class="kpi-value">{_esc(display)}</div>'
            f'<div class="kpi-change {cls}">{_esc(ch_str)} vs prior period</div></div>'
        )

    baseline_html = ""
    deltas = report.get("baseline_deltas") or []
    if deltas:
        items_parts = []
        for d in deltas:
            ch = d.get("change_pct")
            ch_str = f"{ch:+.1f}%" if ch is not None else "—"
            ch_cls = _change_cls(d.get("key") or "", ch)
            items_parts.append(
                f"<tr><td>{_esc(d['label'])}</td>"
                f"<td class='num'>{_esc(_fmt_kpi_value(d['key'], d['baseline']))}</td>"
                f"<td class='num'>{_esc(_fmt_kpi_value(d['key'], d['current']))}</td>"
                f"<td class='num {ch_cls}'>{_esc(ch_str)}</td></tr>"
            )
        items = "".join(items_parts)
        captured = (report.get("baseline") or {}).get("captured_at") or ""
        scaled_note = ""
        if any(d.get("scaled") for d in deltas):
            scaled_note = " Totals aligned to this period's day count so month vs baseline isn't apples-to-oranges."
        baseline_html = (
            f"<section class='detail-block'>"
            f"<h2>Progress since engagement start</h2>"
            f"<p class='muted'>Baseline captured {_esc(str(captured)[:10])}. "
            f"Current period compared to where we started.{scaled_note}</p>"
            f"<table class='data'><thead><tr>"
            f"<th>Metric</th><th>Baseline</th><th>This period</th><th>Change</th>"
            f"</tr></thead><tbody>{items}</tbody></table></section>"
        )

    work = report["work"]
    if work.get("completed_items"):
        lis = "".join(f"<li>{_esc(i['label'])}</li>" for i in work["completed_items"])
        work_items = f"<ul>{lis}</ul>"
    else:
        work_items = "<p class='muted'>No completed work items logged in this period.</p>"

    if report["impact_wins"]:
        wins_lis = "".join(
            f"<li><strong class='up'>{w['avg_primary_metric_change']:+.1f}%</strong> — {_esc(w['label'])}"
            + (f"<br/><span class='muted'>{_esc(w.get('proof_copy') or '')}</span>" if w.get('proof_copy') else "")
            + "</li>"
            for w in report["impact_wins"]
        )
        wins_block = f"<ul>{wins_lis}</ul>"
    else:
        wins_block = "<p class='muted'>No attributed wins measured in this period yet.</p>"

    # Lead with Success Contract + proven levers (client north star, not vanity SEO)
    contract = report.get("success_contract") or {}
    contract_status = (contract.get("status") or "unset").replace("_", " ")
    prog = contract.get("progress") or {}
    contract_line = ""
    if contract.get("configured"):
        label = prog.get("label") or (contract.get("contract") or {}).get("label") or "Primary KPI"
        if prog.get("change_pct") is not None and prog.get("target_delta_pct") is not None:
            contract_line = (
                f"<p><strong>{_esc(str(contract_status).title())}</strong> — "
                f"{_esc(label)} at {prog['change_pct']:+.0f}% "
                f"(target +{prog['target_delta_pct']:.0f}%)</p>"
            )
        else:
            contract_line = f"<p><strong>{_esc(str(contract_status).title())}</strong> — {_esc(label)}</p>"
    else:
        contract_line = "<p class='muted'>Success Contract not set for this client.</p>"

    proven_levers = report.get("proven_levers") or []
    if proven_levers:
        lever_lis = "".join(
            f"<li><strong>{_esc(lev.get('title') or 'Lever')}</strong>"
            + (
                f" — {_esc(str(lev.get('impact_summary') or lev.get('confidence_label') or ''))}"
                if lev.get("impact_summary") or lev.get("confidence_label")
                else ""
            )
            + "</li>"
            for lev in proven_levers[:6]
            if isinstance(lev, dict)
        )
        levers_block = f"<ul>{lever_lis}</ul>"
    elif report["impact_wins"]:
        levers_block = wins_block
    else:
        levers_block = "<p class='muted'>No proven levers yet — execute ranked fixes and wait for Prove.</p>"

    north_star_html = (
        "<section class='loop-section prove'>"
        "<p class='loop-label'>Outcomes</p>"
        "<h2>Contract status &amp; proven levers</h2>"
        f"{contract_line}"
        f"{levers_block}"
        "</section>"
    )

    if report["next_actions"]:
        items = "".join(
            f"<li><strong>{_esc(a.get('title', 'Action'))}</strong>"
            f" — {_esc(a.get('why_it_matters') or a.get('estimated_impact', ''))}</li>"
            for a in report["next_actions"]
            if isinstance(a, dict)
        )
        actions_html = f"<ul>{items}</ul>"
    else:
        actions_html = "<p class='muted'>No next actions queued.</p>"

    funnel = report.get("funnel") or {}
    funnel_html = ""
    stages = funnel.get("stages") or []
    if stages:
        stage_rows = []
        for s in stages:
            if s.get("unreliable") or s.get("conversion_rate") is None:
                rate_s = "n/a"
                drop_s = "n/a"
            else:
                rate_s = f"{s['conversion_rate']:.1f}%"
                drop_s = f"{s['dropoff']:.1f}%"
            stage_rows.append(
                [
                    _esc(s["stage"]),
                    f"{s['entered']:,}",
                    f"{s['exited']:,}",
                    rate_s,
                    drop_s,
                ]
            )
        funnel_note = ""
        if any(s.get("unreliable") for s in stages):
            funnel_note = (
                "<p class='muted'>Click → Session compares search/ad clicks to all-channel "
                "GA4 sessions. When sessions exceed clicks, the ratio is withheld — "
                "it is not a real conversion rate.</p>"
            )
        funnel_html = (
            "<section class='detail-block page-break'><h2>Conversion funnel</h2>"
            + funnel_note
            + _table_rows(
                ["Stage", "Entered", "Exited", "Conv. rate", "Drop-off"],
                stage_rows,
            )
        )
        lever = funnel.get("growth_lever") or funnel.get("biggest_leak")
        if lever:
            title = lever.get("title") or lever.get("stage") or "Biggest leak"
            cause = lever.get("cause") or f"{lever.get('dropoff', lever.get('leak_pct', ''))}% drop-off"
            fix = lever.get("fix") or ""
            funnel_html += (
                f"<div class='callout'><strong>Biggest growth lever:</strong> {_esc(title)}"
                f"<p>{_esc(cause)}</p>"
                + (f"<p class='fix'>{_esc(fix)}</p>" if fix else "")
                + "</div>"
            )
        funnel_html += "</section>"

    opps = report.get("opportunities") or {}
    opps_html = ""
    opp_parts = []
    rising = opps.get("rising_queries") or []
    if rising:
        rows = [
            [
                _esc(str(r["query"])[:60]),
                f"{r.get('impressions', 0):,.0f}",
                f"{r['growth_pct']:+.0f}%",
                f"{r.get('position', 0):.1f}" if r.get("position") is not None else "—",
                f"{r.get('clicks', 0):,.0f}",
            ]
            for r in rising[:8]
        ]
        opp_parts.append(
            "<h3>Rising search queries</h3>"
            + _table_rows(["Query", "Impressions", "Growth", "Position", "Clicks"], rows)
        )
    ctr_u = opps.get("ctr_underperformers") or []
    if ctr_u:
        rows = []
        for r in ctr_u[:8]:
            ctr = r.get("ctr")
            if isinstance(ctr, (int, float)) and ctr <= 1:
                ctr_s = f"{ctr * 100:.2f}%"
            elif ctr is not None:
                ctr_s = f"{ctr:.2f}%"
            else:
                ctr_s = "—"
            rows.append(
                [
                    _esc(str(r["page"])[:70]),
                    f"{r.get('impressions', 0):,.0f}",
                    ctr_s,
                    f"{r['gap_pct']:.0f}%",
                ]
            )
        opp_parts.append(
            "<h3>CTR underperformers</h3>"
            + _table_rows(["Page", "Impressions", "CTR", "Gap vs expected"], rows)
        )
    landing = opps.get("landing_pages") or []
    if landing:
        rows = [
            [
                _esc(str(r["page"])[:70]),
                f"{r.get('sessions', 0):,.0f}",
                f"{r.get('conversions', 0):,.0f}",
                f"{r.get('cvr', 0):.2f}%",
                f"{r.get('vs_avg', 0):+.2f}pp" if r.get("vs_avg") is not None else "—",
            ]
            for r in landing[:8]
        ]
        opp_parts.append(
            "<h3>Landing page conversion</h3>"
            + _table_rows(["Page", "Sessions", "Conversions", "CVR", "vs avg"], rows)
        )
    if opp_parts:
        opps_html = (
            "<section class='detail-block page-break'><h2>Opportunities detail</h2>"
            + "".join(opp_parts)
            + "</section>"
        )

    campaigns = report.get("campaigns") or []
    campaigns_html = ""
    if campaigns:
        rows = [
            [
                _esc(str(c["campaign"])[:50]),
                f"{c['clicks']:,.0f}",
                f"${c['cost']:,.0f}",
                f"{c['conversions']:,.1f}",
                f"${c['conversion_value']:,.0f}",
                f"{c.get('ctr', 0):.2f}%",
            ]
            for c in campaigns
        ]
        campaigns_html = (
            "<section class='detail-block page-break'><h2>Paid campaign performance</h2>"
            + _table_rows(
                ["Campaign", "Clicks", "Spend", "Conversions", "Value", "CTR"],
                rows,
            )
            + "</section>"
        )

    narrative = _render_narrative_html(
        report.get("narrative"),
        heading="Executive summary" if is_monthly else "Priorities",
    )

    glossary_html = ""
    if report.get("glossary"):
        gitems = "".join(
            f"<li><strong>{_esc(g['term'])}</strong> — {_esc(g['definition'])}</li>"
            for g in report["glossary"]
        )
        glossary_html = (
            f"<section class='detail-block page-break'><h2>Glossary</h2>"
            f"<ul class='glossary'>{gitems}</ul></section>"
        )

    detect_bits = []
    if rising:
        top = rising[0]
        detect_bits.append(
            f"Rising query <em>{_esc(str(top['query'])[:48])}</em> "
            f"(<span class='signal'>+{top['growth_pct']:.0f}%</span>)"
        )
    if ctr_u:
        detect_bits.append(
            f"{len(ctr_u)} CTR underperformer{'s' if len(ctr_u) != 1 else ''} surfaced"
        )
    open_n = work.get("insights_open") or 0
    if open_n:
        detect_bits.append(f"{open_n} issue{'s' if open_n != 1 else ''} still open")
    detect_body = (
        "<ul>" + "".join(f"<li>{b}</li>" for b in detect_bits) + "</ul>"
        if detect_bits
        else "<p class='muted'>No new detections highlighted for this period.</p>"
    )

    lever = funnel.get("growth_lever") or funnel.get("biggest_leak") or {}
    prescribe_bits = []
    if lever:
        lt = lever.get("title") or lever.get("stage")
        if lt:
            prescribe_bits.append(f"<strong>{_esc(lt)}</strong>")
        if lever.get("cause"):
            prescribe_bits.append(_esc(lever["cause"]))
        if lever.get("fix"):
            prescribe_bits.append(f"Prescription: {_esc(lever['fix'])}")
    if report.get("next_actions"):
        a0 = report["next_actions"][0]
        if isinstance(a0, dict) and a0.get("title"):
            prescribe_bits.append(f"Next: {_esc(a0['title'])}")
    prescribe_body = (
        "<p>" + "</p><p>".join(prescribe_bits) + "</p>"
        if prescribe_bits
        else "<p class='muted'>No prescription locked for this period.</p>"
    )

    execute_stats = (
        f"<div class='stat-strip'>"
        f"<div><span class='num'>{work['tasks_completed']}</span><span class='lbl'>tasks done</span></div>"
        f"<div><span class='num'>{work['insights_resolved']}</span><span class='lbl'>issues resolved</span></div>"
        f"<div><span class='num'>{work.get('briefs_created', 0)}</span><span class='lbl'>briefs</span></div>"
        f"</div>"
    )

    prove_strip = ""
    if deltas:
        chips = []
        for d in deltas[:4]:
            ch = d.get("change_pct")
            ch_str = f"{ch:+.1f}%" if ch is not None else "—"
            cls = _change_cls(d.get("key") or "", ch)
            chips.append(
                f"<div class='ba-chip'><span class='ba-label'>{_esc(d['label'])}</span>"
                f"<span class='ba-vals'>{_esc(_fmt_kpi_value(d['key'], d['baseline']))}"
                f" → {_esc(_fmt_kpi_value(d['key'], d['current']))}</span>"
                f"<span class='{cls}'>{_esc(ch_str)}</span></div>"
            )
        prove_strip = f"<div class='ba-strip'>{''.join(chips)}</div>"

    if logo_url:
        mark_html = (
            f'<img class="agency-logo" src="{_esc(logo_url)}" alt="{_esc(agency_name)}"/>'
        )
    else:
        mark_html = (
            f'<div class="mark-fallback">'
            f'<span class="mark-glyph" style="background:{brand}">'
            f"{_esc(agency_name[:1].upper())}</span>"
            f'<span class="mark-name">{_esc(agency_name)}</span></div>'
        )
    powered = (
        '<p class="powered">Proof engine by Kinexis</p>'
        if is_wl and agency_name.lower() != "kinexis"
        else ""
    )

    period_extra = ""
    if not is_monthly:
        period_extra = (
            f' <span class="mono">{_esc(period.get("start", ""))}'
            f' → {_esc(period.get("end", ""))}</span>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{_esc(doc_title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet"/>
<style>
  :root {{
    --ink: {INK_GRAPHITE};
    --mist: #6B7280;
    --accent: {brand};
    --signal: {SIGNAL_AMBER};
    --proof: {PROOF_GREEN};
    --momentum: {MOMENTUM_CORAL};
    --focus: {FOCUS_CYAN};
    --risk: {RISK_ROSE};
    --surface: #fafbfc;
    --border: #dce0e6;
  }}
  @page {{ size: letter; margin: 0.7in 0.65in 0.85in; }}
  @media print {{
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; background:#fff; padding:0; }}
    .no-print {{ display:none !important; }}
    .page-break {{ break-before: page; page-break-before: always; }}
    .cover {{ break-after: page; page-break-after: always; min-height: auto; }}
    .sheet {{ box-shadow:none; border:none; border-radius:0; padding:0; max-width:none; }}
    .loop-section {{ break-inside: avoid; }}
    .detail-block {{ break-inside: avoid; }}
    .detail-block.page-break {{ break-before: page; page-break-before: always; }}
  }}
  body {{
    font-family: "Plus Jakarta Sans", "Segoe UI", system-ui, sans-serif;
    background:#f4f5f8; color:var(--ink); margin:0; padding:32px; line-height:1.55;
  }}
  .sheet {{
    max-width:920px; margin:0 auto; background:#fff;
    border:1px solid var(--border); border-radius:4px; padding:0;
    box-shadow:0 12px 40px rgba(20,22,26,.06); overflow:hidden;
  }}
  .cover {{
    padding:56px 56px 48px; min-height:640px; display:flex; flex-direction:column;
    background: linear-gradient(165deg, #fff 0%, #f7f8fb 55%, #eef1f6 100%);
    position:relative;
  }}
  .cover::after {{
    content:""; position:absolute; left:0; right:0; bottom:0; height:6px; background:var(--accent);
  }}
  .agency-logo {{ max-height:48px; max-width:220px; object-fit:contain; }}
  .mark-fallback {{ display:flex; align-items:center; gap:12px; }}
  .mark-glyph {{
    width:36px; height:36px; border-radius:8px; color:#fff;
    display:inline-flex; align-items:center; justify-content:center;
    font-family:"Plus Jakarta Sans", Georgia, serif; font-weight:600; font-size:18px;
  }}
  .mark-name {{
    font-family:"Plus Jakarta Sans", Georgia, serif; font-size:20px; font-weight:600;
    letter-spacing:-0.02em; color:var(--ink);
  }}
  .cover-eyebrow {{
    margin:48px 0 12px; font-size:11px; letter-spacing:.16em; text-transform:uppercase;
    color:var(--mist); font-weight:600;
  }}
  .cover h1 {{
    margin:0; font-family:"Plus Jakarta Sans", Georgia, serif; font-size:42px; font-weight:600;
    letter-spacing:-0.03em; line-height:1.15; color:var(--ink); max-width:16ch;
  }}
  .cover-period {{ margin:16px 0 0; font-size:15px; color:#4a5160; }}
  .cover-period .mono {{
    font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:13px; color:var(--mist);
  }}
  .cover-meta {{ margin-top:auto; padding-top:48px; }}
  .cover-industry {{ font-size:13px; color:var(--mist); margin:0 0 8px; }}
  .powered {{ font-size:11px; color:var(--mist); margin:0; letter-spacing:.04em; }}
  .body {{ padding:40px 56px 48px; }}
  h2 {{
    font-family:"Plus Jakarta Sans", Georgia, serif; font-size:18px; margin:0 0 12px;
    color:var(--ink); font-weight:600; letter-spacing:-0.02em;
  }}
  h3 {{ font-size:13px; margin:18px 0 8px; color:#4a5160; font-weight:600; }}
  .loop-section {{
    border-left:3px solid var(--rail); padding:4px 0 4px 20px; margin:0 0 28px;
  }}
  .loop-section.detect {{ --rail: var(--signal); }}
  .loop-section.prescribe {{ --rail: var(--focus); }}
  .loop-section.execute {{ --rail: var(--momentum); }}
  .loop-section.prove {{ --rail: var(--proof); }}
  .loop-label {{
    font-size:10px; letter-spacing:.14em; text-transform:uppercase; font-weight:700;
    color:var(--rail); margin:0 0 6px;
  }}
  .stat-strip {{ display:flex; gap:28px; flex-wrap:wrap; margin:12px 0 16px; }}
  .stat-strip .num {{
    display:block; font-family:"IBM Plex Mono", ui-monospace, monospace;
    font-size:22px; font-weight:500; color:var(--ink);
  }}
  .stat-strip .lbl {{ font-size:11px; color:var(--mist); text-transform:uppercase; letter-spacing:.06em; }}
  .ba-strip {{ display:flex; flex-wrap:wrap; gap:10px; margin:12px 0 16px; }}
  .ba-chip {{
    border:1px solid var(--border); border-radius:8px; padding:10px 12px; min-width:140px;
    background:var(--surface);
  }}
  .ba-label {{ display:block; font-size:11px; color:var(--mist); margin-bottom:4px; }}
  .ba-vals {{ display:block; font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:12px; margin-bottom:4px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:16px 0 24px; }}
  .kpi {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px; }}
  .kpi-label {{ font-size:11px; letter-spacing:.02em; color:var(--mist); text-transform:uppercase; font-weight:600; }}
  .kpi-value {{
    font-size:22px; font-weight:600; margin:6px 0;
    font-family:"IBM Plex Mono", ui-monospace, monospace; color:var(--ink);
  }}
  .kpi-change.up, .up {{ color:var(--proof); font-size:12px; font-weight:600; }}
  .kpi-change.down, .down {{ color:var(--risk); font-size:12px; font-weight:600; }}
  .kpi-change.flat, .flat {{ color:var(--mist); font-size:12px; font-weight:600; }}
  .signal {{ color:var(--signal); font-weight:600; }}
  ul {{ margin:0; padding-left:18px; line-height:1.65; }}
  .muted {{ color:var(--mist); font-size:13px; }}
  .detail-block {{ margin:32px 0; }}
  .detail-block > h2 {{
    font-size:13px; text-transform:uppercase; letter-spacing:.06em;
    font-family:"Plus Jakarta Sans", sans-serif; border-bottom:2px solid var(--accent);
    padding-bottom:6px; margin-bottom:14px;
  }}
  .callout {{
    background:#f0faf6; border-left:3px solid var(--accent); padding:12px 16px;
    margin:16px 0; border-radius:0 8px 8px 0; font-size:13px;
  }}
  .callout .fix {{ color:#4a5160; margin:8px 0 0; }}
  table.data {{ width:100%; border-collapse:collapse; font-size:12px; margin:8px 0 16px; }}
  table.data th {{
    text-align:left; background:#f1f3f7; color:#4a5160; padding:8px 10px;
    border-bottom:1px solid var(--border); font-weight:600;
  }}
  table.data td {{ padding:8px 10px; border-bottom:1px solid #f1f3f7; color:#2a303c; vertical-align:top; }}
  table.data td.num {{ font-family:"IBM Plex Mono", ui-monospace, monospace; white-space:nowrap; }}
  .glossary {{ font-size:13px; color:var(--mist); }}
  .doc-footer {{
    margin-top:36px; font-size:11px; color:var(--mist);
    border-top:1px solid var(--border); padding-top:16px;
    display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;
  }}
  .btn {{
    background:var(--accent); color:#fff; border:none; padding:10px 16px;
    border-radius:8px; font-weight:600; cursor:pointer; margin-right:8px;
    font-family:"Plus Jakarta Sans", sans-serif;
  }}
  .priority {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px; margin:0 0 10px; }}
  .priority-head {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }}
  .priority-head .num {{ color:var(--mist); font-size:12px; }}
  .priority-head .sev {{ font-size:10px; text-transform:uppercase; letter-spacing:.06em; padding:2px 8px; border-radius:6px; background:#e2e4ea; color:#4a5160; }}
  .issue {{ color:#4a5160; font-size:13px; line-height:1.5; margin:0 0 10px; }}
  .measure {{ color:var(--mist); font-size:12px; margin:10px 0 0; }}
  .headline {{ color:#2a303c; font-size:15px; line-height:1.55; margin:0 0 14px; }}
  .narrative {{ white-space:pre-wrap; background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px; font-size:14px; line-height:1.6; color:#2a303c; }}
  @media (max-width:700px) {{
    .cover, .body {{ padding:28px 24px; }}
    .kpis {{ grid-template-columns:1fr; }}
    .cover h1 {{ font-size:32px; }}
  }}
</style>
</head>
<body>
  <div class="sheet">
    <div class="no-print" style="padding:20px 56px 0">
      <button class="btn" onclick="window.print()">Print / Save PDF</button>
    </div>
    <header class="cover">
      {mark_html}
      <p class="cover-eyebrow">{'Diagnostic / kickoff report' if kind == 'diagnostic' else 'Client success report'}</p>
      <h1>{_esc(client['name'])}</h1>
      <p class="cover-period">
        {('Findings and prescriptions — not yet executed or proven' if kind == 'diagnostic' else ('Monthly performance' if is_monthly else 'Success report'))} · {_esc(title_period)}{period_extra}
      </p>
      <div class="cover-meta">
        <p class="cover-industry">{_esc(industry)}</p>
        {powered}
      </div>
    </header>
    <div class="body">
      {north_star_html}
      <section class="loop-section detect">
        <p class="loop-label">Detected</p>
        <h2>What surfaced</h2>
        {detect_body}
      </section>
      <section class="loop-section prescribe">
        <p class="loop-label">Prescribed</p>
        <h2>What we chose to pull</h2>
        {prescribe_body}
      </section>
      <section class="loop-section execute">
        <p class="loop-label">Executed</p>
        <h2>What shipped</h2>
        {execute_stats}
        {work_items}
      </section>
      <section class="loop-section prove">
        <p class="loop-label">Proved</p>
        <h2>What improved</h2>
        {prove_strip}
        {wins_block}
      </section>
      {narrative}
      <section class="detail-block">
        <h2>Executive KPIs — this period vs prior</h2>
        <div class="kpis">{''.join(kpi_blocks) if kpi_blocks else '<p class="muted">No KPI data for this period.</p>'}</div>
      </section>
      {baseline_html}
      {funnel_html}
      {opps_html}
      {campaigns_html}
      <section class="detail-block page-break">
        <h2>Opportunities next</h2>
        {actions_html}
      </section>
      {glossary_html}
      <div class="doc-footer">
        <span>{_esc(agency_name)} · Confidential</span>
        <span>{_esc(client['name'])} · {_esc(generated)}</span>
      </div>
    </div>
  </div>
</body>
</html>"""


def report_download_filename(report: dict) -> str:
    client = (report.get("client") or {}).get("name") or "Client"
    period = report.get("period") or {}
    if period.get("mode") == "monthly":
        label = f"{period.get('month_name', '')}_{period.get('year', '')}".strip("_")
    else:
        label = f"{period.get('start', '')}_to_{period.get('end', '')}"
    raw = f"{client}_{label}_Success_Report"
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in raw)
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_") + ".pdf"
