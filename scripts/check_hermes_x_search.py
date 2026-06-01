from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kensho_assistant.app.research.hermes_x_search import run_x_research_harness_check


def main(argv: list[str] | None = None) -> int:
    del argv
    report = run_x_research_harness_check()
    print("### Hermes X Search Check")
    print(f"status: {report['status']}")
    print(f"reason: {report['reason']}")
    print(f"output_file: {report['output_file']}")
    print(f"next_action: {report['next_action']}")
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
