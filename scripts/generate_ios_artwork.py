"""iOSアプリのアイコン・スプラッシュ画像を生成する。

使い方: python3 scripts/generate_ios_artwork.py  (要 Pillow)

出力 (ios_app/assets/):
  icon-only.png   1024x1024  アプリアイコン原版
  splash.png      2732x2732  スプラッシュ(ライト)
  splash-dark.png 2732x2732  スプラッシュ(ダーク)

Mac側では `npx @capacitor/assets generate --ios` で全サイズに展開できます。
デザイン: 虫めがね+チェックマーク（「売る前に確認する」の意匠）。
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

BRAND = (15, 110, 93)        # #0f6e5d
BRAND_DARK = (10, 79, 67)    # #0a4f43
LIGHT_BG = (244, 246, 245)   # #f4f6f5
DARK_BG = (24, 33, 30)
WHITE = (255, 255, 255)

OUT = Path(__file__).parent.parent / "ios_app" / "assets"


def draw_logo(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
              color, bg) -> None:
    """虫めがね(レンズ+持ち手)とレンズ内チェックマークを描く。"""
    lw = max(int(r * 0.18), 4)
    # レンズ
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=lw)
    # 持ち手 (右下45度)
    hx = cx + r * math.cos(math.radians(45))
    hy = cy + r * math.sin(math.radians(45))
    ex = cx + r * 1.75 * math.cos(math.radians(45))
    ey = cy + r * 1.75 * math.sin(math.radians(45))
    draw.line([hx, hy, ex, ey], fill=color, width=int(lw * 1.4))
    draw.ellipse([ex - lw * 0.7, ey - lw * 0.7, ex + lw * 0.7, ey + lw * 0.7], fill=color)
    # チェックマーク
    draw.line([cx - r * 0.45, cy + r * 0.02, cx - r * 0.1, cy + r * 0.38], fill=color, width=lw)
    draw.line([cx - r * 0.1, cy + r * 0.38, cx + r * 0.5, cy - r * 0.32], fill=color, width=lw)


def make_icon() -> None:
    size = 1024
    img = Image.new("RGB", (size, size), BRAND)
    draw = ImageDraw.Draw(img)
    # 背景に淡い対角グラデーション風の帯
    for i in range(size):
        ratio = i / size
        c = tuple(int(BRAND[j] + (BRAND_DARK[j] - BRAND[j]) * ratio) for j in range(3))
        draw.line([(0, i), (size, i)], fill=c)
    draw_logo(draw, size * 0.46, size * 0.44, size * 0.27, WHITE, BRAND)
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / "icon-only.png")


def make_splash(name: str, bg, fg) -> None:
    size = 2732
    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)
    draw_logo(draw, size * 0.5, size * 0.47, size * 0.11, fg, bg)
    img.save(OUT / name)


if __name__ == "__main__":
    make_icon()
    make_splash("splash.png", LIGHT_BG, BRAND)
    make_splash("splash-dark.png", DARK_BG, (134, 198, 183))
    for f in ["icon-only.png", "splash.png", "splash-dark.png"]:
        print(f"generated: {OUT / f}")
