# 夜更けローファイ堂 テンプレート

まずは「雨の夜、ベランダでひとり作業するLo-fi」を1本作るための制作テンプレートです。

## 目的

- 5分ループ素材を作る
- 5分素材を6回つないで30分にする
- 背景画像1枚に軽いアニメーションを重ねる
- 権利不明素材を入れない
- 自動投稿はしない

## フォルダ構成

```text
project/
  assets/
    images/
    audio/
    overlays/
  exports/
  metadata/
    youtube_meta.txt
    license_check.md
  scripts/
    make_loop_video.bat
  README.md
```

## 5分ループ動画を作る手順

1. 背景画像を `assets/images/` に置く。
2. BGMを `assets/audio/` に置く。
3. 雨音、環境音、レコードノイズを必要に応じて `assets/audio/` に置く。
4. 雨、湯気、光の揺れなどのオーバーレイ素材を `assets/overlays/` に置く。
5. 1本目の動画を5分で書き出す。
6. 先頭と末尾の見え方を合わせ、ループの継ぎ目を確認する。

オーバーレイは、透過PNGか透過動画を重ねる前提にする。
雨は細い縦流れ、湯気はゆっくり上昇、窓明かりはごく小さい明滅に寄せる。

## 5分動画を6回繰り返して30分にする手順

1. 5分動画を `exports/` に出す。
2. 同じ動画を6回並べた concat 用リストを作る。
3. `ffmpeg -f concat` で30分版を作る。
4. 音声と映像の同期、無音、音割れ、書き出し形式を確認する。

## FFmpeg コマンド例

### 5分ループ動画の例

```powershell
ffmpeg -loop 1 -i .\assets\images\bg_rain_balcony.png `
  -i .\assets\audio\bgm_lofi.wav `
  -i .\assets\audio\rain.wav `
  -i .\assets\audio\room_tone.wav `
  -i .\assets\audio\vinyl_noise.wav `
  -filter_complex ^
    "[0:v]scale=1920:1080,zoompan=z='min(zoom+0.0008,1.10)':d=900:s=1920x1080:fps=30,format=yuv420p[v]; ^
     [1:a]volume=0.95[a1]; ^
     [2:a]volume=0.22[a2]; ^
     [3:a]volume=0.12[a3]; ^
     [4:a]volume=0.05[a4]; ^
     [a1][a2][a3][a4]amix=inputs=4:duration=longest:normalize=0[a]" `
  -map "[v]" -map "[a]" `
  -t 00:05:00 -r 30 `
  -c:v libx264 -pix_fmt yuv420p -profile:v high -preset medium -crf 18 `
  -c:a aac -b:a 192k `
  -movflags +faststart `
  .\exports\lofi_rain_balcony_5m.mp4
```

### 30分版を作る例

`exports\concat_30m.txt` を作成して、次の6行を入れる。

```text
file 'lofi_rain_balcony_5m.mp4'
file 'lofi_rain_balcony_5m.mp4'
file 'lofi_rain_balcony_5m.mp4'
file 'lofi_rain_balcony_5m.mp4'
file 'lofi_rain_balcony_5m.mp4'
file 'lofi_rain_balcony_5m.mp4'
```

```powershell
ffmpeg -f concat -safe 0 -i .\exports\concat_30m.txt `
  -c copy `
  .\exports\lofi_rain_balcony_30m.mp4
```

## YouTube タイトル案

- 夜更けローファイ堂 | 雨の夜、ベランダでひとり作業するLo-fi
- 雨の夜に流す作業用Lo-fi | 夜更けローファイ堂
- 30分 雨音Lo-fi | ベランダで静かに作業する夜

## 概要欄案

```text
雨の夜、ベランダでひとり作業する気分の30分Lo-fiです。

使用素材は権利関係を確認したもの、または自作素材のみを前提にしています。
自動投稿は行いません。

#夜更けローファイ堂 #lofi #作業用BGM #雨音 #夜の作業
```

## タグ案

`lofi, 作業用BGM, 雨音, 夜, ベランダ, 30分, 雨の夜, リラックス, 勉強用, 深夜作業, ambient, chill`

## 実運用メモ

- AI生成画像を使う場合は、AI生成であることを隠さない。
- 権利不明の音源は入れない。
- BGM、雨音、環境音、ノイズは個別に音量調整できるようにしておく。
- 最終出力は YouTube 投稿用の MP4 に整える。
