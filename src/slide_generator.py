from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import AppConfig
from .script_generator import ScenePlan


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\meiryob.ttc" if bold else r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\YuGothM.ttc",
        r"C:\Windows\Fonts\YuGothB.ttc" if bold else r"C:\Windows\Fonts\YuGothM.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            bbox = draw.textbbox((0, 0), candidate, font=font)
            width = bbox[2] - bbox[0]
            if width <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines


def _draw_rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str,
    outline: str | None = None,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3 if outline else 0)


def _draw_mascot(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    head = int(112 * scale)
    body_w = int(128 * scale)
    body_h = int(86 * scale)
    eye = int(12 * scale)
    draw.ellipse((x, y, x + head, y + head), fill="#FFE4C2", outline="#9A4D24", width=max(2, int(3 * scale)))
    draw.polygon(
        [
            (x + int(8 * scale), y + int(30 * scale)),
            (x + int(56 * scale), y - int(16 * scale)),
            (x + int(104 * scale), y + int(30 * scale)),
            (x + int(92 * scale), y + int(56 * scale)),
            (x + int(20 * scale), y + int(56 * scale)),
        ],
        fill="#BFD7FF",
        outline="#6B8FC7",
    )
    draw.ellipse((x + int(32 * scale), y + int(50 * scale), x + int(32 * scale) + eye, y + int(50 * scale) + eye), fill="#102A43")
    draw.ellipse((x + int(72 * scale), y + int(50 * scale), x + int(72 * scale) + eye, y + int(50 * scale) + eye), fill="#102A43")
    draw.arc(
        (x + int(36 * scale), y + int(58 * scale), x + int(82 * scale), y + int(96 * scale)),
        start=20,
        end=160,
        fill="#C2410C",
        width=max(2, int(4 * scale)),
    )
    body_top = y + int(108 * scale)
    draw.rounded_rectangle(
        (x - int(8 * scale), body_top, x - int(8 * scale) + body_w, body_top + body_h),
        radius=int(18 * scale),
        fill="#FFFFFF",
        outline="#BFD3EA",
        width=max(2, int(3 * scale)),
    )
    font = _load_font(max(18, int(24 * scale)), bold=True)
    draw.text((x + int(17 * scale), body_top + int(24 * scale)), "確認", fill="#2E5E8A", font=font)


def render_slide(
    scene: ScenePlan,
    output_path: Path,
    config: AppConfig,
    background: str,
) -> Path:
    width, height = config.video_width, config.video_height
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    accent = config.accent_color
    section_font = _load_font(max(34, config.footer_font_size + 8), bold=True)
    title_font = _load_font(config.title_font_size, bold=True)
    emphasis_font = _load_font(max(config.body_font_size + 10, 54), bold=True)
    body_font = _load_font(config.body_font_size)
    footer_font = _load_font(config.footer_font_size)
    source_font = _load_font(max(22, config.footer_font_size - 4))

    draw.rectangle((0, 0, width, 18), fill=accent)
    draw.rectangle((0, height - 12, width, height), fill=accent)
    draw.rounded_rectangle((54, 48, width - 54, 154), radius=28, fill="#F8FAFC", outline="#D8E1E8", width=2)
    draw.text((88, 70), scene.section, fill=accent, font=section_font)
    _draw_mascot(draw, width - 228, 58, 0.62)

    draw.rounded_rectangle((72, 188, width - 72, 474), radius=config.panel_radius, fill="#FFFFFF", outline="#D9E2EA", width=3)
    title_lines = _wrap_text(draw, scene.title, title_font, width - 220)
    title_y = 214
    for line in title_lines[:2]:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_width = bbox[2] - bbox[0]
        draw.text(((width - line_width) / 2, title_y), line, fill="#17324D", font=title_font)
        title_y += config.title_font_size + 14

    emphasis_text = scene.emphasis
    if "注意" in scene.section or "注意" in scene.title:
        emphasis_fill = "#FFF4B8"
        emphasis_outline = "#E1C84B"
    else:
        emphasis_fill = "#EAF3FF"
        emphasis_outline = "#BFD3EA"
    emphasis_box = (174, 356, width - 174, 470)
    draw.rounded_rectangle(emphasis_box, radius=24, fill=emphasis_fill, outline=emphasis_outline, width=3)
    emphasis_bbox = draw.textbbox((0, 0), emphasis_text, font=emphasis_font)
    emphasis_width = emphasis_bbox[2] - emphasis_bbox[0]
    draw.text(((width - emphasis_width) / 2, 382), emphasis_text, fill="#102A43", font=emphasis_font)

    detail_box = (96, 504, width - 96, height - 154)
    draw.rounded_rectangle(detail_box, radius=28, fill="#FFFFFF", outline="#E6EDF4", width=2)
    inner_left = detail_box[0] + 42
    inner_top = detail_box[1] + 26
    max_width = detail_box[2] - detail_box[0] - 84
    body_lines = _wrap_text(draw, scene.body + "\n" + scene.narration, body_font, max_width)
    current_y = inner_top
    for line in body_lines[:10]:
        if not line:
            current_y += int(config.body_font_size * 0.55)
            continue
        draw.text((inner_left, current_y), line, fill="#1F2A37", font=body_font)
        current_y += int(config.body_font_size * 1.2)

    for offset, color in [(0, "#FFE44D"), (1, "#BFE7FF"), (2, "#FFD6E7")]:
        cx = width - 196 + offset * 48
        cy = height - 190 - (offset % 2) * 18
        draw.ellipse((cx, cy, cx + 26, cy + 26), fill=color, outline="#CAD6E0")

    footer = f"{scene.duration_sec}秒  |  1枚1メッセージ"
    draw.text((96, height - 94), footer, fill="#33506D", font=footer_font)
    source_label = scene.source_note or "出典：日本年金機構"
    source_bbox = draw.textbbox((0, 0), source_label, font=source_font)
    source_width = source_bbox[2] - source_bbox[0]
    draw.text((width - source_width - 86, height - 98), source_label, fill="#5B6B7A", font=source_font)

    image.save(output_path)
    return output_path


def generate_slides(
    scenes: list[ScenePlan],
    output_dir: Path,
    config: AppConfig,
) -> list[Path]:
    slide_dir = output_dir / "slides"
    slide_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    backgrounds = config.bg_colors or ["#FFFFFF", "#F5F0E6", "#EAF3FF"]
    for idx, scene in enumerate(scenes):
        background = backgrounds[idx % len(backgrounds)]
        path = slide_dir / f"slide_{idx + 1:02d}.png"
        render_slide(scene, path, config, background)
        paths.append(path)
    return paths


def _thumbnail_canvas(config: AppConfig, theme: str, accent: str, title: str, subtitle: str, tag: str, output_path: Path) -> Path:
    thumb = Image.new("RGB", (1280, 720), "#DDF5FF")
    draw = ImageDraw.Draw(thumb)
    title_font = _load_font(118, bold=True)
    year_font = _load_font(132, bold=True)
    body_font = _load_font(34, bold=True)
    small_font = _load_font(24, bold=True)
    tag_font = _load_font(42, bold=True)

    for x in range(-120, 1280, 180):
        draw.polygon([(x, 0), (x + 90, 0), (x + 260, 720), (x + 170, 720)], fill="#C7ECFF")
    draw.rectangle((0, 0, 1280, 88), fill="#FFE44D")
    draw.text((34, 20), theme, fill="#111827", font=tag_font)

    draw.rectangle((0, 88, 122, 640), fill="#1F5B95")
    side_label = "公式\n情報\n確認"
    y = 126
    for line in side_label.splitlines():
        draw.text((24, y), line, fill="#FFFFFF", font=body_font, stroke_width=2, stroke_fill="#0F2F4F")
        y += 68

    draw.rounded_rectangle((150, 128, 700, 420), radius=24, fill="#FFFFFF", outline="#1F2937", width=5)
    draw.text((186, 150), "年金", fill="#FFFFFF", font=title_font, stroke_width=8, stroke_fill="#111827")
    title_lines = _wrap_text(draw, title, body_font, 460)
    y = 296
    for line in title_lines[:2]:
        draw.text((188, y), line, fill="#111827", font=body_font)
        y += 48

    draw.rounded_rectangle((162, 454, 704, 634), radius=28, fill="#FFF74D", outline="#111827", width=5)
    draw.text((198, 462), tag, fill="#E11D48", font=year_font, stroke_width=4, stroke_fill="#FFFFFF")

    draw.ellipse((798, 148, 1118, 468), fill="#FFE0BD", outline="#7C2D12", width=4)
    draw.ellipse((880, 250, 914, 284), fill="#111827")
    draw.ellipse((1008, 250, 1042, 284), fill="#111827")
    draw.arc((886, 278, 1040, 390), start=10, end=170, fill="#B91C1C", width=9)
    draw.polygon([(820, 162), (950, 92), (1100, 162), (1068, 222), (860, 222)], fill="#C7D2FE")
    draw.rounded_rectangle((744, 486, 1210, 606), radius=28, fill="#FFFFFF", outline=accent, width=5)
    sub_lines = _wrap_text(draw, subtitle, body_font, 410)
    y = 508
    for line in sub_lines[:2]:
        draw.text((778, y), line, fill="#E11D48", font=body_font, stroke_width=2, stroke_fill="#FFFFFF")
        y += 44

    draw.text((34, 652), "出典：日本年金機構 / 個別条件は必ず確認", fill="#334155", font=small_font)
    thumb.save(output_path)
    return output_path


def generate_thumbnail_variants(
    topic: str,
    output_dir: Path,
    config: AppConfig,
) -> list[Path]:
    variants = [
        (
            "A",
            "年金保存版",
            config.accent_color,
            "自分はいくら増える？",
            "国民年金・厚生年金を公式情報で整理",
            "2026",
        ),
        (
            "B",
            "対象者確認",
            "#2F6B57",
            "あなたは対象？",
            "受給中・これから受給する人へ",
            "確認",
        ),
        (
            "C",
            "2026年最新",
            "#8C5A2B",
            "年金額改定",
            "金額・注意点・確認先をやさしく解説",
            "最新",
        ),
    ]
    paths: list[Path] = []
    for suffix, theme, accent, title, subtitle, tag in variants:
        path = output_dir / f"thumbnail_{suffix}.png"
        _thumbnail_canvas(config, theme, accent, title, subtitle, tag, path)
        paths.append(path)
    return paths


def generate_thumbnail(
    topic: str,
    first_slide_path: Path,
    output_path: Path,
    config: AppConfig,
) -> Path:
    base = Image.open(first_slide_path).convert("RGB")
    thumb = ImageOps.fit(base, (1280, 720), method=Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(thumb)
    title_font = _load_font(56, bold=True)
    small_font = _load_font(30)

    draw.rounded_rectangle((58, 58, 1222, 170), radius=28, fill="#FFFFFF", outline="#CAD6E0", width=3)
    draw.text((94, 82), "年金・給付金解説", fill=config.accent_color, font=small_font)
    draw.text((94, 118), topic, fill="#142433", font=title_font)
    draw.rounded_rectangle((58, 560, 1222, 664), radius=24, fill="#F5F0E6", outline="#E0D4BD", width=2)
    draw.text((92, 594), "60代・70代向け 公式情報をやさしく整理", fill="#31465C", font=small_font)
    thumb.save(output_path)
    return output_path
