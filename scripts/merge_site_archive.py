"""Merge older briefing days into site/ before Cloudflare deploy.

Wrangler Pages uploads replace the whole snapshot. A laptop export that only
has today's files would wipe days GitHub Actions already published. This script
fills gaps from a local tree, the live site (when reachable), or the previous
successful daily-report artifact.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.site_export import (  # noqa: E402
    SITE_DIR,
    ingest_live_archive,
    merge_archive_tree,
    persist_public_archive,
)


def main() -> None:
    dest = SITE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    extra = os.environ.get("ADI_ARCHIVE_SOURCE", "").strip()
    added: list[str] = []
    if extra:
        added.extend(merge_archive_tree(dest, Path(extra)))
    live = ingest_live_archive(dest)
    added.extend(live)
    if os.environ.get("ADI_MERGE_GITHUB_ARTIFACT", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }:
        artifact_site = _download_previous_artifact()
        if artifact_site is not None:
            added.extend(merge_archive_tree(dest, artifact_site))
    dates = persist_public_archive(dest)
    print("archive dates:", dates)
    print("merged:", sorted(set(added)))


def _download_previous_artifact() -> Path | None:
    gh = shutil.which("gh")
    if not gh:
        print("gh not found; skip previous-artifact merge")
        return None
    current = str(os.environ.get("GITHUB_RUN_ID") or "")
    listed = subprocess.run(
        [
            gh,
            "run",
            "list",
            "--workflow",
            "daily.yml",
            "--status",
            "success",
            "--limit",
            "8",
            "--json",
            "databaseId",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        print(listed.stderr.strip() or "could not list previous daily runs")
        return None
    try:
        rows = json.loads(listed.stdout or "[]")
    except json.JSONDecodeError:
        return None
    run_id = ""
    for row in rows:
        ident = str(row.get("databaseId") or "")
        if ident and ident != current:
            run_id = ident
            break
    if not run_id:
        print("no previous successful daily run to merge")
        return None
    tmp = Path(tempfile.mkdtemp(prefix="adi-archive-"))
    pulled = subprocess.run(
        [gh, "run", "download", run_id, "--name", "daily-report", "--dir", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    if pulled.returncode != 0:
        print(pulled.stderr.strip() or f"could not download artifact from run {run_id}")
        return None
    if (tmp / "site").is_dir():
        print(f"merging daily-report artifact from run {run_id}")
        return tmp / "site"
    if (tmp / "data").is_dir() or (tmp / "files").is_dir():
        print(f"merging daily-report artifact from run {run_id}")
        return tmp
    nested = next((path for path in tmp.rglob("history.json")), None)
    if nested is None:
        print(f"artifact from run {run_id} had no site/data")
        return None
    print(f"merging daily-report artifact from run {run_id}")
    return nested.parent.parent


if __name__ == "__main__":
    main()
