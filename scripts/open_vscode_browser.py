"""Open a URL in VS Code / Cursor Simple Browser (inside the editor)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from urllib.parse import quote


def open_in_vscode(url: str) -> bool:
    encoded = quote(url, safe="")
    uris = [
        f"cursor://vscode.simple-browser/show?url={encoded}",
        f"vscode://vscode.simple-browser/show?url={encoded}",
    ]
    for uri in uris:
        if _open_uri(uri):
            print(f"Opened Simple Browser: {url}")
            return True

    for exe in ("cursor", "code"):
        if shutil.which(exe):
            try:
                subprocess.run(
                    [exe, "--reuse-window", "--open-url", uris[0 if exe == "cursor" else 1]],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                print(f"Opened Simple Browser via {exe}: {url}")
                return True
            except OSError:
                continue
    return False


def _open_uri(uri: str) -> bool:
    try:
        if sys.platform == "win32":
            os.startfile(uri)  # noqa: S606
            return True
        opened = webbrowser.open(uri)
        return bool(opened)
    except OSError:
        return False


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8788/"
    if not open_in_vscode(url):
        print("Could not open VS Code Simple Browser.")
        print("In VS Code: Ctrl+Shift+P → Simple Browser: Show → paste the URL.")
        sys.exit(1)


if __name__ == "__main__":
    main()
