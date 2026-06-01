from __future__ import annotations

from pathlib import Path

from .script_generator import ScriptPackage, MANDATORY_CAUTION
from .source_fetcher import SourceDocument


def write_fact_check(
    output_dir: Path,
    source: SourceDocument,
    package: ScriptPackage,
) -> Path:
    lines = [
        "# facts_check",
        "",
        f"- 使用した制度名: {', '.join(package.facts['使用した制度名'])}",
        f"- 使用した金額: {', '.join(package.facts['使用した金額'])}",
        f"- 対象者: {', '.join(package.facts['対象者'])}",
        f"- 申請の有無: {', '.join(package.facts['申請の有無'])}",
        f"- 注意点: {', '.join(package.facts['注意点'])}",
        f"- 参照URL: {', '.join(package.facts['参照URL'])}",
        f"- 確認が必要な表現: {', '.join(package.facts['確認が必要な表現'])}",
        "",
        "## 補足",
        f"- 重要注意文: {MANDATORY_CAUTION}",
        f"- source_status: {source.status}",
    ]
    path = output_dir / "facts_check.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
