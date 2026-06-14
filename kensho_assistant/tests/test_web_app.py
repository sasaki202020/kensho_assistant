from __future__ import annotations

from fastapi.testclient import TestClient

import kensho_assistant.main as main_cli
from kensho_assistant.ui.data_loader import load_apply_queue
from kensho_assistant.web.app import WEB_HOST, WEB_PORT, create_app, _decorate_queue_row, _one_line_reason, _risk_class, _sort_campaign_rows, _start_chrome_prepare


def test_web_app_routes_show_safety_text() -> None:
    app = create_app()
    with TestClient(app) as client:
        for path in ("/", "/today", "/search", "/queue", "/queue/session", "/approved", "/approved/session", "/entries", "/later-queue", "/research", "/mail", "/campaigns", "/review", "/security", "/ai-agents", "/agent-control", "/health"):
            response = client.get(path)
            assert response.status_code == 200
            body = response.text
            if path != "/health":
                assert "本番送信は人間確認が必要" in body
            assert "submit-approved" not in body
            assert "自動送信します" not in body
            assert "一括送信します" not in body
            assert "完全自動応募" not in body
            if path not in {"/", "/security", "/ai-agents", "/agent-control"}:
                assert "profile.enc" not in body
                assert "profile.json" not in body
            assert ".env" not in body
        assert app.state.web_host == WEB_HOST
        assert app.state.web_port == WEB_PORT


def test_web_app_health_reports_localhost() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
    data = response.json()
    assert data["host"] == "127.0.0.1"
    assert data["port"] == 8787
    assert data["status"] == "ok"


def test_web_app_dashboard_search_review_security_copy(monkeypatch) -> None:
    # Seed one campaign so data-dependent action buttons (URL解決 / inspect-form)
    # render deterministically; data/ is gitignored, so a clean checkout has none.
    seeded_campaign = {
        "campaign_id": "seed-campaign",
        "campaign_name": "テスト懸賞",
        "provider": "テスト提供元",
        "deadline": "2026-12-31",
        "winner_count": "10",
        "category": "食品",
        "entry_url": "https://example.com/entry",
        "knshow_url": "https://www.knshow.com/test",
        "resolved_entry_url": "https://example.com/entry",
        "resolve_status": "RESOLVED",
        "status": "SAFE_TO_FILL",
        "form_readiness_status": "READY_FOR_FILL",
        "form_readiness_score": "0.8",
        "readiness_score": "0.8",
    }
    monkeypatch.setattr("kensho_assistant.web.app.load_campaigns", lambda *a, **k: [dict(seeded_campaign)])
    seeded_queue_row = {
        "campaign_id": "seed-campaign",
        "campaign_name": "テスト懸賞",
        "provider": "テスト提供元",
        "deadline": "2026-12-31",
        "queue_status": "PREPARED",
        "approved_by_user": "true",
        "resolved_entry_url": "https://example.com/entry",
        "form_readiness_status": "READY_FOR_FILL",
    }
    monkeypatch.setattr("kensho_assistant.web.app.load_apply_queue", lambda *a, **k: [dict(seeded_queue_row)])
    app = create_app()
    with TestClient(app) as client:
        dashboard = client.get("/").text
        today = client.get("/today").text
        search = client.get("/search").text
        campaigns = client.get("/campaigns").text
        entries = client.get("/entries").text
        later = client.get("/later-queue").text
        queue = client.get("/queue").text
        approved = client.get("/approved").text
        approved_session = client.get("/approved/session").text
        research = client.get("/research").text
        mail = client.get("/mail").text
        review = client.get("/review").text
        security = client.get("/security").text
        agents = client.get("/ai-agents").text
        control = client.get("/agent-control").text

    assert "収集件数" in dashboard
    assert "解析済み" in dashboard
    assert "URL解決済み" in dashboard
    assert "REVIEW_ONLY" in dashboard
    assert "READY_FOR_FILL" in dashboard
    assert "Submitted" in dashboard
    assert "セーフティチェックリスト" in dashboard
    assert "今日のおすすめアクション" in dashboard
    assert "送信件数" in dashboard
    assert "自動送信：無効" in dashboard
    assert "応募キュー" in dashboard
    assert "応募履歴の状況" in dashboard
    assert "今日締切" in dashboard
    assert "今週締切" in dashboard
    assert "応募済み数" in dashboard
    assert "当選確認待ち" in dashboard
    assert "メルマガ解除候補" in dashboard
    assert "重複候補" in dashboard
    assert "今日の候補を開く" in today
    assert "今日見るべき候補" in today
    assert "欲しい賞品から探す" in search
    assert "懸賞を探す" in search
    assert "X懸賞を除外" in search
    assert "送信（無効）" in search or "disabled" in search
    assert "一覧テーブル" in campaigns
    assert "右側詳細パネル" in campaigns
    assert "status チップ" in campaigns
    assert "readiness スコア" in campaigns
    assert "URL解決" in campaigns
    assert "inspect-form" in campaigns
    assert "応募履歴" in entries
    assert "CSV出力" in entries
    assert "当選メール候補" in entries
    assert "あとで応募" in later
    assert "この機能は自動送信しません" in later
    assert "個人情報はこのキューには保存しません" in later
    assert "unknown の項目はユーザー確認が必要です" in later
    assert "応募キュー" in queue
    assert "応募キューを開始" in queue
    assert "承認済み" in queue
    assert "Chromeで応募準備" in queue
    assert "応募対象にする" in queue
    assert "現在の状態" in queue
    assert "アプリは応募送信していません。" in queue
    assert "手動送信済み記録" in queue
    assert "Chrome応募準備：" in queue
    assert "コマンドをコピー" in queue
    assert "start_chrome_prepare.bat の使い方を見る" in queue
    assert "送信（無効）" in queue or "disabled" in queue
    assert "承認済み応募キュー" in approved
    assert "アプリは応募送信しません" in approved
    assert "規約同意は自動チェックしません" in approved
    assert "年齢・生年月日の入力補助を許可する" in approved
    assert "承認済み応募キュー連続処理" in approved_session
    assert "状態カード" in approved_session
    assert "次にやること" in approved_session
    assert "最後の送信はユーザー本人" in approved_session
    assert "年齢・生年月日の入力補助を許可する" in approved_session
    assert "自動送信：無効" in approved_session
    assert "狙い目ランキング" in research
    assert "応募送信はしません" in research
    assert "応募キューに追加" in research
    assert "送信ボタン" not in research
    assert "応募キュー連続処理" in client.get("/queue/session").text
    assert "Chromeで応募準備" in client.get("/queue/session").text
    assert "手動送信済みにする" in client.get("/queue/session").text
    assert "Chrome応募準備状態" in client.get("/queue/session").text
    assert "アプリは送信していません。" in client.get("/queue/session").text
    assert "規約同意は手動" in client.get("/queue/session").text
    assert "クイズ回答は手動" in client.get("/queue/session").text
    assert "迷ったところ" in client.get("/queue/session").text
    assert "前の候補へ" in client.get("/queue/session").text or "次の候補へ" in client.get("/queue/session").text
    assert "送信（無効）" not in client.get("/queue/session").text or "disabled" in client.get("/queue/session").text
    queue_rows = load_apply_queue()
    if queue_rows:
        assert client.get(f"/queue/session/{queue_rows[0]['campaign_id']}").status_code == 200
    assert "メール懸賞" in mail
    assert "要確認" in review
    assert "consent / age / newsletter は自動入力しません" in review
    assert "送信ボタンは無効" in review
    assert "localhost限定" in security
    assert "Chrome応募準備" in security
    assert "本番送信は必ず人間確認が必要です" in security
    assert "Playwright" in security
    assert "Chrome channel" in security
    assert "専用Chromeプロファイル" in security
    assert "headed launch" in security
    assert "last checked" in security
    assert "profile.enc" in security
    assert "profile.json" in security
    assert "release-report" in security
    assert "マスク済みプロフィール" in security
    assert "AI担当者" in agents
    assert "現在はJSON結果表示モード" in agents
    assert "Kensho Safe AI Team" in agents
    assert "通常モード" in agents
    assert "担当者数" in agents
    assert "チーム数" in agents
    assert "実行中" in agents
    assert "警告あり" in agents
    assert "エラー" in agents
    assert "完了" in agents
    assert "エンジニアリング" in agents
    assert "安全・審査" in agents
    assert "自動送信なし" in agents
    assert "profile.enc 未読込" in agents
    assert "PIIログなし" in agents
    assert "X操作自動化なし" in agents
    assert "AI司令塔" in control
    assert "ローカル dry-run" in control
    assert "実行" in control
    assert "停止" in control
    assert "ログ" in control
    assert "結果" in control
    assert "人間確認へ送る" in control
    assert "pending" in control
    assert "running" in control
    assert "needs_review" in control
    assert "blocked" in control
    assert "done" in control
    assert "failed" in control
    assert "submit_attempted=false" in control
    assert "safe_to_submit=false" in control
    assert "応募してよいと承認済み" in approved
    assert "応募対象にする" in queue
    decorated = _decorate_queue_row({"queue_status": "QUEUED", "risk_reasons": "DUPLICATE_ENTRY"})
    assert decorated["risk_notice"].startswith("注意：似た候補")
    assert decorated["risk_detail"] == "DUPLICATE_ENTRY"


def test_web_app_prepare_api_returns_json(monkeypatch) -> None:
    app = create_app()
    monkeypatch.setattr("kensho_assistant.web.app._queue_item_for_id", lambda queue_id: {"campaign_id": queue_id, "campaign_name": "テスト案件", "queue_status": "APPROVED", "approved_by_user": "true", "age_fill_user_approved": "false"})
    monkeypatch.setattr("kensho_assistant.web.app._start_chrome_prepare", lambda queue_id, allow_age_fill=False: "started")
    with TestClient(app) as client:
        response = client.post("/api/queue/test-campaign/prepare")
    data = response.json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert data["campaign_id"] == "test-campaign"
    assert data["campaign_name"] == "テスト案件"
    assert data["action"] == "prepare_started"
    assert data["browser"] == "chrome"
    assert data["queue_status"] == "PREPARED"
    assert "送信はしていません" in data["message"]
    assert "手動送信済みにする" in data["next_action"]
    assert data["submitted_count_auto"] == 0


def test_web_app_prepare_api_failure_returns_fallback(monkeypatch) -> None:
    app = create_app()
    monkeypatch.setattr("kensho_assistant.web.app._queue_item_for_id", lambda queue_id: {"campaign_id": queue_id, "campaign_name": "テスト案件", "queue_status": "QUEUED", "approved_by_user": "false"})
    monkeypatch.setattr("kensho_assistant.web.app._start_chrome_prepare", lambda queue_id, allow_age_fill=False: "launch_failed")
    with TestClient(app) as client:
        response = client.post("/api/queue/test-campaign/prepare")
    data = response.json()
    assert response.status_code == 200
    assert data["ok"] is False
    assert data["action"] == "prepare_failed"
    assert data["browser"] == "chrome"
    assert data["queue_status"] == "QUEUED"
    assert "承認済みではありません" in data["message"]
    assert "応募候補に承認" in data["next_action"]
    assert "python main.py prepare --campaign-id test-campaign" in data["fallback_command"]
    assert data["submitted_count_auto"] == 0


def test_web_app_api_queue_approve_returns_json(monkeypatch) -> None:
    app = create_app()
    monkeypatch.setattr("kensho_assistant.web.app.approve_queue_item", lambda queue_id, note="", age_fill_user_approved=False: True)
    monkeypatch.setattr("kensho_assistant.web.app.load_apply_queue", lambda: [{"queue_id": "test-campaign", "approved_at": "2026-05-19T00:00:00", "approved_note": "応募対象として承認"}])
    with TestClient(app) as client:
        response = client.post("/api/queue/test-campaign/approve", data={"approved_note": "応募対象として承認"})
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["queue_status"] == "APPROVED"
    assert data["approved_by_user"] == "true"
    assert data["approved_at"]
    assert data["auto_submit_allowed"] == "false"


def test_web_app_rejects_cross_origin_state_change() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/later-queue/add-url",
            data={"url": "https://example.com/campaign"},
            headers={"Origin": "https://evil.example"},
        )
    assert response.status_code == 403
    assert response.text == "Forbidden"


def test_web_app_api_approved_prepare_returns_json(monkeypatch) -> None:
    app = create_app()
    monkeypatch.setattr("kensho_assistant.web.app._queue_item_for_id", lambda queue_id: {"campaign_id": queue_id, "campaign_name": "テスト案件", "queue_status": "APPROVED", "approved_by_user": "true", "age_fill_user_approved": "false"})
    monkeypatch.setattr("kensho_assistant.web.app._start_chrome_prepare", lambda queue_id, allow_age_fill=False: "started")
    with TestClient(app) as client:
        response = client.post("/api/approved/test-campaign/prepare")
    data = response.json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert data["queue_status"] == "PREPARED"
    assert data["submitted_count_auto"] == 0


def test_main_approve_campaign_command(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main_cli, "approve_queue_item", lambda queue_id, note="", age_fill_user_approved=False: True)
    result = main_cli.cmd_approve_campaign(__import__("argparse").Namespace(campaign_id="test-campaign", note="応募対象として承認"))
    assert result == 0
    out = capsys.readouterr().out
    assert "approved: test-campaign" in out


def test_web_app_session_self_test_note_saved(tmp_path, monkeypatch) -> None:
    app = create_app()
    log_path = tmp_path / "self_test_log.md"
    monkeypatch.setattr("kensho_assistant.web.app.SELF_TEST_LOG_MD", log_path)
    monkeypatch.setattr(
        "kensho_assistant.web.app._queue_item_for_id",
        lambda queue_id: {"campaign_id": queue_id, "campaign_name": "テスト案件"},
    )
    with TestClient(app) as client:
        response = client.post(
            "/queue/session/test/self-test-note",
            data={
                "next_url": "/queue/session",
                "note_confusion": "迷ったところ",
                "note_interest": "応募したい",
                "note_improve": "改善したい",
            },
        )
    assert response.status_code == 200 or response.status_code == 303
    text = log_path.read_text(encoding="utf-8")
    assert "迷ったところ" in text
    assert "応募したい" in text
    assert "改善したい" in text


def test_start_chrome_prepare_uses_main_prepare(monkeypatch) -> None:
    calls = {}

    def fake_popen(args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("kensho_assistant.web.app.subprocess.Popen", fake_popen)
    status = _start_chrome_prepare("test-campaign")
    assert status == "started"
    assert calls["args"][0] == __import__("sys").executable
    assert calls["args"][1].endswith("main.py")
    assert calls["args"][2:] == [
        "prepare",
        "--campaign-id",
        "test-campaign",
        "--browser",
        "chrome",
        "--keep-open",
        "--no-screenshot",
        "--require-user-approved",
    ]


def test_prepare_requires_user_approved(monkeypatch) -> None:
    monkeypatch.setattr(main_cli, "_load_profile_or_fail", lambda: {})
    monkeypatch.setattr(main_cli, "_campaign_rows", lambda: [{"campaign_id": "x", "status": "SAFE_TO_FILL", "form_readiness_status": "READY_FOR_FILL", "resolved_entry_url": "https://example.com", "resolve_status": "RESOLVED"}])
    monkeypatch.setattr(main_cli, "read_csv_rows", lambda path: [{"campaign_id": "x", "queue_status": "QUEUED", "approved_by_user": "false"}])
    result = main_cli.cmd_prepare(
        __import__("argparse").Namespace(
            campaign_id="x",
            browser="chrome",
            keep_open=False,
            no_screenshot=True,
            force_review=False,
            require_user_approved=False,
            allow_age_fill=False,
        )
    )
    assert result == 1


def test_prepare_passes_allow_age_fill(monkeypatch) -> None:
    calls = {}
    monkeypatch.setattr(main_cli, "_load_profile_or_fail", lambda: {})
    monkeypatch.setattr(main_cli, "_campaign_rows", lambda: [{"campaign_id": "x", "status": "SAFE_TO_FILL", "form_readiness_status": "READY_FOR_FILL", "resolved_entry_url": "https://example.com"}])
    monkeypatch.setattr(main_cli, "has_resolved_form_url", lambda campaign: True)
    monkeypatch.setattr(main_cli, "read_csv_rows", lambda path: [{"campaign_id": "x", "queue_status": "APPROVED", "approved_by_user": "true"}])
    monkeypatch.setattr(main_cli, "open_url_in_chrome", lambda playwright, url, browser: (object(), object(), browser))
    monkeypatch.setattr(main_cli, "close_browser_safely", lambda context: None)

    def fake_fill_campaign_page(*args, **kwargs):
        calls["allow_age_fill"] = kwargs.get("allow_age_fill", False)
        class Result:
            decision = "n"
            submitted = False
        return Result()

    monkeypatch.setattr(main_cli, "fill_campaign_page", fake_fill_campaign_page)
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: __import__("contextlib").nullcontext(object()))
    result = main_cli.cmd_prepare(
        __import__("argparse").Namespace(
            campaign_id="x",
            browser="chrome",
            keep_open=False,
            no_screenshot=True,
            force_review=False,
            require_user_approved=True,
            allow_age_fill=True,
        )
    )
    assert result == 0
    assert calls["allow_age_fill"] is True


def test_prepare_prints_summary_messages(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main_cli, "_load_profile_or_fail", lambda: {})
    monkeypatch.setattr(main_cli, "_campaign_rows", lambda: [{"campaign_id": "x", "status": "SAFE_TO_FILL", "form_readiness_status": "READY_FOR_FILL", "resolved_entry_url": "https://example.com"}])
    monkeypatch.setattr(main_cli, "has_resolved_form_url", lambda campaign: True)
    monkeypatch.setattr(main_cli, "read_csv_rows", lambda path: [{"campaign_id": "x", "queue_status": "APPROVED", "approved_by_user": "true"}])
    monkeypatch.setattr(main_cli, "open_url_in_chrome", lambda playwright, url, browser: (object(), object(), browser))
    monkeypatch.setattr(main_cli, "close_browser_safely", lambda context: None)
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: __import__("contextlib").nullcontext(object()))

    class Result:
        decision = "fill"

    monkeypatch.setattr(main_cli, "fill_campaign_page", lambda *args, **kwargs: Result())
    monkeypatch.setattr(main_cli, "mark_prepared", lambda campaign_id: True)
    result = main_cli.cmd_prepare(__import__("argparse").Namespace(campaign_id="x", browser="chrome", keep_open=False, no_screenshot=True, force_review=False, require_user_approved=True, allow_age_fill=False))
    out = capsys.readouterr().out
    assert result == 0
    assert "Chromeで応募ページを開きました" in out
    assert "アプリは応募送信していません" in out
    assert "送信した場合だけ、Web UIで「手動送信済みにする」を押してください" in out


def test_prepare_prints_cancel_messages(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main_cli, "_load_profile_or_fail", lambda: {})
    monkeypatch.setattr(main_cli, "_campaign_rows", lambda: [{"campaign_id": "x", "status": "SAFE_TO_FILL", "form_readiness_status": "READY_FOR_FILL", "resolved_entry_url": "https://example.com"}])
    monkeypatch.setattr(main_cli, "has_resolved_form_url", lambda campaign: True)
    monkeypatch.setattr(main_cli, "read_csv_rows", lambda path: [{"campaign_id": "x", "queue_status": "APPROVED", "approved_by_user": "true"}])
    monkeypatch.setattr(main_cli, "open_url_in_chrome", lambda playwright, url, browser: (object(), object(), browser))
    monkeypatch.setattr(main_cli, "close_browser_safely", lambda context: None)
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: __import__("contextlib").nullcontext(object()))

    class Result:
        decision = "n"

    monkeypatch.setattr(main_cli, "fill_campaign_page", lambda *args, **kwargs: Result())
    monkeypatch.setattr(main_cli, "mark_prepare_cancelled", lambda campaign_id, previous_queue_status="": True)
    result = main_cli.cmd_prepare(__import__("argparse").Namespace(campaign_id="x", browser="chrome", keep_open=False, no_screenshot=True, force_review=False, require_user_approved=True, allow_age_fill=False))
    out = capsys.readouterr().out
    assert result == 0
    assert "応募準備はキャンセルされました" in out
    assert "送信はしていません" in out
    assert "必要ならもう一度「Chromeで応募準備」を押してください" in out


def test_web_app_reason_and_sort_helpers() -> None:
    assert _one_line_reason("年齢が必要です。自動入力しません。\n追加説明") == "年齢が必要です"
    assert _risk_class("LOW_CONFIDENCE") == "danger-faded"
    rows = [
        {"campaign_id": "b", "deadline": "2026-05-20", "campaign_name": "B"},
        {"campaign_id": "a", "deadline": "2026-05-18", "campaign_name": "A"},
    ]
    assert [row["campaign_id"] for row in _sort_campaign_rows(rows)] == ["a", "b"]


def test_web_app_x_campaign_routes_show_candidates(monkeypatch) -> None:
    app = create_app()
    sample_rows = [
        {
            "candidate_id": "abc123",
            "source": "hermes_x_search",
            "platform": "x",
            "query": "懸賞",
            "status": "research_found",
            "title": "食品プレゼント",
            "organizer": "株式会社A",
            "account_handle": "@official_a",
            "post_url": "https://x.com/a/status/1",
            "campaign_url": "https://example.com/campaign",
            "prize": "食品",
            "deadline": "2026-05-19",
            "requirements": ["フォロー", "リポスト"],
            "eligibility": "日本国内",
            "age_requirement": "18歳以上",
            "region_requirement": "日本",
            "risk_flags": [],
            "safety_score": 88,
            "trust_score": 92,
            "ease_score": 85,
            "value_score": 70,
            "deadline_score": 80,
            "total_score": 87,
            "recommendation": "review",
            "recommendation_reason": "公式性が高く、応募しやすい",
            "apply_difficulty": "low",
            "confidence": 0.92,
            "queue_status": "review",
            "queue_reason": "応募候補に追加",
            "raw_text": "{}",
            "collected_at": "2026-05-19T09:00:00+09:00",
        }
    ]
    monkeypatch.setattr("kensho_assistant.web.app.load_latest_x_campaign_day", lambda: "20260519")
    monkeypatch.setattr("kensho_assistant.web.app.load_x_campaign_days", lambda: ["20260519"])
    monkeypatch.setattr("kensho_assistant.web.app.load_x_campaign_candidates_for_day", lambda day: sample_rows)
    monkeypatch.setattr("kensho_assistant.web.app.load_x_campaign_run_for_day", lambda day: {"status": "ok", "candidate_count": 1})
    monkeypatch.setattr("kensho_assistant.web.app.load_x_campaign_report_for_day", lambda day: {"generated_at": "2026-05-19T09:00:00+09:00", "report_path": "/tmp/report.json", "raw_count": 1, "deduped_count": 1})
    with TestClient(app) as client:
        page = client.get("/research/x-campaigns")
        api = client.get("/api/research/x-campaigns?date=20260519")
        report_api = client.get("/api/research/x-campaigns/report?date=20260519")
    assert page.status_code == 200
    assert "X懸賞候補" in page.text
    assert "応募候補に追加" in page.text
    assert api.status_code == 200
    assert api.json()["count"] == 1
    assert api.json()["candidates"][0]["candidate_id"] == "abc123"
    assert report_api.status_code == 200
    assert report_api.json()["report_path"] == "/tmp/report.json"
    assert report_api.json()["candidates"][0]["candidate_id"] == "abc123"


def test_web_app_x_queue_actions_and_prepare(monkeypatch) -> None:
    app = create_app()
    sample_row = {
        "candidate_id": "abc123",
        "id": "abc123",
        "source": "x_hermes",
        "platform": "x",
        "title": "食品プレゼント",
        "organizer": "株式会社A",
        "account_handle": "@official_a",
        "post_url": "https://x.com/a/status/1",
        "campaign_url": "https://example.com/campaign",
        "prize": "食品",
        "deadline": "2026-05-19",
        "requirements": ["フォロー", "リポスト"],
        "eligibility": "日本国内",
        "age_requirement": "18歳以上",
        "region_requirement": "日本",
        "risk_flags": [],
        "safety_score": 82,
        "trust_score": 90,
        "ease_score": 84,
        "value_score": 70,
        "total_score": 86,
        "recommendation": "review",
        "recommendation_reason": "公式性が高く、応募しやすい",
        "status": "user_selected",
        "selected_at": "2026-05-19T09:00:00+09:00",
        "prepared_at": "",
        "raw_source_path": "/tmp/source.json",
        "notes": "",
        "queue_status": "user_selected",
        "queue_reason": "",
        "confidence": 0.92,
    }
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr("kensho_assistant.web.app.load_latest_x_campaign_day", lambda: "20260519")
    monkeypatch.setattr("kensho_assistant.web.app.load_x_campaign_queue_for_day", lambda day: [sample_row])
    monkeypatch.setattr("kensho_assistant.web.app._x_queue_item_for_id", lambda candidate_id, day="": sample_row if candidate_id == "abc123" else {})
    monkeypatch.setattr(
        "kensho_assistant.app.research.hermes_x_search.update_x_campaign_queue_state",
        lambda candidate_id, **kwargs: calls.append((candidate_id, kwargs.get("queue_status", ""))) or True,
    )
    monkeypatch.setattr("kensho_assistant.web.app._start_x_campaign_prepare", lambda candidate_id, target_url: "started")
    with TestClient(app) as client:
        queue_page = client.get("/queue")
        session_page = client.get("/queue/session")
        select = client.post("/api/research/x-campaigns/select", json={"date": "20260519", "candidate_id": "abc123", "action": "select"})
        skip = client.post("/api/research/x-campaigns/skip", json={"date": "20260519", "candidate_id": "abc123", "post_url": "https://x.com/a/status/1", "skip_reason": "スキップ"})
        prepare = client.post("/api/queue/open-prepare", json={"date": "20260519", "candidate_id": "abc123"})
    assert queue_page.status_code == 200
    assert session_page.status_code == 200
    assert "X懸賞 review キュー" in queue_page.text
    assert "Chromeで応募準備" in queue_page.text
    assert "X懸賞 review キュー" in session_page.text
    assert select.status_code == 200
    assert select.json()["queue_status"] == "user_selected"
    assert skip.status_code == 200
    assert skip.json()["queue_status"] == "skipped"
    assert prepare.status_code == 200
    assert prepare.json()["ok"] is True
    assert prepare.json()["campaign_url"] == "https://example.com/campaign"
    sample_row["safety_score"] = 40
    with TestClient(app) as client:
        prepare_blocked = client.post("/api/queue/open-prepare", json={"date": "20260519", "candidate_id": "abc123"})
    assert prepare_blocked.json()["ok"] is False
    assert prepare_blocked.json()["reason"] == "safety_too_low"
    assert ("abc123", "user_selected") in calls
    assert ("abc123", "skipped") in calls
    assert ("abc123", "apply_prepare_only") in calls
