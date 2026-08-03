"""In-memory storage backend for the orders service."""

from __future__ import annotations

from typing import Any


class Database:
    """A tiny in-memory table keyed by string id."""

    def __init__(self) -> None:
        self._rows: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._rows.get(key)

    def put(self, key: str, value: Any) -> None:
        self._rows[key] = value

    def delete(self, key: str) -> bool:
        return self._rows.pop(key, None) is not None

    def all(self) -> list[Any]:
        return list(self._rows.values())
