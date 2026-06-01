from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubmitResult:
    status: str
    submit_attempted: bool = False
    submit_clicked: bool = False
    auto_submitted: bool = False
    screenshot_path: str = ""
    html_snapshot_path: str = ""
    message: str = ""


class BaseSubmitAdapter:
    def submit(self, page, context: dict[str, object]) -> SubmitResult:
        raise NotImplementedError
