"""Diagnostics for verifying Redcon environment health."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from redcon.config import validate_config


@dataclass(slots=True)
class CheckResult:
    """Outcome of a single diagnostic check."""

    name: str
    status: str  # "ok", "warn", "fail"
    message: str
    detail: str = ""


@dataclass(slots=True)
class DoctorReport:
    """Aggregated diagnostics report."""

    python_version: str
    platform: str
    redcon_version: str
    checks: list[CheckResult] = field(default_factory=list)
    passed: int = 0
    warnings: int = 0
    failures: int = 0
    info: int = 0


def _check_python_version() -> CheckResult:
    version = sys.version_info
    ver_str = f"{version.major}.{version.minor}.{version.micro}"
    if version >= (3, 10):
        return CheckResult(
            name="python_version",
            status="ok",
            message=f"Python {ver_str}",
        )
    return CheckResult(
        name="python_version",
        status="warn",
        message=f"Python {ver_str} detected - redcon requires >= 3.10. Some features may not work.",
        detail=(
            "Upgrade to Python 3.10 or later for full compatibility. "
            "Visit https://www.python.org/downloads/ for installers."
        ),
    )


def _check_toml_parser() -> CheckResult:
    try:
        import tomllib  # noqa: F401

        return CheckResult(name="toml_parser", status="ok", message="tomllib (stdlib)")
    except ModuleNotFoundError:
        pass
    try:
        import tomli  # noqa: F401

        return CheckResult(name="toml_parser", status="ok", message="tomli (backport)")
    except ModuleNotFoundError:
        return CheckResult(
            name="toml_parser",
            status="fail",
            message="No TOML parser available - install tomli for Python < 3.11",
        )


def _check_optional_dep(name: str, package: str, extra: str) -> CheckResult:
    try:
        mod = __import__(package)
        version = getattr(mod, "__version__", getattr(mod, "VERSION", "unknown"))
        return CheckResult(
            name=name,
            status="ok",
            message=f"{package} {version}",
        )
    except ImportError:
        return CheckResult(
            name=name,
            status="info",
            message=f"Optional - not installed. Enable with: pip install 'redcon[{extra}]'",
        )


def _check_config(repo: Path) -> CheckResult:
    config_path = repo / "redcon.toml"
    if not config_path.exists():
        return CheckResult(
            name="config",
            status="warn",
            message="No redcon.toml found - using defaults. Run 'redcon init' to create one.",
        )
    try:
        # load_config raises ConfigValidationError on invalid values, so
        # we parse manually to separate parse vs validation errors.
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        from redcon.config import load_config_from_mapping

        cfg = load_config_from_mapping(data)
        errors = validate_config(cfg)
        if errors:
            return CheckResult(
                name="config",
                status="fail",
                message=f"redcon.toml has {len(errors)} validation error(s)",
                detail="; ".join(errors),
            )
        return CheckResult(name="config", status="ok", message="redcon.toml is valid")
    except Exception as exc:
        return CheckResult(
            name="config",
            status="fail",
            message=f"Failed to parse redcon.toml: {exc}",
        )


def _check_cache_dir(repo: Path) -> CheckResult:
    cache_dir = repo / ".redcon"
    if not cache_dir.exists():
        return CheckResult(
            name="cache_dir",
            status="warn",
            message=".redcon/ directory does not exist - will be created on first run",
        )
    if not cache_dir.is_dir():
        return CheckResult(
            name="cache_dir",
            status="fail",
            message=".redcon exists but is not a directory",
        )
    return CheckResult(name="cache_dir", status="ok", message=".redcon/ directory exists")


def _check_git_repo(repo: Path) -> CheckResult:
    git_dir = repo / ".git"
    if git_dir.exists():
        return CheckResult(name="git_repo", status="ok", message="Git repository detected")
    return CheckResult(
        name="git_repo",
        status="warn",
        message="Not a git repository - git-aware features (dirty file boost, PR audit) will be unavailable",
    )


def _check_disk_space(repo: Path) -> CheckResult:
    """Check available disk space for the workspace (fix 2)."""
    try:
        usage = shutil.disk_usage(repo)
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        pct_free = (usage.free / usage.total) * 100 if usage.total > 0 else 0
        if free_gb < 0.5:
            return CheckResult(
                name="disk_space",
                status="fail",
                message=f"Very low disk space: {free_gb:.1f} GB free of {total_gb:.1f} GB ({pct_free:.0f}% free)",
                detail="Redcon needs disk space for caching run history and artifacts.",
            )
        if free_gb < 2.0:
            return CheckResult(
                name="disk_space",
                status="warn",
                message=f"Low disk space: {free_gb:.1f} GB free of {total_gb:.1f} GB ({pct_free:.0f}% free)",
                detail="Consider freeing up space to avoid issues with run history storage.",
            )
        return CheckResult(
            name="disk_space",
            status="ok",
            message=f"{free_gb:.1f} GB free of {total_gb:.1f} GB ({pct_free:.0f}% free)",
        )
    except OSError as exc:
        return CheckResult(
            name="disk_space",
            status="warn",
            message=f"Could not determine disk space: {exc}",
        )


def _check_redcon_toml(repo: Path) -> CheckResult:
    """Check for redcon.toml existence with helpful guidance (fix 3)."""
    config_path = repo / "redcon.toml"
    if not config_path.exists():
        return CheckResult(
            name="redcon_toml",
            status="warn",
            message="No redcon.toml found in project root",
            detail=(
                "Without a redcon.toml, all settings use defaults. "
                "Create one with 'redcon init' or manually add a redcon.toml "
                "to configure budget limits, scanner options, and policy rules."
            ),
        )
    if not config_path.is_file():
        return CheckResult(
            name="redcon_toml",
            status="fail",
            message="redcon.toml exists but is not a regular file",
        )
    try:
        size = config_path.stat().st_size
        if size == 0:
            return CheckResult(
                name="redcon_toml",
                status="warn",
                message="redcon.toml exists but is empty - defaults will be used",
            )
    except OSError:
        pass
    return CheckResult(
        name="redcon_toml",
        status="ok",
        message="redcon.toml found",
    )


def _check_git_available() -> CheckResult:
    """Check that git CLI is available on PATH (fix 4)."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            version_str = result.stdout.strip()
            return CheckResult(
                name="git_available",
                status="ok",
                message=version_str,
            )
        return CheckResult(
            name="git_available",
            status="warn",
            message="git found but returned an error",
            detail=result.stderr.strip() if result.stderr else "Unknown error",
        )
    except FileNotFoundError:
        return CheckResult(
            name="git_available",
            status="warn",
            message="git is not installed or not on PATH",
            detail=(
                "Git is used by scanners for dirty-file detection and PR audit. "
                "Install git from https://git-scm.com/downloads to enable these features."
            ),
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="git_available",
            status="warn",
            message="git --version timed out after 5 seconds",
        )
    except OSError as exc:
        return CheckResult(
            name="git_available",
            status="warn",
            message=f"Could not run git: {exc}",
        )


def _check_mcp_registration(repo: Path) -> CheckResult:
    """Is the redcon MCP server registered for any detected agent?

    A broken agent integration is the most common silent failure: the
    package imports fine, doctor is green, yet the agent never sees the
    redcon tools. Surface it here.
    """
    try:
        from redcon.mcp.install import detect_targets, installed_path

        detected = detect_targets(repo)
        registered = [t for t in detected if installed_path(t, repo)]
    except Exception as exc:
        return CheckResult(
            name="mcp_registration",
            status="warn",
            message=f"Could not inspect MCP registration: {exc}",
        )
    if not detected:
        return CheckResult(
            name="mcp_registration",
            status="warn",
            message="No agent configs detected in this project",
            detail=(
                "Run 'redcon mcp install' to register the redcon MCP server "
                "for Claude Code, Cursor, Windsurf, VS Code, Codex or Gemini."
            ),
        )
    if registered:
        return CheckResult(
            name="mcp_registration",
            status="ok",
            message=f"Registered for: {', '.join(sorted(registered))}",
        )
    return CheckResult(
        name="mcp_registration",
        status="warn",
        message=f"Agents detected ({', '.join(sorted(detected))}) but redcon is not registered",
        detail="Run 'redcon mcp install' to register the MCP server.",
    )


def _check_secret_exposure(repo: Path) -> CheckResult:
    """Confirm credential files are excluded from the packable scan universe.

    Reports OK with a count when secret-looking files exist and are being
    excluded, and only warns if exclusion has been turned off while such files
    are present (the one configuration that could leak them to an LLM).
    """
    try:
        from redcon.config import load_config
        from redcon.scanners.incremental import _matches_glob
        from redcon.schemas.models import DEFAULT_SECRET_GLOBS

        cfg = load_config(repo)
    except Exception as exc:
        return CheckResult(
            name="secret_exposure",
            status="warn",
            message=f"Could not evaluate secret exclusion: {exc}",
        )

    matches: list[str] = []
    ignore_dirs = set(cfg.scan.ignore_dirs)
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo).parts
        if any(part in ignore_dirs for part in rel_parts[:-1]):
            continue
        rel = path.relative_to(repo).as_posix()
        if any(_matches_glob(rel, pat) for pat in DEFAULT_SECRET_GLOBS):
            matches.append(rel)
        if len(matches) >= 50:
            break

    if not matches:
        return CheckResult(
            name="secret_exposure",
            status="ok",
            message="No credential files detected in scan scope",
        )
    if cfg.scan.exclude_secrets:
        return CheckResult(
            name="secret_exposure",
            status="ok",
            message=f"{len(matches)} credential file(s) present and excluded from packing",
        )
    return CheckResult(
        name="secret_exposure",
        status="fail",
        message=f"{len(matches)} credential file(s) can be packed - [scan].exclude_secrets is false",
        detail=(
            "Set [scan].exclude_secrets = true (the default) so files like "
            + ", ".join(matches[:5])
            + " are never sent to an LLM."
        ),
    )


def _check_license(repo: Path) -> CheckResult:
    """Report the resolved license tier and status. Never prints the key or its path."""
    try:
        from redcon.entitlements import load_entitlement

        entitlement = load_entitlement(repo)
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        return CheckResult(
            name="license", status="info", message=f"Could not resolve license: {exc}"
        )
    return CheckResult(
        name="license",
        status="info",
        message=f"tier={entitlement.tier}, status={entitlement.status}",
        detail=(entitlement.hint or "").strip(),
    )


def _check_scan_index(repo: Path) -> CheckResult:
    """Report whether a scan index exists, its format version and file count."""
    from redcon.scanners.incremental import (
        INDEX_FORMAT_VERSION,
        SCAN_INDEX_DB_FILE,
        load_scan_index,
    )
    from redcon.schemas.models import SCAN_INDEX_FILE

    db_path = repo / SCAN_INDEX_DB_FILE
    json_path = repo / SCAN_INDEX_FILE

    if db_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="scan_index",
                status="info",
                message=f"Scan index present but unreadable: {exc}",
            )
        return CheckResult(
            name="scan_index",
            status="ok",
            message=f"Present (sqlite), format v{INDEX_FORMAT_VERSION}, {count} files",
        )

    if json_path.exists():
        try:
            data = load_scan_index(json_path)
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="scan_index",
                status="info",
                message=f"Scan index present but unreadable: {exc}",
            )
        version = int(data.get("version", 0) or 0)
        count = len(data.get("entries", []) or [])
        if version != INDEX_FORMAT_VERSION:
            return CheckResult(
                name="scan_index",
                status="info",
                message=f"Format v{version} (expected v{INDEX_FORMAT_VERSION}); will rebuild on next run",
                detail=f"{count} files",
            )
        return CheckResult(
            name="scan_index",
            status="ok",
            message=f"Present (json), format v{version}, {count} files",
        )

    return CheckResult(
        name="scan_index", status="info", message="No scan index yet - built on first run"
    )


def _check_cache(repo: Path) -> CheckResult:
    """Report the cache backend, TTL and entry count, and probe write access."""
    from redcon.config import load_config

    try:
        cfg = load_config(repo)
    except Exception:  # noqa: BLE001 - a bad config is already reported by _check_config
        return CheckResult(
            name="cache", status="info", message="skipped: config could not be loaded"
        )
    backend = cfg.cache.backend
    ttl = cfg.cache.local_ttl_seconds
    ttl_desc = "disabled" if ttl <= 0 else f"{ttl}s"
    cache_path = repo / cfg.cache.cache_file
    cache_dir = cache_path.parent

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        probe = cache_dir / ".redcon-doctor-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return CheckResult(
            name="cache",
            status="fail",
            message=f"Cache directory is not writable: {cache_dir}",
            detail=str(exc),
        )

    entries = 0
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            for store in ("summaries", "fragments", "slices"):
                if isinstance(data.get(store), dict):
                    entries += len(data[store])
        except (OSError, json.JSONDecodeError, ValueError):
            entries = 0

    return CheckResult(
        name="cache",
        status="ok",
        message=f"backend={backend}, {entries} entries, ttl={ttl_desc}",
        detail=f"directory: {cache_dir}",
    )


def run_doctor(repo: Path) -> DoctorReport:
    """Run all diagnostic checks and return a report."""
    try:
        from redcon import __version__
    except (ImportError, AttributeError):
        __version__ = "unknown"

    report = DoctorReport(
        python_version=platform.python_version(),
        platform=platform.platform(),
        redcon_version=__version__,
    )

    checks = [
        _check_python_version(),
        _check_toml_parser(),
        _check_optional_dep("tiktoken", "tiktoken", "tokenizers"),
        _check_optional_dep("redis", "redis", "redis"),
        _check_optional_dep("fastapi", "fastapi", "gateway"),
        _check_optional_dep("uvicorn", "uvicorn", "gateway"),
        _check_optional_dep("mcp", "mcp", "mcp"),
        _check_optional_dep("tree_sitter", "tree_sitter", "symbols"),
        _check_optional_dep("ast_grep", "ast_grep_py", "ast_grep"),
        _check_optional_dep("cryptography", "cryptography", "pro"),
        _check_optional_dep("jsonschema", "jsonschema", "validate"),
        _check_optional_dep("llmlingua", "llmlingua", "heavy_compression"),
        _check_mcp_registration(repo),
        _check_secret_exposure(repo),
        _check_config(repo),
        _check_redcon_toml(repo),
        _check_cache_dir(repo),
        _check_cache(repo),
        _check_scan_index(repo),
        _check_license(repo),
        _check_git_repo(repo),
        _check_git_available(),
        _check_disk_space(repo),
    ]

    for check in checks:
        report.checks.append(check)
        if check.status == "ok":
            report.passed += 1
        elif check.status == "info":
            report.info += 1
        elif check.status == "warn":
            report.warnings += 1
        else:
            report.failures += 1

    return report


def doctor_as_dict(report: DoctorReport) -> dict[str, Any]:
    """Convert a DoctorReport to a JSON-serializable dict."""
    return {
        "command": "doctor",
        "python_version": report.python_version,
        "platform": report.platform,
        "redcon_version": report.redcon_version,
        "checks": [
            {
                "name": c.name,
                "status": c.status,
                "message": c.message,
                **({"detail": c.detail} if c.detail else {}),
            }
            for c in report.checks
        ],
        "summary": {
            "passed": report.passed,
            "info": report.info,
            "warnings": report.warnings,
            "failures": report.failures,
            "total": len(report.checks),
        },
    }
