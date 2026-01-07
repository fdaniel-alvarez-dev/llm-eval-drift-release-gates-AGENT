from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_regression(baseline_score: float, current_score: float) -> float:
    if baseline_score <= 0:
        return 0.0
    return (baseline_score - current_score) / baseline_score


def gate_passes(
    *,
    baseline_report: dict[str, Any],
    daily_report: dict[str, Any],
    max_regression: float,
) -> tuple[bool, dict[str, Any]]:
    b = float(baseline_report["summary"]["overall_score"])
    d = float(daily_report["summary"]["overall_score"])
    regression = relative_regression(b, d)

    passed = regression <= max_regression
    detail = {
        "baseline_overall_score": b,
        "daily_overall_score": d,
        "relative_regression": regression,
        "max_regression": max_regression,
        "passed": passed,
    }
    return passed, detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if overall_score regresses beyond the threshold."
    )
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline eval report JSON path.")
    parser.add_argument("--daily", type=Path, required=True, help="Daily eval report JSON path.")
    parser.add_argument(
        "--max-regression",
        type=float,
        default=0.03,
        help="Maximum allowed relative regression (default: 0.03 = 3%%).",
    )
    args = parser.parse_args(argv)

    passed, detail = gate_passes(
        baseline_report=_load(args.baseline),
        daily_report=_load(args.daily),
        max_regression=args.max_regression,
    )

    print(json.dumps(detail, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

