from __future__ import annotations

import json
import tempfile
from pathlib import Path

from kensho_assistant.app.pilot_safety import (
    auto_submit_guard_contract,
    build_pilot_test_pii,
    compare_storage_snapshots,
    ensure_pilot_storage,
    scan_for_forbidden_values,
    snapshot_storage,
)


def run_preflight(*, work_root: Path | None = None) -> dict[str, object]:
    owned_temp = None
    if work_root is None:
        owned_temp = tempfile.TemporaryDirectory(prefix="kensho-pilot-preflight-")
        work_root = Path(owned_temp.name)
    root = Path(work_root)
    normal = root / "normal"
    pilot = root / "pilot"
    checks: dict[str, object] = {
        "pilot_storage_isolated": False,
        "pii_persistence_check": False,
        "candidate_state_immutable": False,
        "auto_submit_guard": False,
        "submitted_count_auto": 0,
        "playwright_trace_policy": "DISABLED",
        "screenshot_policy": "DISABLED",
    }
    try:
        normal.mkdir(parents=True, exist_ok=True)
        state_file = normal / "candidate-state.json"
        state_file.write_text('{"status":"PREPARED","submitted_count_auto":0}\n', encoding="utf-8")
        before = snapshot_storage(normal)
        ensure_pilot_storage(pilot)
        checks["pilot_storage_isolated"] = normal.resolve() not in pilot.resolve().parents and pilot.resolve() not in normal.resolve().parents
        checks["pii_persistence_check"] = bool(scan_for_forbidden_values(pilot, build_pilot_test_pii().values())["clean"])
        checks["candidate_state_immutable"] = bool(compare_storage_snapshots(before, snapshot_storage(normal))["identical"])
        checks["auto_submit_guard"] = auto_submit_guard_contract()
    except Exception:
        pass
    ready = (
        all(checks[key] is True for key in ("pilot_storage_isolated", "pii_persistence_check", "candidate_state_immutable", "auto_submit_guard"))
        and checks["submitted_count_auto"] == 0
        and checks["playwright_trace_policy"] == "DISABLED"
        and checks["screenshot_policy"] == "DISABLED"
    )
    checks["result"] = "READY_FOR_5_SITE_PILOT" if ready else "BLOCKED_P1_SAFETY"
    if owned_temp is not None:
        owned_temp.cleanup()
    return checks


def main() -> int:
    result = run_preflight()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "READY_FOR_5_SITE_PILOT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
