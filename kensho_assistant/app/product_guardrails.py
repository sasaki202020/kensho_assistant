from __future__ import annotations

DEFAULT_RULES = {
    "entry_type_keywords": {
        "X_CAMPAIGN": ["x懸賞", "twitter懸賞", "x(twitter)", "twitter", "フォロー&リポスト", "フォロー＆リポスト", "リポスト"],
        "INSTAGRAM_CAMPAIGN": ["instagram懸賞", "インスタグラム", "insta"],
        "LINE_CAMPAIGN": ["line懸賞", "line"],
        "FACEBOOK_CAMPAIGN": ["facebook懸賞", "facebook"],
        "APP_REQUIRED": ["アプリから応募", "アプリ応募", "app"],
        "LOGIN_REQUIRED": ["ログイン", "member login"],
        "MEMBER_REGISTRATION": ["会員登録応募", "会員登録", "新規登録"],
        "PURCHASE_REQUIRED": ["購入", "買って応募", "対象商品", "レシート", "バーコード"],
        "RECEIPT_REQUIRED": ["レシート"],
        "BARCODE_REQUIRED": ["バーコード", "jan"],
        "AGE_RESTRICTED": ["20歳以上", "年齢確認", "酒", "たばこ"],
        "CAPTCHA_REQUIRED": ["captcha", "recaptcha", "私はロボットではありません"],
        "REGION_LIMITED": ["在住者限定", "地域限定", "県内限定"],
        "CLOSED_CAMPAIGN": ["クローズド懸賞"],
        "SAMPLE": ["サンプル", "試供品", "モニター"],
        "QUIZ": ["クイズ"],
        "SURVEY": ["アンケート", "アンケート・", "調査"],
        "EASY_ENTRY": ["カンタン応募", "簡単応募", "easy"],
        "WEB_FORM": ["webフォーム", "web応募", "フォーム応募"],
    },
    "blocked_terms": {
        "AUTO_ENTRY_FORBIDDEN": ["自動応募禁止", "bot禁止"],
    },
    "deadline_terms": ["本日締切", "明日締切", "明後日締切"],
}

DEFAULT_PRODUCT = {
    "product_name": "懸賞応募アシスタント",
    "positioning": "ユーザー本人の応募作業を安全に補助するローカルツール",
    "disallowed_claims": [
        "当選率アップ",
        "必ず当たる",
        "完全自動で稼げる",
    ],
}

