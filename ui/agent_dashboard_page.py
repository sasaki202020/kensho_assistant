from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QProgressBar, QScrollArea, QVBoxLayout, QWidget

from ..app.agent_dashboard.service import get_agent_org_summary, get_agent_summary, group_agent_teams
from .widgets import Card


class AgentDashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("現在はJSON結果表示モードです。agent_status.json を読み込んで担当者カードを表示します。"))
        layout.addWidget(QLabel("自動送信なし / profile.enc 未読込 / PIIログなし / X操作自動化なし"))
        org_summary = get_agent_org_summary()
        layout.addWidget(QLabel(f"組織: {org_summary.get('org_name', '')} / モード: {org_summary.get('mode_label', '')}"))

        summary = get_agent_summary()
        grid = QGridLayout()
        cards = [
            ("担当者数", str(summary.get("total_agents", 0))),
            ("チーム数", str(org_summary.get("team_count", 0))),
            ("実行中", str(summary.get("running_count", 0))),
            ("警告あり", str(summary.get("warning_count", 0))),
            ("エラー", str(summary.get("error_count", 0))),
            ("完了", str(summary.get("completed_count", 0))),
        ]
        for index, (title, value) in enumerate(cards):
            grid.addWidget(Card(title, value), 0, index)
        layout.addLayout(grid)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(12)

        for team in group_agent_teams():
            team_card = Card(team.get("name", "team"), team.get("purpose", ""))
            team_layout = team_card.layout()
            assert team_layout is not None
            team_layout.addWidget(QLabel(f"team_id: {team.get('id', '')}"))
            team_layout.addWidget(QLabel(f"active_agents: {len(team.get('agents', []))}"))
            for agent in team.get("agents", []):
                status_bucket = agent.get("status_display") or agent.get("status", "idle")
                card = Card(agent.get("display_name", "unknown"), f"{agent.get('status', 'idle')} / {agent.get('progress_percent', 0)}%")
                card_layout = card.layout()
                assert card_layout is not None
                card_layout.addWidget(QLabel(f"role: {agent.get('role', '')}"))
                card_layout.addWidget(QLabel(f"team: {agent.get('team_name', team.get('name', ''))}"))
                card_layout.addWidget(QLabel(f"status: {agent.get('status', '')}"))
                progress = QProgressBar()
                progress.setRange(0, 100)
                progress.setValue(int(agent.get("progress_percent", 0) or 0))
                card_layout.addWidget(progress)
                card_layout.addWidget(
                    QLabel(
                        " / ".join(
                            [
                                f"total {agent.get('total_tasks', 0)}",
                                f"completed {agent.get('completed_tasks', 0)}",
                                f"warning {agent.get('warning_count', 0)}",
                                f"error {agent.get('error_count', 0)}",
                            ]
                        )
                    )
                )
                card_layout.addWidget(QLabel(f"last_message: {agent.get('last_message', '')}"))
                card_layout.addWidget(QLabel(f"updated_at: {agent.get('updated_at', '')}"))
                if agent.get("role") == "safety-director" or agent.get("role") == "privacy-guard" or agent.get("role") == "no-submit-reviewer" or agent.get("role") == "pii-auditor" or agent.get("role") == "external-action-reviewer" or agent.get("role") == "release-gatekeeper":
                    card_layout.addWidget(QLabel("自動送信なし"))
                    card_layout.addWidget(QLabel("profile.enc 未読込"))
                    card_layout.addWidget(QLabel("PIIログなし"))
                    card_layout.addWidget(QLabel("X操作自動化なし"))
                if agent.get("warning_count", 0) or status_bucket == "warning":
                    card.setProperty("class", "agent-warning")
                elif agent.get("error_count", 0) or status_bucket == "error":
                    card.setProperty("class", "agent-error")
                team_layout.addWidget(card)
            container_layout.addWidget(team_card)

        container_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll)
