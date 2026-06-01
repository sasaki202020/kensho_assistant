# Codex Working Rules

## 目的
このリポジトリでは、年金・給付金系YouTube動画をテーマ入力から投稿直前パッケージまで自動生成する。

## 基本方針
- 不要な確認質問はしない。
- 判断に迷ったら安全側で進める。
- 年金情報は公式情報がない限り断定しない。
- 生成後は必ず `facts_check.md` と `warnings.md` を確認する。
- `warnings.md` に重大警告がある場合は `publish_package` を完成扱いにしない。
- `video.mp4` は必ず `h264 / aac / yuv420p / 30fps / 1920x1080 / +faststart` にする。
- 最後に `publish_ready_report.md` を出す。
- ユーザーの最終確認は投稿前だけに寄せる。
- Filmora は必須ではない。使えない場合は Python + FFmpeg で完結させる。
- 生成物は `output/{slug}/publish_package/` に集約する。

## 作業手順
1. `input/topic.json` を確認する。
2. 公式情報を取得し、台本・字幕・スライド・動画を生成する。
3. `facts_check.md` と `warnings.md` を検査する。
4. `publish_package/` を作成する。
5. `publish_ready_report.md` と最終チェック資料を出す。
6. 再生確認できる MP4 形式に整える。

## Filmora
- Filmora は必須ではない。
- 不安定なら使わない。
- 失敗しても Python + FFmpeg で完結させる。
