"""`python -m scheherazades_hoard` — start the app on 127.0.0.1.

Flags: --port, --data-dir, --demo, --no-browser (matches the shared
contract's launch shape so Faustus's `launch_hint` and the
`Iniciar/Detener` scripts work unmodified).
"""
from __future__ import annotations

import argparse
import os
import webbrowser
from pathlib import Path

import uvicorn

from . import __version__
from .api import DEFAULT_PORT, create_app
from .demo import seed_demo_world

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(prog="scheherazades_hoard")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SCHEHERAZADE_PORT", DEFAULT_PORT)))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--demo", action="store_true", help="use data-demo/ seeded with a synthetic world")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab on start")
    args = parser.parse_args()

    if args.data_dir:
        data_dir = args.data_dir
    elif args.demo:
        data_dir = REPO_ROOT / "data-demo"
    else:
        data_dir = Path(os.environ.get("SCHEHERAZADE_DATA_DIR", REPO_ROOT / "data"))

    static_dir = REPO_ROOT / "frontend" / "dist"
    app = create_app(data_dir, static_dir if static_dir.exists() else None, port=args.port)

    if args.demo:
        seed_demo_world(app.state.conn)

    url = f"http://127.0.0.1:{args.port}"
    print(f"Scheherazade's Hoard v{__version__} -> {url} (data: {data_dir})")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
