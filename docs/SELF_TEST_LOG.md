# 自己テストログ

## 使い方

`/queue/session` のメモ欄から追記します。

## 最新記録

### 2026-06-19

- `prepare-all` の進捗を `queue/session` と `approved/session` で見えるようにした
- 進捗カードに percent / 処理中件数 / 現在案件名を追加して見やすくした
- `approve_and_submit` を送信前停止に変え、実送信クリックを外した

#### 確認結果

- `py -3 -m compileall kensho_assistant\main.py kensho_assistant\web\app.py kensho_assistant\app\prepare_all_status.py`
- `py -3 -m pytest kensho_assistant\tests\test_web_app.py -q`
- `py -3 -m pytest kensho_assistant\tests\test_submit_controller.py -q`
- `py -3 main.py prepare-all --help`
- `py -3 web_app.py --smoke-test`

#### 結果

- `compileall`: 成功
- `pytest`: `25 passed`
- `pytest (submit_controller)`: `2 passed`
- `prepare-all --help`: 成功
- `web smoke`: `WEB_SMOKE_TEST_OK`
- 自動送信は未実装のまま維持
- `submitted_count_auto`: 0 の前提を維持

### 2026-06-18

- `prepare-all` を追加し、承認済み候補を順番に安全入力まで自動処理できるようにした

#### 確認結果

- `py -3 -m compileall kensho_assistant\main.py`
- `py -3 -m pytest kensho_assistant\tests\test_web_app.py -k "prepare_all or prepare_requires_user_approved or prepare_passes_allow_age_fill or prepare_prints_summary_messages or prepare_prints_cancel_messages" -q`
- `py -3 main.py prepare-all --help`

#### 結果

- `compileall`: 成功
- `pytest (targeted)`: `5 passed, 17 deselected`
- `prepare-all --help`: 成功
- 自動送信は未実装のまま維持
- `submitted_count_auto`: 0 の前提を維持

### 2026-06-17

- research loop を改良し、複数ソース検索→要約→クロスチェック→再検索→合成の反復を確認

#### 確認結果

- `py -3 -m pytest kensho_assistant\tests\test_x_research_harness.py kensho_assistant\tests\test_research_loop.py -q`
- `py -3 -m compileall kensho_assistant\app kensho_assistant\main.py`
- `py -3 main.py research-loop --help`
- `py -3 main.py research-loop --question "高額当選の懸賞を探したい" --provider mock --confidence-threshold 0.77 --max-rounds 3 --limit 5`
- `py -3 -m pytest kensho_assistant\tests -q -rs`

#### 結果

- `pytest (targeted)`: `8 passed`
- `pytest (full)`: `230 passed`
- `compileall`: 成功
- `research-loop --help`: 成功
- `research-loop`: `status: success`, `decision: complete`, `final_confidence: 0.83`, `round_count: 2`, `source_query_total: 5`

### 2026-06-10

- `docs/CODEX_HANDOFF.md` と実装を突き合わせて引き継ぎ状態を確認
- `kensho_harness` の入口と `later-queue` / `PREPARED` の導線を確認

#### 確認結果

- `py -3 -m pytest kensho_assistant\tests -q -rs`
- `py -3 -m compileall kensho_assistant\app scripts\run_kensho_harness.py`
- `py -3 web_app.py --smoke-test`
- `py -3 main.py harness run --help`
- `py -3 scripts/run_kensho_harness.py --help`

#### 結果

- `pytest`: `228 passed`
- `compileall`: 成功
- `web smoke`: `WEB_SMOKE_TEST_OK`
- `main.py harness run --help`: 成功
- `scripts/run_kensho_harness.py --help`: 成功

### v0.4.3

- site template schema を拡張
- Sites ダッシュボードに注目案件、AI候補、人間確認 checklist、JSON 折りたたみを追加
- `later-queue` から `Sites` 診断へリンクする導線を追加
- 自動送信は未実装のまま維持

#### 確認結果

- `py -3 -m compileall kensho_assistant main.py desktop_app.py web_app.py`
- `py -3 -m pytest kensho_assistant/tests -q -rs -o cache_dir=.pytest-cache-local`
- `py -3 web_app.py --smoke-test`
- `py -3 main.py release-report`
- `py -3 main.py later list --limit 30`
- `py -3 main.py entries list --limit 5`
- `py -3 main.py browser doctor`

#### 結果

- `compileall`: 成功
- `pytest`: `224 passed`
- `web smoke`: `WEB_SMOKE_TEST_OK`
- `release-report`: `release_status: OK`
- `later list`: `total: 0`
- `entries list`: `total: 2`
- `browser doctor`: `playwright: ok / chrome_channel: missing / dedicated_profile: ok / headed_launch: ok`
