from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.harness import x_research_harness as harness


def test_x_research_harness_writes_expected_outputs(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "x_harness"
    monkeypatch.setattr(
        harness,
        "MOCK_X_POSTS",
        [
            harness.XPost(
                author="sample user",
                handle="@sample",
                post_url="https://x.com/sample/status/123",
                text="Codexにサブエージェント3並列レビューをさせると開発が完全自動化できます。寝ている間に全部終わります。",
                engagement_hint="high",
            ),
            harness.XPost(
                author="cautious user",
                handle="@cautious",
                post_url="https://x.com/cautious/status/456",
                text="AI駆動開発は便利だけど、設計レビューとテスト確認を人間がやらないと危ない。完全自動という表現は言いすぎ。",
                engagement_hint="medium",
            ),
        ],
    )

    result = harness.run_x_research_harness(
        query="AI駆動開発 Codex サブエージェント レビュー",
        mode="note",
        mock=True,
        output_root=out_root,
    )

    output_dir = Path(result.output_dir)
    assert (output_dir / "run_plan.json").exists()
    assert (output_dir / "raw_x_results.json").exists()
    assert (output_dir / "claim_analysis.json").exists()
    assert (output_dir / "note_material.md").exists()
    assert (output_dir / "sources.csv").exists()
    assert (output_dir / "run_report.json").exists()

    claim = json.loads((output_dir / "claim_analysis.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))
    note = (output_dir / "note_material.md").read_text(encoding="utf-8")

    assert "完全自動" in claim["exaggeration_flags"]
    assert claim["opposing_points"]
    assert claim["note_article_angles"]
    assert report["status"] == "success"
    assert report["mode"] == "note"
    assert "## Xで話題になっている主張" in note
    assert "## サムネ文言案" in note


def test_x_research_harness_masks_tokens_and_emails_in_saved_files(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "x_harness"
    monkeypatch.setattr(
        harness,
        "MOCK_X_POSTS",
        [
            harness.XPost(
                author="token user",
                handle="@token",
                post_url="https://x.com/token/status/999",
                text="連絡先 me@example.com token=abc123 で案内します。",
                engagement_hint="low",
            )
        ],
    )

    result = harness.run_x_research_harness(
        query="調査用 token@example.com",
        mode="quick",
        mock=True,
        output_root=out_root,
    )

    output_dir = Path(result.output_dir)
    raw = (output_dir / "raw_x_results.json").read_text(encoding="utf-8")
    plan = (output_dir / "run_plan.json").read_text(encoding="utf-8")
    report = (output_dir / "run_report.json").read_text(encoding="utf-8")

    assert "me@example.com" not in raw
    assert "token=abc123" not in raw
    assert "token@example.com" not in plan
    assert "token@example.com" not in report
    assert "me@example.com" not in report
    assert json.loads(report)["provider"] == "mock"


def test_x_research_harness_provider_hermes_writes_outputs(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "x_harness"
    monkeypatch.setattr(
        harness,
        "run_hermes_x_search",
        lambda query: {
            "status": "success",
            "reason": "ok",
            "error_type": "",
            "returncode": 0,
            "stdout": "[redacted]",
            "stderr": "",
            "started_at": "2026-05-20T00:00:00+09:00",
            "finished_at": "2026-05-20T00:00:01+09:00",
            "duration_sec": 1.0,
            "response": {
                "topic": query,
                "related_posts": [
                    {
                        "author": "hermes user",
                        "handle": "@hermes",
                        "post_url": "https://x.com/hermes/status/1",
                        "text": "AI駆動開発は便利です。",
                        "summary": "便利",
                        "claim": "便利",
                        "evidence_level": "high",
                        "risk_flags": [],
                    }
                ],
                "source_urls": ["https://x.com/hermes/status/1"],
            },
            "raw_result_count": 1,
            "parsed_result_count": 1,
        },
    )

    result = harness.run_x_research_harness(
        query="AI駆動開発 Codex サブエージェント レビュー",
        mode="note",
        mock=False,
        provider="hermes",
        output_root=out_root,
    )

    output_dir = Path(result.output_dir)
    report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))
    note = (output_dir / "note_material.md").read_text(encoding="utf-8")

    assert report["provider"] == "hermes"
    assert report["status"] == "success"
    assert report["fallback_used"] is False
    assert report["hermes_status"] == "success"
    assert report["hermes_error_type"] == ""
    assert report["raw_result_count"] == 1
    assert report["parsed_result_count"] == 1
    assert "AI駆動開発は便利です。" in note


def test_x_research_harness_provider_hermes_quick_uses_light_prompt_and_summary(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "x_harness"
    called = {}

    def fake_hermes(query, **kwargs):  # noqa: ANN001
        called["query"] = query
        called["kwargs"] = kwargs
        return {
            "status": "success",
            "reason": "ok",
            "error_type": "",
            "returncode": 0,
            "stdout": "[redacted]",
            "stderr": "",
            "started_at": "2026-05-20T00:00:00+09:00",
            "finished_at": "2026-05-20T00:00:01+09:00",
            "duration_sec": 1.0,
            "response": {
                "topic": query,
                "related_posts": [
                    {
                        "post_url": "https://x.com/hermes/status/1",
                        "summary": "Hermes Agent is live from Nous Research.",
                    }
                ],
                "source_urls": ["https://x.com/hermes/status/1"],
            },
            "raw_result_count": 1,
            "parsed_result_count": 1,
        }

    monkeypatch.setattr(harness, "run_hermes_x_search", fake_hermes)

    result = harness.run_x_research_harness(
        query="Hermes Agent",
        mode="quick",
        mock=False,
        provider="hermes",
        output_root=out_root,
    )

    output_dir = Path(result.output_dir)
    report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))
    raw_posts = json.loads((output_dir / "raw_x_results.json").read_text(encoding="utf-8"))
    note = (output_dir / "note_material.md").read_text(encoding="utf-8")

    assert result.status == "success"
    assert called["query"] == "Hermes Agent"
    assert called["kwargs"]["prefer_array"] is True
    assert "x_searchを使って" in called["kwargs"]["prompt"]
    assert report["status"] == "success"
    assert report["provider"] == "hermes"
    assert report["hermes_error_type"] == ""
    assert report["post_count"] == 1
    assert report["parsed_result_count"] == 1
    assert raw_posts[0]["text"] == "Hermes Agent is live from Nous Research."
    assert "Hermes Agent is live from Nous Research." in note


def test_x_research_harness_provider_hermes_failure_still_writes_report(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "x_harness"
    monkeypatch.setattr(
        harness,
        "run_hermes_x_search",
        lambda query: {
            "status": "failed",
            "reason": "timeout",
            "error_type": "timeout",
            "returncode": 124,
            "stdout": "",
            "stderr": "",
            "started_at": "2026-05-20T00:00:00+09:00",
            "finished_at": "2026-05-20T00:02:00+09:00",
            "duration_sec": 120.0,
            "response": {"topic": query, "related_posts": []},
            "raw_result_count": 0,
            "parsed_result_count": 0,
        },
    )

    result = harness.run_x_research_harness(
        query="AI駆動開発 Codex サブエージェント レビュー",
        mode="note",
        mock=False,
        provider="hermes",
        output_root=out_root,
    )

    output_dir = Path(result.output_dir)
    report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))

    assert report["provider"] == "hermes"
    assert report["status"] == "failed"
    assert report["fallback_used"] is False
    assert report["hermes_error_type"] == "timeout"
    assert not (output_dir / "note_material.md").exists()


def test_x_research_harness_provider_hermes_empty_success_is_failed_empty_result(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "x_harness"
    monkeypatch.setattr(
        harness,
        "run_hermes_x_search",
        lambda query, **kwargs: {
            "status": "success",
            "reason": "ok",
            "error_type": "",
            "returncode": 0,
            "stdout": "[]",
            "stderr": "",
            "started_at": "2026-05-20T00:00:00+09:00",
            "finished_at": "2026-05-20T00:00:01+09:00",
            "duration_sec": 1.0,
            "response": {"topic": query, "related_posts": []},
            "raw_result_count": 0,
            "parsed_result_count": 0,
        },
    )

    result = harness.run_x_research_harness(
        query="Hermes Agent",
        mode="quick",
        mock=False,
        provider="hermes",
        output_root=out_root,
    )

    output_dir = Path(result.output_dir)
    report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))

    assert result.status == "failed"
    assert report["status"] == "failed"
    assert report["hermes_status"] == "success"
    assert report["hermes_error_type"] == "empty_result"
    assert report["reason"] == "empty_result"
    assert not (output_dir / "note_material.md").exists()
