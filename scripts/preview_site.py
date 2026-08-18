"""Serve the local site and open it inside VS Code Simple Browser."""

from __future__ import annotations

import socket
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from open_vscode_browser import open_in_vscode

SITE = ROOT / "site"
HOST = "127.0.0.1"
PORT = 8788
URL = f"http://{HOST}:{PORT}/"


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def main() -> None:
    if not SITE.is_dir():
        print(f"Missing {SITE}. Run: python scripts/export_site.py")
        sys.exit(1)

    already = _port_open(HOST, PORT)
    if not already:
        handler = partial(SimpleHTTPRequestHandler, directory=str(SITE))
        server = ThreadingHTTPServer((HOST, PORT), handler)
        print(f"Serving {SITE} at {URL}")
        print("This window must stay open. Stop with Ctrl+C")

        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        for _ in range(20):
            if _port_open(HOST, PORT):
                break
            time.sleep(0.1)
    else:
        print(f"Server already running on {URL}")

    if not open_in_vscode(URL):
        print("VS Code Simple Browser did not open.")
        print("Press Ctrl+Shift+P, run Simple Browser: Show, paste:")
        print(f"  {URL}")

    if already:
        return

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
