from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _probe_video_duration(video_path: Path) -> float:
    if not video_path.exists():
        return 0.0
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(completed.stdout.strip())
    except Exception:
        return 0.0


def _load_json(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _extract_script_sections(script_path: Path) -> list[dict[str, object]]:
    if not script_path.exists():
        return []
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in script_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = {"title": line[3:], "body": "", "narration": "", "duration_sec": 0}
        elif line.startswith("- 画面:") and current is not None:
            current["body"] = line.split(":", 1)[1].strip()
        elif line.startswith("- ナレーション:") and current is not None:
            current["narration"] = line.split(":", 1)[1].strip()
        elif line.startswith("- 予定尺:") and current is not None:
            value = line.split(":", 1)[1].strip().replace("秒", "")
            try:
                current["duration_sec"] = int(value)
            except ValueError:
                current["duration_sec"] = 0
    if current:
        sections.append(current)
    return sections


def _severity(warnings_text: str) -> str:
    if "重大な警告は検出されませんでした" in warnings_text:
        return "none"
    risky_markers = ["失敗", "抽出できません", "未確認", "サンプル扱い"]
    if any(marker in warnings_text for marker in risky_markers):
        return "major"
    return "minor"


def build_review_report(output_dir: Path) -> str:
    scenes_path = output_dir / "scenes.json"
    scenes = _load_json(scenes_path)
    if not scenes:
        scenes = _extract_script_sections(output_dir / "script.md")
    slide_dir = output_dir / "slides"
    slide_count = len(list(slide_dir.glob("*.png"))) if slide_dir.exists() else len(scenes)
    video_duration = _probe_video_duration(output_dir / "video.mp4")
    avg = video_duration / slide_count if slide_count else 0.0
    long_slides = [
        f"{idx + 1}. {scene.get('title', 'unknown')} ({scene.get('duration_sec', 0)}秒)"
        for idx, scene in enumerate(scenes)
        if int(scene.get("duration_sec", 0) or 0) > 30
    ]
    if not long_slides and slide_count and avg > 30:
        long_slides = [f"{i + 1}. long (平均{avg:.1f}秒)" for i in range(slide_count)]
    text_heavy = [
        f"{idx + 1}. {scene.get('title', 'unknown')} ({len(str(scene.get('body', ''))) + len(str(scene.get('narration', '')))}字)"
        for idx, scene in enumerate(scenes)
        if len(str(scene.get("body", ""))) + len(str(scene.get("narration", ""))) > 110
    ]
    warnings_text = (output_dir / "warnings.md").read_text(encoding="utf-8") if (output_dir / "warnings.md").exists() else ""
    report_lines = [
        "# review_report",
        "",
        f"- scenes.json: {'あり' if scenes_path.exists() else 'なし'}",
        f"- 動画時間: {video_duration:.1f}秒",
        f"- スライド枚数: {slide_count}",
        f"- 1スライドあたりの平均秒数: {avg:.1f}秒",
        f"- 長すぎるスライド: {', '.join(long_slides) if long_slides else 'なし'}",
        f"- 文字量が多すぎるスライド: {', '.join(text_heavy) if text_heavy else 'なし'}",
        f"- 重要金額が目立っているか: {'はい' if scenes and any('70,608円' in str(scene.get('emphasis', '')) or '237,279円' in str(scene.get('emphasis', '')) for scene in scenes) else 'いいえ'}",
        f"- warnings.md の重大度: {_severity(warnings_text)}",
        "- 投稿前に人間が確認すべき点:",
        "  - 金額が公式URLの内容と一致しているか",
        "  - 申請が必要な制度かどうか",
        "  - 自分の通知書、ねんきんネット、年金事務所、自治体の案内で差がないか",
        "  - サムネとタイトルが煽りすぎていないか",
        "  - 字幕が読みやすいか",
        "- 改善提案:",
        "  - 10分動画なら 24〜32 枚に分ける",
        "  - 重要金額、対象者、注意点、確認先を分けて表示する",
        "  - 中間まとめと確認先まとめを必ず入れる",
        "  - サムネは3案作り、最も安全なものを本採用する",
    ]
    return "\n".join(report_lines) + "\n"


def write_review_report(output_dir: Path) -> Path:
    path = output_dir / "review_report.md"
    path.write_text(build_review_report(output_dir), encoding="utf-8")
    return path
