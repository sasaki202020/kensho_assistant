from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from .campaigns_page import CampaignsPage
from .agent_control_page import AgentControlPage
from .agent_dashboard_page import AgentDashboardPage
from .dashboard_page import DashboardPage
from .data_loader import AppSnapshot
from .entries_page import EntriesPage
from .form_diagnosis_page import FormDiagnosisPage
from .help_page import HelpPage
from .profile_security_page import ProfileSecurityPage
from .search_campaigns_page import SearchCampaignsPage
from .theme import APP_STYLESHEET
from ..app.version import APP_VERSION


class MainWindow(QMainWindow):
    def __init__(self, snapshot: AppSnapshot) -> None:
        super().__init__()
        self.setWindowTitle(f"懸賞応募アシスタント {APP_VERSION}")
        self.resize(1280, 820)
        self.setStyleSheet(APP_STYLESHEET)
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.addWidget(QLabel("対象サイト：懸賞生活 https://www.knshow.com/"))
        content = QHBoxLayout()
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(QLabel(f"懸賞応募アシスタント {APP_VERSION}"))
        self.nav = QListWidget()
        self.nav.addItems(["ダッシュボード", "懸賞を探す", "キャンペーン一覧", "応募履歴", "REVIEW_ONLY", "フォーム診断", "プロフィール", "レポート", "設定", "AI担当者", "AI司令塔", "ヘルプ・使い方"])
        sidebar_layout.addWidget(self.nav)
        content.addWidget(sidebar, 1)
        self.stack = QStackedWidget()
        dashboard = DashboardPage(snapshot)
        search = SearchCampaignsPage(snapshot)
        campaigns = CampaignsPage(snapshot)
        entries = EntriesPage(snapshot)
        diagnosis = FormDiagnosisPage(snapshot)
        profile = ProfileSecurityPage(snapshot)
        agents = AgentDashboardPage()
        control = AgentControlPage()
        help_page = HelpPage()
        self.send_button = diagnosis.send_button
        for page in (dashboard, search, campaigns, entries, campaigns, diagnosis, profile, dashboard, profile, agents, control, help_page):
            self.stack.addWidget(page)
        content.addWidget(self.stack, 4)
        outer.addLayout(content)
        outer.addWidget(QLabel("懸賞生活の公式ツールではありません / 応募送信はユーザー本人の確認が必要です"))
        outer.addWidget(QLabel("安全モード / 送信機能：無効 / スクリーンショット保存：OFF / ログのマスキング：ON / profile.enc：保存済み"))
        self.setCentralWidget(root)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
