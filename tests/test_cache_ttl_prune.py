"""Local cache TTL freshness and the `redcon cache prune` command.

TTL is disabled by default (local_ttl_seconds = 0), so existing behaviour is
unchanged. When enabled, local cache entries older than the TTL are treated as
misses. `cache prune` removes expired entries and entries whose referenced file
no longer exists, and is a no-op when nothing qualifies.
"""

from __future__ import annotations

import json
from pathlib import Path

from redcon.cache.backends import LocalFileSummaryCacheBackend
from redcon.cli import build_parser
from redcon.config import load_config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_ttl_disabled_by_default_keeps_entries(tmp_path: Path) -> None:
    backend = LocalFileSummaryCacheBackend(repo_path=tmp_path)  # ttl_seconds defaults to 0
    backend.put_summary("k", "v")
    # Even far in the "future", a disabled TTL never expires an entry.
    backend._now = lambda: 10**12
    assert backend.get_summary("k") == "v"


def test_ttl_expires_stale_entries(tmp_path: Path) -> None:
    backend = LocalFileSummaryCacheBackend(repo_path=tmp_path, ttl_seconds=100)
    base = backend._now()
    backend.put_summary("k", "v")
    backend._now = lambda: base + 50
    assert backend.get_summary("k") == "v"  # within TTL
    backend._now = lambda: base + 200
    assert backend.get_summary("k") is None  # expired -> miss


def test_prune_removes_orphaned_keeps_live(tmp_path: Path) -> None:
    backend = LocalFileSummaryCacheBackend(repo_path=tmp_path)
    backend.put_summary("auth/login.py:10:h1:summary", "LIVE")
    backend.put_summary("deleted/gone.py:5:h2:summary", "ORPHAN")
    result = backend.prune(live_paths={"auth/login.py"})
    assert result["entries_removed"] == 1
    assert result["orphaned"] == 1
    assert result["bytes_freed"] > 0
    assert backend.get_summary("auth/login.py:10:h1:summary") == "LIVE"
    assert backend.get_summary("deleted/gone.py:5:h2:summary") is None


def test_prune_removes_expired(tmp_path: Path) -> None:
    backend = LocalFileSummaryCacheBackend(repo_path=tmp_path, ttl_seconds=100)
    backend.put_summary("auth/login.py:10:h1:summary", "OLD")
    # Backdate the timestamp so the entry is past its TTL.
    backend._timestamps("summaries")["auth/login.py:10:h1:summary"] = backend._now() - 1000
    result = backend.prune(live_paths={"auth/login.py"})
    assert result["expired"] == 1
    assert result["entries_removed"] == 1


def test_prune_with_no_expired_or_orphaned_is_noop(tmp_path: Path) -> None:
    backend = LocalFileSummaryCacheBackend(repo_path=tmp_path)
    backend.put_summary("auth/login.py:10:h1:summary", "LIVE")
    backend._save()
    before = (tmp_path / ".redcon_cache.json").read_text()
    result = backend.prune(live_paths={"auth/login.py"})
    assert result == {"entries_removed": 0, "bytes_freed": 0, "expired": 0, "orphaned": 0}
    assert (tmp_path / ".redcon_cache.json").read_text() == before


def test_prune_dry_run_does_not_write(tmp_path: Path) -> None:
    backend = LocalFileSummaryCacheBackend(repo_path=tmp_path)
    backend.put_summary("gone/x.py:1:h:summary", "ORPHAN")
    backend._save()
    before = (tmp_path / ".redcon_cache.json").read_text()
    result = backend.prune(live_paths={"auth/login.py"}, dry_run=True)
    assert result["entries_removed"] == 1
    assert (tmp_path / ".redcon_cache.json").read_text() == before  # unchanged


def test_prune_empty_live_paths_skips_orphan_removal(tmp_path: Path) -> None:
    # A wrong or empty repo must not wipe the whole cache.
    backend = LocalFileSummaryCacheBackend(repo_path=tmp_path)
    backend.put_summary("auth/login.py:10:h1:summary", "LIVE")
    result = backend.prune(live_paths=set())
    assert result["entries_removed"] == 0
    assert backend.get_summary("auth/login.py:10:h1:summary") == "LIVE"


def test_config_local_ttl_seconds_loads(tmp_path: Path) -> None:
    _write(tmp_path / "redcon.toml", "[cache]\nlocal_ttl_seconds = 3600\n")
    cfg = load_config(tmp_path)
    assert cfg.cache.local_ttl_seconds == 3600
    # Default stays disabled.
    assert load_config(tmp_path / "other").cache.local_ttl_seconds == 0


def test_prune_preserves_entries_written_concurrently(tmp_path: Path) -> None:
    """An entry a concurrent process appends after prune loads is not discarded."""
    backend = LocalFileSummaryCacheBackend(repo_path=tmp_path)
    backend.put_summary("auth/login.py:1:h:summary", "LIVE")
    backend.put_summary("deleted/gone.py:1:g:summary", "ORPHAN")
    backend._save()

    # Simulate another process appending a fresh entry straight to the file
    # after this backend loaded its snapshot.
    cache_path = tmp_path / ".redcon_cache.json"
    disk = json.loads(cache_path.read_text())
    disk["summaries"]["auth/session.py:1:s:summary"] = "CONCURRENT"
    disk.setdefault("timestamps", {}).setdefault("summaries", {})["auth/session.py:1:s:summary"] = (
        backend._now()
    )
    cache_path.write_text(json.dumps(disk))

    result = backend.prune(live_paths={"auth/login.py", "auth/session.py"})

    on_disk = json.loads(cache_path.read_text())["summaries"]
    # The concurrently-added entry survives even though the backend never held it.
    assert "auth/session.py:1:s:summary" in on_disk
    # Live entry kept, orphan still removed.
    assert "auth/login.py:1:h:summary" in on_disk
    assert "deleted/gone.py:1:g:summary" not in on_disk
    assert result["orphaned"] == 1


def _run_cli(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


def test_cli_cache_prune_end_to_end(tmp_path: Path) -> None:
    _write(tmp_path / "auth" / "login.py", "def login(t):\n    return bool(t)\n")
    cache_path = tmp_path / ".redcon_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "summaries": {
                    "auth/login.py:10:h1:summary": "LIVE",
                    "deleted/gone.py:5:h2:summary": "ORPHAN",
                },
                "fragments": {},
                "slices": {},
                "timestamps": {"summaries": {}, "fragments": {}, "slices": {}},
            }
        )
    )
    # Dry run leaves the file untouched.
    before = cache_path.read_text()
    assert _run_cli(["cache", "prune", "--repo", str(tmp_path), "--dry-run"]) == 0
    assert cache_path.read_text() == before

    # Real run removes the orphan, keeps the live entry.
    assert _run_cli(["cache", "prune", "--repo", str(tmp_path)]) == 0
    remaining = json.loads(cache_path.read_text())["summaries"]
    assert "auth/login.py:10:h1:summary" in remaining
    assert "deleted/gone.py:5:h2:summary" not in remaining
