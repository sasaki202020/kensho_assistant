from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..app.version import APP_VERSION
from ..app.entry_history import load_entry_history, summarize_entry_history
from .data_loader import AppSnapshot, SAFE_CLI_ACTIONS, summarize_campaigns, load_auto_scan_report
from .widgets import Card


class DashboardPage(QWidget):
    def __init__(self, snapshot: AppSnapshot) -> None:
        super().__init__()
        report = snapshot.release_report
        layout = QVBoxLayout(self)
        banner = QLabel(f"このアプリは {APP_VERSION} です / 本番送信は人間確認が必要です")
        banner.setObjectName("title")
        layout.addWidget(banner)
        layout.addWidget(QLabel("対象サイト：懸賞生活 https://www.knshow.com/"))
        layout.addWidget(QLabel("懸賞生活の公式ツールではありません"))
        layout.addWidget(QLabel("このアプリは応募を自動送信しません。個人情報はローカルで暗号化保存されます。"))

        grid = QGridLayout()
        cards = [
            ("収集件数", str(report.get("collected_count", 0))),
            ("解析済み", str(report.get("analyzed_count", 0))),
            ("URL解決済み", str(report.get("resolved_count", 0))),
            ("REVIEW_ONLY", str(report.get("review_only_count", 0))),
            ("READY_FOR_FILL", str(report.get("ready_for_fill_count", 0))),
            ("Submitted", str(report.get("submitted_count", 0))),
        ]
        for index, (title, value) in enumerate(cards):
            grid.addWidget(Card(title, value), index // 3, index % 3)
        layout.addLayout(grid)

        entry_summary = summarize_entry_history(load_entry_history())
        history_grid = QGridLayout()
        history_cards = [
            ("今日締切", str(entry_summary.get("today_deadline", 0))),
            ("今週締切", str(entry_summary.get("week_deadline", 0))),
            ("応募済み数", str(entry_summary.get("applied", 0))),
            ("当選確認待ち", str(entry_summary.get("result_pending", 0))),
            ("メルマガ解除候補", str(entry_summary.get("newsletter_unsubscribe_needed", 0))),
            ("重複候補", str(entry_summary.get("duplicate_candidates", 0))),
        ]
        for index, (title, value) in enumerate(history_cards):
            history_grid.addWidget(Card(title, value), index // 3, index % 3)
        layout.addWidget(QLabel("応募履歴"))
        layout.addLayout(history_grid)

        modes = QFrame()
        modes.setObjectName("card")
        mode_layout = QVBoxLayout(modes)
        mode_layout.addWidget(QLabel("動作モード"))
        auto_scan = load_auto_scan_report()
        mode_layout.addWidget(QLabel("自動スキャン：有効"))
        mode_layout.addWidget(QLabel("自動応募送信：無効"))
        mode_layout.addWidget(QLabel("個人情報入力：人間確認時のみ"))
        mode_layout.addWidget(QLabel("本番送信：手動確認が必要"))
        mode_layout.addWidget(QLabel("最終送信は人間確認が必要です"))
        if auto_scan:
            mode_layout.addWidget(QLabel(f"自動スキャン結果: submitted_count={auto_scan.get('submitted_count', 0)} / warning={auto_scan.get('warning', 'OK')}"))
        layout.addWidget(modes)

        actions = QFrame()
        actions.setObjectName("card")
        action_layout = QHBoxLayout(actions)
        for label in ("収集", "解析", "URL解決", "フォーム診断", "review", "release-report"):
            button = QPushButton(label)
            button.setToolTip("安全なCLI操作のみ")
            button.setProperty("safe_command", label)
            action_layout.addWidget(button)
        layout.addWidget(actions)

        activity = QLabel("最近のアクティビティ: " + (" / ".join(snapshot.activity) if snapshot.activity else "未取得"))
        layout.addWidget(activity)
        summary = summarize_campaigns()
        if auto_scan:
            today = auto_scan.get("today_candidates", {})
            layout.addWidget(
                QLabel(
                    "今日見るべき候補: "
                    f"REVIEW_ONLY {len(today.get('review_only', []))}件 / "
                    f"締切間近 {len(today.get('due_soon', []))}件 / "
                    f"Webフォーム {len(today.get('web_form', []))}件"
                )
            )
        else:
            layout.addWidget(
                QLabel(
                    "今日見るべき候補: "
                    f"REVIEW_ONLY {summary.get('review_only', 0)}件 / "
                    f"READY_FOR_FILL {summary.get('ready_for_fill', 0)}件"
                )
            )
        checklist = QLabel(
            "セーフティチェック: profile.enc / ログ秘匿 / 送信停止 / スクリーンショットOFF / release_status "
            + str(report.get("release_status", "未取得"))
        )
        layout.addWidget(checklist)
