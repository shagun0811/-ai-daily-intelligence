"""Daily pipeline. Collect → clean → score → summarize → report."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.runner import run_daily_pipeline


def main() -> None:
    outcome = run_daily_pipeline()
    print(outcome.as_text())
    print("Pipeline finished. Dashboard: streamlit run app/dashboard.py")
    sys.exit(0 if outcome.ok else 1)


if __name__ == "__main__":
    main()
