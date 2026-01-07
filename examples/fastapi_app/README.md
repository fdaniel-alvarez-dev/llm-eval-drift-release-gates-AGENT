# FastAPI example: production event logging

This mini-app shows a minimal pattern for sampling production traffic and logging it for later offline evaluation.

It is intentionally isolated from the core toolkit dependencies. It writes JSONL to a local file.

## Run

```bash
cd examples/fastapi_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export EVAL_EVENTS_PATH=events.jsonl
uvicorn app:app --reload --port 8000
```

## Send an event

```bash
curl -sS http://127.0.0.1:8000/log_event \
  -H 'content-type: application/json' \
  -d '{
    "question":"What changed in release 2.7.0?",
    "context":"Release 2.7.0 changes: Added an optional source field. Improved dashboard load time by caching user preferences.",
    "answer":"Summary: optional source field; caching user preferences.",
    "citations":["caching user preferences"],
    "latency_ms":123,
    "cost_per_answer":0.0004
  }' | jq .
```

Events append to `events.jsonl` (or `$EVAL_EVENTS_PATH`) as one JSON document per line.

