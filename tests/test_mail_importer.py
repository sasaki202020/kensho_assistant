from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from kensho_assistant.app.models import CAMPAIGN_HEADERS
from kensho_assistant.app.storage import read_csv_rows, write_csv_rows
from kensho_assistant.mail_importer import load_mail_sweepstakes, rescan_mail_sweepstakes, sort_mail_sweepstakes
from kensho_assistant.ui.data_loader import register_email_campaign
from kensho_assistant.web.app import create_app


def _write_sample_mail_files(base: Path) -> None:
    (base / "fruitmail_sample.txt").write_text(
        """Subject: 【Fruitmail】フルーツ定期便が当たる！メール懸賞キャンペーン
From: Fruitmail <info@fruitmail.example>
Date: 2026-05-16 09:00:00 +0900

応募はこちら:
https://campaign.fruitmail.example/present/2026-summer
締切は2026年5月16日中です。本日限定です。
""",
        encoding="utf-8",
    )
    (base / "fruitmail_sample.html").write_text(
        """<!doctype html><html><head><meta charset="utf-8"><title>Fruitmail メール懸賞</title>
<meta name="subject" content="【Fruitmail】フルーツ定期便が当たる！メール懸賞キャンペーン">
<meta name="from" content="Fruitmail <info@fruitmail.example>">
<meta name="date" content="2026-05-16 09:00:00 +0900"></head>
<body>応募はこちら: <a href="https://campaign.fruitmail.example/present/2026-summer">キャンペーンページ</a>
締切は5月16日まで。</body></html>""",
        encoding="utf-8",
    )
    (base / "fruitmail_sample.eml").write_text(
        """From: Fruitmail <info@fruitmail.example>
To: user@example.com
Subject: 【Fruitmail】フルーツ定期便が当たる！メール懸賞キャンペーン
Date: Sat, 16 May 2026 09:00:00 +0900
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

応募はこちら:
https://campaign.fruitmail.example/present/2026-summer
締切は2026年5月16日中です。本日限定です。
""",
        encoding="utf-8",
    )


def test_mail_importer_reads_txt_html_eml(tmp_path: Path) -> None:
    _write_sample_mail_files(tmp_path)

    rows = rescan_mail_sweepstakes(samples_dir=tmp_path, output_path=tmp_path / "mail_sweepstakes.json")

    assert len(rows) == 3
    assert any(row["status"] == "duplicate" for row in rows)
    assert load_mail_sweepstakes(tmp_path / "mail_sweepstakes.json")


def test_mail_risk_levels_and_sorting(tmp_path: Path) -> None:
    (tmp_path / "today.txt").write_text(
        """Subject: 今日までのご案内
From: Info <info@example.com>

本日限定で応募できます。締切は2026年5月17日中です。
https://example.com/today
""",
        encoding="utf-8",
    )
    (tmp_path / "tomorrow.txt").write_text(
        """Subject: 明日までのご案内
From: Info <info@example.com>

応募はこちら https://example.com/tomorrow
締切は2026年5月18日まで。
https://example.com/tomorrow
""",
        encoding="utf-8",
    )
    (tmp_path / "week.txt").write_text(
        """Subject: 今週までのご案内
From: Info <info@example.com>

応募はこちら https://example.com/week
締切は2026年5月20日まで。
https://example.com/week
""",
        encoding="utf-8",
    )
    (tmp_path / "unknown.txt").write_text(
        """Subject: 期限不明のご案内
From: Info <info@example.com>

応募はこちら https://example.com/unknown
https://example.com/unknown
""",
        encoding="utf-8",
    )
    (tmp_path / "expired.txt").write_text(
        """Subject: 期限切れのご案内
From: Info <info@example.com>

応募はこちら https://example.com/expired
締切は2026年5月16日まで。
https://example.com/expired
""",
        encoding="utf-8",
    )
    rows = rescan_mail_sweepstakes(samples_dir=tmp_path, output_path=tmp_path / "mail_sweepstakes.json")
    status_map = {row["subject"]: row for row in rows}
    assert status_map["今日までのご案内"]["risk_level"] == "medium"
    assert [row["subject"] for row in sort_mail_sweepstakes(rows)] == [
        "今日までのご案内",
        "明日までのご案内",
        "今週までのご案内",
        "期限不明のご案内",
        "期限切れのご案内",
    ]


def test_mail_shortener_and_card_are_high(tmp_path: Path) -> None:
    (tmp_path / "shortener.txt").write_text(
        """Subject: 短縮URLの懸賞
From: Info <info@example.com>

応募はこちら https://bit.ly/example
""",
        encoding="utf-8",
    )
    (tmp_path / "card.txt").write_text(
        """Subject: カード要求の懸賞
From: Info <info@example.com>

クレジットカード番号の入力が必要です。
https://example.com/present
""",
        encoding="utf-8",
    )
    rows = rescan_mail_sweepstakes(samples_dir=tmp_path, output_path=tmp_path / "mail_sweepstakes.json")
    status_map = {row["subject"]: row for row in rows}
    assert status_map["短縮URLの懸賞"]["risk_level"] == "high"
    assert status_map["カード要求の懸賞"]["risk_level"] == "high"


def test_mail_candidate_registers_source_email(tmp_path: Path) -> None:
    campaigns_path = tmp_path / "campaigns.csv"
    write_csv_rows(campaigns_path, [], CAMPAIGN_HEADERS)
    mail_item = {
        "mail_id": "mail-abc123",
        "subject": "【Fruitmail】フルーツ定期便が当たる！メール懸賞キャンペーン",
        "sender": "Fruitmail <info@fruitmail.example>",
        "deadline_text": "2026年5月16日中",
        "campaign_url": "https://campaign.fruitmail.example/present/2026-summer",
        "body_excerpt": "応募はこちら",
        "updated_at": "2026-05-16T09:00:00",
    }
    assert register_email_campaign(mail_item, path=campaigns_path) is True
    assert register_email_campaign(mail_item, path=campaigns_path) is True
    duplicate_url_item = {
        **mail_item,
        "mail_id": "mail-dup999",
    }
    assert register_email_campaign(duplicate_url_item, path=campaigns_path) is False
    rows = read_csv_rows(campaigns_path)
    assert len(rows) == 1
    assert rows[0]["source"] == "email"
    assert rows[0]["selected_by_user"] == "true"
    assert rows[0]["entry_url"] == "https://campaign.fruitmail.example/present/2026-summer"


def test_mail_duplicate_same_url_is_marked_duplicate(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text(
        """Subject: 【Fruitmail】フルーツ定期便が当たる！メール懸賞キャンペーン
From: Fruitmail <info@fruitmail.example>

https://campaign.fruitmail.example/present/2026-summer
""",
        encoding="utf-8",
    )
    (tmp_path / "b.txt").write_text(
        """Subject: 【Fruitmail】別件
From: Fruitmail <info@fruitmail.example>

https://campaign.fruitmail.example/present/2026-summer
""",
        encoding="utf-8",
    )
    rows = rescan_mail_sweepstakes(samples_dir=tmp_path, output_path=tmp_path / "mail_sweepstakes.json")
    assert any(row["status"] == "duplicate" for row in rows)


def test_mail_duplicate_same_subject_sender_is_blocked(tmp_path: Path) -> None:
    campaigns_path = tmp_path / "campaigns.csv"
    write_csv_rows(campaigns_path, [], CAMPAIGN_HEADERS)
    mail_item = {
        "mail_id": "mail-abc123",
        "subject": "【Fruitmail】フルーツ定期便が当たる！メール懸賞キャンペーン",
        "sender": "Fruitmail <info@fruitmail.example>",
        "deadline_text": "2026年5月17日中",
        "campaign_url": "https://campaign.fruitmail.example/present/2026-summer",
        "body_excerpt": "応募はこちら",
        "updated_at": "2026-05-17T09:00:00",
    }
    alt_item = {
        **mail_item,
        "mail_id": "mail-abc124",
        "campaign_url": "https://campaign.fruitmail.example/present/2026-autumn",
    }
    assert register_email_campaign(mail_item, path=campaigns_path) is True
    assert register_email_campaign(alt_item, path=campaigns_path) is False
    rows = read_csv_rows(campaigns_path)
    assert len(rows) == 1


def test_mail_web_routes_are_safe() -> None:
    app = create_app()
    with TestClient(app) as client:
        mail = client.get("/mail")
        api = client.get("/api/mail-sweepstakes")
        filtered = client.get("/mail?status=duplicate")
    assert mail.status_code == 200
    assert "メール懸賞" in mail.text
    assert "本番送信は人間確認が必要" in mail.text
    assert "submit-approved" not in mail.text
    for label in ("未確認", "応募候補", "応募済み", "危険", "期限切れ", "重複"):
        assert label in mail.text
    assert api.status_code == 200
    assert api.json()["summary"]["total"] >= 0
    assert filtered.status_code == 200
    assert "重複" in filtered.text
