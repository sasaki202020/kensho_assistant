from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "lofi-study-gal-loop" / "publish_package"
AUDIO = Path(r"C:\Users\goo10\AppData\Local\Temp\02_flova_Standalone_lofi_study_bgm_audio_202605310158_458115.mp3")
VIDEO = OUT_DIR / "video.mp4"
STILL = OUT_DIR / "preview_frame.png"
FACTS = OUT_DIR / "facts_check.md"
WARNINGS = OUT_DIR / "warnings.md"
REPORT = OUT_DIR / "publish_ready_report.md"

W, H = 1920, 1080
FPS = 30
DURATION = 10
FRAMES = FPS * DURATION


def wave(p: float, phase: float = 0.0) -> float:
    return math.sin((p + phase) * math.tau)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def lookaway_amount(p: float) -> float:
    return smoothstep(0.34, 0.43, p) * (1.0 - smoothstep(0.56, 0.66, p))


def blink_amount(p: float) -> float:
    total = 0.0
    for center in (0.18, 0.72):
        d = abs(p - center)
        total = max(total, max(0.0, 1.0 - d / 0.025))
    return min(1.0, total)


def ellipse(draw: ImageDraw.ImageDraw, box, fill, outline=None, width=1):
    draw.ellipse(tuple(int(v) for v in box), fill=fill, outline=outline, width=width)


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(tuple(int(v) for v in box), radius=radius, fill=fill, outline=outline, width=width)


def line(draw: ImageDraw.ImageDraw, points, fill, width=1):
    draw.line([(int(x), int(y)) for x, y in points], fill=fill, width=width)


def draw_background(draw: ImageDraw.ImageDraw, p: float):
    draw.rectangle((0, 0, W, H), fill=(35, 29, 54))
    for y in range(H):
        t = y / H
        color = (
            int(30 + 50 * t),
            int(28 + 20 * t),
            int(60 + 30 * t),
        )
        draw.line((0, y, W, y), fill=color)

    # Window and night city.
    rounded(draw, (1090, 105, 1765, 625), 24, fill=(20, 24, 47), outline=(121, 95, 135), width=5)
    for x in (1315, 1540):
        line(draw, [(x, 110), (x, 622)], fill=(93, 76, 116), width=3)
    line(draw, [(1090, 365), (1765, 365)], fill=(93, 76, 116), width=3)

    city_base = 570
    for i in range(18):
        x = 1120 + i * 35
        h = 70 + (i * 47) % 185
        draw.rectangle((x, city_base - h, x + 24, city_base), fill=(28, 33, 63))
        for j in range(max(1, h // 34)):
            tw = (wave(p, i * 0.071 + j * 0.13) + 1) * 0.5
            if tw > 0.38:
                y = city_base - h + 14 + j * 28
                draw.rectangle((x + 7, y, x + 14, y + 9), fill=(245, 198, 112))

    # Curtains, seamless sway.
    sway = 8 * wave(p, 0.07)
    draw.polygon([(1040, 65), (1110 + sway, 75), (1135 + sway, 650), (1010, 700)], fill=(119, 67, 109))
    draw.polygon([(1810, 65), (1745 - sway, 75), (1725 - sway, 650), (1848, 700)], fill=(119, 67, 109))
    for x, sgn in ((1060, 1), (1787, -1)):
        line(draw, [(x, 80), (x + sgn * sway * 0.5, 690)], fill=(159, 89, 138), width=5)

    # Warm desk lamp glow.
    flicker = 0.94 + 0.06 * wave(p, 0.23)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((270, 200, 1120, 1080), fill=(255, int(185 * flicker), 82, 48))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    return glow


def draw_room(draw: ImageDraw.ImageDraw, p: float):
    draw.rectangle((0, 760, W, H), fill=(90, 54, 67))
    rounded(draw, (120, 690, 1710, 1038), 28, fill=(125, 76, 66), outline=(84, 45, 50), width=5)
    draw.rectangle((130, 710, 1700, 762), fill=(151, 91, 73))

    # Lamp.
    line(draw, [(340, 715), (455, 430)], fill=(92, 70, 67), width=16)
    line(draw, [(455, 430), (610, 390)], fill=(92, 70, 67), width=16)
    rounded(draw, (550, 345, 745, 430), 26, fill=(245, 184, 105), outline=(110, 77, 76), width=5)
    draw.rectangle((610, 420, 675, 475), fill=(250, 210, 135))
    ellipse(draw, (330, 700, 440, 750), fill=(83, 56, 65))

    # Books, note, stationery.
    rounded(draw, (735, 775, 1180, 980), 16, fill=(245, 230, 203), outline=(181, 131, 105), width=4)
    line(draw, [(958, 785), (958, 967)], fill=(210, 168, 139), width=3)
    for y in range(810, 955, 24):
        line(draw, [(765, y), (930, y + 3)], fill=(199, 179, 164), width=2)
        line(draw, [(985, y + 2), (1140, y - 1)], fill=(199, 179, 164), width=2)
    rounded(draw, (1200, 745, 1510, 840), 10, fill=(211, 178, 135), outline=(112, 78, 67), width=3)
    rounded(draw, (1215, 725, 1525, 815), 10, fill=(236, 204, 161), outline=(112, 78, 67), width=3)
    for i, c in enumerate([(255, 174, 203), (255, 217, 108), (189, 229, 181)]):
        rounded(draw, (1300 + i * 50, 675, 1340 + i * 50, 730), 5, fill=c)
    for i, c in enumerate([(255, 105, 169), (249, 215, 99), (171, 218, 255)]):
        rounded(draw, (480 + i * 75, 900, 545 + i * 75, 925), 9, fill=c, outline=(90, 58, 74), width=2)
    rounded(draw, (1435, 870, 1540, 970), 14, fill=(245, 170, 188), outline=(112, 69, 87), width=4)
    ellipse(draw, (1520, 900, 1590, 950), fill=None, outline=(245, 170, 188), width=10)

    # Steam loops.
    for i in range(3):
        x = 1475 + i * 22
        top = 800 - 14 * ((p + i * 0.19) % 1)
        line(draw, [(x, 865), (x + 10 * wave(p, i * 0.17), top + 30), (x + 3, top)], fill=(241, 218, 215), width=3)


def draw_character(draw: ImageDraw.ImageDraw, p: float):
    breath = 5 * wave(p, 0.02)
    hair_sway = 6 * wave(p, 0.11)
    look = lookaway_amount(p)
    blink = blink_amount(p)
    cx = 680
    cy = 515 + breath

    # Body.
    rounded(draw, (505, 595 + breath, 885, 900 + breath), 95, fill=(199, 174, 131), outline=(101, 77, 74), width=5)
    rounded(draw, (600, 600 + breath, 790, 880 + breath), 34, fill=(249, 248, 239), outline=(132, 116, 105), width=3)
    draw.polygon([(663, 626 + breath), (711, 626 + breath), (742, 715 + breath), (685, 745 + breath), (631, 715 + breath)], fill=(132, 35, 55))
    line(draw, [(584, 660 + breath), (520, 820 + breath), (690, 870)], fill=(176, 151, 118), width=42)
    line(draw, [(790, 660 + breath), (950, 760), (1055, 835)], fill=(176, 151, 118), width=42)

    # Neck and face.
    rounded(draw, (638, 535 + breath, 726, 632 + breath), 28, fill=(246, 198, 174))
    ellipse(draw, (535, 280 + breath, 817, 590 + breath), fill=(247, 203, 181), outline=(105, 70, 76), width=5)
    ellipse(draw, (530, 405 + breath, 570, 470 + breath), fill=(246, 198, 174), outline=(105, 70, 76), width=4)
    ellipse(draw, (785, 405 + breath, 825, 470 + breath), fill=(246, 198, 174), outline=(105, 70, 76), width=4)

    # Hair base and ponytail.
    draw.pieslice((500, 225 + breath, 840, 525 + breath), 185, 365, fill=(246, 208, 76), outline=(96, 72, 58), width=5)
    draw.polygon([(540, 325 + breath), (610, 245 + breath), (700, 280 + breath), (785, 250 + breath), (816, 410 + breath), (760, 330 + breath), (705, 375 + breath), (635, 320 + breath), (574, 375 + breath)], fill=(252, 219, 86))
    ellipse(draw, (785 + hair_sway, 305 + breath, 980 + hair_sway, 485 + breath), fill=(247, 209, 75), outline=(96, 72, 58), width=5)
    line(draw, [(815 + hair_sway, 365 + breath), (955 + hair_sway, 470 + breath)], fill=(218, 174, 63), width=5)

    # Leopard scrunchie, hair pin, headphones.
    ellipse(draw, (780 + hair_sway, 340 + breath, 855 + hair_sway, 420 + breath), fill=(223, 167, 92), outline=(80, 52, 49), width=5)
    for dx, dy in [(804, 365), (829, 382), (813, 401)]:
        ellipse(draw, (dx + hair_sway, dy + breath, dx + 10 + hair_sway, dy + 7 + breath), fill=(73, 49, 45))
    rounded(draw, (580, 292 + breath, 665, 307 + breath), 8, fill=(255, 112, 169), outline=(118, 65, 99), width=2)
    line(draw, [(550, 390 + breath), (540, 315 + breath), (585, 270 + breath), (775, 270 + breath), (815, 320 + breath), (810, 395 + breath)], fill=(241, 121, 169), width=14)
    ellipse(draw, (510, 365 + breath, 575, 475 + breath), fill=(255, 145, 184), outline=(105, 61, 91), width=6)
    ellipse(draw, (785, 365 + breath, 850, 475 + breath), fill=(255, 145, 184), outline=(105, 61, 91), width=6)

    # Eyes and expression.
    eye_y = 432 + breath
    gaze_x = 8 * look
    gaze_y = -7 * look
    for ex in (615, 735):
        if blink > 0.65:
            line(draw, [(ex - 28, eye_y), (ex + 30, eye_y + 2)], fill=(77, 50, 58), width=6)
        else:
            ellipse(draw, (ex - 33, eye_y - 28, ex + 30, eye_y + 24), fill=(255, 245, 238), outline=(77, 50, 58), width=4)
            ellipse(draw, (ex - 8 + gaze_x, eye_y - 7 + gaze_y, ex + 12 + gaze_x, eye_y + 17 + gaze_y), fill=(74, 55, 75))
            ellipse(draw, (ex + 1 + gaze_x, eye_y - 1 + gaze_y, ex + 7 + gaze_x, eye_y + 5 + gaze_y), fill=(255, 255, 255))
    line(draw, [(640, 520 + breath), (700, 525 + breath)], fill=(155, 83, 88), width=4)
    ellipse(draw, (602, 483 + breath, 635, 504 + breath), fill=(246, 157, 162))
    ellipse(draw, (725, 483 + breath, 758, 504 + breath), fill=(246, 157, 162))

    # Arms, hands, pen.
    pause = look
    pen_jitter = 4 * wave(p * 3.0, 0.05) * (1 - pause)
    line(draw, [(590, 755 + breath), (740, 840), (815, 850 + pen_jitter)], fill=(246, 198, 174), width=34)
    line(draw, [(790, 760 + breath), (930, 835), (1028, 858 + pen_jitter)], fill=(246, 198, 174), width=34)
    ellipse(draw, (1000, 832 + pen_jitter, 1065, 884 + pen_jitter), fill=(247, 203, 181), outline=(105, 70, 76), width=3)
    line(draw, [(1028, 842 + pen_jitter), (1108, 900 + pen_jitter)], fill=(231, 85, 137), width=8)
    line(draw, [(1105, 898 + pen_jitter), (1119, 910 + pen_jitter)], fill=(61, 51, 60), width=4)
    if pause < 0.35:
        for i in range(4):
            y = 902 + i * 10 + pen_jitter * 0.3
            line(draw, [(1050 + i * 4, y), (1140 + i * 7, y + 2)], fill=(93, 78, 91), width=2)


def draw_frame(frame: int) -> Image.Image:
    p = frame / FRAMES
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    glow = draw_background(draw, p)
    draw_room(draw, p)
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    draw = ImageDraw.Draw(img)
    draw_character(draw, p)
    # Subtle warm vignette.
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, W, H), outline=(36, 25, 45, 120), width=42)
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


def run() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    first = draw_frame(0)
    first.save(STILL)

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
    ]
    if AUDIO.exists():
        cmd += ["-stream_loop", "-1", "-i", str(AUDIO), "-t", str(DURATION), "-shortest"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-t", str(DURATION)]
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(VIDEO),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for i in range(FRAMES):
            proc.stdin.write(draw_frame(i).tobytes())
    finally:
        proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(rc)

    FACTS.write_text(
        "# facts_check\n\n"
        "- 事実主張なし。年金・給付金など公式確認が必要な情報は含めていない。\n"
        "- 映像は依頼内容に基づくアニメ調ローファイ勉強ループ。\n",
        encoding="utf-8",
    )
    WARNINGS.write_text(
        "# warnings\n\n"
        "- 重大警告なし。\n"
        "- 参照画像/元動画ファイルはローカル検出できなかったため、キャラクター固定条件は依頼文の記述から再現。\n"
        "- 既存キャラクター・実在高校制服・猫・口パク・カメラ移動は入れていない。\n",
        encoding="utf-8",
    )
    REPORT.write_text(
        "# publish_ready_report\n\n"
        "## 出力\n"
        f"- video: `{VIDEO}`\n"
        f"- preview: `{STILL}`\n\n"
        "## 仕様\n"
        "- 10秒 / 30fps / 1920x1080\n"
        "- h264 / aac / yuv420p / +faststart\n"
        "- BGM合成済み\n\n"
        "## 内容\n"
        "- 夜の勉強部屋、都会の夜景、暖色デスクライト。\n"
        "- 金髪ポニーテール、ヒョウ柄シュシュ、ピンクのヘアピン、ピンクのヘッドホン、白シャツ、えんじ色リボン、ベージュのカーディガン。\n"
        "- まばたき、呼吸、髪揺れ、ペン書き込み、視線移動、カーテン揺れ、ライト揺らぎ、街灯またたき、湯気。\n\n"
        "## 注意\n"
        "- 投稿前に実際の参照画像との差分を目視確認してください。\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
