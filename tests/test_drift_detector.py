from monitoring.drift_detector import detect_drift, render_markdown


def test_drift_detector_action_plan_is_stable() -> None:
    baseline = {
        "summary": {
            "overall_score": 0.90,
            "avg_correctness": 0.92,
            "avg_groundedness": 0.88,
            "safety_violation_rate": 0.00,
            "latency_p50_ms": 200.0,
            "latency_p95_ms": 500.0,
            "cost_per_answer_avg": 0.0010,
        }
    }
    daily = {
        "summary": {
            "overall_score": 0.86,  # -4.44% relative
            "avg_correctness": 0.92,
            "avg_groundedness": 0.80,  # -9.09% relative
            "safety_violation_rate": 0.02,  # increased
            "latency_p50_ms": 200.0,
            "latency_p95_ms": 650.0,  # +30% relative
            "cost_per_answer_avg": 0.0010,
        }
    }

    plan = detect_drift(baseline, daily, regression_threshold=0.03)
    assert plan["drift_detected"] is True

    drifted = {m["name"] for m in plan["drifted_metrics"]}
    assert drifted == {"overall_score", "avg_groundedness", "safety_violation_rate", "latency_p95_ms"}

    # The ranking is deterministic given the scoring in likely_causes().
    assert plan["likely_cause_buckets_ranked"][0] in {"retrieval", "prompt", "infra"}

    md = render_markdown(plan, baseline_path="baseline.json", daily_path="daily.json")
    assert "Drift report" in md
    assert "| overall_score |" in md
    assert "Recommended next steps" in md

