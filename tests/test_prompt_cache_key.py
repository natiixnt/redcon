"""prompt_cache_key: stable fingerprint of the packed content.

Deterministic packing means an unchanged tree and task must reproduce the
same key, and any content change must produce a new one - that is what lets
callers key provider prompt caches on it.
"""

from __future__ import annotations

import re
from pathlib import Path

from redcon.core import pipeline
from redcon.stages.workflow import as_json_dict


def _seed_repo(repo: Path) -> None:
    for i in range(4):
        body = "\n".join(
            f'def handler_{i}_{j}(request):\n    """Handle case {j}."""\n    return request + {j}\n'
            for j in range(20)
        )
        (repo / f"service_{i}.py").write_text(
            f'"""Service module {i}."""\n\n{body}', encoding="utf-8"
        )


def _pack(repo: Path):
    return pipeline.run_pack(
        "adjust the request handlers", repo, max_tokens=8000, record_history=False
    )


def test_same_tree_and_task_reproduce_the_key(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    first = _pack(tmp_path)
    second = _pack(tmp_path)
    assert first.prompt_cache_key
    assert first.prompt_cache_key == second.prompt_cache_key


def test_key_is_short_hex(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    report = _pack(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{16}", report.prompt_cache_key)


def test_packed_content_change_rotates_the_key(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    before = _pack(tmp_path)
    target = tmp_path / "service_0.py"
    target.write_text(
        target.read_text(encoding="utf-8").replace("def handler_0_0(", "def handler_0_0_renamed("),
        encoding="utf-8",
    )
    after = _pack(tmp_path)
    assert before.prompt_cache_key != after.prompt_cache_key


def test_change_outside_the_pack_keeps_the_key_warm(tmp_path: Path) -> None:
    """The key fingerprints the pack, not the tree.

    An edit that does not alter what gets packed must not rotate the key,
    because that is exactly what keeps provider prompt caches hot across
    irrelevant edits.
    """
    _seed_repo(tmp_path)
    before = _pack(tmp_path)
    (tmp_path / "NOTES.txt").write_text("scratchpad note\n", encoding="utf-8")
    after = _pack(tmp_path)

    def pairs(report):
        return [(e.get("path"), e.get("text")) for e in report.compressed_context]

    if pairs(after) == pairs(before):
        assert after.prompt_cache_key == before.prompt_cache_key
    else:
        assert after.prompt_cache_key != before.prompt_cache_key


def test_key_lands_in_run_json_payload(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    report = _pack(tmp_path)
    payload = as_json_dict(report)
    assert payload["prompt_cache_key"] == report.prompt_cache_key
