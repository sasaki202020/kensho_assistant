from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from field_assessment_ai.app import create_app as create_business_app
from field_assessment_ai.config import AppSettings as BusinessSettings
from sell_before_check_ai.app import create_app as create_consumer_app
from sell_before_check_ai.config import AppSettings as ConsumerSettings
from sell_before_check_ai.mobile_preview import ensure_mobile_preview_screenshot_dir


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAA=="
)


def make_consumer_client(tmp_path: Path) -> tuple[TestClient, ConsumerSettings]:
    settings = ConsumerSettings(runtime_root=tmp_path / "runtime")
    app = create_consumer_app(settings)
    return TestClient(app), settings


def make_business_client(tmp_path: Path) -> tuple[TestClient, BusinessSettings]:
    settings = BusinessSettings(runtime_root=tmp_path / "runtime")
    app = create_business_app(settings)
    return TestClient(app), settings


def test_consumer_crud_generation_and_reports(tmp_path: Path) -> None:
    client, settings = make_consumer_client(tmp_path)
    with client:
        health = client.get("/api/v0/consumer/health")
        assert health.status_code == 200

        flyer = client.post(
            "/api/v0/consumer/flyer-checks",
            json={
                "company_name": "サンプル訪問買取",
                "phone_number": "000-1111-2222",
                "flyer_text": "着物高価買取 / 出張査定無料 / 即日現金化",
                "outcall_fee_text": "出張費無料",
                "cancellation_fee_text": "キャンセル料無料",
                "high_price_text": "高価買取",
                "same_day_cash_text": "即日現金化",
                "inducement_text": "貴金属も査定",
            },
        ).json()
        assert flyer["judgement_result"] == "確認推奨"

        flyer_upload = client.post(
            "/api/v0/consumer/images/upload",
            data={"check_type": "flyer", "check_id": flyer["id"]},
            files={"file": ("flyer.png", PNG_BYTES, "image/png")},
        ).json()
        assert flyer_upload["public_url"].startswith("/uploads/consumer/flyer/")

        item = client.post(
            "/api/v0/consumer/item-checks",
            json={
                "item_category": "ミシン",
                "item_name": "JUKI ミシン",
                "brand": "JUKI",
                "condition_note": "動作未確認",
                "accessories": "フットコントローラーなし",
                "offered_price": 1000,
                "market_memo": "型番不明",
            },
        ).json()
        assert item["judgement_result"] == "即決注意"

        quote = client.post(
            "/api/v0/consumer/quote-checks",
            json={
                "offered_price": 9800,
                "package_price": 9800,
                "same_day_extra_charge": 80000,
                "additional_charge_conditions": "当日追加請求あり",
                "estimate_sheet_present": False,
                "memo": "軽トラックパック9,800円",
            },
        ).json()
        assert quote["judgement_result"] == "相談推奨"

        risk = client.post(
            "/api/v0/consumer/risk-judgements/generate",
            json={"check_type": "quote", "check_id": quote["id"]},
        ).json()
        assert risk["judgement"]["refusal_phrase"]
        assert risk["market_links"]["mercari"].startswith("https://")

        official = client.get("/api/v0/consumer/official-info").json()
        assert official
        assert any(info["category"] == "消費者ホットライン188" for info in official)

        report = client.get(f"/api/v0/consumer/reports/quote/{quote['id']}").json()
        assert report["report"]["format"] == "json"
        assert report["content_json"]["judgement"] == "相談推奨"
        assert report["content_json"]["hotline_notice"]
        assert report["content_json"]["refusal_phrase"]

    assert settings.database_path.exists()


def test_business_api_still_works_after_consumer_addition(tmp_path: Path) -> None:
    client, _settings = make_business_client(tmp_path)
    with client:
        health = client.get("/api/v0/health")
        assert health.status_code == 200

        job = client.post("/api/v0/jobs", json={"title": "案件C"}).json()
        item = client.post("/api/v0/items", json={"job_id": job["id"], "name": "ゲーム機", "category": "ゲーム"}).json()
        assert item["job_id"] == job["id"]


def test_consumer_home_render(tmp_path: Path) -> None:
    client, _settings = make_consumer_client(tmp_path)
    with client:
        response = client.get("/")
        assert response.status_code == 200
        assert "売る前チェックAI" in response.text
        assert "その場で売る前に、まず写真でチェック。" in response.text
        assert "チラシをチェック" in response.text
        assert "商品をチェック" in response.text
        assert "見積もりをチェック" in response.text
        assert "1分で確認できます" in response.text


def test_consumer_form_pages_render(tmp_path: Path) -> None:
    client, _settings = make_consumer_client(tmp_path)
    with client:
        flyer = client.get("/flyer-check")
        assert flyer.status_code == 200
        assert "チラシチェック" in flyer.text
        assert "チラシ文言" in flyer.text
        assert "出張費無料の記載あり" in flyer.text

        item = client.get("/item-check")
        assert item.status_code == 200
        assert "商品チェック" in item.text
        assert "商品カテゴリ" in item.text
        assert "確認ポイント" in item.text
        assert "追加で撮るべき写真" in item.text

        quote = client.get("/quote-check")
        assert quote.status_code == 200
        assert "見積もりチェック" in quote.text
        assert "広告表示額" in quote.text
        assert "追加料金条件" in quote.text


def test_consumer_dashboard_still_available(tmp_path: Path) -> None:
    client, _settings = make_consumer_client(tmp_path)
    with client:
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "新規チェックを登録" in response.text
        assert "スマホ導線レビュー" in response.text


def test_consumer_result_page_render(tmp_path: Path) -> None:
    client, _settings = make_consumer_client(tmp_path)
    with client:
        response = client.get("/result")
        assert response.status_code == 200
        assert "今やること" in response.text
        assert "断り文例" in response.text
        assert "相場リンク" in response.text
        assert "188相談案内" in response.text

        flyer = client.post(
            "/api/v0/consumer/flyer-checks",
            json={
                "company_name": "サンプル訪問買取",
                "phone_number": "000-1111-2222",
                "flyer_text": "着物高価買取 / 出張査定無料 / 即日現金化",
            },
        ).json()
        result = client.get(f"/result?check_type=flyer&check_id={flyer['id']}")
        assert result.status_code == 200
        assert "今やること" in result.text
        assert "断り文例" in result.text
        assert "188相談案内" in result.text


def test_mobile_preview_live_render(tmp_path: Path) -> None:
    client, _settings = make_consumer_client(tmp_path)
    with client:
        response = client.get("/mobile-preview")
        assert response.status_code == 200
        assert "このまま売るのは少し待ってください" in response.text
        assert "本番想定のライブ表示" in response.text
        assert "危険度" in response.text
        assert "チラシをチェック" in response.text
        assert "診断結果" in response.text
        assert "断り文例をコピー" in response.text
        assert "家族に共有" in response.text
        assert 'aria-label="診断シナリオ"' not in response.text


def test_mobile_preview_view_shell_render(tmp_path: Path) -> None:
    client, _settings = make_consumer_client(tmp_path)
    with client:
        response = client.get("/mobile-preview?view=home")
        assert response.status_code == 200
        assert "<iframe" in response.text
        assert 'src="/"' in response.text
        assert "iPhone縦" in response.text


def test_mobile_preview_scenario_render(tmp_path: Path) -> None:
    client, _settings = make_consumer_client(tmp_path)
    with client:
        response = client.get("/mobile-preview?scenario=kikinzoku")
        assert response.status_code == 200
        assert 'aria-label="診断シナリオ"' in response.text
        assert "貴金属査定" in response.text
        assert "即決はせず、相場と複数査定で比べてください" in response.text
        assert "即決を求められても、その場で売らない" in response.text
        assert "188を見る" in response.text
        assert "断り文例をコピー" in response.text
        assert 'data-scenario="kikinzoku"' in response.text


def test_mobile_preview_recovery_quote_render(tmp_path: Path) -> None:
    client, _settings = make_consumer_client(tmp_path)
    with client:
        response = client.get("/mobile-preview?scenario=recovery_quote")
        assert response.status_code == 200
        assert 'aria-label="診断シナリオ"' in response.text
        assert "追加料金の条件がそろうまで、契約は待ってください" in response.text
        assert "追加料金の条件があいまい" in response.text
        assert "見積書と明細を紙かメールで残す" in response.text
        assert "188を見る" in response.text
        assert 'data-scenario="recovery_quote"' in response.text


def test_mobile_preview_screenshot_dir_created(tmp_path: Path) -> None:
    screenshot_dir = ensure_mobile_preview_screenshot_dir(tmp_path / "runtime" / "screenshots")
    assert screenshot_dir.exists()
    assert screenshot_dir.is_dir()
