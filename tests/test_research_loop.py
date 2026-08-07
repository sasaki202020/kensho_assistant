from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.research_loop import run_research_loop


def test_research_loop_runs_multiple_rounds_until_threshold(tmp_path: Path) -> None:
    out_root = tmp_path / "data" / "research" / "loop"

    result = run_research_loop(
        question="高額当選の懸賞を探したい",
        mode="verify",
        provider="mock",
        confidence_threshold=0.82,
        max_rounds=3,
        limit=5,
        output_root=out_root,
    )

    output_dir = Path(result["output_dir"])
    report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))
    rounds = json.loads((output_dir / "rounds.json").read_text(encoding="utf-8"))
    final_answer = (output_dir / "final_answer.md").read_text(encoding="utf-8")

    assert result["status"] in {"success", "partial"}
    assert report["status"] in {"success", "partial"}
    assert report["decision"] in {"complete", "needs_more_research"}
    assert report["source_query_total"] >= report["round_count"] * 2
    assert report["source_run_total"] >= report["round_count"] * 2
    assert report["final_confidence"] >= 0.0
    assert len(rounds) == report["round_count"]
    assert (output_dir / "rounds" / "round_01" / "source_runs.json").exists()
    assert (output_dir / "rounds" / "round_01" / "aggregated_analysis.json").exists()
    assert (output_dir / "rounds" / "round_01" / "cross_check.json").exists()
    assert rounds[0]["source_query_count"] >= 2
    assert rounds[0]["source_run_count"] >= 2
    assert rounds[0]["unique_source_count"] >= 2
    assert rounds[0]["source_queries"]
    assert rounds[0]["source_runs"]
    assert rounds[0]["aggregated_analysis_path"]
    assert rounds[0]["cross_check_path"]
    assert rounds[0]["follow_up_query"]
    assert "## 信頼スコア" in final_answer


def test_research_loop_masks_sensitive_tokens(tmp_path: Path) -> None:
    out_root = tmp_path / "data" / "research" / "loop"

    result = run_research_loop(
        question="調査用 me@example.com token=abc123",
        mode="verify",
        provider="mock",
        confidence_threshold=0.8,
        max_rounds=2,
        limit=5,
        output_root=out_root,
    )

    output_dir = Path(result["output_dir"])
    report_text = (output_dir / "run_report.json").read_text(encoding="utf-8")
    plan_text = (output_dir / "run_plan.json").read_text(encoding="utf-8")

    assert "me@example.com" not in report_text
    assert "token=abc123" not in report_text
    assert "me@example.com" not in plan_text
    assert "token=abc123" not in plan_text
