import json
from pathlib import Path

from jsonschema import validate

from eval.runner import run_eval


def test_report_validates_against_json_schema(tmp_path: Path) -> None:
    out = tmp_path / "eval_report.json"
    report = run_eval(
        dataset_path=Path("eval/datasets/golden_set.jsonl"),
        out_path=out,
        validate_output=True,
    )

    schema = json.loads(Path("eval/report_schema.json").read_text(encoding="utf-8"))
    validate(instance=report, schema=schema)

    on_disk = json.loads(out.read_text(encoding="utf-8"))
    validate(instance=on_disk, schema=schema)

