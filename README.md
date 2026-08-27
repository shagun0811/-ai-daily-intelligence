# AI Daily Intelligence Aggregator

Automated daily AI intelligence collection, ranking, and reporting.

**Current status: local pipeline plus a Cloudflare Pages site for going live.**

The pipeline still runs on your machine. The public UI is a **static site** in `site/`, which Cloudflare Pages can host. Streamlit is no longer the live dashboard. Each report also writes an infographic, story cards, and a short GIF briefing from the same text — no paid image or video APIs.

---

## What works now

- Collect RSS / arXiv (Phase 2)
- Clean, normalize, and cluster duplicates (Phase 3)
- Keyword relevance, categories, topics, and explainable scores (Phase 4)
- Structured summaries with cache (Phase 5, mock by default)
- Ranked Markdown / HTML / PDF report; stories already used on a prior day are not repeated (Phase 6)
- Cloudflare Pages static briefing site (Phase 7 live UI)
- Daily schedule at 17:00 IST: local APScheduler + GitHub Actions (Phase 8)
- Hardened text pipeline: isolated stages, incremental clustering, extra tests (Phase 9)
- Infographic, story cards, and GIF briefing generated from the daily text report
- Cloudflare Pages static site (replaces Streamlit for going live)

---

## Installation

```powershell
cd C:\Users\KIIT0001\Desktop\ai-daily-intelligence
.\.venv\Scripts\Activate.ps1
pip install pydantic pydantic-settings SQLAlchemy python-dotenv PyYAML python-dateutil pytest requests feedparser beautifulsoup4 lxml trafilatura numpy Jinja2 reportlab streamlit pandas APScheduler pillow
```

---

## Run once (VS Code terminal)

One line only:

```powershell
python scripts/run_pipeline.py
```

That also exports `site/` for Cloudflare. To export the site only:

```powershell
python scripts/export_site.py
```

Preview inside VS Code (Simple Browser, not Chrome):

```powershell
python scripts/preview_site.py
```

Or **Terminal → Run Task… → Preview briefing in VS Code**.
If Simple Browser does not appear: **Ctrl+Shift+P** → **Simple Browser: Show** → paste `http://127.0.0.1:8788`

Go live on Cloudflare Pages (needs a free Cloudflare account and Node.js once):

```powershell
npx wrangler login
npx wrangler pages deploy site --project-name ai-daily-intelligence
```

Wrangler will print a `*.pages.dev` URL. Do not type `data\aggregator.db` in the terminal — that file is a SQLite database, not a program.

---

## Local daily timer

Optional. Only needed if this PC will stay on at 5pm. Otherwise use GitHub Actions below and leave the laptop off.

```
SCHEDULER_ENABLED=true
SCHEDULER_HOUR=17
SCHEDULER_MINUTE=0
SCHEDULER_TIMEZONE=Asia/Kolkata
CLOUDFLARE_AUTO_DEPLOY=true
CLOUDFLARE_PAGES_PROJECT=ai-daily-intelligence
```

Then run **one line**:

```powershell
python scripts/run_scheduler.py
```

Leave that terminal open. Stop with `Ctrl+C`. You must have run `npx wrangler login` once on this PC.

Run once through the same lock (no daemon):

```powershell
python scripts/run_scheduler.py --once
```

---

## GitHub Actions (laptop can be off)

This is the path that updates the live website every day at **17:00 IST** without your PC.

1. Put this project on GitHub (one-time).
2. In the GitHub repo: **Settings → Secrets and variables → Actions**
   - Secret `CLOUDFLARE_API_TOKEN`: a Cloudflare **custom** API token. Include the correct account, then:
     - Account → **Cloudflare Pages → Edit**
     - Account Settings → **Read** (if listed)
     - User → **Memberships → Read** (needed if Wrangler still calls `GET /memberships` and fails with API 10000)
   - Variable `CLOUDFLARE_ACCOUNT_ID`: the Cloudflare account ID (dashboard URL after `dash.cloudflare.com/`). This lets Wrangler skip User Memberships Read.
3. After the first push, GitHub runs `.github/workflows/daily.yml` every day at 11:30 UTC (5:00pm IST), builds the report, and deploys https://ai-daily-intelligence.pages.dev (the Pages **production** branch, not the `master` preview alias).

You can also run it by hand: GitHub → **Actions → Daily pipeline → Run workflow**.

Workflows:

- `tests.yml` — pytest on push / pull request (mock LLM, no Ollama)
- `daily.yml` — pipeline every day at 17:00 IST, then Cloudflare Pages deploy

GitHub cannot run Ollama cheaply, so Actions always use `LLM_PROVIDER=mock`.

---

## Test

```powershell
pytest
```

Tests do not start the scheduler daemon, Streamlit, Ollama, Wrangler, or live websites.

---

## Failure handling

Each pipeline stage (collect → clean → score → summarize → report) commits on its own. If summarization fails, collected and scored items stay in the database. One RSS/arXiv outage does not stop other sources. A stale `data/pipeline.lock` from a crashed run is replaced. The dashboard shows an error instead of crashing if the database cannot be read.

---

## Next

The Cloudflare site updates automatically from **GitHub Actions** at 5pm IST (laptop can be off) after you add the `CLOUDFLARE_API_TOKEN` secret. Every daily report from **2026-08-17 onward** stays in the archive. On the live page, open **Archive**, pick a day, and read the briefing on the page (downloads stay as extras). Subscribe in Feedly or any RSS app at https://ai-daily-intelligence.pages.dev/feed.xml — or click **RSS** next to Download PDF. The stable URL is https://ai-daily-intelligence.pages.dev
