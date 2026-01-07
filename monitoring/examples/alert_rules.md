# Example alert rules (Prometheus)

These alerts assume you scrape the exported text metrics (see `monitoring/metrics_exporter.py`) into Prometheus, and that you keep a baseline run for comparison.

The exact thresholds are product decisions. The intent here is to show a sensible starting point.

## Quality regressions

Hard stop (release gate / canary stop):

```promql
llm_eval_overall_score < 0.97
```

If you export drift deltas (baseline + daily), alert on deltas directly:

```promql
llm_eval_drift_delta{metric="overall_score"} < -0.03
```

Groundedness-specific:

```promql
llm_eval_drift_delta{metric="avg_groundedness"} < -0.05
```

## Safety

Safety is usually a hard stop. Even a small increase can matter.

```promql
llm_eval_safety_violation_rate > 0
```

## Latency

Alert on p95 latency spikes:

```promql
llm_eval_latency_p95_ms > 1500
```

Or relative delta if you track it:

```promql
llm_eval_drift_delta{metric="latency_p95_ms"} > 200
```

## Cost

Cost is rarely a hard stop, but it should be visible:

```promql
llm_eval_drift_delta{metric="cost_per_answer_avg"} > 0.0005
```

