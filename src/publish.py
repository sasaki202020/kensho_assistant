from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .filmora import FilmoraStatus, detect_filmora
from .review import build_review_report
from .script_generator import ScriptPackage
from .source_fetcher import SourceDocument


@dataclass
class VideoProbe:
    duration: float
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    pix_fmt: str | None
    fps: str | None
    audio_present: bool


def probe_video(video_path: Path) -> VideoProbe:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,channels,sample_rate",
            "-of",
            "json",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(completed.stdout)
    streams = data.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    duration = float(data.get("format", {}).get("duration", 0.0) or 0.0)
    return VideoProbe(
        duration=duration,
        video_codec=video_stream.get("codec_name"),
        audio_codec=audio_stream.get("codec_name"),
        width=video_stream.get("width"),
        height=video_stream.get("height"),
        pix_fmt=video_stream.get("pix_fmt"),
        fps=video_stream.get("avg_frame_rate"),
        audio_present=bool(audio_stream),
    )


def _count_subtitle_blocks(path: Path) -> int:
    if not path.exists():
        return 0
    blocks = 0
    current_has_text = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            current_has_text = True
        elif current_has_text:
            blocks += 1
            current_has_text = False
    if current_has_text:
        blocks += 1
    return blocks


def _image_size(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    with Image.open(path) as image:
        return image.size


def _build_thumbnail_review(topic: str, thumbnails: list[Path]) -> str:
    lines = ["# thumbnails_review", ""]
    ranking = [
        ("thumbnail_A.png", 1, "年金額改定訴求", "はい", "はい"),
        ("thumbnail_B.png", 2, "対象者確認訴求", "はい", "はい"),
        ("thumbnail_C.png", 3, "2026年最新訴求", "やや広い", "はい"),
    ]
    for filename, rank, theme, hype, readable in ranking:
        lines.extend(
            [
                f"## {filename}",
                f"- 何を訴求しているか: {theme}",
                f"- 煽りすぎていないか: {hype}",
                f"- 高齢者向けに読みやすいか: {readable}",
                f"- 採用推奨順位: {rank}位",
                "",
            ]
        )
    lines.extend(
        [
            "## 総評",
            "- 採用本命は `thumbnail_A.png`",
            "- 補助候補は `thumbnail_B.png`",
            "- `thumbnail_C.png` は差し替え候補として残す",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_publish_checklist(official_url: str | None) -> str:
    lines = [
        "# publish_checklist",
        "",
        "- [ ] 動画冒頭10秒で結論が出ているか",
        "- [ ] 文字がスマホでも読めるか",
        "- [ ] 金額が公式情報と一致しているか",
        "- [ ] 「全員もらえる」「必ず増える」などの断定がないか",
        "- [ ] 申請要否を断定していないか",
        "- [ ] 個別確認の注意書きがあるか",
        "- [ ] サムネが煽りすぎていないか",
        "- [ ] タイトルが誤認誘導になっていないか",
        "- [ ] 概要欄に公式URLが入っているか",
        "- [ ] 固定コメント案に注意書きが入っているか",
        "",
        "## 最終確認メモ",
        f"- 公式URL: {official_url or 'なし'}",
    ]
    return "\n".join(lines) + "\n"


def _build_final_video_check(probe: VideoProbe, subtitle_blocks: int, images: list[Path]) -> str:
    image_lines = []
    for path in images:
        size = _image_size(path)
        image_lines.append(f"- {path.name}: {'存在' if path.exists() else 'なし'} / {size[0]}x{size[1] if size else 0 if size else 0}" if size else f"- {path.name}: なし")
    lines = [
        "# final_video_check",
        "",
        f"- duration: {probe.duration:.1f}秒",
        f"- video codec: {probe.video_codec or 'unknown'}",
        f"- audio codec: {probe.audio_codec or 'none'}",
        f"- resolution: {probe.width or 0}x{probe.height or 0}",
        f"- pixel format: {probe.pix_fmt or 'unknown'}",
        f"- fps: {probe.fps or 'unknown'}",
        f"- audio stream: {'あり' if probe.audio_present else 'なし'}",
        f"- subtitles blocks: {subtitle_blocks}",
        "- thumbnail files:",
        *image_lines,
    ]
    return "\n".join(lines) + "\n"


def _build_publish_ready_report(
    probe: VideoProbe,
    source: SourceDocument,
    package: ScriptPackage,
    warnings_text: str,
    publish_ok: bool,
    upload_files: list[str],
) -> str:
    warning_major = "重大な警告は検出されませんでした" not in warnings_text
    lines = [
        "# publish_ready_report",
        "",
        f"- 投稿可否: {'可' if publish_ok else '不可'}",
        f"- 推奨タイトル: 2026年度の年金額改定｜公式情報をやさしく整理",
        f"- 推奨サムネ: thumbnail_A.png",
        f"- 動画時間: {probe.duration:.1f}秒",
        f"- スライド枚数: {len(package.scenes)}",
        f"- video codec: {probe.video_codec or 'unknown'}",
        f"- audio codec: {probe.audio_codec or 'none'}",
        f"- pixel format: {probe.pix_fmt or 'unknown'}",
        f"- fps: {probe.fps or 'unknown'}",
        f"- 公式情報URL: {source.official_url or 'なし'}",
        f"- 使用した金額: {', '.join(package.facts.get('使用した金額', []))}",
        f"- warnings の重大警告有無: {'あり' if warning_major else 'なし'}",
        "- 人間が最終確認すべき3点:",
        "  - 金額が公式URLの内容と一致しているか",
        "  - 申請が必要な制度かどうか",
        "  - タイトル・サムネ・概要欄に誤認誘導がないか",
        "- YouTubeにアップロードするファイル一覧:",
    ]
    lines.extend(f"  - {name}" for name in upload_files)
    return "\n".join(lines) + "\n"


def _build_filmora_reason(status: FilmoraStatus) -> str:
    return "\n".join(
        [
            "# filmora_not_used_reason",
            "",
            f"- available: {'yes' if status.available else 'no'}",
            f"- executable: {status.executable or 'none'}",
            f"- cli_supported: {'yes' if status.cli_supported else 'no'}",
            f"- gui_stability: {status.gui_stability}",
            f"- should_use: {'yes' if status.should_use else 'no'}",
            f"- reason: {status.reason}",
        ]
    ) + "\n"


def _copy_publish_files(source_dir: Path, publish_dir: Path, filenames: list[str]) -> list[str]:
    publish_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in filenames:
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, publish_dir / name)
            copied.append(name)
    return copied


def prepare_publish_package(output_dir: Path, source: SourceDocument, package: ScriptPackage) -> dict[str, object]:
    publish_dir = output_dir / "publish_package"
    video_path = output_dir / "video.mp4"
    subtitles_path = output_dir / "subtitles.srt"
    thumbnails = [output_dir / "thumbnail_A.png", output_dir / "thumbnail_B.png", output_dir / "thumbnail_C.png"]
    youtube_meta_path = output_dir / "youtube_meta.txt"
    facts_path = output_dir / "facts_check.md"
    warnings_path = output_dir / "warnings.md"
    review_path = output_dir / "review_report.md"

    probe = probe_video(video_path)
    subtitle_blocks = _count_subtitle_blocks(subtitles_path)
    warnings_text = warnings_path.read_text(encoding="utf-8", errors="replace") if warnings_path.exists() else ""
    checklist_text = _build_publish_checklist(source.official_url)
    final_video_check_text = _build_final_video_check(probe, subtitle_blocks, thumbnails)
    thumbnails_review_text = _build_thumbnail_review(source.topic, thumbnails)
    filmora_status = detect_filmora()
    filmora_reason_text = _build_filmora_reason(filmora_status)

    publish_ok = (
        probe.video_codec == "h264"
        and probe.audio_codec == "aac"
        and probe.pix_fmt == "yuv420p"
        and probe.fps == "30/1"
        and probe.width == 1920
        and probe.height == 1080
        and probe.audio_present
        and "重大な警告は検出されませんでした" in warnings_text
    )

    publish_ready_report_text = _build_publish_ready_report(
        probe,
        source,
        package,
        warnings_text,
        publish_ok,
        [
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
        ],
    )

    root_reports = {
        "publish_checklist.md": checklist_text,
        "final_video_check.md": final_video_check_text,
        "thumbnails_review.md": thumbnails_review_text,
        "publish_ready_report.md": publish_ready_report_text,
        "filmora_not_used_reason.md": filmora_reason_text,
    }
    for name, text in root_reports.items():
        (output_dir / name).write_text(text, encoding="utf-8")

    copied = _copy_publish_files(
        output_dir,
        publish_dir,
        [
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
        ],
    )
    return {
        "publish_dir": publish_dir,
        "publish_ok": publish_ok,
        "video_probe": probe,
        "subtitle_blocks": subtitle_blocks,
        "copied_files": copied,
        "filmora_status": filmora_status,
    }
