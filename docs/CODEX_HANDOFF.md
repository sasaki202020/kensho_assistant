# Claude Code 引き継ぎ: Kensho Entry Assistant

## 最初に読む一文

本体は `C:\Users\goo10\OneDrive\ドキュメント\New project\kensho_assistant` です。
自動送信はしません。`submitted_count_auto` は 0 のままです。

---

## 本体リポジトリ

- ローカルパス: `C:\Users\goo10\OneDrive\ドキュメント\New project\kensho_assistant`
- GitHub: `https://github.com/sasaki202020/kensho_assistant`
- 対象サービス: 懸賞生活 `https://www.knshow.com/`
- 目的: 懸賞応募補助（スキャン、キュー管理、Chrome入力補助まで。**最終送信は人間**）

## ai-agent-lab との関係

- `ai-agent-lab` 側にある `X懸賞 real_submit` などは**別コピーの実験系統**です
- `kensho_assistant` 本流には組み込まない
- 本セッションでは本体リポジトリのみを触る

---

## 安全ルール（絶対）

| 項目 | ルール |
|------|--------|
| 自動送信 | **しない** |
| `submitted_count_auto` | **常に 0**（mock シミュレーション内部値を除く） |
| `run_mode` | `mock` / `dry_run` / `review` のみ。実送信モードなし |
| 送信ボタン | 人間が `submit` を 2 回手入力しないと発火しない |
| consent / 年齢 / クイズ / メルマガ | 自動操作しない |

コード根拠:
- `kensho_assistant/app/run_mode.py` — モード定義（3種のみ）
- `kensho_assistant/app/submit_controller.py` — approve_and_submit は人間入力必須
- `kensho_assistant/web/app.py:2209` — `submitted_count_auto=1` は mock 内部の検証値のみ

---

## 主要導線: PREPARED → later-queue → harness run

### 1. PREPARED

```
応募候補スキャン (auto_scan)
  → apply_queue に APPROVED で登録
  → /api/queue/{id}/prepare
  → _start_chrome_prepare: 安全フィールドのみ入力補助 → 入力レビューで停止
  → mark_prepared → queue_status = PREPARED
```

「Chrome 上で確認 → 手動送信 → `手動送信済み` ボタン」が正規フロー。

### 2. later-queue

```
python main.py later add-url --url "https://..."
  → app/later_queue.py
  → 状態: queued / needs_review / blocked
  → bridge_later_queue_to_campaign で campaign 行に変換
```

UI: `/later-queue` で確認・管理。

### 3. harness run（agent-control ジョブ）

```
/agent-control → dry-run ジョブ
  → app/agent_control/controller.py
  → run_form_check_job / run_safety_check_job
  → later_queue 行を取り込み → フォーム検査 / 安全確認
  → safe_to_submit=False, submit_attempted=False のまま完了
```

**X調査ハーネス (`app/harness/x_research_harness.py`) は別物**（X投稿調査用）。混同しないこと。

---

## よく使うコマンド

```powershell
# スキャン・キュー更新
python main.py auto-scan --limit 30
python main.py build-queue --limit 30

# later-queue
python main.py later add-url --url "https://..."
python main.py later list --limit 30

# dry-run 確認
python main.py apply dry-run --campaign-id <id>
python main.py apply dry-run-all --status PREPARED --limit 12

# 起動
python web_app.py   # → http://127.0.0.1:8787

# テスト
python -m pytest -q
python -m compileall kensho_assistant\app
python web_app.py --smoke-test
```

## 主なファイル

| ファイル | 役割 |
|----------|------|
| `kensho_assistant/web/app.py` | Web API ルート全体 |
| `kensho_assistant/app/apply_queue.py` | 応募キュー管理 |
| `kensho_assistant/app/later_queue.py` | later-queue 管理 |
| `kensho_assistant/app/submit_controller.py` | 送信制御（人間確認必須） |
| `kensho_assistant/app/run_mode.py` | run_mode 定義 |
| `kensho_assistant/app/agent_control/controller.py` | agent-control ジョブ |
| `kensho_assistant/app/auto_apply_engine.py` | フォーム自動入力エンジン |

---

## 現状（2026-06-14 時点）

- `submitted_count_auto = 0` 維持確認済み
- `PREPARED → later-queue → harness run` 導線は既存実装あり、動作確認済み
- `ai-agent-lab` 側差分は本流に取り込まない方針で合意済み
- auto-submit の土台（`RealSubmitAdapter`）は意図的な未実装スタブ。`_adapter()` が
  `{mock, dry_run, review}` 以外でしか返さず、その範囲外は `normalize_run_mode` が
  弾くため二重ガードで到達不能。実送信コードは未記述（「土台だけ」の状態）
- 検索画面の安全境界（自動送信は無効 / 送信（無効））を常時表示に修正済み
- web コピー検査テストを seed 化して hermetic 化（`data/` 非依存）

### 「選ぶ→応募するまで」の検証結果（dry_run, 合成フォーム）

実エンジン `AutoApplyEngine("dry_run")` を knshow 風の実フォーム（氏名・住所・
メール・確認用メール・性別・希望賞品 + 規約同意 + メルマガ + 自由記述）に対して
実行し、以下を確認:

- 安全な個人情報フィールドを 10 件入力
- `status = REVIEW_FILL_READY`（人間レビューへ誘導）
- `consent_required` / `newsletter_opt_in` / `free_text_present` /
  `required_checkbox_unchecked` を人間確認項目として正しく検出
- `submit_attempted = False` / `auto_submitted = False`、submit ボタンは検出するが
  クリックしない。送信完了画面に遷移しない

→ 開発側の導線は完成。残るのは **実サイト（knshow.com）でのログイン後 1 件通し確認**
   と、そこで判明する **本番フォーム selector の最終微調整** のみ（人間の手元が必要）。

### 次にやる 1 ステップ（運用確認）

1. Windows で `python web_app.py` → `http://127.0.0.1:8787`
2. `/search` で 1 件選んで承認 → `/approved/session` で「Chromeで応募準備」
3. Chrome 上で入力補助の結果を確認（selector がズレていたらそこだけ調整）
4. 送信は人間が手動で行い、`手動送信済み` を押す

- 次の担当者はこのファイルを読んだ後、`README.md` → `docs/PRODUCT_SPEC.md` の順で読むと全体像が掴める
