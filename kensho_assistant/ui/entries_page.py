from __future__ import annotations

from datetime import date, datetime

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..app.entry_history import export_entry_history_csv, load_entry_history, load_win_mail_candidates, rescan_win_mail_candidates, summarize_entry_history, summarize_win_mail_candidates
from .data_loader import AppSnapshot
from .widgets import Card


def _deadline_bucket(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "unknown"
    if any(keyword in text for keyword in ("今日", "本日")):
        return "today"
    if "明日" in text:
        return "tomorrow"
    if "今週" in text or "週末" in text:
        return "week"
    if any(keyword in text for keyword in ("期限切れ", "終了")):
        return "expired"
    return "future"


def _sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: (_deadline_bucket(row.get("deadline", "")), row.get("title", ""), row.get("campaign_id", "")))


def _filter_rows(rows: list[dict[str, str]], query: str, deadline: str, result: str, newsletter: str) -> list[dict[str, str]]:
    query_text = query.casefold().strip()
    filtered: list[dict[str, str]] = []
    for row in rows:
        haystack = " ".join(
            row.get(field, "")
            for field in ("campaign_id", "title", "source_site", "url", "prize", "deadline", "status", "newsletter_status", "memo", "duplicate_key")
        ).casefold()
        if query_text and query_text not in haystack:
            continue
        if deadline != "all" and _deadline_bucket(row.get("deadline", "")) != deadline:
            continue
        if result != "all":
            status = row.get("status", "").upper()
            if result == "pending" and status not in {"APPLIED", "PENDING_RESULT"}:
                continue
            if result == "checked" and status != "RESULT_CHECKED":
                continue
            if result == "duplicate" and status != "DUPLICATE":
                continue
            if result == "applied" and status != "APPLIED":
                continue
        if newsletter != "all" and row.get("newsletter_status", "unknown") != newsletter:
            continue
        filtered.append(row)
    return _sort_rows(filtered)


class EntriesPage(QWidget):
    def __init__(self, snapshot: AppSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot
        self._entry_rows: list[dict[str, str]] = []
        self._mail_rows: list[dict[str, str]] = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("応募履歴 / 当選メール候補 / メルマガ管理"))
        layout.addWidget(QLabel("自動送信はしません。応募履歴と確認作業だけを扱います。"))

        summary_grid = QGridLayout()
        self.summary_cards = [
            Card("今日締切", "0"),
            Card("今週締切", "0"),
            Card("応募済み数", "0"),
            Card("当選確認待ち", "0"),
            Card("メルマガ解除候補", "0"),
            Card("重複候補", "0"),
        ]
        for index, card in enumerate(self.summary_cards):
            summary_grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(summary_grid)

        controls = QFrame()
        controls.setObjectName("card")
        controls_layout = QHBoxLayout(controls)
        self.query = QLineEdit()
        self.query.setPlaceholderText("キーワード検索")
        self.deadline_filter = QComboBox()
        self.deadline_filter.addItems(["all", "today", "tomorrow", "week", "future", "expired"])
        self.result_filter = QComboBox()
        self.result_filter.addItems(["all", "applied", "pending", "checked", "duplicate"])
        self.newsletter_filter = QComboBox()
        self.newsletter_filter.addItems(["all", "unknown", "opt_in", "unsubscribe_needed", "unsubscribed", "opt_out"])
        self.export_button = QPushButton("CSV出力")
        self.rescan_button = QPushButton("当選メール再スキャン")
        controls_layout.addWidget(self.query)
        controls_layout.addWidget(self.deadline_filter)
        controls_layout.addWidget(self.result_filter)
        controls_layout.addWidget(self.newsletter_filter)
        controls_layout.addWidget(self.export_button)
        controls_layout.addWidget(self.rescan_button)
        layout.addWidget(controls)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["campaign_id", "タイトル", "締切", "status", "newsletter", "応募日", "結果確認日", "重複キー"])
        layout.addWidget(self.table)

        self.mail_table = QTableWidget(0, 4)
        self.mail_table.setHorizontalHeaderLabels(["subject", "sender", "received_at", "keywords"])
        layout.addWidget(QLabel("当選メール候補"))
        layout.addWidget(self.mail_table)

        self.status = QLabel("")
        layout.addWidget(self.status)

        self.query.textChanged.connect(self.refresh)
        self.deadline_filter.currentTextChanged.connect(self.refresh)
        self.result_filter.currentTextChanged.connect(self.refresh)
        self.newsletter_filter.currentTextChanged.connect(self.refresh)
        self.export_button.clicked.connect(self.export_csv)
        self.rescan_button.clicked.connect(self.rescan_mail_candidates)
        self.refresh()

    def refresh(self) -> None:
        self._entry_rows = load_entry_history()
        self._mail_rows = load_win_mail_candidates()
        summary = summarize_entry_history(self._entry_rows)
        mail_summary = summarize_win_mail_candidates(self._mail_rows)
        values = [
            summary.get("today_deadline", 0),
            summary.get("week_deadline", 0),
            summary.get("applied", 0),
            summary.get("result_pending", 0),
            summary.get("newsletter_unsubscribe_needed", 0),
            summary.get("duplicate_candidates", 0),
        ]
        for card, value in zip(self.summary_cards, values, strict=False):
            value_widget = card.layout().itemAt(1).widget()
            if isinstance(value_widget, QLabel):
                value_widget.setText(str(value))
        rows = _filter_rows(
            self._entry_rows,
            self.query.text(),
            self.deadline_filter.currentText(),
            self.result_filter.currentText(),
            self.newsletter_filter.currentText(),
        )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row.get("campaign_id", ""),
                row.get("title", ""),
                row.get("deadline", ""),
                row.get("status", ""),
                row.get("newsletter_status", ""),
                row.get("applied_at", ""),
                row.get("result_check_date", ""),
                row.get("duplicate_key", ""),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row_index, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

        self.mail_table.setRowCount(len(self._mail_rows))
        for row_index, row in enumerate(self._mail_rows):
            values = [
                row.get("subject", ""),
                row.get("sender", ""),
                row.get("received_at", ""),
                ", ".join(row.get("keyword_hits", [])) if isinstance(row.get("keyword_hits", []), list) else str(row.get("keyword_hits", "")),
            ]
            for col, value in enumerate(values):
                self.mail_table.setItem(row_index, col, QTableWidgetItem(value))
        self.mail_table.resizeColumnsToContents()
        self.status.setText(
            f"応募履歴 {len(rows)} 件 / 当選メール候補 {mail_summary.get('total', 0)} 件 / 自動送信 無効 / profile.enc 使用"
        )

    def export_csv(self) -> None:
        path = export_entry_history_csv()
        self.status.setText(f"CSV出力: {path}")

    def rescan_mail_candidates(self) -> None:
        rows = rescan_win_mail_candidates()
        self._mail_rows = rows
        self.refresh()
