from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..app.knshow_scraper import build_keyword_search_url
from ..app.version import APP_VERSION
from ..app.paths import SELECTED_CAMPAIGNS_CSV
from ..app.storage import ensure_csv, read_csv_rows, write_csv_rows
from .data_loader import AppSnapshot
from .widgets import CampaignCard, Card, DisabledSubmitButton, FilterChip, SectionTitle, StatusPill


CATEGORY_LABELS = [
    "すべて",
    "大量当選",
    "締切間近",
    "食品",
    "飲料",
    "商品券",
    "家電",
    "日用品",
    "化粧品",
    "旅行",
    "映画・チケット",
    "Amazonギフト券",
    "QUOカード",
    "ビール",
    "コーヒー",
    "お菓子",
    "ゲーム",
    "スマホ",
    "防災用品",
]

DEFAULT_FILTER_STATES = {
    "web_form_only": True,
    "include_review_only": True,
    "ready_for_fill_only": False,
    "deadline_before_only": True,
    "massive_only": False,
    "prefer_low_personal_info": True,
    "exclude_x": True,
    "exclude_instagram": True,
    "exclude_line": True,
    "exclude_app": True,
    "exclude_member_registration": True,
    "exclude_receipt": True,
    "exclude_purchase": True,
    "exclude_captcha": True,
    "exclude_age": True,
}

SEARCH_SELECTION_HEADERS = [
    "campaign_id",
    "campaign_name",
    "selected_by_user",
    "selected_at",
    "selection_reason",
    "user_note",
    "excluded_by_user",
    "excluded_at",
    "excluded_reason",
    "resolved_entry_url",
    "status",
]


def _campaign_text(row: dict[str, str]) -> str:
    return " ".join(
        [
            row.get("campaign_name", ""),
            row.get("prize", ""),
            row.get("provider", ""),
            row.get("category", ""),
            row.get("entry_type_raw", ""),
            row.get("notes", ""),
            row.get("status", ""),
            row.get("resolve_status", ""),
            row.get("form_readiness_status", ""),
        ]
    ).casefold()


def _state_text(row: dict[str, str]) -> str:
    return row.get("form_readiness_status") or row.get("resolve_status") or row.get("status") or "未収集"


def _state_color(status: str) -> str:
    mapping = {
        "REVIEW_ONLY": "pillBlue",
        "READY_FOR_FILL": "pillGreen",
        "LANDING_PAGE": "pillOrange",
        "SEARCH_ONLY": "pillPurple",
        "LOW_CONFIDENCE": "pillRed",
        "RESOLVED": "pillBlue",
        "BLOCKED": "pillGray",
    }
    return mapping.get(status, "pillGray")


def _make_pill(text: str, color: str) -> StatusPill:
    pill = StatusPill(text, color)
    pill.setProperty("class", color)
    pill.setObjectName(color)
    return pill


def _matches_category(row: dict[str, str], active_categories: list[str]) -> bool:
    if not active_categories or "すべて" in active_categories:
        return True
    haystack = _campaign_text(row)
    return any(category.casefold() in haystack for category in active_categories)


def _row_is_excluded(row: dict[str, str], filters: dict[str, bool]) -> bool:
    haystack = _campaign_text(row)
    if filters["exclude_x"] and any(term in haystack for term in ("x懸賞", "twitter", "x(twitter)", "x応募")):
        return True
    if filters["exclude_instagram"] and "instagram" in haystack:
        return True
    if filters["exclude_line"] and "line" in haystack:
        return True
    if filters["exclude_app"] and ("アプリ" in haystack or "app" in haystack):
        return True
    if filters["exclude_member_registration"] and ("会員登録" in haystack or "member" in haystack):
        return True
    if filters["exclude_receipt"] and "レシート" in haystack:
        return True
    if filters["exclude_purchase"] and ("購入" in haystack or "レシート" in haystack):
        return True
    if filters["exclude_captcha"] and "captcha" in haystack:
        return True
    if filters["exclude_age"] and "18歳" in haystack:
        return True
    return False


def filter_campaigns(
    rows: list[dict[str, str]],
    query: str,
    active_categories: list[str],
    filters: dict[str, bool],
) -> list[dict[str, str]]:
    query = query.casefold().strip()
    filtered: list[dict[str, str]] = []
    for row in rows:
        text = _campaign_text(row)
        if query and query not in text:
            continue
        if not _matches_category(row, active_categories):
            continue
        if filters["ready_for_fill_only"] and row.get("form_readiness_status") != "READY_FOR_FILL":
            continue
        if not filters["include_review_only"] and row.get("form_readiness_status") == "REVIEW_ONLY":
            continue
        if filters["web_form_only"] and row.get("form_readiness_status") not in {"READY_FOR_FILL", "REVIEW_ONLY"}:
            continue
        if filters["deadline_before_only"] and not row.get("deadline"):
            continue
        if filters["massive_only"] and "大量" not in text:
            continue
        if _row_is_excluded(row, filters):
            continue
        filtered.append(row)
    return filtered


def _upsert_selection(path: Path, row: dict[str, str]) -> None:
    ensure_csv(path, SEARCH_SELECTION_HEADERS)
    rows = read_csv_rows(path)
    merged = {existing.get("campaign_id", ""): existing for existing in rows if existing.get("campaign_id")}
    merged[row["campaign_id"]] = {**merged.get(row["campaign_id"], {}), **row}
    write_csv_rows(path, merged.values(), SEARCH_SELECTION_HEADERS)


def save_campaign_selection(campaign: dict[str, str], path: Path = SELECTED_CAMPAIGNS_CSV, reason: str = "ユーザー選択", user_note: str = "") -> Path:
    _upsert_selection(
        path,
        {
            "campaign_id": campaign.get("campaign_id", ""),
            "campaign_name": campaign.get("campaign_name", ""),
            "selected_by_user": "true",
            "selected_at": campaign.get("collected_at", ""),
            "selection_reason": reason,
            "user_note": user_note,
            "excluded_by_user": "false",
            "excluded_at": "",
            "excluded_reason": "",
            "resolved_entry_url": campaign.get("resolved_entry_url", "") or campaign.get("entry_url", ""),
            "status": campaign.get("form_readiness_status", "") or campaign.get("status", ""),
        },
    )
    return path


def save_campaign_exclusion(campaign: dict[str, str], path: Path = SELECTED_CAMPAIGNS_CSV, reason: str = "ユーザー除外") -> Path:
    _upsert_selection(
        path,
        {
            "campaign_id": campaign.get("campaign_id", ""),
            "campaign_name": campaign.get("campaign_name", ""),
            "selected_by_user": "false",
            "selected_at": "",
            "selection_reason": "",
            "user_note": "",
            "excluded_by_user": "true",
            "excluded_at": campaign.get("collected_at", ""),
            "excluded_reason": reason,
            "resolved_entry_url": campaign.get("resolved_entry_url", "") or campaign.get("entry_url", ""),
            "status": campaign.get("form_readiness_status", "") or campaign.get("status", ""),
        },
    )
    return path


class SearchCampaignsPage(QWidget):
    def __init__(self, snapshot: AppSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.filtered_campaigns = list(snapshot.campaigns)
        self.selected_campaign_id = ""
        self.active_categories: list[str] = []
        self.filters = dict(DEFAULT_FILTER_STATES)

        root = QVBoxLayout(self)
        root.addWidget(SectionTitle("懸賞を探す"))
        root.addWidget(QLabel("懸賞生活 https://www.knshow.com/ から応募候補を探し、安全に診断する懸賞を選びます。"))

        top_cards = QHBoxLayout()
        top_cards.addWidget(Card(f"このアプリは {APP_VERSION} です", "診断・確認専用", "応募送信はしません"))
        top_cards.addWidget(Card("本番送信は人間確認が必要です", "自動送信は無効", "最後の送信は人間確認"))
        top_cards.addWidget(Card("個人情報はローカル保存", "profile.enc 運用", "実値は表示しません"))
        root.addLayout(top_cards)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ビール、Amazonギフト券、食品、QUOカード")
        search_row.addWidget(self.search_input, 4)
        self.search_button = QPushButton("検索")
        self.search_button.clicked.connect(self.refresh_results)
        search_row.addWidget(self.search_button)
        self.top_collect_button = QPushButton("トップから取得")
        self.top_collect_button.clicked.connect(lambda: self._run_cli(["collect", "--limit", "30"]))
        search_row.addWidget(self.top_collect_button)
        self.reset_button = QPushButton("条件リセット")
        self.reset_button.clicked.connect(self.reset_filters)
        search_row.addWidget(self.reset_button)
        root.addLayout(search_row)

        scan_row = QHBoxLayout()
        self.auto_scan_button = QPushButton("自動スキャンを実行")
        self.auto_scan_button.setObjectName("safe")
        self.auto_scan_button.clicked.connect(lambda: self._run_cli(["auto-scan", "--limit", "30"]))
        scan_row.addWidget(self.auto_scan_button)
        self.today_update_button = QPushButton("今日の候補を更新")
        self.today_update_button.clicked.connect(self.refresh_results)
        scan_row.addWidget(self.today_update_button)
        self.review_only_button = QPushButton("REVIEW_ONLYを確認")
        self.review_only_button.clicked.connect(lambda: self._run_cli(["review", "--limit", "10"]))
        scan_row.addWidget(self.review_only_button)
        self.safe_only_button = QPushButton("安全候補だけ表示")
        self.safe_only_button.clicked.connect(self._show_safe_only)
        scan_row.addWidget(self.safe_only_button)
        root.addLayout(scan_row)

        chip_label = QLabel("カテゴリ")
        chip_label.setObjectName("section")
        root.addWidget(chip_label)
        chip_grid = QGridLayout()
        self.category_buttons: dict[str, FilterChip] = {}
        for index, label in enumerate(CATEGORY_LABELS):
            button = FilterChip(label)
            if label == "すべて":
                button.setChecked(True)
            button.clicked.connect(self.refresh_results)
            self.category_buttons[label] = button
            chip_grid.addWidget(button, index // 6, index % 6)
        root.addLayout(chip_grid)

        filter_panel = QFrame()
        filter_panel.setObjectName("card")
        filter_layout = QGridLayout(filter_panel)
        left_filters = [
            ("web_form_only", "Webフォームのみ"),
            ("include_review_only", "REVIEW_ONLY候補を含める"),
            ("ready_for_fill_only", "READY_FOR_FILLのみ"),
            ("deadline_before_only", "締切前のみ"),
            ("massive_only", "大量当選のみ"),
            ("prefer_low_personal_info", "個人情報少なめを優先"),
        ]
        right_filters = [
            ("exclude_x", "X懸賞を除外"),
            ("exclude_instagram", "Instagram懸賞を除外"),
            ("exclude_line", "LINE懸賞を除外"),
            ("exclude_app", "アプリ応募を除外"),
            ("exclude_member_registration", "会員登録必須を除外"),
            ("exclude_receipt", "レシート応募を除外"),
            ("exclude_purchase", "購入条件ありを除外"),
            ("exclude_captcha", "CAPTCHAありを除外"),
            ("exclude_age", "年齢確認ありを除外"),
        ]
        self.filter_boxes: dict[str, QCheckBox] = {}
        for index, (key, label) in enumerate(left_filters):
            box = QCheckBox(label)
            box.setChecked(DEFAULT_FILTER_STATES[key])
            box.stateChanged.connect(self.refresh_results)
            self.filter_boxes[key] = box
            filter_layout.addWidget(box, index // 2, index % 2)
        for index, (key, label) in enumerate(right_filters):
            box = QCheckBox(label)
            box.setChecked(DEFAULT_FILTER_STATES[key])
            box.stateChanged.connect(self.refresh_results)
            self.filter_boxes[key] = box
            filter_layout.addWidget(box, index // 2, 3 + (index % 2))
        self.save_filter_button = QPushButton("フィルター保存")
        self.save_filter_button.setObjectName("safe")
        self.save_filter_button.clicked.connect(self.refresh_results)
        filter_layout.addWidget(self.save_filter_button, 3, 5)
        root.addWidget(filter_panel)

        main_row = QHBoxLayout()

        left_panel = QVBoxLayout()
        left_panel.addWidget(SectionTitle("検索結果"))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.result_host = QWidget()
        self.result_layout = QVBoxLayout(self.result_host)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        self.result_layout.setSpacing(12)
        self.scroll.setWidget(self.result_host)
        left_panel.addWidget(self.scroll)
        main_row.addLayout(left_panel, 4)

        detail_panel = QFrame()
        detail_panel.setObjectName("panel")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.addWidget(SectionTitle("詳細パネル"))
        self.detail_title = QLabel("候補を選択してください")
        self.detail_title.setWordWrap(True)
        self.detail_title.setObjectName("title")
        detail_layout.addWidget(self.detail_title)
        self.detail_body = QLabel("")
        self.detail_body.setWordWrap(True)
        detail_layout.addWidget(self.detail_body)
        detail_layout.addWidget(QLabel("本番送信はユーザー本人の確認が必要です"))
        detail_layout.addWidget(QLabel("懸賞生活の公式ツールではありません"))
        detail_layout.addWidget(QLabel("対象サイト：懸賞生活 https://www.knshow.com/"))
        self.safe_submit_button = DisabledSubmitButton()
        detail_layout.addWidget(self.safe_submit_button)
        self.add_button = QPushButton("候補に追加")
        self.add_button.clicked.connect(self.mark_selected)
        detail_layout.addWidget(self.add_button)
        self.exclude_button = QPushButton("除外する")
        self.exclude_button.clicked.connect(self.mark_excluded)
        detail_layout.addWidget(self.exclude_button)
        self.other_button = QPushButton("その他")
        self.other_button.clicked.connect(lambda: self._run_cli(["review", "--limit", "5"]))
        detail_layout.addWidget(self.other_button)
        main_row.addWidget(detail_panel, 2)

        root.addLayout(main_row)

        footer = QHBoxLayout()
        footer.addWidget(QLabel("安全モード"))
        footer.addWidget(QLabel("送信機能：無効"))
        footer.addWidget(QLabel("スクリーンショット保存：OFF"))
        footer.addWidget(QLabel("ログのマスキング：ON"))
        footer.addWidget(QLabel("profile.enc：保存済み"))
        footer.addStretch(1)
        root.addLayout(footer)

        self.refresh_results()

    def _run_cli(self, args: list[str]) -> None:
        subprocess.Popen([sys.executable, "main.py", *args], cwd=Path(__file__).resolve().parents[2])

    def _current_row(self) -> dict[str, str] | None:
        if not self.selected_campaign_id:
            return None
        for row in self.filtered_campaigns:
            if row.get("campaign_id") == self.selected_campaign_id:
                return row
        return None

    def _card_widget(self, row: dict[str, str]) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        header = QHBoxLayout()
        thumb = QFrame()
        thumb.setFixedSize(72, 72)
        thumb.setObjectName("card")
        header.addWidget(thumb)

        body = QVBoxLayout()
        title = QLabel(row.get("campaign_name", ""))
        title.setObjectName("section")
        body.addWidget(title)
        body.addWidget(QLabel(f"提供企業: {row.get('provider', '')}"))
        body.addWidget(QLabel(f"当選人数: {row.get('winner_count', '')} / 締切: {row.get('deadline', '')}"))
        tags = QHBoxLayout()
        tags.addWidget(_make_pill(row.get("entry_type_raw", "未分類"), "pillGray"))
        tags.addWidget(_make_pill(_state_text(row), _state_color(_state_text(row))))
        tags.addWidget(_make_pill(row.get("risk_level", "") or row.get("risk_reason", "") or "安全確認", "pillOrange"))
        tags.addStretch(1)
        body.addLayout(tags)
        body.addWidget(QLabel(f"フォーム有無: {row.get('form_readiness_status', '') or '未取得'}"))
        header.addLayout(body, 1)
        layout.addLayout(header)

        actions = QHBoxLayout()
        select = QPushButton("候補に追加")
        select.clicked.connect(lambda *_: self._set_selection(row.get("campaign_id", "")))
        actions.addWidget(select)
        resolve = QPushButton("URL解決")
        resolve.clicked.connect(lambda *_: self._run_cli(["resolve-urls", "--limit", "30"]))
        actions.addWidget(resolve)
        inspect = QPushButton("フォーム診断")
        inspect.clicked.connect(lambda *_: self._inspect_campaign(row.get("campaign_id", "")))
        actions.addWidget(inspect)
        favorite = QPushButton("☆お気に入り")
        favorite.clicked.connect(lambda *_: self._set_selection(row.get("campaign_id", ""), reason="お気に入り"))
        actions.addWidget(favorite)
        exclude = QPushButton("除外する")
        exclude.clicked.connect(lambda *_: self._set_exclusion(row.get("campaign_id", "")))
        actions.addWidget(exclude)
        actions.addStretch(1)
        layout.addLayout(actions)
        card.mousePressEvent = lambda event, cid=row.get("campaign_id", ""): self._set_selection(cid)
        return card

    def _inspect_campaign(self, campaign_id: str) -> None:
        if campaign_id:
            self._run_cli(["inspect-form", "--campaign-id", campaign_id])

    def _set_selection(self, campaign_id: str, reason: str = "ユーザー選択") -> None:
        self.selected_campaign_id = campaign_id
        campaign = self._current_by_id(campaign_id)
        if campaign:
            save_campaign_selection(campaign, reason=reason)
            self.update_details()

    def _set_exclusion(self, campaign_id: str, reason: str = "ユーザー除外") -> None:
        campaign = self._current_by_id(campaign_id)
        if campaign:
            save_campaign_exclusion(campaign, reason=reason)
            self.update_details()

    def _current_by_id(self, campaign_id: str) -> dict[str, str] | None:
        for row in self.filtered_campaigns:
            if row.get("campaign_id") == campaign_id:
                return row
        for row in self.snapshot.campaigns:
            if row.get("campaign_id") == campaign_id:
                return row
        return None

    def _detail_text(self, row: dict[str, str]) -> str:
        return "\n".join(
            [
                f"キャンペーン名: {row.get('campaign_name', '')}",
                f"賞品: {row.get('prize', '')}",
                f"当選人数: {row.get('winner_count', '')}",
                f"締切: {row.get('deadline', '')}",
                f"提供企業: {row.get('provider', '')}",
                f"応募タイプ: {row.get('entry_type_raw', '')}",
                f"応募条件: {row.get('description', '') or '未取得'}",
                f"レシート要否: {'あり' if 'レシート' in _campaign_text(row) else 'なし/未取得'}",
                f"購入条件: {'あり' if '購入' in _campaign_text(row) else 'なし/未取得'}",
                f"年齢確認: {'あり' if '18歳' in _campaign_text(row) else 'なし/未取得'}",
                f"URL: {row.get('entry_url', '')}",
                f"解決済みURL: {row.get('resolved_entry_url', '') or '未解決'}",
                f"安全判定: {row.get('form_readiness_status', '') or row.get('status', '')}",
                f"手動確認が必要な項目: {row.get('notes', '') or 'なし'}",
                f"次のおすすめアクション: {self._next_action(row)}",
            ]
        )

    def _next_action(self, row: dict[str, str]) -> str:
        if not row.get("resolved_entry_url"):
            return "URLを解決してください"
        readiness = row.get("form_readiness_status", "")
        if readiness == "READY_FOR_FILL":
            return "フォーム診断を行ってください"
        if readiness == "REVIEW_ONLY":
            return "内容を確認後、REVIEW_ONLYとして候補に保持してください"
        if row.get("entry_type_raw", "").find("X") >= 0 or "Twitter" in row.get("entry_type_raw", ""):
            return "SNS応募のため自動操作対象外です"
        if "購入" in _campaign_text(row):
            return "購入条件があるため除外推奨です"
        return "安全確認後に候補として保持してください"

    def _refresh_card_list(self) -> None:
        while self.result_layout.count():
            item = self.result_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not self.filtered_campaigns:
            self.result_layout.addWidget(QLabel("候補がありません"))
            self.result_layout.addStretch(1)
            return
        for row in self.filtered_campaigns:
            card = self._card_widget(row)
            self.result_layout.addWidget(card)
        self.result_layout.addStretch(1)

    def refresh_results(self) -> None:
        self.filters = {key: box.isChecked() for key, box in self.filter_boxes.items()}
        self.active_categories = [label for label, button in self.category_buttons.items() if button.isChecked()]
        if "すべて" in self.active_categories and len(self.active_categories) > 1:
            self.active_categories = [item for item in self.active_categories if item != "すべて"]
        self.filtered_campaigns = filter_campaigns(self.snapshot.campaigns, self.search_input.text(), self.active_categories, self.filters)
        self._refresh_card_list()
        if self.filtered_campaigns:
            self.selected_campaign_id = self.filtered_campaigns[0].get("campaign_id", "")
            self.update_details()
        else:
            self.detail_title.setText("候補がありません")
            self.detail_body.setText("")

    def reset_filters(self) -> None:
        self.search_input.clear()
        for label, button in self.category_buttons.items():
            button.setChecked(label == "すべて")
        for key, box in self.filter_boxes.items():
            box.setChecked(DEFAULT_FILTER_STATES[key])
        self.refresh_results()

    def _show_safe_only(self) -> None:
        self.filter_boxes["ready_for_fill_only"].setChecked(False)
        self.filter_boxes["include_review_only"].setChecked(True)
        self.filter_boxes["web_form_only"].setChecked(True)
        self.refresh_results()

    def update_details(self) -> None:
        row = self._current_row()
        if not row:
            self.detail_title.setText("候補を選択してください")
            self.detail_body.setText("")
            return
        self.detail_title.setText(row.get("campaign_name", ""))
        self.detail_body.setText(self._detail_text(row))

    def mark_selected(self) -> None:
        row = self._current_row()
        if row:
            self._set_selection(row.get("campaign_id", ""))

    def mark_excluded(self) -> None:
        row = self._current_row()
        if row:
            self._set_exclusion(row.get("campaign_id", ""))
