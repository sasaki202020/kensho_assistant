from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import scripts.run_x_search as run_x_search_cli
from kensho_assistant.app.research import x_search_tool as xst


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False


def test_x_search_tool_uses_prompt_and_extracts_answer(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "# 反応分類\n- ポジティブ\n\n## 誤解\n- なし\n",
                            "annotations": [{"url": "https://x.com/sample/status/1"}],
                        }
                    ],
                }
            ],
            "citations": ["https://x.com/sample/status/1"],
            "inline_citations": [],
        }
        return _FakeHTTPResponse(payload)

    monkeypatch.setenv("XAI_API_KEY", "sk-test-xai")
    monkeypatch.setattr(xst.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(xst, "RESEARCH_X_SEARCH_DIR", tmp_path / "data" / "research" / "x_search")

    result = xst.x_search_tool(
        "懸賞 プレゼントキャンペーン 締切 今週 食品",
        note_mode=True,
        allowed_x_handles=["xai"],
        from_date="2026-05-01",
        to_date="2026-05-19",
        timeout_sec=15,
    )
    paths = xst.save_x_search_outputs(result, day="2026-05-19")

    assert result["status"] == "success"
    assert "# 反応分類" in result["answer"]
    assert captured["url"] == "https://api.x.ai/v1/responses"
    assert captured["auth"] == "Bearer sk-test-xai"
    assert captured["timeout"] == 15
    body = captured["body"]
    assert body["tools"][0]["type"] == "x_search"
    assert body["tools"][0]["allowed_x_handles"] == ["xai"]
    assert body["tools"][0]["from_date"] == "2026-05-01"
    assert body["tools"][0]["to_date"] == "2026-05-19"
    assert "## 反応分類" in body["input"][0]["content"]
    assert paths["answer_path"].read_text(encoding="utf-8").startswith("# 反応分類")
    assert json.loads(paths["response_path"].read_text(encoding="utf-8"))["citations"] == ["https://x.com/sample/status/1"]


def test_resolve_token_from_hermes_auth_json(tmp_path: Path, monkeypatch) -> None:
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir(parents=True, exist_ok=True)
    (hermes_home / "auth.json").write_text(
        json.dumps({"providers": {"xai-oauth": {"access_token": "oauth-token-123"}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    token, source = xst.resolve_x_search_token()

    assert token == "oauth-token-123"
    assert source == "hermes_auth.json"


def test_run_x_search_cli_saves_outputs_and_passes_note_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    called: dict[str, object] = {}

    def fake_tool(query, **kwargs):  # noqa: ANN001
        called["query"] = query
        called["kwargs"] = kwargs
        return {
            "status": "success",
            "reason": "ok",
            "answer": "## 反応分類\n- 反応あり\n",
            "response": {"output": [], "citations": []},
            "citations": [],
            "inline_citations": [],
            "credential_source": "env:XAI_API_KEY",
            "model": "grok-4.3",
            "query": query,
            "provider": "xai",
            "tool": "x_search",
            "prompt": "prompt",
            "requested_at": "2026-05-19T12:00:00+09:00",
        }

    def fake_save(result, day=None):  # noqa: ANN001
        out_dir = tmp_path / "data" / "research" / "x_search" / "20260519"
        out_dir.mkdir(parents=True, exist_ok=True)
        answer_path = out_dir / "result.md"
        response_path = out_dir / "result.response.json"
        run_path = out_dir / "result.run.json"
        answer_path.write_text(result["answer"], encoding="utf-8")
        response_path.write_text(json.dumps(result["response"], ensure_ascii=False), encoding="utf-8")
        run_path.write_text(json.dumps({"status": result["status"]}, ensure_ascii=False), encoding="utf-8")
        return {"answer_path": answer_path, "response_path": response_path, "run_path": run_path}

    monkeypatch.setattr(run_x_search_cli, "x_search_tool", fake_tool)
    monkeypatch.setattr(run_x_search_cli, "save_x_search_outputs", fake_save)

    exit_code = run_x_search_cli.main(["--query", "from:tetumemo Hermes Agent", "--note", "--date", "2026-05-19"])
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert called["query"] == "from:tetumemo Hermes Agent"
    assert called["kwargs"]["note_mode"] is True
    assert "status: success" in captured
    assert "answer_path:" in captured
