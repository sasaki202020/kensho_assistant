# 掲載元ポリシー

- `knshow` は既存の低頻度・robots確認済み経路を再利用する。
- `chance` と `ken-kaku` は、まずユーザーが開いて保存したHTMLを `high-value import-html` で取り込む。
- 自動巡回、大量アクセス、Cloudflare・CAPTCHA・bot検知の回避は行わない。
- DOM構造が変わった場合は `SOURCE_LAYOUT_CHANGED` でfail-closedにする。
- 取り込み後は既存候補CSV、重複排除、応募キューを利用する。

例:

```powershell
py -3.12 -m kensho_assistant.main high-value import-html --source chance --html-file .\chance-list.html --source-url https://chance.com/list
py -3.12 -m kensho_assistant.main high-value list --min-value 30000 --limit 30
```
