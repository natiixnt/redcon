"""Artifact schema validation.

redcon ships versioned draft 2020-12 schemas for its pack (run), diff and
benchmark JSON artifacts, and `redcon validate` checks an artifact against
the schema chosen by its `command` field. Validation runs on a built-in
zero-dependency checker (jsonschema is used instead when installed).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from redcon.core import pipeline
from redcon.stages.workflow import as_json_dict
from redcon.validation import (
    ARTIFACT_TYPES,
    detect_artifact_type,
    schema_for,
    validate_artifact,
)

_SAMPLES = Path(__file__).resolve().parent.parent / "examples" / "sample-outputs"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_all_schemas_load_and_are_objects() -> None:
    for artifact_type in ARTIFACT_TYPES:
        schema = schema_for(artifact_type)
        assert schema["type"] == "object"
        assert schema["$schema"].endswith("2020-12/schema")


def test_detect_artifact_type() -> None:
    assert detect_artifact_type({"command": "pack"}) == "run"
    assert detect_artifact_type({"command": "diff"}) == "diff"
    assert detect_artifact_type({"command": "benchmark"}) == "benchmark"
    assert detect_artifact_type({"command": "plan"}) is None
    assert detect_artifact_type(["not", "a", "dict"]) is None


def test_real_run_pack_artifact_validates(tmp_path: Path) -> None:
    """A run.json produced by run_pack passes its own schema."""
    _write(tmp_path / "auth" / "login.py", "def login(token):\n    return validate(token)\n")
    _write(tmp_path / "auth" / "validate.py", "def validate(token):\n    return bool(token)\n")
    report = pipeline.run_pack("fix the login auth flow", tmp_path, max_tokens=5000)
    data = as_json_dict(report)

    assert detect_artifact_type(data) == "run"
    assert data["ranked_files"][0]["score_breakdown"]  # the feature under contract
    assert validate_artifact(data) == []


def test_committed_benchmark_and_diff_samples_validate() -> None:
    """The repo's own sample artifacts satisfy the schemas."""
    benchmark = json.loads((_SAMPLES / "risky-auth-benchmark.json").read_text())
    assert validate_artifact(benchmark) == []

    diff = json.loads((_SAMPLES / "risky-auth-vs-language-aware.diff.json").read_text())
    assert validate_artifact(diff) == []


def test_missing_required_field_is_reported() -> None:
    data = {"command": "pack", "task": "t", "repo": "."}  # missing most required keys
    errors = validate_artifact(data)
    messages = [e.message for e in errors]
    assert all(e.path == "$" for e in errors)
    assert any("ranked_files" in m for m in messages)
    assert any("budget" in m for m in messages)


def test_wrong_type_is_reported() -> None:
    benchmark = json.loads((_SAMPLES / "risky-auth-benchmark.json").read_text())
    benchmark["strategies"] = "not-a-list"
    errors = validate_artifact(benchmark)
    assert any(e.path == "$.strategies" for e in errors)


def test_score_breakdown_values_must_be_numbers(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "def a():\n    return 1\n")
    data = as_json_dict(pipeline.run_pack("do a thing", tmp_path, max_tokens=2000))
    data["ranked_files"][0]["score_breakdown"]["path_keyword"] = "high"
    errors = validate_artifact(data)
    assert any("score_breakdown" in e.path for e in errors)


def test_enum_violation_is_reported() -> None:
    diff = json.loads((_SAMPLES / "risky-auth-vs-language-aware.diff.json").read_text())
    diff["ranked_score_changes"][0]["change_type"] = "mutated"
    errors = validate_artifact(diff)
    assert any("ranked_score_changes[0].change_type" in e.path for e in errors)


def test_undetectable_type_is_a_single_error() -> None:
    errors = validate_artifact({"not": "an artifact"})
    assert len(errors) == 1
    assert errors[0].path == "$"
    assert "artifact type" in errors[0].message


def test_type_override_bypasses_detection() -> None:
    benchmark = json.loads((_SAMPLES / "risky-auth-benchmark.json").read_text())
    # Force the wrong schema: a benchmark artifact is not a valid run artifact.
    errors = validate_artifact(benchmark, artifact_type="run")
    assert errors  # command const "benchmark" != "pack", plus missing run keys


def test_jsonschema_backend_parity_when_available(tmp_path: Path) -> None:
    """If jsonschema is installed, it agrees the sample artifacts are valid."""
    pytest.importorskip("jsonschema")
    benchmark = json.loads((_SAMPLES / "risky-auth-benchmark.json").read_text())
    assert validate_artifact(benchmark) == []
