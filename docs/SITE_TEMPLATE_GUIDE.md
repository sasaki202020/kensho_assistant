# Site Template Guide

## 目的

`config/site_templates.json` で、サイトごとのフォームの癖と安全ルールを共有します。

## 主な項目

- `domain`
- `site_name`
- `known_form_labels`
- `known_required_fields`
- `known_radio_groups`
- `known_select_options`
- `confirmation_button_texts`
- `submit_button_texts`
- `skip_rules`
- `manual_review_terms`
- `safety_notes`
- `last_verified_at`

## 運用ルール

- unknown は無理に推測しない
- 同じサイトはテンプレートで再利用する
- 危険系は `skip_rules` と `safety_notes` に寄せる
- 送信ボタン文言と確認ボタン文言は分けて持つ
- 選択肢は `known_select_options` に明示する
- 自動送信はしない

## 使いどころ

- `app/site_templates.py`
- `app/form_analyzer.py`
- `app/pre_submit_verifier.py`
- `app/answer_assistant.py`
- `web/templates/sites_dashboard.html`
