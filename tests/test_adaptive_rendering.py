"""Tests for adaptive render mode ([render] mode = "adaptive").

Adaptive rendering walks ranked files and includes each one whole when it fits
the remaining budget, falling back to the compressed entry on overflow and
skipping only when neither fits. These tests pin the guarantees from the design:
the budget is never exceeded, the walk is deterministic, a repo that fits the
budget degenerates to all-whole, overflow produces a whole+compressed mix, and
the default mode is unchanged (compressed).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from redcon.config import CompressionSettings, RedconConfig, load_config
from redcon.core import pipeline
from redcon.stages.workflow import as_json_dict


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init")
    return repo


def _pack(repo: Path, task: str, max_tokens: int, mode: str | None = None) -> dict:
    compression = CompressionSettings() if mode is None else CompressionSettings(render_mode=mode)
    config = RedconConfig(compression=compression)
    return as_json_dict(
        pipeline.run_pack(task, repo, max_tokens=max_tokens, config=config, record_history=False)
    )


_SMALL_FILES = {
    "auth.py": 'def login_retry(user):\n    """login retry"""\n    return retry(user)\n',
    "db.py": "def connect():\n    return 1\n",
}


def test_default_mode_is_adaptive(tmp_path: Path):
    # Default flipped to adaptive (Exp 3, next release): a repo that fits the budget
    # is delivered whole with no render_mode set.
    assert CompressionSettings().render_mode == "adaptive"
    repo = _repo(tmp_path, _SMALL_FILES)
    data = _pack(repo, "login retry", max_tokens=5000)
    assert data["compressed_context"], "expected at least one included file"
    assert all(e["delivery"] == "whole" for e in data["compressed_context"])


def test_compressed_mode_still_available(tmp_path: Path):
    # The old behaviour is still selectable explicitly.
    repo = _repo(tmp_path, _SMALL_FILES)
    data = _pack(repo, "login retry", max_tokens=5000, mode="compressed")
    assert all(e["delivery"] == "compressed" for e in data["compressed_context"])


def test_small_repo_degenerates_to_all_whole(tmp_path: Path):
    # A repo that fits the budget is delivered entirely as whole files.
    repo = _repo(tmp_path, _SMALL_FILES)
    data = _pack(repo, "login retry", max_tokens=5000, mode="adaptive")
    assert data["compressed_context"]
    assert all(e["delivery"] == "whole" for e in data["compressed_context"])
    assert all(e["text"].startswith("# Full:") for e in data["compressed_context"])
    # Zero compression: nothing saved because everything is whole.
    assert data["budget"]["estimated_saved_tokens"] == 0


def _overflow_repo(tmp_path: Path) -> Path:
    big = "\n".join(
        f"def helper_{i}(retry_login):\n    # retry login helper {i}\n    return {i}\n"
        for i in range(200)
    )
    return _repo(
        tmp_path,
        {
            "auth.py": 'def login_retry(user):\n    """login retry"""\n    return retry(user)\n',
            "big.py": big,
        },
    )


def test_budget_never_exceeded_on_overflow(tmp_path: Path):
    repo = _overflow_repo(tmp_path)
    for budget in (400, 800, 1500):
        data = _pack(repo, "login retry helper", max_tokens=budget, mode="adaptive")
        assert data["budget"]["estimated_input_tokens"] <= budget


def test_mixed_whole_and_compressed_on_overflow(tmp_path: Path):
    # A large ranked-first file must compress while a small file stays whole.
    repo = _overflow_repo(tmp_path)
    data = _pack(repo, "login retry helper", max_tokens=400, mode="adaptive")
    deliveries = {e["path"].split("/")[-1]: e["delivery"] for e in data["compressed_context"]}
    assert deliveries.get("big.py") == "compressed"
    assert deliveries.get("auth.py") == "whole"


def test_adaptive_is_deterministic(tmp_path: Path):
    repo = _overflow_repo(tmp_path)
    first = _pack(repo, "login retry helper", max_tokens=600, mode="adaptive")["compressed_context"]
    second = _pack(repo, "login retry helper", max_tokens=600, mode="adaptive")[
        "compressed_context"
    ]
    assert [(e["path"], e["delivery"], e["text"]) for e in first] == [
        (e["path"], e["delivery"], e["text"]) for e in second
    ]


def test_render_section_and_compression_key_parse(tmp_path: Path):
    # [render] mode and [compression] render_mode both reach the setting.
    cfg_render = tmp_path / "a.toml"
    cfg_render.write_text('[render]\nmode = "adaptive"\n')
    assert load_config(tmp_path, config_path=cfg_render).compression.render_mode == "adaptive"

    cfg_comp = tmp_path / "b.toml"
    cfg_comp.write_text('[compression]\nrender_mode = "adaptive"\n')
    assert load_config(tmp_path, config_path=cfg_comp).compression.render_mode == "adaptive"


def test_invalid_render_mode_warns():
    cfg = RedconConfig(compression=CompressionSettings(render_mode="nonsense"))
    warnings = cfg.validate()
    assert any("mode" in w and "adaptive" in w for w in warnings)
