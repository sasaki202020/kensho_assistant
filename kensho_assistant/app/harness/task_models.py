from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


HarnessMode = Literal["quick", "verify", "note", "ttp"]


@dataclass(frozen=True)
class XResearchTask:
    query: str
    mode: HarnessMode
    mock: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class XPost:
    author: str
    handle: str
    post_url: str
    text: str
    engagement_hint: str = "unknown"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class HarnessRunResult:
    output_dir: str
    files: dict[str, str] = field(default_factory=dict)
    status: str = "success"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
