from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout


class Card(QFrame):
    def __init__(self, title: str, value: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        title_label = QLabel(title)
        title_label.setObjectName("muted")
        value_label = QLabel(value)
        value_label.setObjectName("title")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("muted")
            layout.addWidget(sub)


class MetricCard(Card):
    pass


class SafetyCard(Card):
    pass


class CampaignCard(Card):
    pass


class DetailPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("panel")


class SectionTitle(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("section")


class StatusPill(QLabel):
    def __init__(self, text: str, color: str = "pillGray") -> None:
        super().__init__(text)
        self.setObjectName("pill")
        self.setProperty("class", color)
        self.setStyleSheet("")


class FilterChip(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setObjectName("chip")


class SafeButton(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("safe")


class DisabledSubmitButton(QPushButton):
    def __init__(self, text: str = "送信（無効）") -> None:
        super().__init__(text)
        self.setObjectName("dangerless")
        self.setEnabled(False)
