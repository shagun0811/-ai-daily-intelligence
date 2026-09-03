# AI Daily Intelligence

A student/mentor deliverable: collect AI news (plus a few papers), rank it, and publish a daily briefing.

**Live site:** https://ai-daily-intelligence.pages.dev  
**RSS:** https://ai-daily-intelligence.pages.dev/feed.xml (Feedly, or Edge via the XSL stylesheet)  
**Daily runs:** GitHub Actions at **1:00am** and **5:00pm IST**. Laptop can be off. Deploys Cloudflare Pages `--branch production`.

Each edition includes ranked stories with why-it-matters, an on-page archive reader, a PDF, visuals, and a short MP4.

---

## What it is

RSS / arXiv come in, get cleaned and scored, then a **news-first** pack is written as Markdown / HTML / PDF. The public UI is the static site in `site/`, not Streamlit.

Summaries default to the **mock** provider (keyword-shaped JSON). GitHub Actions always uses mock. Ollama is optional locally and is **not** required.

Video is a **local** product feature: Pillow slides encoded with ffmpeg. No Runway, HeyGen, ElevenLabs, or other paid media APIs. There is **no voiceover**.

---

## Daily schedule

| When | What |
| --- | --- |
| 01:00 IST | Overnight pipeline so “today” is not yesterday’s leftover |
| 17:00 IST | Afternoon refresh |

Both jobs install ffmpeg, write today’s MP4 (GIF only if encode fails; the job stays green), export `site/`, and deploy production.

---

## How video is made

1. The report writer renders title / story / end-card slides from the same text as the PDF.
2. ffmpeg (PATH, `imageio-ffmpeg`, or a one-time Windows download) encodes H.264 MP4.
3. The site shows **Watch video** next to **Download PDF**, an in-page player, and **Download MP4**.

If ffmpeg is missing, a GIF still writes. That is a fallback, not the intended daily output.

---

## Run once (local)

```powershell
cd C:\Users\KIIT0001\Desktop\ai-daily-intelligence
.\.venv\Scripts\Activate.ps1
pip install -r requirements-ci.txt
python scripts/run_pipeline.py
```

That collects, ranks, writes reports, exports `site/`, and encodes video when ffmpeg is available. To export the site only: `python scripts/export_site.py`.

Preview: `python scripts/preview_site.py`

---

## GitHub Actions (laptop off)

Repo: `shagun0811/-ai-daily-intelligence` (leading hyphen).

1. Secrets: `CLOUDFLARE_API_TOKEN` (Cloudflare Pages Edit on this account).
2. Variable: `CLOUDFLARE_ACCOUNT_ID`.
3. Workflow: `.github/workflows/daily.yml` — pytest is `.github/workflows/tests.yml` (mock LLM, no Ollama).

Do not commit `.env`.

---

## Honest limits

- Actions uses **mock summaries**, not a hosted LLM.
- Video is silent local slides, not a studio/voice product.
- A calendar day always publishes an IST edition; if RSS is thin after a gap, the pack may reuse still-fresh stories (dates stay on each item).
- Streamlit (`app/dashboard.py`) is a local inspector, not the live site.

---

## Tests

```powershell
pytest
```

Tests do not start the scheduler, Streamlit, Ollama, Wrangler, or the live website.
