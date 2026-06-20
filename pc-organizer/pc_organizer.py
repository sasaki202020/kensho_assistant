#!/usr/bin/env python3
"""pc_organizer.py — PC ファイル整理ツール / PC file organizer.

汎用のファイル整理ユーティリティです。特定のアプリには依存しません。
A general-purpose, dependency-free (standard library only) file organizer.

サブコマンド / Sub-commands:
  old     2年以上前の古いファイルを退避（アーカイブ）する
          Archive files that have not been modified for N years (default 2).
  photos  写真をひとつのフォルダーにまとめる
          Gather image files into one folder.
  music   音楽をひとつのフォルダーにまとめる
          Gather audio files into one folder.

安全方針 / Safety:
  - デフォルトは「確認のみ（ドライラン）」です。実際にファイルを動かすには
    --execute を付けてください。
    Dry-run by default. Nothing is changed unless you pass --execute.
  - 既定の動作はファイルのコピーです。移動したい場合は --move を付けます。
    (old のみ、退避という性質上つねに移動します。)
    Copies by default; pass --move to move instead. (`old` always moves.)
  - 出力先フォルダーは走査対象から除外し、二重処理や自己ループを防ぎます。
    The destination folder is excluded from the scan to avoid re-processing.

使い方の例 / Examples:
  # 古いファイル（2年以上前）を退避
  python pc_organizer.py old "C:\\Users\\あなた\\Documents"            # まず確認
  python pc_organizer.py old "C:\\Users\\あなた\\Documents" --execute  # 本実行

  # 写真をまとめる
  python pc_organizer.py photos "C:\\Users\\あなた" --execute --move

  # 音楽をまとめる
  python pc_organizer.py music "C:\\Users\\あなた" --execute --move
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# 拡張子セット / Extension sets (lower-case, with leading dot).
PHOTO_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".heic", ".heif", ".svg", ".raw", ".cr2", ".cr3", ".nef", ".arw",
    ".dng", ".orf", ".rw2", ".raf",
}
MUSIC_EXTS = {
    ".mp3", ".flac", ".wav", ".aac", ".m4a", ".m4b", ".ogg", ".oga",
    ".opus", ".wma", ".aiff", ".aif", ".aifc", ".alac", ".mid", ".midi",
    ".ape", ".wv",
}

SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


@dataclass
class Plan:
    """整理プラン / The set of (source, destination) actions to perform."""

    action: str  # "move" or "copy"
    pairs: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    total_bytes: int = 0


def human_size(num: float) -> str:
    """バイト数を読みやすい単位に変換 / Format a byte count for humans."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def unique_destination(dest: Path, reserved: set[Path]) -> Path:
    """衝突しない出力パスを返す / Return a non-colliding destination path.

    既存ファイルや、同一プラン内で既に予約済みのパスと衝突する場合は
    " (1)", " (2)" ... を付与する。
    """
    candidate = dest
    counter = 1
    while candidate.exists() or candidate in reserved:
        candidate = dest.with_name(f"{dest.stem} ({counter}){dest.suffix}")
        counter += 1
    reserved.add(candidate)
    return candidate


def iter_files(root: Path, exclude: set[Path]):
    """root 以下のファイルを再帰的に走査 / Recursively yield files under root.

    exclude に含まれるディレクトリ配下はスキップする。
    """
    excl_resolved = {p.resolve() for p in exclude}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if any(resolved == e or e in resolved.parents for e in excl_resolved):
            continue
        yield path


def build_plan_collect(root: Path, dest_dir: Path, exts: set[str], move: bool) -> Plan:
    """写真／音楽をまとめるプランを作成 / Plan for gathering files by extension."""
    plan = Plan(action="move" if move else "copy")
    reserved: set[Path] = set()
    for path in iter_files(root, exclude={dest_dir}):
        if path.suffix.lower() not in exts:
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            plan.skipped.append((path, f"stat 失敗: {exc}"))
            continue
        target = unique_destination(dest_dir / path.name, reserved)
        plan.pairs.append((path, target))
        plan.total_bytes += size
    return plan


def build_plan_old(root: Path, dest_dir: Path, years: float) -> Plan:
    """古いファイルを年ごとに退避するプラン / Plan for archiving old files by year."""
    plan = Plan(action="move")  # 退避は常に移動 / archiving always moves.
    reserved: set[Path] = set()
    cutoff = time.time() - years * SECONDS_PER_YEAR
    for path in iter_files(root, exclude={dest_dir}):
        try:
            stat = path.stat()
        except OSError as exc:
            plan.skipped.append((path, f"stat 失敗: {exc}"))
            continue
        if stat.st_mtime >= cutoff:
            continue  # まだ新しい / still recent.
        year = time.localtime(stat.st_mtime).tm_year
        target = unique_destination(dest_dir / str(year) / path.name, reserved)
        plan.pairs.append((path, target))
        plan.total_bytes += stat.st_size
    return plan


def execute_plan(plan: Plan) -> tuple[int, list[tuple[Path, str]]]:
    """プランを実行 / Carry out the planned moves/copies. Returns (done, errors)."""
    done = 0
    errors: list[tuple[Path, str]] = []
    for src, dest in plan.pairs:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if plan.action == "move":
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(str(src), str(dest))
            done += 1
        except OSError as exc:
            errors.append((src, str(exc)))
    return done, errors


def report(plan: Plan, dest_dir: Path, execute: bool) -> None:
    """プラン内容と結果を表示 / Print the plan (and run it when execute=True)."""
    verb = "移動" if plan.action == "move" else "コピー"
    mode = "本実行" if execute else "確認（ドライラン）"
    print(f"モード: {mode}")
    print(f"操作  : {verb}")
    print(f"出力先: {dest_dir}")
    print(f"対象  : {len(plan.pairs)} 件 / {human_size(plan.total_bytes)}")
    print("-" * 60)

    if not plan.pairs:
        print("対象ファイルはありませんでした。")
    else:
        preview = plan.pairs if execute else plan.pairs[:50]
        for src, dest in preview:
            print(f"  {src}  ->  {dest}")
        if not execute and len(plan.pairs) > len(preview):
            print(f"  ... 他 {len(plan.pairs) - len(preview)} 件")

    if plan.skipped:
        print("-" * 60)
        print(f"スキップ: {len(plan.skipped)} 件")
        for path, reason in plan.skipped[:20]:
            print(f"  {path}  ({reason})")

    if not execute:
        print("-" * 60)
        print("これは確認のみです。実行するには --execute を付けてください。")
        return

    print("-" * 60)
    print("実行中...")
    done, errors = execute_plan(plan)
    print(f"完了: {done} 件を{verb}しました。")
    if errors:
        print(f"エラー: {len(errors)} 件")
        for path, reason in errors[:20]:
            print(f"  {path}  ({reason})")


def resolve_target(raw: str) -> Path:
    """対象ディレクトリを検証 / Validate the target directory argument."""
    target = Path(raw).expanduser()
    if not target.exists():
        sys.exit(f"エラー: 指定したフォルダーが見つかりません: {target}")
    if not target.is_dir():
        sys.exit(f"エラー: フォルダーではありません: {target}")
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pc_organizer.py",
        description="PC のファイルを整理する汎用ツール（標準ライブラリのみ）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("target", help="整理の対象フォルダー / target folder")
        p.add_argument(
            "--execute",
            action="store_true",
            help="実際にファイルを動かす（既定は確認のみ） / actually perform changes",
        )
        p.add_argument(
            "--dest",
            help="出力先フォルダー（省略時は対象内に自動作成） / destination folder",
        )

    p_old = sub.add_parser("old", help="古いファイルを退避する / archive old files")
    add_common(p_old)
    p_old.add_argument(
        "--years",
        type=float,
        default=2.0,
        help="この年数より古いファイルを退避（既定 2） / age threshold in years",
    )

    p_photos = sub.add_parser("photos", help="写真をまとめる / gather photos")
    add_common(p_photos)
    p_photos.add_argument(
        "--move",
        action="store_true",
        help="コピーではなく移動する / move instead of copy",
    )

    p_music = sub.add_parser("music", help="音楽をまとめる / gather music")
    add_common(p_music)
    p_music.add_argument(
        "--move",
        action="store_true",
        help="コピーではなく移動する / move instead of copy",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = resolve_target(args.target)

    if args.command == "old":
        dest_dir = Path(args.dest).expanduser() if args.dest else target / "_Archive"
        if args.years <= 0:
            sys.exit("エラー: --years は正の数を指定してください。")
        plan = build_plan_old(target, dest_dir, args.years)
        print(f"対象: {args.years} 年以上前のファイル")
    elif args.command == "photos":
        dest_dir = Path(args.dest).expanduser() if args.dest else target / "_Photos"
        plan = build_plan_collect(target, dest_dir, PHOTO_EXTS, move=args.move)
    elif args.command == "music":
        dest_dir = Path(args.dest).expanduser() if args.dest else target / "_Music"
        plan = build_plan_collect(target, dest_dir, MUSIC_EXTS, move=args.move)
    else:  # argparse が required=True なので通常到達しない。
        sys.exit("不明なコマンドです。")

    report(plan, dest_dir, args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
