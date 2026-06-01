from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.harness.x_research_harness import run_x_research_harness


def test_x_research_harness_mock_creates_expected_artifacts(tmp_path: Path) -> None:
    result = run_x_research_harness(
        query="AI駆動開発 Codex サブエージェント レビュー",
        mode="note",
        mock=True,
        output_root=tmp_path,
    )

    output_dir = Path(result.output_dir)
    expected = [
        "run_plan.json",
        "raw_x_results.json",
        "claim_analysis.json",
        "note_material.md",
        "sources.csv",
        "run_report.json",
    ]
    for name in expected:
        assert (output_dir / name).exists()

    analysis = json.loads((output_dir / "claim_analysis.json").read_text(encoding="utf-8"))
    assert "完全自動" in analysis["exaggeration_flags"]
    assert analysis["opposing_points"]


def test_x_research_harness_sanitizes_tokens_and_email(tmp_path: Path) -> None:
    result = run_x_research_harness(
        query="token=secret123 test@example.com AI駆動開発",
        mode="quick",
        mock=True,
        output_root=tmp_path,
    )

    combined = "\n".join(path.read_text(encoding="utf-8") for path in Path(result.output_dir).iterdir())
    assert "secret123" not in combined
    assert "test@example.com" not in combined
