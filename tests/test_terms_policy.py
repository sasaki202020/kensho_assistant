import json
from datetime import datetime

import pytest

from kensho_assistant.app.terms_policy import detect_automation_restrictions


def test_automated_entry_prohibition():
    assert detect_automation_restrictions("ツール等を用いた自動応募は禁止します") == {
        "restricted": True, "categories": ["automated_entry"], "uncertain": False,
    }


@pytest.mark.parametrize("text,restricted,categories,uncertain", [
    ("応募は必ずご本人が行ってください。代理応募は無効とします", True, ["proxy_entry"], False),
    ("プログラムの詳細はこちら", False, ["automated_entry"], True),
    ("お一人様1回まで", False, [], False),
    ("", False, [], False),
    ("　 \n", False, [], False),
    ("ＢＯＴ に よ る 自 動 応 募 は 禁 止", True, ["automated_entry"], False),
    ("botによる応募は不可", True, ["automated_entry"], False),
    ("BOTによる応募はお断り", True, ["automated_entry"], False),
    ("ボットによる応募は失格", True, ["automated_entry"], False),
    ("代理入力は認めません", True, ["proxy_entry"], False),
    ("代理での応募はできません", True, ["proxy_entry"], False),
    ("ご本人以外の入力はご遠慮ください", True, ["proxy_entry"], False),
    ("第三者による応募は無効", True, ["proxy_entry"], False),
    ("自動で応募、機械的な応募、自動化、スクリプト、一括応募は禁止", True, ["automated_entry"], False),
    ("代理応募、ツールによる応募は禁止", True, ["automated_entry", "proxy_entry"], False),
    ("ツールの説明。" + "あ" * 41 + "禁止", False, ["automated_entry"], True),
    ("禁止。" + "あ" * 41 + "ツールの説明", False, ["automated_entry"], True),
    ("自動応募\n禁止します", True, ["automated_entry"], False),
    ("禁止します。代理応募", True, ["proxy_entry"], False),
    ("プログラム" + "あ" * 80 + "は禁止", True, ["automated_entry"], False),
    ("robotとbottleの紹介", False, [], False),
])
def test_detection_rules(text, restricted, categories, uncertain):
    assert detect_automation_restrictions(text) == {
        "restricted": restricted, "categories": categories, "uncertain": uncertain,
    }


def test_inspection_persists_flags_without_page_text(tmp_path, monkeypatch):
    import kensho_assistant.main as cli

    body = "LOCAL_BODY_SENTINEL_7f39 ツール等を用いた自動応募は禁止します"

    class Locator:
        def count(self):
            return 0

    class Page:
        def locator(self, selector):
            return Locator()

        def inner_text(self, selector):
            assert selector == "body"
            return body

    monkeypatch.setattr(cli, "detect_fields", lambda _page: [])
    monkeypatch.setattr(cli, "extract_quiz_items", lambda _page: [])
    record = cli._inspection_record({"campaign_id": "fixture"}, Page(), {})
    path = tmp_path / "inspections.jsonl"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    saved = path.read_text(encoding="utf-8")
    assert "LOCAL_BODY_SENTINEL_7f39" not in saved
    assert body not in saved
    policy = json.loads(saved)["terms_policy"]
    assert set(policy) == {"restricted", "categories", "uncertain", "checked_at"}
    assert policy["restricted"] is True
    assert policy["categories"] == ["automated_entry"]
    assert policy["uncertain"] is False
    assert datetime.fromisoformat(policy["checked_at"]).tzinfo is not None
