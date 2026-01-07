from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from rich.table import Table


CauseBucket = Literal["retrieval", "prompt", "data", "model", "infra"]


KEY_METRICS = [
    "overall_score",
    "avg_correctness",
    "avg_groundedness",
    "safety_violation_rate",
    "latency_p50_ms",
    "latency_p95_ms",
    "cost_per_answer_avg",
]


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rel_delta(baseline: float, current: float) -> float:
    if baseline == 0:
        return 0.0 if current == 0 else 1.0
    return (current - baseline) / baseline


@dataclass(frozen=True)
class DriftMetric:
    name: str
    baseline: float
    current: float
    absolute_delta: float
    relative_delta: float
    drifted: bool
    direction: Literal["up", "down", "flat"]


def compare_summaries(
    baseline_report: dict[str, Any],
    daily_report: dict[str, Any],
    *,
    regression_threshold: float = 0.03,
) -> list[DriftMetric]:
    b = baseline_report["summary"]
    d = daily_report["summary"]

    metrics: list[DriftMetric] = []
    for name in KEY_METRICS:
        bv = float(b[name])
        dv = float(d[name])
        abs_delta = dv - bv
        rel_delta = _rel_delta(bv, dv)
        direction: Literal["up", "down", "flat"]
        if abs_delta > 0:
            direction = "up"
        elif abs_delta < 0:
            direction = "down"
        else:
            direction = "flat"

        drifted = False
        if name in {"overall_score", "avg_correctness", "avg_groundedness"}:
            drifted = rel_delta < -regression_threshold
        elif name == "safety_violation_rate":
            drifted = abs_delta > 0.0
        elif name.startswith("latency_"):
            drifted = rel_delta > regression_threshold
        elif name == "cost_per_answer_avg":
            drifted = rel_delta > regression_threshold

        metrics.append(
            DriftMetric(
                name=name,
                baseline=bv,
                current=dv,
                absolute_delta=abs_delta,
                relative_delta=rel_delta,
                drifted=drifted,
                direction=direction,
            )
        )

    metrics.sort(key=lambda m: (not m.drifted, m.name))
    return metrics


def likely_causes(metrics: list[DriftMetric]) -> list[CauseBucket]:
    # Score buckets based on which metrics drifted.
    scores: dict[CauseBucket, float] = {
        "retrieval": 0.0,
        "prompt": 0.0,
        "data": 0.0,
        "model": 0.0,
        "infra": 0.0,
    }

    def m(name: str) -> DriftMetric | None:
        for dm in metrics:
            if dm.name == name:
                return dm
        return None

    grd = m("avg_groundedness")
    corr = m("avg_correctness")
    lat95 = m("latency_p95_ms")
    cost = m("cost_per_answer_avg")
    safety = m("safety_violation_rate")

    if grd and grd.drifted and (not corr or not corr.drifted):
        scores["retrieval"] += 2.0
        scores["prompt"] += 1.0
    if corr and corr.drifted:
        scores["prompt"] += 2.0
        scores["model"] += 1.5
        scores["data"] += 1.0
    if safety and safety.drifted:
        scores["prompt"] += 2.0
        scores["model"] += 1.5
        scores["data"] += 0.5
    if lat95 and lat95.drifted:
        scores["infra"] += 2.5
        scores["retrieval"] += 0.5
    if cost and cost.drifted:
        scores["model"] += 1.5
        scores["prompt"] += 0.5

    order: list[CauseBucket] = ["retrieval", "prompt", "data", "model", "infra"]
    ranked = sorted(order, key=lambda k: (-scores[k], order.index(k)))
    # Always return all buckets, but put the most likely first.
    return ranked


def recommended_next_steps(metrics: list[DriftMetric]) -> list[str]:
    drifted_names = {m.name for m in metrics if m.drifted}
    steps: list[str] = []

    if "safety_violation_rate" in drifted_names:
        steps.append("Treat as a hard stop: block rollout and investigate safety regressions first.")
        steps.append("Review must_refuse cases and compare answer text between baseline and daily.")
        steps.append("Check for prompt or routing changes that weakened refusal behavior.")

    if "avg_groundedness" in drifted_names:
        steps.append("Inspect citations: verify they still match the provided context verbatim.")
        steps.append("If retrieval changed, confirm document selection and citation formatting.")

    if "avg_correctness" in drifted_names or "overall_score" in drifted_names:
        steps.append("Diff top regressed cases by id; confirm whether expected_points changed meaningfully.")
        steps.append("Review recent prompt changes and model adapter changes side-by-side.")

    if any(n.startswith("latency_") for n in drifted_names):
        steps.append("Check runtime regressions: timeouts, retries, cold starts, or dependency latency.")

    if "cost_per_answer_avg" in drifted_names:
        steps.append("Confirm cost inputs and token/length behavior; large prompts or verbose answers can inflate cost.")

    if not steps:
        steps.append("No material drift detected; keep monitoring and run the next scheduled eval.")

    # Keep it short and stable.
    return steps[:7]


def detect_drift(
    baseline_report: dict[str, Any],
    daily_report: dict[str, Any],
    *,
    regression_threshold: float = 0.03,
) -> dict[str, Any]:
    metrics = compare_summaries(
        baseline_report,
        daily_report,
        regression_threshold=regression_threshold,
    )
    drifted = [m for m in metrics if m.drifted]
    causes = likely_causes(metrics)
    steps = recommended_next_steps(metrics)
    plan = {
        "regression_threshold": regression_threshold,
        "drift_detected": bool(drifted),
        "drifted_metrics": [
            {
                "name": m.name,
                "baseline": m.baseline,
                "current": m.current,
                "absolute_delta": m.absolute_delta,
                "relative_delta": m.relative_delta,
                "direction": m.direction,
            }
            for m in drifted
        ],
        "likely_cause_buckets_ranked": causes,
        "recommended_next_steps": steps,
    }
    return plan


def render_markdown(plan: dict[str, Any], *, baseline_path: str, daily_path: str) -> str:
    lines: list[str] = []
    lines.append("# Drift report")
    lines.append("")
    lines.append(f"- Baseline: `{baseline_path}`")
    lines.append(f"- Daily: `{daily_path}`")
    lines.append(f"- Regression threshold: {plan['regression_threshold']:.2%}")
    lines.append(f"- Drift detected: **{str(plan['drift_detected']).lower()}**")
    lines.append("")

    if plan["drifted_metrics"]:
        lines.append("## Drifted metrics")
        lines.append("")
        lines.append("| metric | baseline | current | abs delta | rel delta |")
        lines.append("|---|---:|---:|---:|---:|")
        for m in plan["drifted_metrics"]:
            lines.append(
                f"| {m['name']} | {m['baseline']:.6g} | {m['current']:.6g} | {m['absolute_delta']:.6g} | {m['relative_delta']:.2%} |"
            )
        lines.append("")
    else:
        lines.append("## Drifted metrics")
        lines.append("")
        lines.append("No metrics exceeded thresholds.")
        lines.append("")

    lines.append("## Likely causes (ranked)")
    lines.append("")
    for bucket in plan["likely_cause_buckets_ranked"][:5]:
        lines.append(f"- {bucket}")
    lines.append("")

    lines.append("## Recommended next steps")
    lines.append("")
    for step in plan["recommended_next_steps"]:
        lines.append(f"- {step}")
    lines.append("")

    return "\n".join(lines)


def _print_console(
    console: Console,
    plan: dict[str, Any],
    *,
    baseline_report: dict[str, Any],
    daily_report: dict[str, Any],
) -> None:
    table = Table(title="Drift detector", show_lines=False)
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Rel delta", justify="right")
    table.add_column("Drifted", justify="right")

    drifted = {m["name"] for m in plan["drifted_metrics"]}
    b = baseline_report["summary"]
    d = daily_report["summary"]
    for name in KEY_METRICS:
        bv = float(b[name])
        dv = float(d[name])
        rel = _rel_delta(bv, dv)
        table.add_row(
            name,
            f"{bv:.6g}",
            f"{dv:.6g}",
            f"{rel:.2%}",
            "yes" if name in drifted else "no",
        )

    console.print(table)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare baseline vs daily evaluation reports and detect drift.")
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline eval report JSON path.")
    parser.add_argument("--daily", type=Path, required=True, help="Daily eval report JSON path.")
    parser.add_argument("--out-json", type=Path, default=Path("drift_report.json"), help="Output JSON plan path.")
    parser.add_argument("--out-md", type=Path, default=Path("drift_report.md"), help="Output Markdown summary path.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.03,
        help="Relative threshold for regressions or increases (default: 0.03 = 3%%).",
    )
    args = parser.parse_args(argv)

    baseline = load_report(args.baseline)
    daily = load_report(args.daily)
    plan = detect_drift(baseline, daily, regression_threshold=args.threshold)

    args.out_json.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = render_markdown(plan, baseline_path=str(args.baseline), daily_path=str(args.daily))
    args.out_md.write_text(md, encoding="utf-8")

    console = Console()
    _print_console(console, plan, baseline_report=baseline, daily_report=daily)
    console.print(f"Wrote {args.out_json} and {args.out_md}")

    return 1 if plan["drift_detected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
