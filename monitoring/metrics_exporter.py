from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric_lines(report: dict[str, Any], *, prefix: str = "llm_eval_") -> list[str]:
    s = report["summary"]
    return [
        f"# HELP {prefix}overall_score Overall evaluation score (0..1).",
        f"# TYPE {prefix}overall_score gauge",
        f"{prefix}overall_score {s['overall_score']}",
        f"# HELP {prefix}avg_correctness Average correctness (0..1).",
        f"# TYPE {prefix}avg_correctness gauge",
        f"{prefix}avg_correctness {s['avg_correctness']}",
        f"# HELP {prefix}avg_groundedness Average groundedness (0..1).",
        f"# TYPE {prefix}avg_groundedness gauge",
        f"{prefix}avg_groundedness {s['avg_groundedness']}",
        f"# HELP {prefix}safety_violation_rate Fraction of cases with a safety violation (0..1).",
        f"# TYPE {prefix}safety_violation_rate gauge",
        f"{prefix}safety_violation_rate {s['safety_violation_rate']}",
        f"# HELP {prefix}latency_p50_ms P50 latency in milliseconds.",
        f"# TYPE {prefix}latency_p50_ms gauge",
        f"{prefix}latency_p50_ms {s['latency_p50_ms']}",
        f"# HELP {prefix}latency_p95_ms P95 latency in milliseconds.",
        f"# TYPE {prefix}latency_p95_ms gauge",
        f"{prefix}latency_p95_ms {s['latency_p95_ms']}",
        f"# HELP {prefix}cost_per_answer_avg Average cost per answer in dollars.",
        f"# TYPE {prefix}cost_per_answer_avg gauge",
        f"{prefix}cost_per_answer_avg {s['cost_per_answer_avg']}",
    ]


def _delta_lines(
    baseline: dict[str, Any],
    daily: dict[str, Any],
    *,
    prefix: str = "llm_eval_",
) -> list[str]:
    b = baseline["summary"]
    d = daily["summary"]
    pairs = [
        ("overall_score", b["overall_score"], d["overall_score"]),
        ("avg_correctness", b["avg_correctness"], d["avg_correctness"]),
        ("avg_groundedness", b["avg_groundedness"], d["avg_groundedness"]),
        ("safety_violation_rate", b["safety_violation_rate"], d["safety_violation_rate"]),
        ("latency_p50_ms", b["latency_p50_ms"], d["latency_p50_ms"]),
        ("latency_p95_ms", b["latency_p95_ms"], d["latency_p95_ms"]),
        ("cost_per_answer_avg", b["cost_per_answer_avg"], d["cost_per_answer_avg"]),
    ]

    lines = [
        f"# HELP {prefix}drift_delta Difference between daily and baseline for key metrics.",
        f"# TYPE {prefix}drift_delta gauge",
    ]
    for name, bv, dv in pairs:
        delta = float(dv) - float(bv)
        lines.append(f'{prefix}drift_delta{{metric="{name}"}} {delta}')
    return lines


def export_metrics(
    *,
    report: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
    daily: dict[str, Any] | None = None,
) -> str:
    if report is None and (baseline is None or daily is None):
        raise ValueError("Provide either report=... or both baseline=... and daily=....")

    if report is not None:
        lines = _metric_lines(report)
        return "\n".join(lines) + "\n"

    lines = []
    lines.extend(_metric_lines(daily))  # expose current values by default
    lines.append("")
    lines.extend(_delta_lines(baseline, daily))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Prometheus-style metrics from an eval report.")
    parser.add_argument("--report", type=Path, help="Eval report JSON path.")
    parser.add_argument("--baseline", type=Path, help="Baseline eval report JSON path.")
    parser.add_argument("--daily", type=Path, help="Daily eval report JSON path.")
    parser.add_argument("--out", type=Path, default=Path("metrics.prom"), help="Output text file path.")
    args = parser.parse_args(argv)

    if args.report:
        text = export_metrics(report=_load(args.report))
    else:
        if not args.baseline or not args.daily:
            raise SystemExit("Provide either --report or both --baseline and --daily.")
        text = export_metrics(baseline=_load(args.baseline), daily=_load(args.daily))

    args.out.write_text(text, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

