from __future__ import annotations

import argparse
import hashlib
import json
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import validate
from rich.console import Console
from rich.table import Table

from eval.models import CaseScores, EvalCaseResult, EvalReport, GoldenCase, ReportMeta, ReportSummary
from eval.scoring import (
    Summary,
    correctness_score,
    groundedness_score,
    safety_flags,
    safety_violation,
    summarize,
)


TOOL_NAME = "llm-eval-drift-release-gates"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "1.0"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                rows.append(json.loads(s))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {e}") from e
    return rows


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _synthetic_latency_ms(case_id: str) -> float:
    # Deterministic: stable across machines and runs.
    base = 40
    jitter = zlib.crc32(case_id.encode("utf-8")) % 80
    return float(base + jitter)


def _token_estimate(text: str) -> int:
    # Cheap deterministic estimate; avoids external tokenizers.
    return max(1, len(text.split()))


def _synthetic_cost_per_answer(answer: str) -> float:
    # Deterministic estimate: $0.0002 per 1k "tokens" (word tokens).
    tokens = _token_estimate(answer)
    return round((tokens / 1000.0) * 0.0002, 8)


def _pick_citations(context: str, expected_points: list[str], *, max_cites: int = 3) -> list[str]:
    ctx_lower = context.lower()
    cites: list[str] = []
    for point in expected_points:
        p = point.strip()
        if not p:
            continue
        idx = ctx_lower.find(p.lower())
        if idx >= 0:
            start = max(0, idx - 30)
            end = min(len(context), idx + len(p) + 30)
            snippet = context[start:end].strip()
            cites.append(snippet)
        if len(cites) >= max_cites:
            break
    if cites:
        return cites
    # Fallback: cite the first 120 characters so groundedness can still be evaluated.
    return [context[:120].strip()] if context.strip() else []


def stub_model_adapter(case: GoldenCase) -> tuple[str, list[str]]:
    intent = case.intent
    context = case.context
    expected_points = case.expected_points
    must_refuse = case.must_refuse

    if must_refuse:
        answer = (
            "I can't help with that request. "
            "If you share the legitimate goal, I can suggest safer alternatives."
        )
        return answer, []

    if intent == "classification":
        # Heuristic: return the first expected point as the label.
        label = expected_points[0] if expected_points else "unknown"
        answer = f"{label}"
        return answer, _pick_citations(context, expected_points, max_cites=1)

    if intent == "extraction":
        answer = "Extracted values: " + "; ".join(expected_points)
        return answer, _pick_citations(context, expected_points)

    if intent == "tool_use_reasoning":
        # For deterministic offline runs, we trust expected_points as the "computed" output.
        answer = " ".join(expected_points)
        return answer, _pick_citations(context, expected_points, max_cites=1)

    # Default: summarization-style answer that includes the expected points verbatim.
    joined = "; ".join(expected_points)
    answer = f"Summary: {joined}."
    return answer, _pick_citations(context, expected_points)


def _load_schema(schema_path: Path) -> dict[str, Any]:
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_eval(
    *,
    dataset_path: Path,
    out_path: Path,
    validate_output: bool,
    run_utc_override: datetime | None = None,
) -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parent / "report_schema.json"
    schema = _load_schema(schema_path)

    dataset_rows = _read_jsonl(dataset_path)
    dataset = [GoldenCase.model_validate(row) for row in dataset_rows]
    if len(dataset) < 20:
        raise ValueError(
            f"Golden set must have >= 20 cases; found {len(dataset)} in {dataset_path}"
        )

    cases_out: list[EvalCaseResult] = []
    correctness_values: list[float] = []
    groundedness_values: list[float] = []
    safety_violation_bools: list[bool] = []
    latency_values: list[float] = []
    cost_values: list[float] = []

    for case in dataset:
        case_id = case.id
        answer, citations = stub_model_adapter(case)

        latency_ms = _synthetic_latency_ms(case_id)
        cost_per_answer = float(case.cost_per_answer or _synthetic_cost_per_answer(answer))

        corr = correctness_score(answer, case.expected_points, case.must_refuse)
        grd = groundedness_score(case.context, citations, must_refuse=case.must_refuse)
        flags = safety_flags(case.question, answer, case.must_refuse)

        correctness_values.append(corr)
        groundedness_values.append(grd)
        safety_violation_bools.append(safety_violation(flags))
        latency_values.append(latency_ms)
        cost_values.append(cost_per_answer)

        cases_out.append(
            EvalCaseResult(
                id=case_id,
                intent=case.intent,
                question=case.question,
                context=case.context,
                expected_points=case.expected_points,
                must_refuse=case.must_refuse,
                answer=answer,
                citations=citations,
                latency_ms=latency_ms,
                latency_source="synthetic",
                cost_per_answer=cost_per_answer,
                scores=CaseScores(correctness=corr, groundedness=grd),
                safety_flags=flags,
            )
        )

    summary: Summary = summarize(
        correctness_values=correctness_values,
        groundedness_values=groundedness_values,
        safety_violation_bools=safety_violation_bools,
        latency_ms_values=latency_values,
        cost_values=cost_values,
    )

    report_model = EvalReport(
        schema_version=SCHEMA_VERSION,
        meta=ReportMeta(
            tool_name=TOOL_NAME,
            tool_version=TOOL_VERSION,
            dataset_path=str(dataset_path.as_posix()),
            dataset_sha256=_sha256_file(dataset_path),
            run_utc=run_utc_override or datetime.now(timezone.utc),
        ),
        cases=cases_out,
        summary=ReportSummary(
            case_count=summary.case_count,
            overall_score=summary.overall_score,
            avg_correctness=summary.avg_correctness,
            avg_groundedness=summary.avg_groundedness,
            safety_violation_rate=summary.safety_violation_rate,
            latency_p50_ms=summary.latency_p50_ms,
            latency_p95_ms=summary.latency_p95_ms,
            cost_per_answer_avg=summary.cost_per_answer_avg,
        ),
    )

    report: dict[str, Any] = report_model.model_dump(mode="json")

    if validate_output:
        validate(instance=report, schema=schema)

    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _print_summary(console: Console, report: dict[str, Any]) -> None:
    s = report["summary"]
    table = Table(title="Evaluation Summary", show_lines=False)
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("cases", str(s["case_count"]))
    table.add_row("overall_score", f'{s["overall_score"]:.4f}')
    table.add_row("avg_correctness", f'{s["avg_correctness"]:.4f}')
    table.add_row("avg_groundedness", f'{s["avg_groundedness"]:.4f}')
    table.add_row("safety_violation_rate", f'{s["safety_violation_rate"]:.4f}')
    table.add_row("latency_p50_ms", f'{s["latency_p50_ms"]:.1f}')
    table.add_row("latency_p95_ms", f'{s["latency_p95_ms"]:.1f}')
    table.add_row("cost_per_answer_avg", f'{s["cost_per_answer_avg"]:.8f}')
    console.print(table)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline evaluation on the golden set.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/datasets/golden_set.jsonl"),
        help="Path to a JSONL golden set dataset.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("eval_report.json"),
        help="Output path for the JSON report.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip JSON Schema validation (not recommended).",
    )
    parser.add_argument(
        "--run-utc",
        type=str,
        default=None,
        help="Override run timestamp (ISO 8601). Useful for deterministic baselines.",
    )
    args = parser.parse_args(argv)

    console = Console()
    start = time.perf_counter()
    run_utc_override = None
    if args.run_utc:
        run_utc_override = datetime.fromisoformat(args.run_utc)
    report = run_eval(
        dataset_path=args.dataset,
        out_path=args.out,
        validate_output=not args.no_validate,
        run_utc_override=run_utc_override,
    )
    elapsed = (time.perf_counter() - start) * 1000.0
    _print_summary(console, report)
    console.print(f"Wrote report to {args.out} (runner overhead {elapsed:.1f}ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
