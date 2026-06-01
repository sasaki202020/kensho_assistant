from __future__ import annotations

from pathlib import Path

from .script_generator import ScriptPackage, MANDATORY_CAUTION
from .source_fetcher import SourceDocument


RISKY_PHRASES = [
    "必ず得する",
    "絶対",
    "今すぐ",
    "100%",
    "全員",
    "完全に",
    "損しない",
    "断言",
    "確実に",
    "最速",
    "大損",
    "国が隠す",
    "国が教えない",
    "全員もらえる",
    "必ず増える",
    "申請すれば必ずもらえる",
]


def scan_risky_phrases(text: str) -> list[str]:
    warnings: list[str] = []
    for phrase in RISKY_PHRASES:
        if phrase in text:
            warnings.append(f"煽りすぎ・断定強め表現の可能性: {phrase}")
    return warnings


def build_warnings(source: SourceDocument, package: ScriptPackage) -> list[str]:
    warnings: list[str] = []
    if not source.official_url:
        warnings.append("公式URLなしのため、制度名・金額・対象条件はサンプル出力です。")
    if source.status == "fetch_failed":
        warnings.append("公式URLの取得に失敗しました。")
    if source.summary_lines and "本文の抽出に失敗" in source.summary_lines[0]:
        warnings.append("公式本文の抽出が弱いため、原文確認が必要です。")
    text = "\n".join([package.title, package.narration_text, MANDATORY_CAUTION])
    warnings.extend(scan_risky_phrases(text))
    if not source.official_url:
        warnings.append("数値・制度名・対象条件を断定していません。")
    return warnings


def write_warnings(output_dir: Path, warnings: list[str]) -> Path:
    lines = ["# warnings", ""]
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- 重大な警告は検出されませんでした。")
    path = output_dir / "warnings.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
