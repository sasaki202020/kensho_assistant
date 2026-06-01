from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from .data_loader import AppSnapshot


class CampaignsPage(QWidget):
    def __init__(self, snapshot: AppSnapshot) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        filters = QLabel("すべて / REVIEW_ONLY / LANDING_PAGE / SEARCH_ONLY / LOW_CONFIDENCE / RESOLVED / READY_FOR_FILL")
        layout.addWidget(filters)
        table = QTableWidget(len(snapshot.campaigns), 6)
        table.setHorizontalHeaderLabels(["campaign_id", "キャンペーン名", "応募先URL", "状態", "readiness", "更新日時"])
        for row_index, row in enumerate(snapshot.campaigns):
            values = [
                row.get("campaign_id", ""),
                row.get("campaign_name", ""),
                row.get("resolved_entry_url", "") or row.get("entry_url", ""),
                row.get("status", ""),
                row.get("form_readiness_status", ""),
                row.get("inspected_at", "") or row.get("resolved_at", "") or row.get("collected_at", ""),
            ]
            for col, value in enumerate(values):
                table.setItem(row_index, col, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        layout.addWidget(QLabel("詳細パネル: 外部ブラウザでの確認のみ。自動応募や送信は行いません。"))
