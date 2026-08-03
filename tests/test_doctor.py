from __future__ import annotations

from pathlib import Path

from redcon.core.doctor import (
    _check_cache,
    _check_license,
    _check_optional_dep,
    _check_scan_index,
    doctor_as_dict,
    run_doctor,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_missing_optional_dep_is_info_not_warning() -> None:
    # A missing optional dependency is informational, not an alarming warning,
    # so a plain `pip install redcon` doesn't look half-broken in doctor.
    result = _check_optional_dep("nope", "definitely_not_a_real_package_xyz", "extra")
    assert result.status == "info"
    assert "Optional" in result.message


def test_doctor_counts_optional_deps_as_info(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    # The optional deps that aren't installed land in info, not warnings.
    assert report.info >= 1
    summary = doctor_as_dict(report)["summary"]
    assert summary["info"] == report.info


def test_doctor_passes_with_default_setup(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    assert report.failures == 0
    assert report.passed > 0
    # Python and TOML parser should always pass
    names = [c.name for c in report.checks]
    assert "python_version" in names
    assert "toml_parser" in names


def test_doctor_warns_no_config_file(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    config_check = next(c for c in report.checks if c.name == "config")
    assert config_check.status == "warn"
    assert "No redcon.toml found" in config_check.message


def test_doctor_validates_config(tmp_path: Path) -> None:
    _write(tmp_path / "redcon.toml", "[budget]\nmax_tokens = -1\n")
    report = run_doctor(tmp_path)
    config_check = next(c for c in report.checks if c.name == "config")
    assert config_check.status == "fail"
    assert "validation error" in config_check.message


def test_doctor_detects_valid_config(tmp_path: Path) -> None:
    _write(tmp_path / "redcon.toml", "[budget]\nmax_tokens = 5000\n")
    report = run_doctor(tmp_path)
    config_check = next(c for c in report.checks if c.name == "config")
    assert config_check.status == "ok"


def test_doctor_warns_no_cache_dir(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    cache_check = next(c for c in report.checks if c.name == "cache_dir")
    assert cache_check.status == "warn"


def test_doctor_ok_cache_dir_exists(tmp_path: Path) -> None:
    (tmp_path / ".redcon").mkdir()
    report = run_doctor(tmp_path)
    cache_check = next(c for c in report.checks if c.name == "cache_dir")
    assert cache_check.status == "ok"


def test_doctor_warns_no_git(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    git_check = next(c for c in report.checks if c.name == "git_repo")
    assert git_check.status == "warn"


def test_doctor_ok_git_exists(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    report = run_doctor(tmp_path)
    git_check = next(c for c in report.checks if c.name == "git_repo")
    assert git_check.status == "ok"


def test_doctor_as_dict_structure(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    data = doctor_as_dict(report)
    assert data["command"] == "doctor"
    assert "python_version" in data
    assert "platform" in data
    assert "redcon_version" in data
    assert isinstance(data["checks"], list)
    assert "summary" in data
    assert data["summary"]["total"] == len(report.checks)


def test_doctor_reports_nonzero_on_failure(tmp_path: Path) -> None:
    _write(tmp_path / "redcon.toml", "[budget]\nmax_tokens = -1\n")
    report = run_doctor(tmp_path)
    assert report.failures > 0


def test_doctor_includes_license_scan_index_and_cache(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    names = {c.name for c in report.checks}
    assert {"license", "scan_index", "cache"} <= names
    # The new named extras are checked too.
    assert {"cryptography", "jsonschema", "llmlingua"} <= names


def test_license_without_key_is_free_info(tmp_path: Path) -> None:
    result = _check_license(tmp_path)
    assert result.status == "info"  # a license status is never a failure
    assert "tier=free" in result.message
    assert "status=free" in result.message
    # The token and key-file path must never appear in the output.
    blob = f"{result.message} {result.detail}"
    assert "token" not in blob.lower()
    assert ".redcon/license" not in blob


def test_scan_index_absent_is_info(tmp_path: Path) -> None:
    result = _check_scan_index(tmp_path)
    assert result.status == "info"
    assert "No scan index" in result.message


def test_cache_check_reports_backend_and_ttl(tmp_path: Path) -> None:
    _write(tmp_path / "redcon.toml", "[cache]\nlocal_ttl_seconds = 3600\n")
    result = _check_cache(tmp_path)
    assert result.status == "ok"
    assert "backend=local_file" in result.message
    assert "ttl=3600s" in result.message


def test_cache_check_fails_on_unwritable_directory(tmp_path: Path) -> None:
    # Point the cache at a subdirectory that cannot be created because a file
    # occupies its path, so the write probe fails deterministically.
    _write(tmp_path / "redcon.toml", '[cache]\ncache_file = "blocked/cache.json"\n')
    (tmp_path / "blocked").write_text("not a directory", encoding="utf-8")
    result = _check_cache(tmp_path)
    assert result.status == "fail"
    assert "not writable" in result.message


def test_doctor_json_matches_exit_code(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    data = doctor_as_dict(report)
    fails = sum(1 for c in data["checks"] if c["status"] == "fail")
    # A clean tmp repo has no failures, and the report agrees.
    assert fails == report.failures == 0


def test_doctor_survives_broken_config(tmp_path: Path) -> None:
    # An unparseable redcon.toml must not crash doctor: the config check reports
    # the failure and the cache check skips gracefully rather than raising.
    _write(tmp_path / "redcon.toml", "[cache\nthis is not valid toml =\n")
    report = run_doctor(tmp_path)  # must not raise
    config_check = next(c for c in report.checks if c.name == "config")
    assert config_check.status == "fail"
    cache_check = next(c for c in report.checks if c.name == "cache")
    assert cache_check.status == "info"
    assert "config could not be loaded" in cache_check.message
    assert report.failures >= 1


def test_cli_doctor_exit_1_on_broken_config(tmp_path: Path) -> None:
    from redcon.cli import build_parser

    _write(tmp_path / "redcon.toml", "[cache\nbad =\n")
    args = build_parser().parse_args(["doctor", "--repo", str(tmp_path)])
    assert int(args.func(args)) == 1
