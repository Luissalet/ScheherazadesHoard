"""`python -m scheherazades_hoard` — start the app on 127.0.0.1.

Flags: --port, --data-dir, --demo, --no-browser (matches the shared
contract's launch shape so Faustus's `launch_hint` and the
`Iniciar/Detener` scripts work unmodified).
"""
from __future__ import annotations

import argparse
import logging
import os
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from . import __version__
from .api import DEFAULT_PORT, create_app
from .demo import seed_demo_world

REPO_ROOT = Path(__file__).resolve().parent.parent


def setup_logging(data_dir: Path) -> logging.Handler:
    """Rotating `data/logs/app.log` (1 MB x 3). Tool names, timings and
    errors only — never story text, secrets or tokens."""
    logs = Path(data_dir) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    for name in ("scheherazades_hoard", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.addHandler(handler)
    return handler


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

    setup_logging(data_dir)
    static_dir = REPO_ROOT / "frontend" / "dist"
    app = create_app(data_dir, static_dir if static_dir.exists() else None, port=args.port)

    if args.demo:
        seed_demo_world(app.state.conn)

    url = f"http://127.0.0.1:{args.port}"
    print(f"Scheherazade's Hoard v{__version__} -> {url} (data: {data_dir})")
    logging.getLogger("scheherazades_hoard").info("starting v%s on %s", __version__, url)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
