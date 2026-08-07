from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class XPostAssistantPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.repo_root = Path(__file__).resolve().parents[2]
        self.launch_script = self.repo_root / "scripts" / "windows" / "x_post_assistant.ps1"
        self.install_script = self.repo_root / "scripts" / "windows" / "install_x_post_assistant_shortcut.ps1"

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("X投稿アシスタント"))
        layout.addWidget(QLabel("1. クリップボードの文を使うか、その場で投稿文を入力します。"))
        layout.addWidget(QLabel("2. dry-run で payload と警告だけを確認します。"))
        layout.addWidget(QLabel("3. 本番投稿はしません。送信ボタンもありません。"))
        layout.addWidget(QLabel("長さ、URL数、ハッシュタグ数、重複だけを見ます。"))

        open_button = QPushButton("安全な下書きを開く")
        open_button.clicked.connect(self.open_assistant)
        layout.addWidget(open_button)

        install_button = QPushButton("ショートカットを作成/更新")
        install_button.clicked.connect(self.install_shortcut)
        layout.addWidget(install_button)

        self.status = QLabel("デスクトップのショートカットからも同じ dry-run を開けます。")
        layout.addWidget(self.status)
        layout.addStretch(1)

    def open_assistant(self) -> None:
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.launch_script)],
                cwd=self.repo_root,
            )
            self.status.setText("安全な下書きスクリプトを起動しました。")
        except Exception as exc:  # pragma: no cover - UI safety
            self.status.setText(f"起動に失敗しました: {exc}")

    def install_shortcut(self) -> None:
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.install_script)],
                cwd=self.repo_root,
            )
            self.status.setText("ショートカット作成スクリプトを起動しました。")
        except Exception as exc:  # pragma: no cover - UI safety
            self.status.setText(f"作成に失敗しました: {exc}")
