"""Export the static Cloudflare Pages site from the local database."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.logging import setup_logging
from app.database.database import init_db, session_scope
from app.site_export import export_public_site


def main() -> None:
    setup_logging()
    init_db(seed=True)
    with session_scope() as session:
        summary = export_public_site(session)
    print(summary.as_text())
    print("Open inside VS Code Simple Browser:")
    print("  python scripts/preview_site.py")
    print("Or: Terminal → Run Task → Preview briefing in VS Code")
    print("Live site: https://ai-daily-intelligence.pages.dev")
    print("The daily scheduler deploys this automatically when CLOUDFLARE_AUTO_DEPLOY=true")
    sys.exit(0 if not summary.errors else 1)


if __name__ == "__main__":
    main()
