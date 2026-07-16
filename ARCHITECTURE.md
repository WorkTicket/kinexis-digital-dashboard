# Kinexis Digital Dashboard - Architecture

## Project Overview

Windows desktop **Success Engine** for a digital marketing agency. Connects to Google Search Console, GA4, Cloudflare, Bing, PageSpeed, HubSpot, Google Ads, Meta Ads, Ads CSV, Clarity, CrUX, GBP, backlinks, and optional SERP. Stores marketing data locally in SQLite, surfaces rule-based SEO/CRO insights, generates AI playbooks and content briefs, tracks work via growth levers, and **proves metric lift** with client-ready success reports (PDF/HTML).

**Client portal (beta):** Settings → Client portal enables remote tokenized Success Pulse (`/pulse/{token}/html`) and report links (`/portal/report/{token}/html`) via a public base URL (Cloudflare Tunnel / ngrok). Agency API stays token-protected; the agency SPA remains loopback-only for remote hosts.

**Product loop:** Detect → Prescribe → Execute → Prove → Report

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy, SQLite (WAL) |
| Frontend | Next.js 15 (static export), Tailwind CSS, Recharts |
| AI | Anthropic Claude or local Ollama (optional) |
| Scheduler | APScheduler (in-process, max_instances=1, coalesce) |
| Desktop | Electron, electron-builder |
| Backend bundling | PyInstaller |

## Security (local desktop)

- API requires `X-Kinexis-Token` / `Authorization: Bearer` (token from env `KINEAXIS_API_TOKEN` or auto-generated `.kinexis_api_token`). Electron generates and injects the token; Next.js dev uses `NEXT_PUBLIC_KINEAXIS_API_TOKEN`.
- Non-loopback clients rejected unless `KINEAXIS_ALLOW_REMOTE=1`.
- Connector API keys in AppSetting are Fernet-encrypted; GET `/settings/` returns masks + `*_configured` flags only.
- Datasource APIs never return `credentials_encrypted` (only `has_credentials`).
- Outbound page fetches are SSRF-guarded (`url_safety.py`).
- OAuth `state`/PKCE use constant-time compare + TTL.

## How It Runs

- **Dev:** `uvicorn app.main:app` on :8000 + `next dev` on :3000 (set matching API tokens)
- **Desktop:** Electron spawns PyInstaller-bundled backend on :8000 with `KINEAXIS_API_TOKEN`, FastAPI serves built frontend static files. Electron loads `http://127.0.0.1:8000`.

## Repo Structure

```
kinexis/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI + LocalAuthMiddleware + safe SPA static
│   │   ├── local_auth.py        # Desktop API token + loopback gate
│   │   ├── models.py            # SQLAlchemy models + composite indexes
│   │   ├── database.py          # SQLite WAL / busy_timeout / FK
│   │   ├── db_migrate.py        # Alembic upgrade head at startup
│   │   ├── config.py            # .env + oauth.json
│   │   ├── credentials.py       # Fernet encrypt/decrypt (+ secret strings)
│   │   ├── url_safety.py        # SSRF checks for outbound HTTP
│   │   ├── ai_client.py         # Anthropic / Ollama abstraction
│   │   ├── ai_summarizer.py     # Weekly AI narratives
│   │   ├── action_planner.py    # AI action plans
│   │   ├── content_brief.py     # AI content briefs
│   │   ├── impact_tracker.py    # Baseline + recheck + portfolio wins
│   │   ├── portfolio_scoring.py # Portfolio health / risk / contract eval
│   │   ├── success_report/      # build / narrative / HTML / library / branding
│   │   ├── agent_fix_report/   # playbooks + helpers + markdown builder
│   │   ├── success_contract.py  # Per-client success contracts
│   │   ├── brand_queries.py     # Brand vs non-brand split
│   │   ├── ship_log.py          # Ship-log → tasks
│   │   ├── lever_service.py     # Growth lever threads
│   │   ├── rankings.py          # Keyword rankings
│   │   ├── pdf_export.py        # HTML → PDF via Playwright
│   │   ├── opportunities.py     # Rising queries / CTR / landing pages
│   │   ├── funnel_analyzer.py
│   │   ├── insight_service.py   # Deduped insight generation
│   │   ├── scheduler.py         # Daily sync, weekly AI, impact, monthly reports
│   │   ├── connectors/          # gsc, ga4, cloudflare, clarity, pagespeed, bing,
│   │   │                        # hubspot, ads_csv, serp, page_content + base helpers
│   │   ├── insights/rules.py    # Rule-based detectors
│   │   └── routers/             # clients, metrics, insights, tasks, summaries,
│   │                            # actions, onboarding, auth, google_auth,
│   │                            # cloudflare_auth, settings, rankings, levers
│   ├── alembic/                 # Versioned migrations (additive SQLite patches)
│   ├── alembic.ini
│   ├── requirements.txt
│   └── .env
├── scripts/
├── frontend/
│   ├── app/page.tsx             # Shell container (Home + AppHome)
│   ├── components/              # Portfolio, Report, shell/*, WorkBoard, levers, …
│   ├── components/report/       # ReportCover / Library / Document / utils
│   ├── hooks/useReportView.ts
│   └── lib/api/                 # Typed client + domain endpoints + X-Kinexis-Token
└── electron/                    # main.js / preload.js (contextIsolation)
```

## Connectors

| Source | Auth |
|---|---|
| GSC | Google OAuth |
| GA4 | Google OAuth |
| Cloudflare | OAuth or encrypted API token |
| Bing Webmaster | API key (per datasource / settings) |
| Clarity | Live connector + scheduler auto-wire when token present (page-level bounce metrics) |
| PageSpeed | API key (settings → auto-wired DS) |
| HubSpot | Per-datasource credentials |
| Google Ads | Developer token + OAuth refresh (adwords scope) / Settings |
| Meta Ads | Access token + ad account ID |
| Ads CSV | Local CSV path credentials |
| SERP | Licensed API (optional, env) |
| Page content / site crawl | Public HTTP fetch (SSRF-safe); BFS crawl after sync |

New connectors should use `connectors/base.py` helpers (`run_connector_sync`, `replace_metrics_window`) rather than copy-paste session boilerplate.

### MetricDaily uniqueness & datasource status

- `metric_daily` has a unique constraint on `(client_id, source, date, metric_name, dimension_type, dimension_value)`. Dimension columns are normalized to `""` (never NULL) so SQLite UNIQUE works. Sync uses `replace_metrics_window` (delete+insert under a per-client/source lock) for idempotent window rewrites.
- Datasource statuses include `active`, `pending`, `error`, `partial`, and `reauth_required`. Scheduled sync retries `active`/`pending`/`error`/`partial` only — `reauth_required` is skipped until the operator reconnects (avoids hammering dead credentials). Decrypt failures mark `reauth_required`. Archived clients are skipped by scheduler jobs.
- Alembic `upgrade head` failures abort startup (no fail-open half-migrated schema).
- Scheduler persists `JobRun` rows; `/health` exposes the latest finished job as a heartbeat.

## Insights (12 active rules + page_content crawl)

1. Content opportunity — rising impressions, positions ~11–20  
2. CTR vs expected-for-position  
3. Decline alert — clicks/impressions dropping WoW  
4. Zero-click high impressions  
5. GA4 CRO — high traffic, low CVR  
6. Cloudflare threats up + GA4 sessions down  
7. PageSpeed mobile thresholds  
8. Mobile vs desktop CTR gap  
9. Bing vs Google gap  
10. Ads spend with low leads (CSV ads metrics)  
11. Leads → revenue leak (HubSpot / CRM metrics)  
12. Organic traffic → leads leak  
13. Page content / crawl issues (`crawl_broken_pages`, `crawl_missing_title`, `crawl_missing_h1`, `crawl_missing_meta`, `crawl_thin_content`)

Clarity high-bounce rule runs when page-level bounce rows are present after sync.

Insights dedupe on stable fingerprint `sha256(type|target_url or target_query)`. Prune/stale resolve set `resolve_reason` to `pruned`/`stale` (not user-fixed).

Thresholds can be tuned per client via profile settings. Manual sync (`POST /metrics/sync/{id}`) **always** regenerates insights (deduped) and returns `insights_created`. Use `?background=true` or `POST /metrics/sync-all` to queue work off the request.

## AI

- Provider: `AI_PROVIDER=anthropic|ollama` (also settable in Settings UI)
- Features: weekly summaries, action plans, content briefs
- Ollama base URL restricted to loopback
- Ollama uses `/api/chat` with optional JSON mode

## Scheduled Jobs

- Daily sync: 03:00 UTC (connectors + insights) — `max_instances=1`, `coalesce=True`; writes `JobRun`
- Weekly AI summaries: Monday 05:00 UTC (skips archived clients)
- Impact recheck: daily 06:00 UTC (auto proving→proven on win)
- Monthly reports: 1st of month 07:00 UTC (previous calendar month)

## Key API Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/actions/benchmark` | Portfolio health / risk / WoW |
| GET | `/actions/today` | Portfolio today queue |
| GET | `/actions/report/{id}` | Success report JSON |
| GET | `/actions/report/{id}/html` | Printable success report |
| GET | `/actions/report/{id}/pdf` | Download PDF (Playwright/Chromium) |
| GET/POST | `/actions/briefs/*` | Content briefs |
| GET | `/actions/impact/wins/portfolio` | Attributed wins |
| GET | `/metrics/opportunities/{id}` | Rising queries, CTR gaps, landing pages |
| GET/PUT | `/settings/` | AI + connector settings (secrets masked) |
| POST | `/metrics/sync/{id}` | Sync + insight refresh |
| GET | `/rankings/*` | Keyword rankings |
| GET/POST | `/levers/*` | Growth lever threads |

List endpoints (`/insights/`, `/tasks/`) are paginated (`limit`/`offset`).

## Database migrations

Startup runs `Base.metadata.create_all` (new tables from models) then **Alembic** `upgrade head` (`app/db_migrate.py`). Additive SQLite column/index patches live under `backend/alembic/versions/`. Do not reintroduce ad-hoc `schema_migrate` patches — add a new revision instead.

## PDF export setup (client reports)

```powershell
cd kinexis\backend
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Or from `kinexis/`:

```powershell
.\scripts\setup-pdf.ps1
```

## Frontend Tabs

- **Portfolio** — all clients (default landing)
- Per client: **Detect** · **Prescribe** · **Execute** · **Prove** · **Report**
- **Settings** — AI provider, masked API keys, DB backup, assignee presets

## .env Variables

- `FERNET_KEY` — required
- `KINEAXIS_API_TOKEN` — local API auth (auto-generated if unset)
- `KINEAXIS_REQUIRE_API_TOKEN` — `1` default; `0` for unit tests
- `KINEAXIS_ALLOW_REMOTE` — `0` default; portal mode sets `1`
- `PUBLIC_BASE_URL` — HTTPS tunnel URL for share links
- `KINEAXIS_PORTAL_MODE` — Electron binds `0.0.0.0` and enables remote share access
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
- `CLOUDFLARE_CLIENT_ID` / `CLOUDFLARE_CLIENT_SECRET`
- `AI_PROVIDER` — `anthropic` or `ollama`
- `ANTHROPIC_API_KEY` — Claude
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL` — local models (loopback only via Settings)
- `BACKEND_PORT` — default 8000
- `DATABASE_URL` — override DB path (Electron sets userData path)
- `SERP_*` — optional licensed SERP

## Windows Packaging

1. `cd frontend && npm run build` → `frontend/out/`
2. `cd backend && pyinstaller kinexis-backend.spec` → `backend/dist/kinexis-backend/`
3. `cd electron && npx electron-builder --win` → installer
