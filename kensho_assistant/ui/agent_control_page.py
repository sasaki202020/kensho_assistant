from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..app.agent_control.controller import cancel_job, get_agent_control_report, get_agent_control_status, list_agent_control_agents, list_agent_control_jobs, run_agent_job
from .widgets import Card, SafeButton, StatusPill


class AgentControlPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.target_url = QLineEdit()
        self.target_url.setPlaceholderText("任意の target_url（入力しても外部送信しません）")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("現在はJSON結果表示モードです。Agent Control はローカル dry-run のみ実行します。"))
        layout.addWidget(QLabel("自動送信なし / submit・click 系の自動化なし / profile.enc 非読込 / PIIログなし / X操作自動化なし"))
        layout.addWidget(QLabel("target_url は入力補助用で、外部送信やブラウザ操作は行いません。"))
        layout.addWidget(self.target_url)

        report = get_agent_control_report()
        grid = QGridLayout()
        cards = [
            ("pending", str(report.get("counts", {}).get("pending", 0))),
            ("running", str(report.get("counts", {}).get("running", 0))),
            ("needs_review", str(report.get("counts", {}).get("needs_review", 0))),
            ("blocked", str(report.get("counts", {}).get("blocked", 0))),
            ("done", str(report.get("counts", {}).get("done", 0))),
            ("failed", str(report.get("counts", {}).get("failed", 0))),
        ]
        for index, (title, value) in enumerate(cards):
            grid.addWidget(Card(title, value), 0, index)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        refresh_button = SafeButton("更新")
        refresh_button.clicked.connect(self.refresh_view)
        actions.addWidget(refresh_button)
        layout.addLayout(actions)

        self.summary = QLabel("")
        layout.addWidget(self.summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setSpacing(12)
        scroll.setWidget(container)
        layout.addWidget(scroll)
        self.refresh_view()

    def refresh_view(self) -> None:
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        status = get_agent_control_status()
        report = get_agent_control_report()
        self.summary.setText(
            " / ".join(
                [
                    f"jobs={report.get('total_jobs', 0)}",
                    f"submitted_count_auto={status.get('submitted_count_auto', 0)}",
                    f"safe_to_submit={status.get('safe_to_submit', False)}",
                ]
            )
        )

        for agent in list_agent_control_agents():
            card = Card(agent.get("display_name", "agent"), agent.get("role", ""), agent.get("purpose", ""))
            card_layout = card.layout()
            assert card_layout is not None
            card_layout.addWidget(QLabel(f"status: {agent.get('status', 'idle')}"))
            card_layout.addWidget(QLabel(f"last_run_at: {agent.get('last_run_at', '') or '未実行'}"))
            card_layout.addWidget(QLabel(f"latest_result: {agent.get('latest_result', '') or '未実行'}"))
            card_layout.addWidget(QLabel(f"latest_safety_memo: {agent.get('latest_safety_memo', '') or '未設定'}"))
            pill_row = QHBoxLayout()
            pill_row.addWidget(StatusPill("実行", "pillBlue"))
            pill_row.addWidget(StatusPill("停止", "pillGray"))
            pill_row.addWidget(StatusPill("ログ", "pillGray"))
            pill_row.addWidget(StatusPill("結果", "pillGray"))
            pill_row.addWidget(StatusPill("人間確認へ送る", "pillOrange"))
            card_layout.addLayout(pill_row)

            run_button = SafeButton("実行")
            run_button.clicked.connect(lambda _=False, name=agent.get("agent_name", ""), action="": run_agent_job(name, action, self.target_url.text()))
            stop_button = SafeButton("停止")
            stop_button.clicked.connect(lambda _=False, name=agent.get("agent_name", ""): cancel_job(agent_name=name))
            card_layout.addWidget(run_button)
            card_layout.addWidget(stop_button)
            if agent.get("status") in {"warning", "error"} or agent.get("blocked_count", 0):
                card.setProperty("class", "agent-error")
            self.container_layout.addWidget(card)

        jobs = list_agent_control_jobs(limit=20)
        jobs_card = Card("ジョブ一覧", f"{len(jobs)}件")
        jobs_layout = jobs_card.layout()
        assert jobs_layout is not None
        for job in jobs[:10]:
            jobs_layout.addWidget(
                QLabel(
                    " / ".join(
                        [
                            f"{job.get('created_at', '')}",
                            f"{job.get('agent_name', '')}",
                            f"{job.get('target_url', '') or 'unknown'}",
                            f"{job.get('status', '')}",
                            f"{job.get('safety_memo', '')}",
                            f"{job.get('result_summary', '')}",
                        ]
                    )
                )
            )
        self.container_layout.addWidget(jobs_card)
