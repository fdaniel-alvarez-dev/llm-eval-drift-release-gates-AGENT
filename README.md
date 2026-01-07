# llm-eval-drift-release-gates

Stability is a feature. LLM behavior changes over time: prompts evolve, retrieval changes, models are swapped, and infrastructure drifts. This repo is a small, offline-first evaluation toolkit meant to make those changes visible and enforceable.

It runs a deterministic evaluation against a golden dataset, emits a strict JSON report, compares reports to detect drift, exports Prometheus-style metrics, and provides a GitHub Actions “release gate” that blocks merges on regressions.

## Quickstart (local, offline)

Requirements: Python 3.11.

```bash
cd llm-eval-drift-release-gates
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run an evaluation (writes `eval_report.json` in the repo root by default):

```bash
python -m eval.runner
```

Detect drift (baseline vs daily) and write both JSON and Markdown summaries:

```bash
python -m monitoring.drift_detector --baseline baseline_eval_report.json --daily eval_report.json --out-json drift_report.json --out-md drift_report.md
```

Export Prometheus text metrics from a report:

```bash
python -m monitoring.metrics_exporter --report eval_report.json --out metrics.prom
```

Export metrics plus drift deltas:

```bash
python -m monitoring.metrics_exporter --baseline baseline_eval_report.json --daily eval_report.json --out metrics.prom
```

## What the report means

The report is designed for automation:

- Every run is validated against `eval/report_schema.json`.
- The runner produces per-case results (answer, citations, latency, cost), plus aggregated metrics.
- `overall_score` is a single number for release gating; it is deliberately simple so it stays stable.

### Drift interpretation examples

- **Groundedness drops** while correctness stays flat: citations no longer match context; likely retrieval changes, citation formatting drift, or prompt changes that stopped quoting context.
- **Correctness drops** while groundedness stays flat: model behavior or prompting changed; verify expected points vs answer content.
- **Safety violation rate increases**: prompt, routing, or dataset changes; treat as a “hard stop” before rollout.
- **Latency p95 increases**: infrastructure/regression in runtime; treat as canary “stop” if sustained.

## Release gating (CI)

This repo includes a GitHub Actions workflow that:

1. runs evaluation on the golden set
2. compares the run to a committed baseline report
3. fails the workflow if `overall_score` regresses by more than 3%

The workflow file lives at `.github/workflows/eval_gate.yml` and a copy is kept at `integrations/github_actions/eval_gate.yml`.

Baseline process (recommended):

- On `main`, commit `baseline_eval_report.json`.
- When you intentionally accept a behavior change, regenerate the baseline in a dedicated PR and document why.

Trade-off:

- A strict gate catches silent regressions early.
- It can also slow iteration if your golden set is too broad or too sensitive.

The practical compromise is to keep the gate strict on safety and reasonably strict on quality, and to update the baseline intentionally (on main) after review.

## Extending the rubric safely

- Add new golden cases by extending `eval/datasets/golden_set.jsonl`.
- Update the rubric guidance in `eval/datasets/rubric.md`.
- When you change the report shape, bump `schema_version` and regenerate `eval/report_schema.json`.

Schema versioning is how you avoid “mysterious” CI failures after a refactor.

## Canary rollout + rollback

Canary stages, hard-stop metrics, and an incident note template are documented at `integrations/canary/rollout_plan.md`.

## Prometheus metrics

`monitoring/metrics_exporter.py` emits Prometheus text with a `llm_eval_` prefix. If you also provide a baseline and a daily report, it exports `llm_eval_drift_delta{metric="..."}` to make alerting on deltas straightforward.

## Support Hero Debug Loop (practical)

1. Re-run eval locally: `python -m eval.runner`.
2. Compare to baseline: `python -m monitoring.drift_detector ...`.
3. Check which cases regressed and whether it is correctness, groundedness, safety, latency, or cost.
4. If groundedness regressed, confirm citation formatting and retrieval context.
5. If correctness regressed, review expected points and prompt changes side-by-side.
6. Update baseline only after you can explain the change in plain language.
