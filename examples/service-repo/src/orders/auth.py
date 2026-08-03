"""Authentication for the orders service (a critical-path module)."""

from __future__ import annotations

from orders.errors import AuthError

_VALID_TOKENS = {"tok_admin": "admin", "tok_user": "user"}


def authenticate(token: str) -> str:
    """Return the role for a bearer token or raise AuthError."""
    role = _VALID_TOKENS.get(token)
    if role is None:
        raise AuthError("invalid or missing token")
    return role


def require_role(token: str, needed: str) -> None:
    """Raise AuthError unless the token grants at least the needed role."""
    role = authenticate(token)
    if needed == "admin" and role != "admin":
        raise AuthError("admin role required")
