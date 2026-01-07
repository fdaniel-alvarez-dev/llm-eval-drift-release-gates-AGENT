# Prompt contract (practical)

Prompts are part of your product surface. Treat them as a contract: if the contract changes, behavior changes, and you should expect drift.

This document defines a small contract that helps you:

- keep outputs stable enough to evaluate
- log the right data from production sampling
- evolve prompts safely (with schema versioning and baseline updates)

## Inputs (what the model sees)

Minimum inputs to log for eval reproduction:

- `question`: the user question
- `context`: the retrieved context or tool output shown to the model

Optional but useful:

- `system_prompt_version`: a semantic identifier (e.g., `support-v3`)
- `tool_outputs`: if you show tool results to the model

## Outputs (what you should log)

To evaluate groundedness and safety, capture:

- `answer`: the model output
- `citations`: a list of short snippets that the answer claims to rely on (verbatim from `context`)
- `latency_ms`
- `cost_per_answer` (numeric dollars; if you do not have it, record `0` and track separately)

## Citation format

Keep citations easy to check offline:

- citations must be short snippets that appear in `context` (copy/paste fragments)
- avoid opaque document ids as citations unless you also log the referenced document text

## Versioning rule

If you change output shape or requirements (for example you require a different citation format), bump:

- the prompt contract version in your application logs
- the evaluation report schema version if the report fields change

The baseline update should be an intentional action after review.

