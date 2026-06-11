"""売る前チェックのスマホ幅スクリーンショットを撮る (App Storeドラフト用)。

使い方:
    1. py -3 run_sell_before_check.py  でサーバーを起動しておく
    2. py -3 -m playwright install chromium  (初回のみ)
    3. py -3 scripts/capture_sbc_screenshots.py

出力: project/exports/sbc_screenshots/*.png (iPhone 15 Pro相当 1179x2556)
最終提出用は実機/シミュレータで撮り直すこと。
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8788"
OUT = Path(__file__).parent.parent / "project" / "exports" / "sbc_screenshots"

SHOTS = [
    ("01_home", "/"),
    ("02_flyer_check", "/flyer-check"),
    ("03_result_sample", "/result"),
    ("04_refusal", "/refusal-examples"),
    ("05_hotline_188", "/hotline-188"),
    ("06_settings", "/settings"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 393, "height": 852},
                                device_scale_factor=3, is_mobile=True)
        for name, path in SHOTS:
            page.goto(BASE + path)
            page.wait_for_load_state("networkidle")
            page.screenshot(path=OUT / f"{name}.png")
            print(f"captured: {OUT / name}.png")
        browser.close()


if __name__ == "__main__":
    main()
