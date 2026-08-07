from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from kensho_assistant.app.paths import PACKAGE_ROOT
import kensho_assistant.main as main_cli
from kensho_assistant.ui.data_loader import load_apply_queue
from kensho_assistant.web.app import WEB_HOST, WEB_PORT, create_app, _decorate_queue_row, _one_line_reason, _review_item_summary, _risk_class, _sort_campaign_rows, _start_chrome_prepare, _start_prepare_all


def test_web_app_routes_show_safety_text() -> None:
    app = create_app()
    with TestClient(app) as client:
        for path in ("/", "/sites", "/today", "/search", "/queue", "/queue/session", "/approved", "/approved/session", "/entries", "/later-queue", "/research", "/mail", "/campaigns", "/review", "/security", "/ai-agents", "/agent-control", "/health"):
            response = client.get(path)
            assert response.status_code == 200
            body = response.text
            if path != "/health":
                assert "本番送信は人間確認が必要" in body
            assert "submit-approved" not in body
            assert "自動送信します" not in body
            assert "一括送信します" not in body
            assert "完全自動応募" not in body
            if path not in {"/", "/security", "/ai-agents", "/agent-control", "/sites"}:
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
    assert data["app"] == "kensho_assistant"
    assert data["submitted_count_auto"] == 0
    assert isinstance(data["session_active"], bool)
    assert set(data) == {"status", "app", "host", "port", "submitted_count_auto", "session_active"}


def test_web_app_allows_localhost_without_tailscale_identity(monkeypatch) -> None:
    monkeypatch.delenv("KENSHO_ALLOWED_TAILSCALE_USERS", raising=False)
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_web_app_allows_configured_tailscale_user(monkeypatch) -> None:
    monkeypatch.setenv("KENSHO_ALLOWED_TAILSCALE_USERS", "allowed@example.com, other@example.com")
    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={
                "Tailscale-User-Login": "allowed@example.com",
                "Tailscale-User-Name": "Allowed User",
            },
        )
    assert response.status_code == 200


def test_web_app_rejects_unconfigured_or_unapproved_tailscale_user(monkeypatch) -> None:
    app = create_app()
    with TestClient(app) as client:
        monkeypatch.delenv("KENSHO_ALLOWED_TAILSCALE_USERS", raising=False)
        unset_response = client.get("/health", headers={"Tailscale-User-Login": "allowed@example.com"})
        monkeypatch.setenv("KENSHO_ALLOWED_TAILSCALE_USERS", "allowed@example.com")
        denied_response = client.get("/health", headers={"Tailscale-User-Login": "denied@example.com"})
    assert unset_response.status_code == 403
    assert denied_response.status_code == 403


def test_web_app_rejects_tailnet_host_without_identity_headers(monkeypatch) -> None:
    monkeypatch.setenv("KENSHO_ALLOWED_TAILSCALE_USERS", "allowed@example.com")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health", headers={"host": "home.example.ts.net"})
    assert response.status_code == 403


def test_web_app_rejects_spoofed_tailscale_headers_from_non_loopback(monkeypatch) -> None:
    monkeypatch.setenv("KENSHO_ALLOWED_TAILSCALE_USERS", "allowed@example.com")
    app = create_app()
    with TestClient(app, client=("198.51.100.20", 50000)) as client:
        response = client.get("/health", headers={"Tailscale-User-Login": "allowed@example.com"})
    assert response.status_code == 403


def test_web_app_tailscale_state_change_requires_same_origin(monkeypatch) -> None:
    monkeypatch.setenv("KENSHO_ALLOWED_TAILSCALE_USERS", "allowed@example.com")
    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {"status": "FILLING", "state_health": "ok", "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")},
    )
    app = create_app()
    identity = {"Tailscale-User-Login": "allowed@example.com", "host": "home.example.ts.net"}
    with TestClient(app) as client:
        allowed = client.post(
            "/queue/session/start",
            headers={**identity, "origin": "https://home.example.ts.net"},
            follow_redirects=False,
        )
        denied = client.post(
            "/queue/session/start",
            headers={**identity, "origin": "https://attacker.example"},
            follow_redirects=False,
        )
    assert allowed.status_code == 303
    assert denied.status_code == 403


def test_web_app_dashboard_search_review_security_copy(monkeypatch) -> None:
    queue_fixture = [{
        "campaign_id": "fixture-campaign",
        "campaign_name": "Fixture Campaign",
        "queue_status": "PREPARED",
        "readiness_status": "READY_FOR_FILL",
        "resolved_entry_url": "https://example.com/form",
        "deadline": "2099-12-31",
    }]
    monkeypatch.setattr("kensho_assistant.web.app.load_apply_queue", lambda *args, **kwargs: queue_fixture)
    monkeypatch.setattr("kensho_assistant.web.app.load_campaigns", lambda *args, **kwargs: queue_fixture)
    app = create_app()
    with TestClient(app) as client:
        dashboard = client.get("/").text
        sites = client.get("/sites").text
        today = client.get("/today").text
        search = client.get("/search").text
        campaigns = client.get("/campaigns").text
        entries = client.get("/entries").text
        later = client.get("/later-queue").text
        queue = client.get("/queue").text
        queue_session = client.get("/queue/session").text
        approved = client.get("/approved").text
        approved_session = client.get("/approved/session").text
        prepare_all_status = client.get("/api/prepare-all/status").json()
        research = client.get("/research").text
        mail = client.get("/mail").text
        review = client.get("/review").text
        security = client.get("/security").text
        agents = client.get("/ai-agents").text
        control = client.get("/agent-control").text

    assert "今日やること" in dashboard
    assert "要確認" in dashboard
    assert "応募できそう" in dashboard
    assert "完了" in dashboard
    assert "安全に止まっています" in dashboard
    assert "確認する" in dashboard
    assert "候補を見る" in dashboard
    assert "履歴を見る" in dashboard
    assert "収集件数" not in dashboard
    assert "解析済み" not in dashboard
    assert "URL解決済み" not in dashboard
    assert "REVIEW_ONLY" not in dashboard
    assert "READY_FOR_FILL" not in dashboard
    assert "Submitted" not in dashboard
    assert "localhost only" not in dashboard
    assert "暗号化保存" not in dashboard
    assert "X投稿アシスタントを開く" not in dashboard
    assert "Sites 管理ダッシュボード" in sites
    assert "キャンペーン一覧" in sites
    assert "応募ステータス" in sites
    assert "フォーム診断結果" in sites
    assert "人間確認が必要な項目" in sites
    assert "テンプレート一致" in sites
    assert "submitted_count=0" in sites
    assert "profile.enc" in sites
    assert dashboard.count("nav-item") <= 5
    assert "承認済みをまとめて入力補助" in queue_session
    assert "承認済みをまとめて入力補助" in approved_session
    assert "一括入力補助の進捗" in queue_session
    assert "一括入力補助の進捗" in approved_session
    assert "件目を処理中" in queue_session
    assert "件目を処理中" in approved_session
    assert prepare_all_status["submitted_count_auto"] == 0
    assert "今日の候補を見る" in today
    assert "応募前に必ず確認画面で止まります" in today or "今日の候補はまだありません" in today
    assert "確認する" in today
    assert "REVIEW_ONLY" not in today
    assert "READY_FOR_FILL" not in today
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
    assert ">APPLIED<" not in entries
    assert "status</div>" not in entries
    assert "newsletter_status" not in entries
    assert "pii_used" not in entries
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
    assert "応募準備する" in review or "今日の候補を見る" in review
    assert "同意・年齢・メルマガ" in review or "確認待ちはありません" in review
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


def test_web_app_sites_and_later_queue_cross_links(tmp_path, monkeypatch) -> None:
    analysis_dir = tmp_path / "analysis"
    check_dir = tmp_path / "checks"
    analysis_dir.mkdir()
    check_dir.mkdir()
    campaign_rows = [
        {
            "campaign_id": "abc",
            "campaign_name": "案件A",
            "prize": "賞品A",
            "provider": "提供元",
            "deadline": "2026-06-10",
            "resolved_entry_url": "https://example.com/form",
            "entry_url": "https://example.com/form",
            "form_readiness_status": "READY_FOR_FILL",
            "form_readiness_reason": "主要項目入力済み",
            "resolve_status": "RESOLVED",
            "status": "SAFE_TO_FILL",
        }
    ]
    queue_rows = [
        {
            "campaign_id": "abc",
            "campaign_name": "案件A",
            "prize": "賞品A",
            "provider": "提供元",
            "deadline": "2026-06-10",
            "queue_status": "APPROVED",
            "dry_run_status": "PRE_SUBMIT_READY",
            "dry_run_pre_submit_score": "96",
            "dry_run_fill_completion_rate": "100",
            "dry_run_unresolved_required_fields_count": "0",
            "dry_run_total_fields_count": "8",
            "dry_run_submit_button_detected": "true",
            "dry_run_reason_summary": "送信直前まで入力済み",
            "skip_reason_summary": "なし",
            "manual_review_required_fields": "",
            "dry_run_review_items": json.dumps(
                [
                    {
                        "kind": "quiz",
                        "field_name": "quiz_answer",
                        "reason": "human confirmation required",
                        "suggested_answer": "福岡県",
                        "suggested_confidence": 0.91,
                    }
                ],
                ensure_ascii=False,
            ),
            "dry_run_analysis_path": str(analysis_dir / "abc.json"),
            "dry_run_check_path": str(check_dir / "abc.json"),
            "dry_run_screenshot_path": str(tmp_path / "shot.png"),
            "dry_run_html_snapshot_path": str(tmp_path / "snapshot.html"),
        }
    ]
    later_rows = [
        {
            "id": "later-1",
            "title": "あとで案件",
            "site_name": "Example",
            "url": "https://example.com/form",
            "normalized_url": "https://example.com/form",
            "duplicate_key": "url:https://example.com/form",
            "deadline": "2026-06-10",
            "status": "ready_for_fill",
            "source_type": "manual_url",
            "safety_memo": "unknownなし",
            "review_note": "確認中",
            "created_at": "2026-06-04T10:00:00+09:00",
            "updated_at": "2026-06-04T10:05:00+09:00",
        }
    ]
    inspection_rows = {
        "abc": {
            "campaign_id": "abc",
            "detected_forms_count": 1,
            "detected_fields": [
                {"field_name": "full_name", "required": True, "will_fill": True, "label_text": "お名前"},
                {"field_name": "quiz_answer", "required": True, "will_fill": False, "label_text": "クイズ"},
            ],
        }
    }
    analysis_path = analysis_dir / "abc.json"
    analysis_path.write_text(
        json.dumps(
            {
                "site_template_id": "fs_fukuoka_present",
                "site_template_label": "福岡県農林水産物プレゼント",
                "site_template_notes": ["自由記述は候補文を保存する"],
                "site_template_signal_hits": {"known_form_labels": ["お名前"]},
                "site_template_signal_score": 12,
                "last_verified_at": "2026-06-04",
                "safety_notes": ["年齢確認とクイズは人間確認に回す"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    check_path = check_dir / "abc.json"
    check_path.write_text(
        json.dumps(
            {
                "status": "PRE_SUBMIT_READY",
                "pre_submit_score": 96,
                "skip_reason": "なし",
                "safety_memo": "年齢確認とクイズは人間確認に回す",
                "review_items": [
                    {
                        "kind": "quiz",
                        "field_name": "quiz_answer",
                        "reason": "human confirmation required",
                        "suggested_answer": "福岡県",
                        "suggested_confidence": 0.91,
                    }
                ],
                "human_checklist": ["quiz / quiz_answer / human confirmation required"],
                "ai_candidates": ["quiz / quiz_answer / human confirmation required / 候補=福岡県 / 信頼度=0.91"],
                "unresolved_required_fields": [],
                "html_snapshot_path": str(tmp_path / "snapshot.html"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tmp_path / "snapshot.html").write_text("<html><body>snapshot</body></html>", encoding="utf-8")
    monkeypatch.setattr("kensho_assistant.web.app.FORM_ANALYSIS_DIR", analysis_dir)
    monkeypatch.setattr("kensho_assistant.web.app.PRE_SUBMIT_CHECKS_DIR", check_dir)
    monkeypatch.setattr("kensho_assistant.web.app.load_campaigns", lambda: campaign_rows)
    monkeypatch.setattr("kensho_assistant.web.app.load_apply_queue", lambda: queue_rows)
    monkeypatch.setattr("kensho_assistant.web.app.load_form_inspections", lambda: inspection_rows)
    monkeypatch.setattr("kensho_assistant.web.app.list_later_queue", lambda: later_rows)
    monkeypatch.setattr("kensho_assistant.web.app.load_entry_history", lambda: [{"campaign_id": "abc", "status": "APPLIED"}])
    monkeypatch.setattr("kensho_assistant.web.app.load_masked_profile_preview", lambda: {"name": "山田***", "postal_code": "123-****", "email": "y***@example.com", "phone": "090-****-1234"})
    monkeypatch.setattr("kensho_assistant.web.app.profile_storage_state", lambda: {"profile_enc": "保存済み", "profile_json": "検出"})
    monkeypatch.setattr("kensho_assistant.web.app.bridge_later_queue_to_campaign", lambda url: {"campaign_id": "abc"} if url == "https://example.com/form" else {})
    app = create_app()
    with TestClient(app) as client:
        sites = client.get("/sites?campaign_id=abc")
        later = client.get("/later-queue?selected=later-1")
    assert sites.status_code == 200
    assert "注目案件" in sites.text
    assert "あとで応募との接続" in sites.text
    assert "AI候補" in sites.text
    assert "送信前チェックJSON" in sites.text
    assert "Sites診断で開く" in sites.text
    assert "ready_for_fill" in sites.text
    assert later.status_code == 200
    assert "Sites診断で開く" in later.text
    assert "ready_for_fill" in later.text


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


def test_web_app_x_post_assistant_action(monkeypatch) -> None:
    launched: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        launched["command"] = command
        launched["kwargs"] = kwargs

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr("kensho_assistant.web.app.subprocess.Popen", fake_popen)
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/action/x_post_assistant", data={"next_url": "/"}, follow_redirects=False)
    assert response.status_code == 303
    script = next(part for part in launched["command"] if "x_post_assistant.ps1" in str(part))
    assert Path(script) == PACKAGE_ROOT / "scripts" / "windows" / "x_post_assistant.ps1"
    assert Path(launched["kwargs"]["cwd"]) == PACKAGE_ROOT.parent


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


def test_web_app_api_approved_html_snapshot_returns_file(tmp_path: Path, monkeypatch) -> None:
    queue_id = "fixture-campaign"
    snapshot = tmp_path / "snapshot.html"
    snapshot.write_text("<!doctype html><html><body>fixture</body></html>", encoding="utf-8")
    monkeypatch.setattr(
        "kensho_assistant.web.app._queue_item_for_id",
        lambda candidate_id: {
            "campaign_id": candidate_id,
            "dry_run_html_snapshot_path": str(snapshot),
        },
    )
    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/api/approved/{queue_id}/html-snapshot")
    assert response.status_code == 200
    assert "<html" in response.text.lower() or "<!doctype" in response.text.lower()


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


def test_start_prepare_all_uses_main_prepare_all(monkeypatch) -> None:
    calls = {}

    def fake_popen(args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("kensho_assistant.web.app.subprocess.Popen", fake_popen)
    status = _start_prepare_all()
    assert status == "started"
    assert calls["args"][0] == __import__("sys").executable
    assert calls["args"][1].endswith("main.py")
    assert calls["args"][2:] == [
        "prepare-all",
        "--status",
        "APPROVED,PREPARED",
        "--limit",
        "12",
        "--browser",
        "chrome",
        "--no-screenshot",
    ]


def test_prepare_session_command_calls_runner(monkeypatch, capsys) -> None:
    calls = {}
    monkeypatch.setattr(
        main_cli,
        "run_assisted_application_session",
        lambda **kwargs: calls.update(kwargs) or {"status": "completed", "processed": 2, "submitted_count_auto": 0},
    )
    result = main_cli.cmd_prepare_session(
        __import__("argparse").Namespace(status="APPROVED,PREPARED", limit=12, browser="chrome", keep_open=False)
    )
    assert result == 0
    assert calls["status_filter"] == "APPROVED,PREPARED"
    assert calls["limit"] == 12
    assert calls["browser"] == "chrome"
    assert "submitted_count_auto: 0" in capsys.readouterr().out


def test_web_app_session_start_spawns_prepare_session(monkeypatch) -> None:
    calls = {}

    def fake_popen(args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {"status": "IDLE", "state_health": "missing", "updated_at": ""},
    )
    monkeypatch.setattr("kensho_assistant.web.app.subprocess.Popen", fake_popen)
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/queue/session/start", follow_redirects=False)
    assert response.status_code == 303
    assert calls["args"][0] == __import__("sys").executable
    assert "prepare-session" in calls["args"]


def test_web_app_session_start_skips_duplicate_active_session(monkeypatch) -> None:
    calls = {}

    def fake_popen(args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {"status": "FILLING", "state_health": "ok", "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")},
    )
    monkeypatch.setattr("kensho_assistant.web.app.subprocess.Popen", fake_popen)
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/queue/session/start", follow_redirects=False)
    assert response.status_code == 303
    assert calls == {}


def test_web_app_session_status_api_returns_safe_state(monkeypatch) -> None:
    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {"status": "AWAITING_USER_SUBMIT", "submitted_count_auto": 0, "current_campaign_id": "abc"},
    )
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/session/status")
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "AWAITING_USER_SUBMIT"
    assert data["submitted_count_auto"] == 0
    assert "profile" not in response.text
    assert "address" not in response.text


def test_web_app_manual_submitted_records_session_command(monkeypatch) -> None:
    calls = {}

    def fake_request(action, queue_id="", note="", session_id="", candidate_id="", operation_id="", hold_reason=""):
        calls["action"] = action
        calls["queue_id"] = queue_id
        calls["note"] = note
        calls["session_id"] = session_id
        calls["candidate_id"] = candidate_id
        calls["operation_id"] = operation_id
        return __import__("pathlib").Path("session.json")

    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {
            "status": "AWAITING_USER_SUBMIT",
            "workflow_state": "HUMAN_ACTION_REQUIRED",
            "state_health": "ok",
            "session_id": "sess-1",
            "current_campaign_id": "test",
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )
    monkeypatch.setattr("kensho_assistant.web.app.request_assisted_session_action", fake_request)
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/queue/session/test/manual-submitted",
            data={"next_url": "/queue/session", "session_id": "sess-1", "candidate_id": "test", "operation_id": "op-1"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert calls["action"] == "submitted_next"
    assert calls["queue_id"] == "test"
    assert calls["session_id"] == "sess-1"
    assert calls["candidate_id"] == "test"
    assert calls["operation_id"] == "op-1"


def test_web_app_submitted_next_preserves_session_and_operation_id(monkeypatch) -> None:
    calls = {}

    def fake_request(action, queue_id="", note="", session_id="", candidate_id="", operation_id="", hold_reason=""):
        calls.update(
            action=action,
            queue_id=queue_id,
            session_id=session_id,
            candidate_id=candidate_id,
            operation_id=operation_id,
        )
        return Path("session.json")

    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {
            "status": "AWAITING_USER_SUBMIT",
            "workflow_state": "HUMAN_ACTION_REQUIRED",
            "state_health": "ok",
            "session_id": "session-1",
            "current_campaign_id": "candidate-1",
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )
    monkeypatch.setattr("kensho_assistant.web.app.request_assisted_session_action", fake_request)
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/queue/session/candidate-1/submitted-next",
            data={
                "next_url": "/approved/session",
                "session_id": "session-1",
                "candidate_id": "candidate-1",
                "operation_id": "operation-1",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert calls == {
        "action": "submitted_next",
        "queue_id": "candidate-1",
        "session_id": "session-1",
        "candidate_id": "candidate-1",
        "operation_id": "operation-1",
    }


def test_web_app_rejects_manual_submitted_before_human_action_required(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {
            "status": "AWAITING_USER_SUBMIT",
            "workflow_state": "MAPPING_REVIEW_REQUIRED",
            "state_health": "ok",
            "session_id": "session-1",
            "current_campaign_id": "candidate-1",
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )
    monkeypatch.setattr(
        "kensho_assistant.web.app.request_assisted_session_action",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/queue/session/candidate-1/manual-submitted",
            data={
                "session_id": "session-1",
                "candidate_id": "candidate-1",
                "operation_id": "operation-1",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert calls == []


def test_extension_capability_requires_mapping_before_profile_load(monkeypatch) -> None:
    profile_loads = []
    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {
            "workflow_state": "MAPPING_REVIEW_REQUIRED",
            "session_id": "session-1",
            "active_candidate_id": "candidate-1",
        },
    )
    monkeypatch.setattr(
        "kensho_assistant.web.app.load_profile",
        lambda: profile_loads.append(True) or {},
    )
    app = create_app()
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/session/extension-capability",
            json={
                "session_id": "session-1",
                "candidate_id": "candidate-1",
                "origin": "https://example.invalid",
                "fingerprint": "fingerprint-1",
                "profile_keys": ["email"],
            },
        )

    assert response.status_code == 409
    assert profile_loads == []


def test_extension_capability_passes_only_requested_profile_keys(monkeypatch) -> None:
    issued = {}
    fictional_profile = {
        "email": "fictional@example.invalid",
        "phone": "00000000000",
    }

    def fake_issue(**kwargs):
        issued.update(kwargs)
        return {"host": "127.0.0.1", "port": 45678, "submitted_count_auto": 0}

    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {
            "workflow_state": "MAPPING_CONFIRMED",
            "session_id": "session-1",
            "active_candidate_id": "candidate-1",
        },
    )
    monkeypatch.setattr("kensho_assistant.web.app.load_profile", lambda: fictional_profile)
    monkeypatch.setattr("kensho_assistant.web.app.issue_extension_capability", fake_issue)
    app = create_app()
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/session/extension-capability",
            json={
                "session_id": "session-1",
                "candidate_id": "candidate-1",
                "origin": "https://example.invalid",
                "fingerprint": "fingerprint-1",
                "profile_keys": ["email"],
            },
        )

    assert response.status_code == 200
    assert issued["profile_keys"] == ["email"]
    assert issued["profile"] is fictional_profile


def test_web_app_manual_submitted_ignores_stale_session_id(monkeypatch) -> None:
    calls = {}

    def fake_request(action, queue_id="", note="", session_id="", candidate_id="", operation_id="", hold_reason=""):
        calls["action"] = action
        return __import__("pathlib").Path("session.json")

    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {
            "status": "AWAITING_USER_SUBMIT",
            "state_health": "ok",
            "session_id": "sess-current",
            "current_campaign_id": "test",
            "updated_at": "2026-06-10T00:00:00+09:00",
        },
    )
    monkeypatch.setattr("kensho_assistant.web.app.request_assisted_session_action", fake_request)
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/queue/session/test/manual-submitted",
            data={"next_url": "/queue/session", "session_id": "sess-stale", "candidate_id": "test", "operation_id": "op-1"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert calls == {}


def test_web_app_hold_records_reason_and_session_command(monkeypatch) -> None:
    calls = {}

    def fake_request(action, queue_id="", note="", session_id="", candidate_id="", operation_id="", hold_reason=""):
        calls["action"] = action
        calls["queue_id"] = queue_id
        calls["note"] = note
        calls["session_id"] = session_id
        calls["candidate_id"] = candidate_id
        calls["operation_id"] = operation_id
        calls["hold_reason"] = hold_reason
        return __import__("pathlib").Path("session.json")

    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {
            "status": "AWAITING_USER_SUBMIT",
            "state_health": "ok",
            "session_id": "sess-1",
            "current_campaign_id": "test",
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )
    monkeypatch.setattr("kensho_assistant.web.app.request_assisted_session_action", fake_request)
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/queue/session/test/hold",
            data={"next_url": "/queue/session", "session_id": "sess-1", "candidate_id": "test", "operation_id": "op-2", "hold_reason": "captcha"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert calls["action"] == "hold"
    assert calls["hold_reason"] == "captcha"
    assert calls["session_id"] == "sess-1"
    assert calls["candidate_id"] == "test"


def test_web_app_stop_records_session_command(monkeypatch) -> None:
    calls = {}

    def fake_request(action, queue_id="", note="", session_id="", candidate_id="", operation_id="", hold_reason=""):
        calls["action"] = action
        calls["queue_id"] = queue_id
        calls["note"] = note
        calls["session_id"] = session_id
        calls["candidate_id"] = candidate_id
        calls["operation_id"] = operation_id
        return __import__("pathlib").Path("session.json")

    monkeypatch.setattr(
        "kensho_assistant.web.app.load_assisted_session_state",
        lambda: {
            "status": "AWAITING_USER_SUBMIT",
            "state_health": "ok",
            "session_id": "sess-1",
            "current_campaign_id": "test",
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )
    monkeypatch.setattr("kensho_assistant.web.app.request_assisted_session_action", fake_request)
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/queue/session/test/stop",
            data={"next_url": "/queue/session", "session_id": "sess-1", "candidate_id": "test", "operation_id": "op-3"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert calls["action"] == "stop"
    assert calls["queue_id"] == "test"
    assert calls["session_id"] == "sess-1"
    assert calls["candidate_id"] == "test"


def test_prepare_all_status_api_returns_default_state() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/prepare-all/status")
    data = response.json()
    assert response.status_code == 200
    assert data["submitted_count_auto"] == 0
    assert "status_label" in data


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


def test_prepare_all_invokes_prepare_for_approved_rows(monkeypatch, capsys) -> None:
    calls: list[dict[str, object]] = []
    status_calls: list[dict[str, object]] = []
    queue_rows = [
        {"campaign_id": "a", "campaign_name": "A", "queue_status": "APPROVED", "approved_by_user": "true"},
        {"campaign_id": "b", "campaign_name": "B", "queue_status": "PREPARED", "approved_by_user": "true"},
        {"campaign_id": "c", "campaign_name": "C", "queue_status": "APPROVED", "approved_by_user": "false"},
    ]

    monkeypatch.setattr(main_cli, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(main_cli, "read_csv_rows", lambda path: queue_rows)
    monkeypatch.setattr(main_cli, "save_prepare_all_status", lambda payload: status_calls.append(payload))

    def fake_prepare(args):
        calls.append(
            {
                "campaign_id": args.campaign_id,
                "browser": args.browser,
                "keep_open": args.keep_open,
                "no_screenshot": args.no_screenshot,
                "force_review": args.force_review,
                "require_user_approved": args.require_user_approved,
                "allow_age_fill": args.allow_age_fill,
                "yes_known_fields": args.yes_known_fields,
            }
        )
        return 0

    monkeypatch.setattr(main_cli, "cmd_prepare", fake_prepare)
    result = main_cli.cmd_prepare_all(
        __import__("argparse").Namespace(
            status="APPROVED",
            limit=5,
            browser="chrome",
            keep_open=False,
            no_screenshot=True,
            force_review=False,
            allow_age_fill=False,
        )
    )
    out = capsys.readouterr().out
    assert result == 0
    assert calls == [
        {
            "campaign_id": "a",
            "browser": "chrome",
            "keep_open": False,
            "no_screenshot": True,
            "force_review": False,
            "require_user_approved": True,
            "allow_age_fill": False,
            "yes_known_fields": True,
        }
    ]
    assert "processed: 1" in out
    assert "submitted_count_auto: 0" in out
    assert status_calls[0]["status"] == "running"
    assert status_calls[-1]["status"] == "success"
    assert status_calls[-1]["done"] == 1


def test_web_app_reason_and_sort_helpers() -> None:
    assert _one_line_reason("年齢が必要です。自動入力しません。\n追加説明") == "年齢が必要です"
    assert _risk_class("LOW_CONFIDENCE") == "danger-faded"
    rows = [
        {"campaign_id": "b", "deadline": "2026-05-20", "campaign_name": "B"},
        {"campaign_id": "a", "deadline": "2026-05-18", "campaign_name": "A"},
    ]
    assert [row["campaign_id"] for row in _sort_campaign_rows(rows)] == ["a", "b"]


def test_web_app_review_item_summary_shows_ai_candidate() -> None:
    summary = _review_item_summary(
        {
            "kind": "quiz",
            "field_name": "quiz_answer",
            "reason": "human confirmation required",
            "suggested_answer": "福岡県",
            "suggested_confidence": 0.91,
        }
    )
    assert "候補=福岡県" in summary
    assert "信頼度=0.91" in summary


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


def test_trial_report_api_contains_metrics_without_personal_data(monkeypatch, tmp_path) -> None:
    from kensho_assistant.app.real_site_trials import TrialStore, build_trial_record

    path = tmp_path / "trials.jsonl"
    store = TrialStore(path)
    store.append(build_trial_record(
        site_id="site-1",
        url="https://example.com/form?email=secret@example.com",
        started_at="2026-07-18T10:00:00+09:00",
        finished_at="2026-07-18T10:01:00+09:00",
        recognized_fields=3,
        filled_fields=3,
        unfilled_fields=0,
        manual_interventions=0,
        final_step="AWAITING_USER_SUBMIT",
    ))
    monkeypatch.setattr("kensho_assistant.web.app.REAL_SITE_TRIALS_JSONL", path)
    with TestClient(create_app()) as client:
        response = client.get("/api/trial-report")
    assert response.status_code == 200
    assert response.json()["trial_count"] == 1
    assert response.json()["a_rate"] == 100.0
    assert "secret@example.com" not in response.text
