from __future__ import annotations

import argparse
import subprocess

from kensho_assistant import main as cli
from kensho_assistant.app.harness.task_models import HarnessRunResult
from kensho_assistant.app.harness.safety_rules import sanitize_output


def test_isolated_harness_terminates_process_tree_on_timeout(monkeypatch) -> None:
    class FakeProcess:
        pid = 1234
        returncode = 1

        def __init__(self) -> None:
            self.calls = 0

        def communicate(self, timeout=None):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(cmd="harness", timeout=timeout)
            return ("", "")

        def poll(self):  # noqa: ANN201
            return None

    process = FakeProcess()
    terminated = []
    popen_calls = []

    def fake_popen(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        popen_calls.append((args, kwargs))
        return process

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli, "_terminate_process_tree", lambda target: terminated.append(target.pid))
    monkeypatch.setattr(
        cli,
        "write_harness_timeout",
        lambda **kwargs: HarnessRunResult(output_dir="C:/tmp/timeout", status="TIMEOUT"),
    )
    args = argparse.Namespace(
        campaign_id="",
        later_id="later-timeout",
        mode="dry_run",
        keep_open=False,
        output_root="",
        timeout_sec=60,
    )

    assert cli._run_harness_isolated(args) == 1
    assert terminated == [1234]
    assert popen_calls[0][1]["env"]["PYTHONIOENCODING"] == "utf-8"
    assert popen_calls[0][1]["env"]["PYTHONUTF8"] == "1"


def test_sanitize_output_preserves_operational_ids_and_urls() -> None:
    payload = sanitize_output(
        {
            "later_id": "later-7f3995779c80",
            "campaign_id": "later-7f3995779c80",
            "url": "https://example.com/campaign/09012345678",
            "note": "連絡先 090-1234-5678",
        }
    )

    assert payload["later_id"] == "later-7f3995779c80"
    assert payload["campaign_id"] == "later-7f3995779c80"
    assert payload["url"] == "https://example.com/campaign/09012345678"
    assert "090-1234-5678" not in payload["note"]


def test_sanitize_output_preserves_operational_id_in_free_text() -> None:
    assert sanitize_output("run later-7f3995779c80") == "run later-7f3995779c80"
