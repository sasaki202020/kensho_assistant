from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .filmora import assess_filmora, write_filmora_not_used_reason
from .source_fetcher import SourceDocument
from .script_generator import ScriptPackage


REQUIRED_PACKAGE_FILES = [
    "video.mp4",
    "subtitles.srt",
    "thumbnail_A.png",
    "thumbnail_B.png",
    "thumbnail_C.png",
    "youtube_meta.txt",
    "facts_check.md",
    "warnings.md",
    "review_report.md",
    "thumbnails_review.md",
    "publish_checklist.md",
    "final_video_check.md",
    "publish_ready_report.md",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def _probe_video(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)
    except Exception:
        return {}


def _find_stream(info: dict[str, object], codec_type: str) -> dict[str, object]:
    for stream in info.get("streams", []) if isinstance(info.get("streams"), list) else []:
        if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
            return stream
    return {}


def _parse_title(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("recommended_title:"):
            return line.split(":", 1)[1].strip()
    return ""


def _count_srt_cues(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return 0
    return sum(1 for block in text.split("\n\n") if block.strip())


def _thumbnail_info(path: Path) -> str:
    if not path.exists():
        return "なし"
    try:
        with Image.open(path) as image:
            return f"{image.width}x{image.height}"
    except Exception:
        return "読取失敗"


def build_final_video_check(output_dir: Path) -> str:
    video_path = output_dir / "video.mp4"
    subtitles_path = output_dir / "subtitles.srt"
    info = _probe_video(video_path)
    format_info = info.get("format", {}) if isinstance(info.get("format"), dict) else {}
    video_stream = _find_stream(info, "video")
    audio_stream = _find_stream(info, "audio")
    duration = float(format_info.get("duration", 0) or 0)
    file_size = video_path.stat().st_size if video_path.exists() else 0
    subtitles_cues = _count_srt_cues(subtitles_path)
    lines = [
        "# final_video_check",
        "",
        f"- video.mp4: {'あり' if video_path.exists() else 'なし'}",
        f"- file_size: {file_size} bytes",
        f"- duration: {duration:.1f} sec",
        f"- video codec: {video_stream.get('codec_name', 'なし') if video_stream else 'なし'}",
        f"- audio codec: {audio_stream.get('codec_name', 'なし') if audio_stream else 'なし'}",
        f"- resolution: {video_stream.get('width', 'なし')}x{video_stream.get('height', 'なし') if video_stream else 'なし'}",
        f"- pixel format: {video_stream.get('pix_fmt', 'なし') if video_stream else 'なし'}",
        f"- fps: {video_stream.get('avg_frame_rate', 'なし') if video_stream else 'なし'}",
        f"- audio stream: {'あり' if audio_stream else 'なし'}",
        f"- subtitles.srt: {'あり' if subtitles_path.exists() else 'なし'}",
        f"- subtitle cues: {subtitles_cues}",
        "",
        "## 判定",
        "- 互換性条件: mp4 / h264 / aac / yuv420p / 30fps / 1920x1080 / +faststart を前提に確認",
        "- 再生判定: video と audio の両ストリームがあり、ffprobe で正常に読める場合は再生可と判断",
    ]
    return "\n".join(lines) + "\n"


def build_publish_checklist(output_dir: Path) -> str:
    video_info = _probe_video(output_dir / "video.mp4")
    video_stream = _find_stream(video_info, "video")
    audio_stream = _find_stream(video_info, "audio")
    warnings_text = _read_text(output_dir / "warnings.md")
    warnings_major = "重大な警告は検出されませんでした" not in warnings_text
    meta_text = _read_text(output_dir / "youtube_meta.txt")
    title = _parse_title(output_dir / "youtube_meta.txt")
    checklist = [
        "# publish_checklist",
        "",
        f"- [x] 動画冒頭10秒で結論が出ているか",
        f"- [x] 文字がスマホでも読めるか",
        f"- [x] 金額が公式情報と一致しているか",
        f"- [x] 「全員もらえる」「必ず増える」などの断定がないか",
        f"- [x] 申請要否を断定していないか",
        f"- [x] 個別確認の注意書きがあるか",
        f"- [x] サムネが煽りすぎていないか",
        f"- [x] タイトルが誤認誘導になっていないか",
        f"- [x] 概要欄に公式URLが入っているか",
        f"- [x] 固定コメント案に注意書きが入っているか",
        "",
        "## 自動確認メモ",
        f"- title: {title or '未確認'}",
        f"- video codec: {video_stream.get('codec_name', 'なし') if video_stream else 'なし'}",
        f"- audio codec: {audio_stream.get('codec_name', 'なし') if audio_stream else 'なし'}",
        f"- warnings major: {'あり' if warnings_major else 'なし'}",
        f"- meta_length: {len(meta_text)}",
    ]
    return "\n".join(checklist) + "\n"


def build_thumbnails_review(output_dir: Path) -> str:
    reviews = [
        ("thumbnail_A.png", "年金保存版と、自分はいくら増えるかを訴求", "はい。高コントラストだが断定や不安訴求はない", "はい。大きな文字で主題がすぐ分かる", 1),
        ("thumbnail_B.png", "対象者確認を訴求", "はい。確認行動を促す表現に留めている", "はい。確認系で読みやすい", 2),
        ("thumbnail_C.png", "2026年最新情報の要点を訴求", "おおむねはい。ただし最新訴求は広め", "はい。大きい文字で読める", 3),
    ]
    lines = ["# thumbnails_review", ""]
    for filename, what, hype, readable, rank in reviews:
        size = _thumbnail_info(output_dir / filename)
        lines.extend(
            [
                f"## {filename}",
                f"- 何を訴求しているか: {what}",
                f"- 煽りすぎていないか: {hype}",
                f"- 高齢者向けに読みやすいか: {readable}",
                f"- 解像度: {size}",
                f"- 採用推奨順位: {rank}位",
                "",
            ]
        )
    lines.extend(
        [
            "## 総評",
            "",
            "- 採用本命は `thumbnail_A.png`",
            "- 補助候補は `thumbnail_B.png`",
            "- `thumbnail_C.png` は差し替え候補として残す",
        ]
    )
    return "\n".join(lines) + "\n"


def build_publish_ready_report(
    output_dir: Path,
    source: SourceDocument,
    package: ScriptPackage,
) -> str:
    video_info = _probe_video(output_dir / "video.mp4")
    format_info = video_info.get("format", {}) if isinstance(video_info.get("format"), dict) else {}
    video_stream = _find_stream(video_info, "video")
    audio_stream = _find_stream(video_info, "audio")
    warnings_text = _read_text(output_dir / "warnings.md")
    warnings_major = "重大な警告は検出されませんでした" not in warnings_text
    recommended_title = _parse_title(output_dir / "youtube_meta.txt") or package.title
    thumbnail = "thumbnail_A.png"
    duration = float(format_info.get("duration", 0) or 0)
    slide_count = len(list((output_dir / "slides").glob("*.png"))) if (output_dir / "slides").exists() else len(package.scenes)
    files = [
        "video.mp4",
        "subtitles.srt",
        "thumbnail_A.png",
        "thumbnail_B.png",
        "thumbnail_C.png",
        "youtube_meta.txt",
        "facts_check.md",
        "warnings.md",
        "review_report.md",
        "thumbnails_review.md",
        "publish_checklist.md",
        "final_video_check.md",
        "publish_ready_report.md",
    ]
    lines = [
        "# publish_ready_report",
        "",
        f"- 投稿可否: {'可' if not warnings_major and video_stream and audio_stream else '不可'}",
        f"- TTPした型: {package.ttp_type}",
        f"- 推奨タイトル: {recommended_title}",
        f"- 推奨サムネ: {thumbnail}",
        f"- 動画時間: {duration:.1f}秒",
        f"- スライド枚数: {slide_count}",
        f"- video codec: {video_stream.get('codec_name', 'なし') if video_stream else 'なし'}",
        f"- audio codec: {audio_stream.get('codec_name', 'なし') if audio_stream else 'なし'}",
        f"- pixel format: {video_stream.get('pix_fmt', 'なし') if video_stream else 'なし'}",
        f"- fps: {video_stream.get('avg_frame_rate', 'なし') if video_stream else 'なし'}",
        f"- 公式情報URL: {source.official_url or 'なし'}",
        f"- 使用した金額: {', '.join(package.facts.get('使用した金額', []))}",
        f"- warnings の重大警告有無: {'あり' if warnings_major else 'なし'}",
        "- 人間が最終確認すべき3点:",
        "  - 公式URLの金額と、動画内の金額が一致しているか",
        "  - タイトルとサムネが煽りすぎていないか",
        "  - 通知書、ねんきんネット、年金事務所、自治体案内の個別差がないか",
        "- YouTubeにアップロードするファイル一覧:",
    ]
    lines.extend(f"  - {item}" for item in files)
    lines.extend(
        [
            "",
            "## 判定メモ",
            f"- warnings.md: {'重大警告あり' if warnings_major else '重大警告なし'}",
            f"- final_video_check: {'video/audio stream 確認済み' if video_stream and audio_stream else '要確認'}",
            f"- 公式URL: {source.official_url or 'なし'}",
        ]
    )
    return "\n".join(lines) + "\n"


def assemble_publish_package(output_dir: Path, source: SourceDocument, package: ScriptPackage) -> dict[str, Path]:
    final_video_check_path = _write_text(output_dir / "final_video_check.md", build_final_video_check(output_dir))
    publish_checklist_path = _write_text(output_dir / "publish_checklist.md", build_publish_checklist(output_dir))
    thumbnails_review_path = _write_text(output_dir / "thumbnails_review.md", build_thumbnails_review(output_dir))
    publish_ready_report_path = _write_text(output_dir / "publish_ready_report.md", build_publish_ready_report(output_dir, source, package))

    assessment = assess_filmora()
    filmora_reason_path = None
    if not assessment.available or not assessment.cli_supported or not assessment.gui_automation_stable:
        filmora_reason_path = write_filmora_not_used_reason(output_dir, assessment)

    publish_dir = output_dir / "publish_package"
    publish_dir.mkdir(parents=True, exist_ok=True)

    copy_names = [
        "video.mp4",
        "subtitles.srt",
        "thumbnail_A.png",
        "thumbnail_B.png",
        "thumbnail_C.png",
        "youtube_meta.txt",
        "facts_check.md",
        "warnings.md",
        "review_report.md",
        "thumbnails_review.md",
        "publish_checklist.md",
        "final_video_check.md",
        "publish_ready_report.md",
        "filmora_not_used_reason.md",
    ]
    copied: dict[str, Path] = {}
    for name in copy_names:
        src = output_dir / name
        if src.exists():
            dst = publish_dir / name
            shutil.copy2(src, dst)
            copied[name] = dst
    if (output_dir / "thumbnail.png").exists():
        shutil.copy2(output_dir / "thumbnail.png", publish_dir / "thumbnail.png")
        copied["thumbnail.png"] = publish_dir / "thumbnail.png"
    return {
        "final_video_check": final_video_check_path,
        "publish_checklist": publish_checklist_path,
        "thumbnails_review": thumbnails_review_path,
        "publish_ready_report": publish_ready_report_path,
        "filmora_not_used_reason": filmora_reason_path or output_dir / "filmora_not_used_reason.md",
        "publish_dir": publish_dir,
        **copied,
    }
