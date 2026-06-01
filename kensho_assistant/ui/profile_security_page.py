from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ..app.version import APP_VERSION
from .data_loader import AppSnapshot, profile_storage_state


class ProfileSecurityPage(QWidget):
    def __init__(self, snapshot: AppSnapshot) -> None:
        super().__init__()
        storage = profile_storage_state()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"profile.enc: {storage['profile_enc']}"))
        layout.addWidget(QLabel(f"profile.json: {storage['profile_json']}"))
        layout.addWidget(QLabel("スクリーンショット保存: OFF"))
        layout.addWidget(QLabel("ログのマスキング: ON"))
        layout.addWidget(QLabel("安全モード: 有効"))
        layout.addWidget(QLabel("対象サイト：懸賞生活 https://www.knshow.com/"))
        layout.addWidget(QLabel("懸賞生活の公式ツールではありません"))
        layout.addWidget(QLabel("本番profileテスト済み: 1件 / 応募送信なし"))
        layout.addWidget(QLabel("実値は表示しません"))
        layout.addWidget(QLabel("本番送信は人間確認が必要です"))
        layout.addWidget(QLabel(f"{APP_VERSION} として固定済み"))
        layout.addWidget(QLabel(f"release-report: {snapshot.release_report.get('release_status', '未取得')}"))
        layout.addWidget(
            QLabel(
                "プレビュー: "
                f"{snapshot.profile_preview['name']} / {snapshot.profile_preview['postal_code']} / "
                f"{snapshot.profile_preview['email']} / {snapshot.profile_preview['phone']}"
            )
        )
        for label in ("profile check", "doctor", "release-reportを開く", "データ保存先を開く"):
            layout.addWidget(QPushButton(label))
