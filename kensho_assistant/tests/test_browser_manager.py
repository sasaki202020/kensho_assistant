from pathlib import Path

from kensho_assistant.app.browser_manager import check_browser_doctor, get_browser_profile_dir


def test_browser_profile_uses_dedicated_dir():
    path = get_browser_profile_dir()
    assert isinstance(path, Path)
    assert "browser_profile" in path.parts
    assert path.name == "chrome_user_data"


def test_browser_doctor_has_expected_shape():
    result = check_browser_doctor()
    assert set(result) == {
        "playwright",
        "chrome_channel",
        "dedicated_profile",
        "headed_launch",
        "keep_open_supported",
        "fallback_browser",
    }
