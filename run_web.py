from __future__ import annotations

import argparse

from .web.app import WEB_HOST, WEB_PORT, create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local kensho_assistant web app")
    parser.add_argument("--smoke-test", action="store_true")
    # Used only by the owned Windows launcher to identify its child process.
    parser.add_argument("--managed-by", default="", help=argparse.SUPPRESS)
    return parser


def run_smoke_test() -> int:
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        for path in ("/", "/review", "/entries", "/health"):
            response = client.get(path)
            if response.status_code != 200:
                return 1
        health = client.get("/health").json()
    if health.get("submitted_count_auto") != 0:
        return 1
    print("WEB_SMOKE_TEST_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke_test:
        return run_smoke_test()

    import uvicorn

    uvicorn.run(create_app(), host=WEB_HOST, port=WEB_PORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
