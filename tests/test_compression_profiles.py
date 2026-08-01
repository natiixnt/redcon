"""The max compression profile: preset overrides and pipeline wiring.

The 'max' profile tightens the tier thresholds for every run. It is free for
everyone, no license required, and the run always reports which profile
actually ran. An unknown profile name still falls back to the default with a
warning.
"""

from __future__ import annotations

from pathlib import Path

from redcon.compressors.profiles import (
    MAX_PROFILE_OVERRIDES,
    PROFILE_DEFAULT,
    PROFILE_MAX,
    resolve_compression_profile,
)
from redcon.config import CompressionSettings, load_config_from_mapping
from redcon.core import pipeline
from redcon.entitlements import PRO_FEATURES, Entitlement


def _free() -> Entitlement:
    return Entitlement()


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def test_max_is_free_for_everyone() -> None:
    assert "compression.max" not in PRO_FEATURES
    # Ungated features are available to everyone, including a free entitlement.
    assert _free().has("compression.max") is True


def test_default_profile_passes_settings_through() -> None:
    settings = CompressionSettings()
    out, applied, note = resolve_compression_profile(settings, _free())
    assert out is settings
    assert applied == PROFILE_DEFAULT
    assert note == ""


def test_max_applies_every_override_without_a_license() -> None:
    out, applied, note = resolve_compression_profile(CompressionSettings(profile="max"), _free())
    assert applied == PROFILE_MAX
    assert note == ""
    for key, value in MAX_PROFILE_OVERRIDES.items():
        assert getattr(out, key) == value
    # The preset is strictly tighter than the defaults it replaces.
    defaults = CompressionSettings()
    assert out.full_file_threshold_tokens < defaults.full_file_threshold_tokens
    assert out.snippet_total_line_limit < defaults.snippet_total_line_limit
    assert out.summary_preview_lines < defaults.summary_preview_lines


def test_unknown_profile_falls_back_and_warns() -> None:
    out, applied, note = resolve_compression_profile(CompressionSettings(profile="turbo"), _free())
    assert applied == PROFILE_DEFAULT
    assert "unknown" in note
    assert out.full_file_threshold_tokens == CompressionSettings().full_file_threshold_tokens


def test_config_parses_profile_key() -> None:
    cfg = load_config_from_mapping({"compression": {"profile": "MAX"}})
    assert cfg.compression.profile == "max"


# ---------------------------------------------------------------------------
# Pipeline wiring
# ---------------------------------------------------------------------------


def _seed_repo(repo: Path) -> None:
    for i in range(6):
        body = "\n".join(
            f'def handler_{i}_{j}(request):\n    """Handle case {j}."""\n    return request + {j}\n'
            for j in range(30)
        )
        (repo / f"service_{i}.py").write_text(
            f'"""Service module {i}."""\n\n{body}', encoding="utf-8"
        )


def test_run_pack_max_profile_packs_tighter_and_reports_it(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    default_report = pipeline.run_pack(
        "adjust the request handlers", tmp_path, max_tokens=8000, record_history=False
    )
    max_report = pipeline.run_pack(
        "adjust the request handlers",
        tmp_path,
        max_tokens=8000,
        record_history=False,
        compression_profile="max",
    )

    assert default_report.compression_profile == "default"
    assert max_report.compression_profile == "max"
    default_tokens = int(default_report.budget.get("estimated_input_tokens", 0) or 0)
    max_tokens_used = int(max_report.budget.get("estimated_input_tokens", 0) or 0)
    assert 0 < max_tokens_used <= default_tokens


def test_run_pack_max_runs_for_free(tmp_path: Path) -> None:
    # No license and no monkeypatch: max must still run for everyone.
    _seed_repo(tmp_path)

    report = pipeline.run_pack(
        "adjust the request handlers",
        tmp_path,
        max_tokens=8000,
        record_history=False,
        compression_profile="max",
    )

    assert report.compression_profile == "max"


def test_run_pack_profile_from_config_toml(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    (tmp_path / "redcon.toml").write_text('[compression]\nprofile = "max"\n', encoding="utf-8")

    report = pipeline.run_pack(
        "adjust the request handlers", tmp_path, max_tokens=8000, record_history=False
    )

    assert report.compression_profile == "max"
