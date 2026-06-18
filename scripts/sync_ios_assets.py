"""WebのルールとCSSを iOSアプリ(Capacitor) の www に同期する。

使い方: python3 scripts/sync_ios_assets.py
tests/test_sell_before_check_ai.py::test_ios_rules_copy_is_in_sync が同期漏れを検出します。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
RULES = ROOT / "sell_before_check_ai" / "rules.json"
CSS = ROOT / "sell_before_check_ai" / "static" / "style.css"
WWW = ROOT / "ios_app" / "www"


def main() -> None:
    WWW.mkdir(parents=True, exist_ok=True)
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    js = "// 自動生成: scripts/sync_ios_assets.py が rules.json から生成します。直接編集しないでください。\n"
    js += "window.SBC_RULES = " + json.dumps(rules, ensure_ascii=False, indent=2) + ";\n"
    (WWW / "rules.js").write_text(js, encoding="utf-8")
    shutil.copyfile(CSS, WWW / "style.css")
    print(f"synced: {WWW / 'rules.js'}")
    print(f"synced: {WWW / 'style.css'}")


if __name__ == "__main__":
    main()
