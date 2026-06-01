from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FilmoraAssessment:
    available: bool
    executable: str | None
    cli_supported: bool
    gui_automation_stable: bool
    reason: str


def assess_filmora() -> FilmoraAssessment:
    candidates = [
        shutil.which("filmora"),
        shutil.which("Filmora"),
        shutil.which("filmora.exe"),
        shutil.which("Filmora.exe"),
    ]
    executable = next((item for item in candidates if item), None)
    if executable:
        return FilmoraAssessment(
            available=True,
            executable=executable,
            cli_supported=False,
            gui_automation_stable=False,
            reason="Filmora executable was found, but this pipeline does not rely on a stable CLI or GUI automation.",
        )
    return FilmoraAssessment(
        available=False,
        executable=None,
        cli_supported=False,
        gui_automation_stable=False,
        reason="Filmora executable was not found in PATH, and GUI automation would be unstable for the posting pipeline.",
    )


def write_filmora_not_used_reason(output_dir: Path, assessment: FilmoraAssessment) -> Path:
    path = output_dir / "filmora_not_used_reason.md"
    lines = [
        "# filmora_not_used_reason",
        "",
        f"- available: {'yes' if assessment.available else 'no'}",
        f"- executable: {assessment.executable or 'なし'}",
        f"- cli_supported: {'yes' if assessment.cli_supported else 'no'}",
        f"- gui_automation_stable: {'yes' if assessment.gui_automation_stable else 'no'}",
        f"- reason: {assessment.reason}",
        "",
        "- 結論: Filmora は使わず、Python + FFmpeg で完結させる。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
