"""Read-only Success Pulse — shareable tokenized client status page."""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, ImpactSnapshot, PulseShareToken, Task
from app.timeutil import utcnow

router = APIRouter(prefix="/pulse", tags=["pulse"])


class PulseCreateBody(BaseModel):
    client_id: int
    expires_days: int = 90


def _build_pulse_payload(db: Session, client: Client) -> dict:
    from app.success_contract import evaluate_success_contract, parse_success_contract
    from app.impact_tracker import portfolio_impact_wins
    from app.portfolio_scoring import build_client_health_detail

    contract = None
    if parse_success_contract(client):
        try:
            contract = evaluate_success_contract(db, client)
        except Exception:
            contract = None

    health = None
    try:
        health = build_client_health_detail(db, client.id)
    except Exception:
        health = None

    wins_raw = portfolio_impact_wins(days=90) or []
    wins = [
        {
            "label": w.get("label") or w.get("title") or "Win",
            "avg_primary_change": w.get("avg_primary_change") or w.get("avg_primary_metric_change"),
            "primary_metric": w.get("primary_metric"),
            "outcome": w.get("outcome") or "win",
        }
        for w in wins_raw
        if w.get("client_id") == client.id
    ][:8]

    since = utcnow() - timedelta(days=7)
    # Baselines mark work started; done tasks created recently approximate ship volume
    started_ids = {
        r[0]
        for r in db.query(ImpactSnapshot.task_id)
        .filter(
            ImpactSnapshot.client_id == client.id,
            ImpactSnapshot.snapshot_type == "baseline",
            ImpactSnapshot.created_at >= since,
        )
        .distinct()
        .all()
    }
    done_week = (
        db.query(Task)
        .filter(
            Task.client_id == client.id,
            Task.status == "done",
            Task.created_at >= since,
        )
        .count()
    )
    shipped_week = max(done_week, len(started_ids))

    return {
        "client": {
            "id": client.id,
            "name": client.name,
            "industry": client.industry or "",
        },
        "success_contract": contract,
        "health": {
            "score": (health or {}).get("health_score") or (health or {}).get("score"),
            "risk": (health or {}).get("risk"),
            "top_action": (health or {}).get("top_action"),
        },
        "proven_wins": wins,
        "ship_cadence": {
            "fixes_done_7d": shipped_week,
            "target_min": 3,
            "target_max": 5,
            "on_pace": shipped_week >= 3,
        },
        "generated_at": utcnow().isoformat(),
    }


@router.post("/share")
def create_pulse_share(body: PulseCreateBody, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == body.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    days = max(7, min(365, int(body.expires_days or 90)))
    token = secrets.token_urlsafe(24)
    row = PulseShareToken(
        client_id=client.id,
        token=token,
        expires_at=utcnow() + timedelta(days=days),
        revoked=False,
    )
    db.add(row)
    db.commit()
    from app.public_urls import absolute_public_url

    path = f"/pulse/{token}"
    html_path = f"{path}/html"
    return {
        "token": token,
        "client_id": client.id,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "path": path,
        "api_path": path,
        "html_path": html_path,
        "html_url": absolute_public_url(html_path, db),
        "url": absolute_public_url(html_path, db),
    }


@router.get("/{token}")
def get_pulse(token: str, db: Session = Depends(get_db)):
    row = (
        db.query(PulseShareToken)
        .filter(PulseShareToken.token == token, PulseShareToken.revoked == False)  # noqa: E712
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Pulse link not found")
    if row.expires_at and row.expires_at < utcnow():
        raise HTTPException(status_code=410, detail="Pulse link expired")
    client = db.query(Client).filter(Client.id == row.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return _build_pulse_payload(db, client)


@router.get("/{token}/html", response_class=HTMLResponse)
def get_pulse_html(token: str, db: Session = Depends(get_db)):
    data = get_pulse(token, db)
    client = data["client"]
    contract = data.get("success_contract") or {}
    prog = contract.get("progress") or {}
    health = data.get("health") or {}
    wins = data.get("proven_wins") or []
    cadence = data.get("ship_cadence") or {}
    status = contract.get("status") or "unset"
    try:
        from app.success_report.branding import agency_branding

        agency = agency_branding(db) or {}
    except Exception:
        agency = {}
    agency_name = (agency.get("name") or "Agency").strip() or "Agency"
    accent = (agency.get("accent") or "#0891B2").strip() or "#0891B2"
    logo = (agency.get("logo_url") or "").strip()
    logo_html = (
        f'<img src="{_esc(logo)}" alt="{_esc(agency_name)}" '
        f'style="max-height:36px;max-width:160px;margin:0 0 12px"/>'
        if logo.startswith(("http://", "https://", "data:"))
        else ""
    )
    wins_html = "".join(
        f"<li><strong>{_esc(str(w.get('avg_primary_change') or 0))}% </strong>"
        f"{_esc(w.get('label') or 'Win')}</li>"
        for w in wins
    ) or "<li class='muted'>Wins will appear here as work is proven.</li>"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_esc(client['name'])} — Success Pulse · {_esc(agency_name)}</title>
<style>
body{{font-family:Georgia,serif;margin:0;background:#f6f4f1;color:#1a1a1a}}
.wrap{{max-width:640px;margin:0 auto;padding:32px 20px}}
h1{{font-size:28px;margin:0 0 4px}}
.agency{{color:{_esc(accent)};font-size:13px;margin:0 0 8px;letter-spacing:.04em;text-transform:uppercase}}
.sub{{color:#666;margin:0 0 24px}}
.card{{background:#fff;border:1px solid #e5e1da;padding:16px 18px;margin:0 0 14px;border-radius:4px}}
.label{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#888;margin:0 0 6px}}
.stat{{font-size:32px;font-weight:700;color:{_esc(accent)}}}
.muted{{color:#888}}
ul{{padding-left:18px;margin:8px 0 0}}
.footer{{font-size:12px;color:#888;margin-top:24px}}
</style></head><body><div class="wrap">
{logo_html}
<p class="agency">{_esc(agency_name)}</p>
<p class="label">Success Pulse</p>
<h1>{_esc(client['name'])}</h1>
<p class="sub">{_esc(client.get('industry') or '')} · Live status for your growth program</p>
<div class="card">
  <p class="label">Success contract</p>
  <p class="stat">{_esc(str(status).replace('_',' '))}</p>
  <p class="muted">{_esc(prog.get('label') or 'Primary KPI')}
  {f" · {prog.get('change_pct'):+.0f}% vs +{prog.get('target_delta_pct'):.0f}% target" if prog.get('change_pct') is not None and prog.get('target_delta_pct') is not None else ""}</p>
</div>
<div class="card">
  <p class="label">Program health</p>
  <p class="stat">{_esc(str(health.get('score') if health.get('score') is not None else '—'))}</p>
  <p class="muted">Status: {_esc(str(health.get('risk') or '—').replace('_',' '))}</p>
</div>
<div class="card">
  <p class="label">Work shipped (7 days)</p>
  <p class="stat">{int(cadence.get('fixes_done_7d') or 0)}</p>
  <p class="muted">Target cadence 3–5 ranked fixes / week · {"On pace" if cadence.get("on_pace") else "Ramping"}</p>
</div>
<div class="card">
  <p class="label">Proven wins</p>
  <ul>{wins_html}</ul>
</div>
<p class="footer">Prepared by {_esc(agency_name)} · Updated {_esc(str(data.get('generated_at') or '')[:19])} · Read-only</p>
</div></body></html>"""


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@router.post("/{token}/revoke")
def revoke_pulse(token: str, db: Session = Depends(get_db)):
    row = db.query(PulseShareToken).filter(PulseShareToken.token == token).first()
    if not row:
        raise HTTPException(status_code=404, detail="Pulse link not found")
    row.revoked = True
    db.commit()
    return {"ok": True}
