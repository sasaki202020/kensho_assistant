# pc-organizer

PC のファイルを整理するための、シンプルな汎用コマンドラインツールです。
追加のライブラリは不要で、Python 3 の標準ライブラリだけで動きます。

A simple, general-purpose command-line tool to tidy up files on your PC.
No third-party dependencies — just Python 3 standard library.

## できること / Features

- `old` … 一定期間（既定 2 年）更新されていない古いファイルを `_Archive/<年>/` に退避します。
- `photos` … 画像ファイルを 1 つのフォルダー（`_Photos`）にまとめます。
- `music` … 音楽ファイルを 1 つのフォルダー（`_Music`）にまとめます。

## 安全のしくみ / Safety

- **既定はドライラン（確認のみ）**。`--execute` を付けたときだけ実際に動きます。
- `photos` / `music` は既定で **コピー**。`--move` を付けると移動します。
- `old` はその性質上つねに **移動** します。
- 出力先フォルダーは走査対象から除外されるため、二重処理や自己ループは起きません。
- 同名ファイルは ` (1)`, ` (2)` … を付けて衝突を回避します。

## 使い方 / Usage

```bash
# 古いファイル（2年以上前）を退避
python pc_organizer.py old "C:\Users\あなた\Documents"            # まず確認
python pc_organizer.py old "C:\Users\あなた\Documents" --execute  # 本実行

# 写真をまとめる
python pc_organizer.py photos "C:\Users\あなた" --execute --move

# 音楽をまとめる
python pc_organizer.py music "C:\Users\あなた" --execute --move
```

### オプション / Options

| オプション | 説明 |
| --- | --- |
| `--execute` | 実際にファイルを動かす（既定は確認のみ） |
| `--move` | コピーではなく移動する（`photos` / `music`） |
| `--dest PATH` | 出力先フォルダーを指定する（省略時は対象内に自動作成） |
| `--years N` | この年数より古いファイルを退避（`old` のみ、既定 2） |

## 動作環境 / Requirements

- Python 3.9 以上 / Python 3.9+
- 追加パッケージ不要 / no extra packages

## 注意 / Notes

まずは `--execute` を付けずに実行し、表示される一覧で対象を確認してから本実行してください。
Always run without `--execute` first and review the listed files before doing it for real.
