import os

import pytest
from kensho_assistant.ui.data_loader import AppSnapshot

try:
    from PySide6.QtWidgets import QApplication
except ModuleNotFoundError:  # pragma: no cover - optional desktop dependency
    QApplication = None


@pytest.fixture(scope="session")
def qt_app():
    if QApplication is None:
        pytest.skip("PySide6 is not installed")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


@pytest.fixture
def qt_snapshot():
    return AppSnapshot(
        release_report={"submitted_count": 0, "release_status": "OK"},
        campaigns=[],
        apply_queue=[],
        inspections={
            "abc": {
                "readiness_status": "REVIEW_ONLY",
                "readiness_score": 0.8,
                "detected_fields": [],
            }
        },
        activity=[],
        profile_preview={
            "name": "山田 **",
            "postal_code": "100-****",
            "email": "ke***@example.com",
            "phone": "090-****-0000",
        },
    )
