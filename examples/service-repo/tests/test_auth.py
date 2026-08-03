import pytest

from orders.auth import authenticate, require_role
from orders.errors import AuthError


def test_authenticate_valid():
    assert authenticate("tok_admin") == "admin"


def test_require_admin_rejects_user():
    with pytest.raises(AuthError):
        require_role("tok_user", "admin")
