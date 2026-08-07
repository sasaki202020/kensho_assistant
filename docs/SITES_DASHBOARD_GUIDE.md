# Sites Dashboard Guide

## 見る場所

- `/sites`

## 見る項目

- `pre_submit_score`
- `score_state`
- 未解決項目
- AI候補
- 人間確認 checklist
- `skip_reason`
- `safety_memo`
- `site_template_label`
- `site_template_last_verified_at`
- `site_template_signal_score`
- `site_template_signal_hits`
- `analysis JSON`
- `pre-submit check JSON`
- `HTML snapshot`
- `later-queue` との接続

## 判定の見方

- `OK`
  - ほぼ入力済み
- `要確認`
  - 人間確認が必要
- `危険`
  - CAPTCHA や対象外
- `スキップ推奨`
  - 人手対応が前提

## 注意

- `submitted_count` はこの画面では常に `0`
- 個人情報はマスク表示
- 実サイトの自動送信は無効
- JSON は折りたたみで見る
- 未解決項目は上部で先に確認する
