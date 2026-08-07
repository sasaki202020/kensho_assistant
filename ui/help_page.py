from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class HelpPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("ヘルプ・使い方"))
        layout.addWidget(QLabel("1. 懸賞を探す で候補を選びます。"))
        layout.addWidget(QLabel("2. URL解決 / フォーム診断で安全性を確認します。"))
        layout.addWidget(QLabel("3. REVIEW_ONLY は人間確認付きの安全モードです。"))
        layout.addWidget(QLabel("4. 本番送信は行いません。送信はユーザー本人が別途確認してください。"))
