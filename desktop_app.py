from __future__ import annotations

import argparse
import os
import sys

from .ui.data_loader import load_app_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="desktop_app.py", description="Kensho desktop UI")
    parser.add_argument("--smoke-test", action="store_true", help="initialize UI without showing a window")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from .ui.main_window import MainWindow
    except ModuleNotFoundError as exc:
        raise SystemExit("PySide6 is required for desktop_app.py") from exc
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = MainWindow(load_app_snapshot())
    if args.smoke_test:
        assert window.send_button.isEnabled() is False
        return 0
    window.show()
    return app.exec()
