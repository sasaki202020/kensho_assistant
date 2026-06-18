from __future__ import annotations

import argparse

import uvicorn

from .app import create_app
from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="現場査定AI v0.1 backend")
    parser.add_argument("--host", default=None, help="bind host")
    parser.add_argument("--port", type=int, default=None, help="bind port")
    parser.add_argument("--reload", action="store_true", help="enable auto reload")
    args = parser.parse_args(argv)

    settings = load_settings()
    host = args.host or settings.host
    port = args.port or settings.port
    app = create_app(settings)
    uvicorn.run(app, host=host, port=port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

