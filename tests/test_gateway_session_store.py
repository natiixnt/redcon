"""Gateway session persistence: SessionStore and the save/restore roundtrip.

Covers the Redis-backed and in-memory SessionStore, and locks in that a session
survives a save -> load -> restore cycle field-for-field - including
last_run_artifact, whose omission from as_dict() silently disabled auto-delta on
cross-replica resume.
"""

from __future__ import annotations

import sys

import pytest

from redcon.gateway.handlers import _restore_session
from redcon.gateway.session_store import SessionStore
from redcon.runtime.session import RuntimeSession


def test_as_dict_includes_last_run_artifact() -> None:
    session = RuntimeSession()
    session.last_run_artifact = {"files": ["a.py"]}
    assert session.as_dict()["last_run_artifact"] == {"files": ["a.py"]}


def test_session_survives_save_load_restore_roundtrip() -> None:
    # The bug guard: last_run_artifact (and every other field) must round-trip.
    session = RuntimeSession()
    session.cumulative_tokens = 1234
    session.turns = [{"task": "add caching"}]
    session.last_run_artifact = {"files": ["a.py"], "estimated_input_tokens": 5000}

    store = SessionStore()  # in-memory
    store.save(session.session_id, session.as_dict())
    loaded = store.load(session.session_id)
    assert loaded is not None

    restored = RuntimeSession()
    _restore_session(restored, loaded)

    assert restored.session_id == session.session_id
    assert restored.cumulative_tokens == 1234
    assert restored.turns == [{"task": "add caching"}]
    assert restored.last_run_artifact == {"files": ["a.py"], "estimated_input_tokens": 5000}


def test_in_memory_store_save_load_delete() -> None:
    store = SessionStore()
    assert store.is_distributed is False
    assert store.load("missing") is None

    store.save("s1", {"session_id": "s1", "cumulative_tokens": 7})
    assert store.load("s1") == {"session_id": "s1", "cumulative_tokens": 7}

    store.delete("s1")
    assert store.load("s1") is None
    store.delete("s1")  # deleting an absent key is a no-op


def test_in_memory_store_ping_is_true() -> None:
    assert SessionStore().ping() is True


def test_from_env_without_redis_url_is_in_memory(monkeypatch) -> None:
    monkeypatch.setattr("redcon.gateway.session_store._REDIS_URL", "")
    store = SessionStore.from_env()
    assert store.is_distributed is False


def test_missing_redis_package_falls_back_to_memory(monkeypatch) -> None:
    # `import redis` raising ImportError must not break the store.
    monkeypatch.setitem(sys.modules, "redis", None)
    store = SessionStore(redis_url="redis://localhost:6379/0")
    assert store.is_distributed is False
    store.save("s", {"session_id": "s"})
    assert store.load("s") == {"session_id": "s"}


# --- Redis-backed path via fakeredis (skipped if fakeredis absent) ---


def _redis_store() -> SessionStore:
    fakeredis = pytest.importorskip("fakeredis")
    store = SessionStore()
    store._redis = fakeredis.FakeRedis(decode_responses=True)
    store._using_redis = True
    return store


def test_redis_backed_store_roundtrip() -> None:
    store = _redis_store()
    assert store.is_distributed is True

    store.save("sid", {"session_id": "sid", "turns": [{"task": "x"}]})
    assert store.load("sid") == {"session_id": "sid", "turns": [{"task": "x"}]}

    assert store.ping() is True

    store.delete("sid")
    assert store.load("sid") is None


def test_redis_backed_store_uses_prefixed_key() -> None:
    store = _redis_store()
    store.save("abc", {"session_id": "abc"})
    # The documented key format is rc_session:<id>.
    assert store._redis.get("rc_session:abc") is not None
