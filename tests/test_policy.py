from __future__ import annotations

from pathlib import Path

from redcon.core.policy import default_strict_policy, evaluate_policy, load_policy


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_payload(
    *, input_tokens: int, saved_tokens: int, files_included: list[str], risk: str
) -> dict:
    return {
        "files_included": files_included,
        "budget": {
            "estimated_input_tokens": input_tokens,
            "estimated_saved_tokens": saved_tokens,
            "quality_risk_estimate": risk,
        },
        "cache_hits": 0,
    }


def test_load_policy_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    _write(
        path,
        """
[policy]
max_estimated_input_tokens = 30000
max_files_included = 12
max_quality_risk_level = "medium"
min_estimated_savings_percentage = 15.0
""".strip(),
    )

    policy = load_policy(path)
    assert policy.max_estimated_input_tokens == 30000
    assert policy.max_files_included == 12
    assert policy.max_quality_risk_level == "medium"
    assert policy.min_estimated_savings_percentage == 15.0


def test_evaluate_policy_reports_violations() -> None:
    policy = default_strict_policy(max_estimated_input_tokens=100)
    policy.max_files_included = 1
    policy.max_quality_risk_level = "medium"
    policy.min_estimated_savings_percentage = 50.0

    run = _run_payload(
        input_tokens=120,
        saved_tokens=20,
        files_included=["a.py", "b.py"],
        risk="high",
    )

    result = evaluate_policy(run, policy)
    assert result.passed is False
    assert any("estimated input tokens" in v for v in result.violations)
    assert any("files included" in v for v in result.violations)
    assert any("quality risk" in v for v in result.violations)
    assert any("estimated savings" in v for v in result.violations)


def test_evaluate_policy_passes_when_thresholds_met() -> None:
    policy = default_strict_policy(max_estimated_input_tokens=200)
    policy.max_files_included = 3
    policy.max_quality_risk_level = "high"
    policy.min_estimated_savings_percentage = 10.0

    run = _run_payload(
        input_tokens=120,
        saved_tokens=40,
        files_included=["a.py", "b.py"],
        risk="medium",
    )

    result = evaluate_policy(run, policy)
    assert result.passed is True
    assert result.violations == []


def _critical_payload(*, skipped: list[str], keywords: list[str]) -> dict:
    return {
        "files_included": ["auth/login.py"],
        "files_skipped": skipped,
        "critical_path_keywords": keywords,
        "budget": {"estimated_input_tokens": 100, "quality_risk_estimate": "low"},
    }


def test_forbid_skipped_critical_files_fails_when_critical_skipped() -> None:
    run = _critical_payload(skipped=["auth/legacy.py", "utils/misc.py"], keywords=["auth"])
    from redcon.core.policy import PolicySpec

    result = evaluate_policy(run, PolicySpec(forbid_skipped_critical_files=True))
    assert result.passed is False
    assert any(
        "critical files were skipped" in v and "auth/legacy.py" in v for v in result.violations
    )
    assert result.checks["forbid_skipped_critical_files"]["actual"] == 1


def test_forbid_skipped_critical_files_passes_when_none_critical_skipped() -> None:
    run = _critical_payload(skipped=["utils/misc.py"], keywords=["auth"])
    from redcon.core.policy import PolicySpec

    result = evaluate_policy(run, PolicySpec(forbid_skipped_critical_files=True))
    assert result.passed is True
    assert result.checks["forbid_skipped_critical_files"]["passed"] is True


def test_forbid_skipped_critical_files_disabled_by_default() -> None:
    run = _critical_payload(skipped=["auth/legacy.py"], keywords=["auth"])
    from redcon.core.policy import PolicySpec

    # None (default) leaves the rule off, so a skipped critical file is fine.
    result = evaluate_policy(run, PolicySpec())
    assert result.passed is True
    assert "forbid_skipped_critical_files" not in result.checks


def test_load_forbid_skipped_critical_files_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    _write(path, "[policy]\nforbid_skipped_critical_files = true\n")
    policy = load_policy(path)
    assert policy.forbid_skipped_critical_files is True


def test_run_pack_artifact_carries_critical_path_keywords(tmp_path: Path) -> None:
    from redcon.config import default_config
    from redcon.core import pipeline
    from redcon.stages.workflow import as_json_dict

    _write(tmp_path / "auth" / "login.py", "def login(t):\n    return bool(t)\n")
    cfg = default_config()
    cfg.score.critical_path_keywords = ["auth"]
    data = as_json_dict(pipeline.run_pack("harden auth", tmp_path, max_tokens=5000, config=cfg))
    assert data.get("critical_path_keywords") == ["auth"]
