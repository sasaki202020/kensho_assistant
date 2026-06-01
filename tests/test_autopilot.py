from __future__ import annotations

from pathlib import Path

from src.autopilot import run_autopilot


def test_autopilot_sample_creates_expected_artifacts(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    data_root = tmp_path / "data"
    result = run_autopilot(
        area="北九州市 小倉北区",
        industry="整骨院",
        limit=3,
        sample=True,
        report_root=report_root,
        data_root=data_root,
    )

    report_dir = Path(result["report_dir"])
    assert report_dir.exists()
    assert (report_dir / "index.html").exists()
    assert (report_dir / "leads_scored.csv").exists()
    assert (report_dir / "crm.csv").exists()
    assert Path(result["generated_leads_csv"]).exists()

    company_dirs = sorted((report_dir / "companies").iterdir())
    assert company_dirs
    first = company_dirs[0]
    assert (first / "customer_report.pdf").exists()
    assert (first / "internal_report.html").exists()
    assert (first / "proposal.txt").exists()
    assert (first / "estimate.md").exists()
    assert (first / "fix_plan.md").exists()
    assert (first / "raw.json").exists()
    assert (first / "screenshots" / "desktop.png").exists()
    assert (first / "marketplace_helper.html").exists()

