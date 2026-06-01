from __future__ import annotations

import argparse
import sys

import uvicorn
from fastapi.testclient import TestClient

from kensho_assistant.web.app import WEB_HOST, WEB_PORT, create_app


def smoke_test() -> None:
    app = create_app()
    with TestClient(app) as client:
        for path in ("/", "/today", "/search", "/queue", "/later-queue", "/mail", "/campaigns", "/review", "/security"):
            response = client.get(path)
            response.raise_for_status()
            text = response.text
        assert "本番送信は人間確認が必要" in text
        assert "submit-approved" not in text
        if path == "/later-queue":
            assert "あとで応募" in text
            assert "自動送信しません" in text
        if path not in {"/", "/security"}:
            assert "profile.enc" not in text
            assert "profile.json" not in text
            assert ".env" not in text
        assert "今日のおすすめアクション" in client.get("/").text
        assert "今日見るべき候補" in client.get("/today").text
        assert app.state.web_host == WEB_HOST
        assert app.state.web_port == WEB_PORT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="kensho_assistant local web ui")
    parser.add_argument("--smoke-test", action="store_true", help="Run a startup smoke test and exit")
    args = parser.parse_args(argv)
    if args.smoke_test:
        smoke_test()
        print("WEB_SMOKE_TEST_OK")
        return 0
    uvicorn.run(create_app(), host=WEB_HOST, port=WEB_PORT, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
