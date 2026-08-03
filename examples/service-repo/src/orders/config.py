"""Runtime settings for the orders service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    currency: str = "USD"
    max_items_per_order: int = 50
    allow_guest_checkout: bool = False


def load_settings() -> Settings:
    """Return default settings. Real deployments would read the environment."""
    return Settings()
