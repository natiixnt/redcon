"""Bearer-token authentication for the Redcon Runtime Gateway.

Auth is enforced identically on both server implementations: FastAPI + uvicorn
when the ``[gateway]`` extra is installed, and the stdlib HTTP fallback (which
is what default CI runs, since ``[dev]`` does not pull FastAPI). Handlers are
mocked at the boundary so these tests exercise only routing and auth.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from redcon.gateway import GatewayConfig, GatewayServer

_CANNED_PREPARE = {
    "optimized_context": {"files": [], "prompt_text": "", "files_included": []},
    "token_estimate": 0,
    "cache_hits": 0,
}


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _canned_handlers() -> MagicMock:
    """A handlers double whose responses serialize to a fixed dict."""
    handlers = MagicMock()
    handlers.handle_prepare_context.return_value.as_dict.return_value = dict(_CANNED_PREPARE)
    handlers.handle_run_agent_step.return_value.as_dict.return_value = dict(_CANNED_PREPARE)
    handlers.handle_report_run.return_value.as_dict.return_value = {"acknowledged": True}
    return handlers


def _post(
    url: str, body: dict[str, Any], headers: dict[str, str] | None = None
) -> tuple[int, dict[str, Any]]:
    raw = json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json", "Content-Length": str(len(raw))}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=raw, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _wait_ready(base: str, timeout: float = 8.0) -> None:
    """Poll GET /health (unauthenticated on both paths) until the server binds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    raise RuntimeError(f"gateway did not become ready within {timeout}s")


@contextmanager
def _running_gateway(config: GatewayConfig):
    """Start a live gateway with mocked handlers; yield its base URL.

    Exercises whichever implementation is installed (FastAPI when present, the
    stdlib fallback otherwise), so the auth path is validated end-to-end.
    """
    srv = GatewayServer(config, handlers=_canned_handlers())
    srv.start(block=False)
    try:
        base = f"http://127.0.0.1:{config.port}"
        _wait_ready(base)
        yield base
    finally:
        srv.stop()


@contextmanager
def _fastapi_client(config: GatewayConfig):
    """Build the FastAPI app in-process (ASGI TestClient); skip without the extra."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from redcon.gateway.server import _build_fastapi_app

    app, _ = _build_fastapi_app(config, _canned_handlers())
    assert app is not None
    yield TestClient(app)


# ---------------------------------------------------------------------------
# Live server: auth enforced when api_key is set
# ---------------------------------------------------------------------------

_API_KEY = "s3cret-gateway-token"


class TestGatewayAuthLive:
    @pytest.fixture(autouse=True)
    def server(self):
        config = GatewayConfig(
            host="127.0.0.1", port=_free_port(), api_key=_API_KEY, log_requests=False
        )
        with _running_gateway(config) as base:
            self._base = base
            yield

    def test_missing_authorization_header_is_401(self):
        status, _ = _post(f"{self._base}/prepare-context", {"task": "x"})
        assert status == 401

    def test_non_bearer_scheme_is_401(self):
        # The right secret under the wrong scheme is still rejected.
        status, _ = _post(
            f"{self._base}/prepare-context",
            {"task": "x"},
            {"Authorization": f"Basic {_API_KEY}"},
        )
        assert status == 401

    def test_wrong_bearer_token_is_401(self):
        status, _ = _post(
            f"{self._base}/prepare-context",
            {"task": "x"},
            {"Authorization": "Bearer wrong-token"},
        )
        assert status == 401

    def test_trailing_space_token_is_401(self):
        # Locks in exact (constant-time) comparison: a one-char near-miss fails.
        status, _ = _post(
            f"{self._base}/prepare-context",
            {"task": "x"},
            {"Authorization": f"Bearer {_API_KEY} "},
        )
        assert status == 401

    def test_correct_bearer_token_is_200(self):
        status, body = _post(
            f"{self._base}/prepare-context",
            {"task": "x"},
            {"Authorization": f"Bearer {_API_KEY}"},
        )
        assert status == 200
        assert "optimized_context" in body

    def test_auth_gates_run_step_endpoint_too(self):
        no_key, _ = _post(f"{self._base}/run-step", {"task": "x"})
        assert no_key == 401
        ok, _ = _post(
            f"{self._base}/run-step",
            {"task": "x"},
            {"Authorization": f"Bearer {_API_KEY}"},
        )
        assert ok == 200


class TestGatewayAuthDisabledLive:
    def test_no_api_key_allows_unauthenticated_request(self):
        config = GatewayConfig(host="127.0.0.1", port=_free_port(), log_requests=False)
        with _running_gateway(config) as base:
            status, body = _post(f"{base}/prepare-context", {"task": "x"})
            assert status == 200
            assert "optimized_context" in body


# ---------------------------------------------------------------------------
# FastAPI path, in-process (deterministic; skipped without the [gateway] extra)
# ---------------------------------------------------------------------------


class TestGatewayFastAPIAuth:
    def test_valid_body_is_accepted_without_auth(self):
        # Regression guard: a param the annotation namespace cannot resolve makes
        # FastAPI 422 every POST before auth even runs. This pins that shut.
        config = GatewayConfig(api_key=None, log_requests=False)
        with _fastapi_client(config) as client:
            resp = client.post("/prepare-context", json={"task": "x"})
            assert resp.status_code == 200
            assert "optimized_context" in resp.json()

    def test_missing_header_is_401(self):
        config = GatewayConfig(api_key=_API_KEY, log_requests=False)
        with _fastapi_client(config) as client:
            assert client.post("/prepare-context", json={"task": "x"}).status_code == 401

    def test_wrong_token_is_401(self):
        config = GatewayConfig(api_key=_API_KEY, log_requests=False)
        with _fastapi_client(config) as client:
            resp = client.post(
                "/prepare-context",
                json={"task": "x"},
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert resp.status_code == 401

    def test_correct_token_is_200(self):
        config = GatewayConfig(api_key=_API_KEY, log_requests=False)
        with _fastapi_client(config) as client:
            resp = client.post(
                "/prepare-context",
                json={"task": "x"},
                headers={"Authorization": f"Bearer {_API_KEY}"},
            )
            assert resp.status_code == 200
            assert "optimized_context" in resp.json()

    def test_invalid_json_body_is_400(self):
        # Error contract matches the stdlib path: malformed body -> 400, not 422.
        config = GatewayConfig(api_key=None, log_requests=False)
        with _fastapi_client(config) as client:
            resp = client.post(
                "/prepare-context",
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 400

    def test_unknown_endpoint_is_404_with_error_body(self):
        config = GatewayConfig(api_key=None, log_requests=False)
        with _fastapi_client(config) as client:
            resp = client.post("/does-not-exist", json={"task": "x"})
            assert resp.status_code == 404
            assert "error" in resp.json()
