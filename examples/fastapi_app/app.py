from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class EvalEvent(BaseModel):
    question: str
    context: str
    answer: str
    citations: list[str] = Field(default_factory=list)
    latency_ms: float = Field(ge=0.0)
    cost_per_answer: float = Field(ge=0.0)


app = FastAPI(title="Eval Event Logger", version="0.1.0")
_lock = threading.Lock()


def _events_path() -> Path:
    path = os.environ.get("EVAL_EVENTS_PATH", "events.jsonl")
    return Path(path)


@app.post("/log_event")
def log_event(event: EvalEvent) -> dict[str, str]:
    out = {
        "received_utc": datetime.now(timezone.utc).isoformat(),
        **event.model_dump(mode="json"),
    }
    path = _events_path()
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(out, sort_keys=True) + "\n")
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"status": "ok"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

