"""Launch the app:  python -m app  [--port 8765] [--data-dir PATH] [--no-browser]"""
from __future__ import annotations

import argparse
import os
import threading
import webbrowser

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(description="Kindred Compass — local genealogy research workspace")
    ap.add_argument("--port", type=int, default=int(os.environ.get("KINDRED_PORT", 8765)))
    ap.add_argument("--data-dir", default=None, help="Where research data is stored (default ./data or $KINDRED_DATA_DIR)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if args.data_dir:
        os.environ["KINDRED_DATA_DIR"] = args.data_dir

    from .main import create_app
    app = create_app()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Kindred Compass running at {url}")
    print(f"Research data: {app.state.settings.data_dir}")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # Bound to loopback only: the app is a single-user local tool.
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
