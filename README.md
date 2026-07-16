# Kinexis Digital Dashboard — Beta v0.0.1

![Version](https://img.shields.io/badge/version-0.0.1--beta-0ea5e9?style=flat)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/typescript-5.x-3178C6?style=flat&logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-64748b?style=flat)

Windows desktop **Success Engine** for digital marketing agencies. Diagnose, fix, and prove client SEO, CRO, and paid-media performance — all from a single command center.

> **Beta v0.0.1** — first public cut. Core loop (Detect → Prescribe → Execute → Prove → Report) is live, including score-driven growth plays when health is low and no incidents are open.

**Product loop:** Detect → Prescribe → Execute → Prove → Report

---

## Features

### Portfolio Command Center
- Cross-client health dashboard with risk heatmap (critical / watch / healthy)
- Today's priority queue — stuck tasks, off-contract alerts, overdue work
- Bulk sync, bulk archive, CSV export, client comparison (side-by-side KPIs)
- My Book filtering by owner, priority, risk, and report readiness

### 12 Data Connectors
| Connector | Data Pulled |
|-----------|------------|
| Google Search Console | Clicks, impressions, CTR, position, queries |
| GA4 | Sessions, key events, landing pages |
| Cloudflare | Analytics, threats, bandwidth |
| Bing Webmaster | Clicks, impressions, rankings |
| PageSpeed Insights | Mobile/desktop performance scores |
| HubSpot | Leads, opportunities, deals, revenue |
| Google Ads | Clicks, cost, conversions, value |
| Meta Ads | Clicks, cost, conversions |
| Ads CSV | Generic paid media import |
| Google Business Profile (CSV) | Local search/map views, calls, directions |
| Backlinks (CSV) | Referring domains, DR, toxic/new/lost links |
| Clarity | Page-level sessions / derived bounce / rage clicks via Data Export API |
| CrUX | Real-user LCP/INP/CLS via PageSpeed API key |
| SERP | Live search result snapshots (optional) |
| Site Crawl & Content | Page structure, titles, H1s, schema, word count, broken pages |

### 14 Insight Rules
| Rule | Category |
|------|----------|
| Content opportunity (striking-distance queries) | Opportunity |
| CTR below expected-for-position | Problem / Opportunity |
| GSC decline alert (clicks/impressions WoW) | Problem |
| Zero-click queries (impressions but no clicks) | Problem |
| GA4 CRO leak (high-traffic, low-conversion pages) | Problem |
| Cloudflare threat spike + traffic drop | Problem |
| PageSpeed urgent / improve | Problem / Opportunity |
| Mobile vs desktop CTR gap | Problem |
| Bing vs Google share gap | Opportunity |
| Ads spend with low/no CRM leads | Problem |
| Pause weak campaigns (spend, 0 conversions) | Problem |
| High Clarity bounce + low GA4 conversion | Problem |
| CrUX field CWV failures (LCP/INP/CLS) | Problem |
| Leads to revenue handoff leak | Problem |
| Organic clicks to leads tracking leak | Problem |
| Crawled page issues (broken, missing titles/H1s/meta, thin content) | Problem / Opportunity |
| Missing structured data (schema.org) | Opportunity |

Each insight includes a **playbook** with concrete fix steps, effort estimate, estimated ROI, and metrics to verify.

### Detect Tab (with sub-navigation)
- **Health** — 5-pillar health score (Visibility, Engagement, Conversion, Technical, Efficiency) with industry-adjusted benchmarks
- **Levers** — Top growth lever with cause + fix + impact gauge
- **Funnel** — Full organic → paid → CRM funnel visualization with leak detection
- **Campaigns** — Paid campaign rollups with pause candidates (zero-conversion spend)
- **Learning** — Recommendation lifecycle + cross-client win rates
- **Explore** — Content inventory table, keyword rankings with position charts, keyword tracking

### Charts (Detect → Dig Deeper)
- 8 trend series (clicks, impressions, sessions, conversions, CTR, position, paid clicks, ad conversions)
- Period-over-period comparison overlay (7d/30d/90d vs prior period)
- 30-day linear projection with automatic forecast
- Known-event annotations (Google core updates, seasonal events)
- Configurable grid (2/3/4 columns)

### Prescribe Tab
- Fix queue ranked by impact score with severity/effort/ROI/confidence badges
- Quick wins filter, high impact filter, urgent-only filter
- Bulk select, bulk assign, bulk resolve with undo
- One-click "Assign to Cursor" opens IDE with fix context
- AI action plan generation (Claude or Ollama)

### Execute Tab
- Work board with list and kanban views
- Open / In Progress / Done / Skipped columns
- Assignee chips, due dates, overdue alerts
- Task editing with notes, reassignment, date picker
- Completion captures impact baseline for Prove

### Prove Tab
- Impact measurement after task completion
- Win / Loss / Flat outcome with manual override
- Causal inference verdict with bootstrap confidence intervals
- Funnel proof (organic → revenue step-by-step before/after)
- Aggregate win rate and average lift across proven tasks

### Report Tab
- Client success report with cover, narrative, KPIs, commercial proof
- Monthly report library with save/delete
- PDF download (Chromium headless) + HTML fallback
- Agency white-label branding (name, accent, logo)
- Copy share link for client distribution

### AI Capabilities
- Weekly AI summaries with anomaly detection
- Action plans with prioritized experiments
- Content briefs from rising queries
- Provider toggle: Anthropic Claude or local Ollama
- AI usage tracking by client and model

### Settings
- AI provider configuration + test endpoint
- API keys (PageSpeed, Bing, Clarity, Google Ads)
- Impact evidence window days
- Assignee presets for team routing
- Database backup with timestamped files
- Full data reset

### Desktop App (Electron)
- Native Windows title bar with drag region
- System tray with background sync
- Desktop notifications for critical insights
- Cursor IDE integration (open tasks directly)
- OAuth browser flow for Cloudflare + Google

---

## Quick Start (dev)

### Backend

```powershell
cd kinexis\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.template .env   # set FERNET_KEY and OAuth IDs
uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd kinexis\frontend
npm install
npm run dev
```

Open http://localhost:3000 (API at http://127.0.0.1:8000).

### PDF Export

```powershell
cd kinexis
.\scripts\setup-pdf.ps1
```

If Chromium is missing, the Report tab opens HTML — use Print → Save as PDF.

### OAuth (Google / Cloudflare)

```powershell
.\scripts\setup-oauth.ps1
```

---

## Desktop Packaging

```powershell
.\scripts\build-installer.ps1
```

Requires `backend/.env` and `backend/oauth.json`. Output installer is under `electron/dist/`.

**Database location (packaged app):** Electron sets `DATABASE_URL` under the app userData folder. Use **Settings → Backup database** to copy a timestamped SQLite backup.

---

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 15 (static export), React 19, Tailwind CSS, Recharts |
| Backend | Python 3.11+, FastAPI, SQLAlchemy, SQLite (WAL) |
| Desktop | Electron + PyInstaller-bundled backend |
| AI | Anthropic Claude or local Ollama |
| Scheduling | APScheduler (daily sync, weekly AI, monthly reports) |
| Migrations | Alembic |

---

## Tests

```powershell
cd kinexis\backend
pytest
```

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full connector details, API routes, scheduled jobs, security model, and database schema.
