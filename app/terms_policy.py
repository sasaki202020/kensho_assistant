from __future__ import annotations

import re
import unicodedata


_KEYWORDS = {
    "automated_entry": re.compile(
        r"自動応募|自動で応募|プログラム|ツール|(?<![a-z])bot(?![a-z])|ボット|機械的|自動化|スクリプト|一括応募"
    ),
    "proxy_entry": re.compile(r"代理応募|代理入力|代理での応募|(?:ご)?本人以外|第三者による応募"),
}
_PROHIBITION = re.compile(r"禁止|無効|お断り|認めません|できません|ご遠慮|失格|不可")


def detect_automation_restrictions(text: str) -> dict:
    """Return flags only; normalized page text never leaves this function."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"[^\S\n\r]+", "", normalized)
    prohibitions = list(_PROHIBITION.finditer(normalized))
    categories = []
    restricted = False
    uncertain = False
    for category, pattern in _KEYWORDS.items():
        matches = list(pattern.finditer(normalized))
        if not matches:
            continue
        categories.append(category)
        category_restricted = False
        for match in matches:
            for prohibition in prohibitions:
                start = min(match.end(), prohibition.end())
                end = max(match.start(), prohibition.start())
                between = normalized[start:end]
                if len(between) <= 40 or not re.search(r"[。\r\n]", between):
                    category_restricted = True
                    break
        restricted |= category_restricted
        uncertain |= not category_restricted
    return {"restricted": restricted, "categories": categories, "uncertain": uncertain}
