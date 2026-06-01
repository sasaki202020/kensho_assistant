# Cleanup Audit

## Snapshot

- 主導線: `start_web_app.bat` -> `http://127.0.0.1:8787` -> `auto_scan.bat` -> `/queue` -> `Chromeで応募準備`
- 配布物は Web UI 中心へ寄せた
- `dist/` は最新版 ZIP 1件のみ
- 旧成果物は削除せず `archive/` へ退避した

## ルート直下

主な残存ファイル:

- `README.md`
- `main.py`
- `web_app.py`
- `desktop_app.py`
- `auto_scan.bat`
- `start_web_app.bat`
- `start_chrome_prepare.bat`
- `doctor_check.bat`
- `release_report.bat`
- `requirements.txt`
- `.env.example`
- `config.yaml`
- `topics.csv`
- `docs/`
- `archive/`
- `dist/`
- `kensho_assistant/`

## dist

残存:

- `dist/kensho_assistant_v0.3_beta.zip`

退避先:

- `archive/old_dist/`

移動済みの旧成果物:

- `kensho_assistant_v0.3_beta.zip`
- `kensho_assistant_v0.1_beta.zip`
- `kensho_assistant_v0.1_beta_gui.zip`
- `kensho_assistant_v0.1_beta_gui_final.zip`
- `kensho_assistant_v0.2_beta_final.zip`
- `kensho_assistant_v0.2_beta_final_gui.zip`
- `test_install/`
- `test_install_gui/`
- `test_install_gui_final/`
- `test_install_v0.2_final/`
- `test_install_v0.3/`
- `staging_gui_final/`
- `release_report_v0.1.md/.json`
- `release_report_v0.2.md/.json`

## docs 重複整理

新しい案内:

- `README.md`
- `docs/QUICK_START.md`
- `docs/BETA_TESTER_GUIDE.md`
- `docs/PRIVACY.md`
- `docs/FAQ.md`
- `docs/PRODUCT_SPEC.md`
- `docs/SELLING_PAGE_DRAFT.md`
- `docs/ARCHIVE/`

退避先:

- `archive/legacy_ui/docs/`

退避した旧 docs:

- `README.md`
- `USER_GUIDE.md`
- `TERMS_DRAFT.md`
- `DISTRIBUTION_MESSAGE.md`
- `KNOWN_LIMITATIONS.md`

残存の旧 docs:

- `kensho_assistant/docs/hermes_x_search_setup.md`

## PySide6 desktop UI

使用箇所:

- `kensho_assistant/desktop_app.py`
- `kensho_assistant/tests/conftest.py`
- `kensho_assistant/tests/test_desktop_ui_logic.py`

現状:

- desktop UI はまだテスト参照があるため未移動
- legacy UI 候補として扱う

## Web UI

使用箇所:

- `web_app.py`
- `kensho_assistant/web/app.py`
- `kensho_assistant/tests/test_web_app.py`

現状:

- Web UI が主導線
- `start_web_app.bat` と `http://127.0.0.1:8787` を推奨

## tests の参照状況

主な参照ファイル:

- `kensho_assistant/desktop_app.py`
- `kensho_assistant/ui/main_window.py`
- `kensho_assistant/ui/search_campaigns_page.py`
- `kensho_assistant/ui/data_loader.py`
- `kensho_assistant/web/app.py`
- `kensho_assistant/main.py`
- `kensho_assistant/mail_importer.py`

補足:

- `submit-approved` はテストの否定チェックにのみ残している
- 実行導線には残していない

## main.py 参照モジュール

`kensho_assistant/main.py` の主な import:

- `campaign_classifier`
- `entry_logger`
- `entry_url_resolver`
- `form_detector`
- `form_filler`
- `form_readiness`
- `auto_scan_report`
- `apply_queue`
- `browser_manager`
- `knshow_scraper`
- `models`
- `research_engine`
- `paths`
- `profile_manager`
- `privacy_guard`
- `report_generator`
- `release_report`
- `version`
- `safety_checker`
- `storage`

主要コマンド:

- `collect`
- `analyze`
- `fill`
- `prepare`
- `approve-campaign`
- `approved-queue`
- `inspect-form`
- `resolve-urls`
- `status`
- `report`
- `review`
- `build-queue`
- `research`
- `research-report`
- `release-report`
- `auto-scan`
- `export`
- `doctor`
- `browser doctor`
- `profile check`
- `profile encrypt`
- `profile decrypt`
- `profile rotate-key`

## web_app.py 参照モジュール

`web_app.py` は薄い起動ラッパー:

- `kensho_assistant.main`

`kensho_assistant/web/app.py` の主な import:

- `fastapi`
- `uvicorn`
- `browser_manager`
- `entry_logger`
- `version`
- `mail_importer`
- `apply_queue`
- `ui.data_loader`
- `report_generator`
- `research_engine`

## 削除候補 / archive 対象

archive へ移動済み:

- 古い v0.1 / v0.2 ZIP
- `test_install*`
- 古い release report
- 旧 docs

deprecated 化候補:

- PySide6 desktop UI

## 混入チェック

配布 ZIP から除外すべきもの:

- `.env`
- `profile.json`
- `profile.enc`
- `profile.enc.backup`
- `logs/`
- `screenshots/`
- `data/`
- `browser_profile/`
- `archive/`
- `__pycache__/`
- `run.jsonl`
- `Cookie`
- `session`
- 個人情報

現在の `dist/` には最新 ZIP 1件のみを残している。
