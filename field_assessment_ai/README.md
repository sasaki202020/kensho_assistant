# 現場査定AI v0.1

業者向けのバックエンド土台です。案件、商品、画像、相場メモ、見積もり、レポートを扱います。`売る前チェックAI v0.1` と同じ SQLite と画像保存領域を共有します。

## 起動

```powershell
py -3 -m field_assessment_ai
```

または、ダブルクリック用に:

```powershell
start_field_assessment_ai.bat
```

## 開くURL

- API Health: `http://127.0.0.1:8001/api/v0/health`

## 補足

- `sell_before_check_ai` のテーブル定義も同じ DB に作成されます
- 画像は `field_assessment_ai/runtime/uploads` に保存されます
