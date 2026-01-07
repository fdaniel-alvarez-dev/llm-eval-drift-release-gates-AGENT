# Canary rollout and rollback plan

This plan assumes you have two sources of evidence:

1. Offline evaluation (`eval_report.json` compared to a baseline).
2. Production metrics sampled from real traffic (latency, errors, safety flags, and user-facing success proxies).

The goal is simple: ship changes gradually, stop early when you see harm, and leave a clear trail for incident review.

## Canary stages

Suggested stages:

1. **1%** of eligible traffic for 30–60 minutes
2. **10%** for 2–4 hours
3. **50%** for 12–24 hours
4. **100%** when stable

Eligibility rules should be stable (hash-based routing) so you do not bias metrics during rollout.

## Hard stops (automatic rollback triggers)

Hard stops are “stop the rollout now” signals.

Offline eval hard stops:

- Any increase in `safety_violation_rate` relative to baseline.
- `overall_score` regression greater than 3% relative to baseline.

Production hard stops (example defaults; tune per product):

- Safety incidents: any confirmed unsafe completion or policy-bypass pattern.
- Error rate: sustained increase > 1.0 percentage point for 10 minutes.
- Latency: p95 latency increase > 30% for 15 minutes.

## Soft stops (pause and investigate)

Soft stops are “hold at the current stage” signals:

- Small quality regression (<3%) that is concentrated in one intent category.
- Cost increase > 10% without quality gains.
- Partial degradation that affects a single tenant, region, or traffic segment.

## What to do on rollback

1. Roll back the change using your normal deployment rollback mechanism.
2. Capture evidence:
   - baseline report and daily report
   - drift report (`drift_report.json` + `drift_report.md`)
   - production dashboards and sample events
3. Identify likely cause bucket:
   - retrieval, prompt, data, model, or infra
4. Make the smallest safe fix:
   - prompt adjustment, retrieval correction, model adapter change, or infra revert
5. Re-run offline eval and confirm the hard-stop metrics are back within bounds.

## Minimal incident note template

Copy/paste and fill in:

```
Title:
Start time (UTC):
End time (UTC):

What happened (plain language):

Impact:
- who was affected:
- what users saw:

Signals:
- offline eval: (metric, baseline, daily, delta)
- production: (metric, stage, observed values)

Rollback decision:
- trigger:
- action taken:

Likely cause bucket:
- retrieval | prompt | data | model | infra

Fix:

What we will watch next time:
```

