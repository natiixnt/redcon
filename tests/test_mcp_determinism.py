"""End-to-end determinism checks for redcon over the MCP stdio transport.

These are marked ``e2e`` and deselected from the default test run (see the
``addopts`` in ``pyproject.toml``); run them with ``pytest -m e2e``. The stdio
test spawns the real ``redcon mcp serve`` process and speaks the MCP protocol
over it, so it requires the ``mcp`` extra (``pip install 'redcon[mcp]'``) and is
skipped when that package is absent.

What they pin down:

- redcon's packing is deterministic: the same task against the same repository
  yields byte-identical tool output, both across many calls in one server and
  across a fresh server process.
- The pack is cache-stable: an edit to a file that is not part of the packed
  context does not perturb the output, while an edit to a file that is part of
  it does. The engine-level test asserts the same contract directly on the
  ``prompt_cache_key`` that backs prompt caching.

The irrelevant-edit target is a file under ``build/`` (which redcon excludes),
not README: redcon packs README as legitimate context, so "irrelevant" here has
to mean "outside the pack's universe", not merely "a doc".
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

# A task that clearly points at the http/retry sources.
TASK = "add exponential backoff to the retry logic in the http client"
REPEATS = 100
_BUDGET_CALL = (
    "redcon_budget",
    {"files": ["retry.py", "client.py"], "task": TASK, "max_tokens": 4000, "repo": "."},
)
# A generated artifact under build/, which redcon excludes from packing by
# default. Editing it is a real "irrelevant" change: it never enters the pack,
# so it can never move the cache key. (redcon does pack README and other docs,
# so a README edit is not a safe stand-in for "irrelevant".)
_IRRELEVANT_REL = "build/generated.txt"


def _build_repo(root: Path) -> Path:
    """A small repository whose relevant code is unambiguous, plus a generated
    build artifact that redcon never packs (the irrelevant-edit target)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "build").mkdir()
    (root / _IRRELEVANT_REL).write_text("generated report v1\n", encoding="utf-8")
    (root / "retry.py").write_text(
        "import time\n\n\n"
        "def request_with_retry(client, url, retries=3, backoff=0.1):\n"
        "    last = None\n"
        "    for attempt in range(retries):\n"
        "        try:\n"
        "            return client.get(url)\n"
        "        except Exception as exc:\n"
        "            last = exc\n"
        "            time.sleep(backoff * (2 ** attempt))\n"
        "    raise last\n",
        encoding="utf-8",
    )
    (root / "client.py").write_text(
        "class HttpClient:\n"
        "    def __init__(self, base_url):\n"
        "        self.base_url = base_url\n\n"
        "    def get(self, path):\n"
        "        return (self.base_url, path)\n",
        encoding="utf-8",
    )
    (root / "helpers.py").write_text(
        "def slugify(text):\n    return text.strip().lower().replace(' ', '-')\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Widget\n\nInstall the widget and read the licence.\n",
        encoding="utf-8",
    )
    return root


def _selected_names(pack_result: dict) -> set[str]:
    files = pack_result.get("files_included") or [
        item.get("path", "") for item in pack_result.get("compressed_context", [])
    ]
    return {Path(p).name for p in files if p}


# --- Engine-level cache-key contract (no mcp package required) ---


def test_pack_cache_key_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    from redcon.engine import RedconEngine

    repo = _build_repo(tmp_path / "repo")
    engine = RedconEngine()

    def cache_key() -> str:
        return engine.pack(task=TASK, repo=str(repo), max_tokens=6000)["prompt_cache_key"]

    baseline = cache_key()
    assert baseline, "pack did not surface a prompt_cache_key"

    selected = _selected_names(engine.pack(task=TASK, repo=str(repo), max_tokens=6000))
    assert "retry.py" in selected, f"expected retry.py in the pack, got {selected}"
    assert "generated.txt" not in selected, (
        "the build artifact leaked into the pack; fixture is wrong"
    )

    # Determinism: the key never drifts across repeated packs.
    for _ in range(50):
        assert cache_key() == baseline

    # Irrelevant edit: a file that is not in the pack must not move the key.
    artifact = repo / _IRRELEVANT_REL
    artifact.write_text(
        artifact.read_text(encoding="utf-8") + "generated report v2\n", encoding="utf-8"
    )
    assert cache_key() == baseline

    # Relevant edit: changing a packed file must produce a new key.
    retry = repo / "retry.py"
    retry.write_text(
        retry.read_text(encoding="utf-8") + "\n\ndef jitter(seconds):\n    return seconds * 0.5\n",
        encoding="utf-8",
    )
    assert cache_key() != baseline


# --- MCP stdio transport determinism (requires the mcp extra) ---


async def _session_calls(repo: Path, calls: list[tuple[str, dict]]) -> tuple[list[str], list[str]]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    import redcon

    # The server runs with cwd=repo so redcon operates on the fixture, but it
    # must still import redcon from wherever it is installed; put that root on
    # PYTHONPATH (a no-op when redcon is already importable from any directory).
    redcon_root = str(Path(redcon.__file__).resolve().parent.parent)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [redcon_root, env.get("PYTHONPATH", "")]))
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "redcon", "mcp", "serve"],
        cwd=str(repo),
        env=env,
    )
    outputs: list[str] = []
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        listing = await session.list_tools()
        names = [tool.name for tool in listing.tools]
        for tool, args in calls:
            result = await session.call_tool(tool, args)
            text = "".join(
                getattr(part, "text", "")
                for part in result.content
                if getattr(part, "type", "") == "text"
            )
            outputs.append(text)
    return names, outputs


def test_mcp_stdio_pack_is_deterministic_and_cache_stable(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    repo = _build_repo(tmp_path / "repo")

    async def drive() -> dict:
        names, base = await _session_calls(repo, [_BUDGET_CALL] * REPEATS)
        _, restart = await _session_calls(repo, [_BUDGET_CALL])

        artifact = repo / _IRRELEVANT_REL
        artifact.write_text(
            artifact.read_text(encoding="utf-8") + "generated report v2\n",
            encoding="utf-8",
        )
        _, after_irrelevant = await _session_calls(repo, [_BUDGET_CALL])

        (repo / "retry.py").write_text(
            (repo / "retry.py").read_text(encoding="utf-8")
            + "\n\ndef jitter(seconds):\n    return seconds * 0.5\n",
            encoding="utf-8",
        )
        _, after_relevant = await _session_calls(repo, [_BUDGET_CALL])
        return {
            "names": names,
            "base": base,
            "restart": restart[0],
            "after_irrelevant": after_irrelevant[0],
            "after_relevant": after_relevant[0],
        }

    out = asyncio.run(drive())

    # The stdio server advertises the packing tools.
    assert {"redcon_rank", "redcon_budget", "redcon_repo_map"} <= set(out["names"])

    # Byte-identical across every call in one server process.
    assert len(set(out["base"])) == 1, "pack output drifted across repeated calls"
    baseline = out["base"][0]
    assert baseline, "empty tool output"

    # Byte-identical across a fresh server process.
    assert out["restart"] == baseline

    # Irrelevant edit (a build artifact redcon never packs) leaves output unchanged.
    assert out["after_irrelevant"] == baseline

    # Relevant edit (retry.py, in the pack) changes the output.
    assert out["after_relevant"] != baseline
