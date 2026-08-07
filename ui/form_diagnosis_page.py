from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ..app.version import APP_VERSION
from .data_loader import AppSnapshot


class FormDiagnosisPage(QWidget):
    def __init__(self, snapshot: AppSnapshot) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        inspection = next(iter(snapshot.inspections.values()), {})
        fields = list(inspection.get("detected_fields", []))
        layout.addWidget(QLabel(f"readiness_status: {inspection.get('readiness_status', '未取得')}"))
        bar = QProgressBar()
        bar.setValue(int(float(inspection.get("readiness_score", 0) or 0) * 100))
        layout.addWidget(bar)
        table = QTableWidget(len(fields), 6)
        table.setHorizontalHeaderLabels(["field_name", "必須", "信頼度", "入力方針", "スキップ理由", "selector"])
        for row_index, field in enumerate(fields):
            if field.get("field_name") in {"age", "consent"}:
                policy = "要確認"
            elif field.get("will_fill"):
                policy = "入力"
            else:
                policy = "スキップ"
            values = [
                str(field.get("field_name", "")),
                "必須" if field.get("required") else "任意",
                f"{float(field.get('confidence', 0) or 0):.2f}",
                policy,
                str(field.get("skip_reason", "")),
                str(field.get("selector", "")),
            ]
            for col, value in enumerate(values):
                table.setItem(row_index, col, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        layout.addWidget(
            QLabel(
                "プロフィール: "
                f"{snapshot.profile_preview['name']} / {snapshot.profile_preview['postal_code']} / "
                f"{snapshot.profile_preview['email']} / {snapshot.profile_preview['phone']}"
            )
        )
        layout.addWidget(QLabel("対象サイト：懸賞生活 https://www.knshow.com/"))
        layout.addWidget(QLabel("懸賞生活の公式ツールではありません"))
        layout.addWidget(QLabel("本番profileテスト済み: 1件 / 応募送信なし"))
        layout.addWidget(QLabel("実値は表示しません"))
        layout.addWidget(QLabel("本番送信は人間確認が必要です"))
        layout.addWidget(QLabel(f"{APP_VERSION} の安全停止確認済み"))
        self.send_button = QPushButton("送信（無効）")
        self.send_button.setEnabled(False)
        self.send_button.setToolTip("自動送信は無効です。手動で確認してください。")
        layout.addWidget(self.send_button)
