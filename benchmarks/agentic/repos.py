"""The repositories the corpus is pinned to.

redcon is mined at its release tag; the two external repositories are permissive
(BSD-3-Clause) Python projects with long, small-commit histories and strong test
suites, pinned to a fixed SHA so the corpus never shifts under a re-clone. They
are cloned by the runner into a cache, not vendored into this repository.
"""

from __future__ import annotations

from corpus import RepoSpec

REPOS = (
    RepoSpec(name="redcon", ref="v1.15.0", url="https://github.com/natiixnt/redcon"),
    RepoSpec(
        name="httpx",
        ref="b5addb64f0161ff6bfe94c124ef76f6a1fba5254",
        url="https://github.com/encode/httpx",
    ),
    RepoSpec(
        name="click",
        ref="00e592cea702e0b2caa0dee42489fdb1c22cd845",
        url="https://github.com/pallets/click",
    ),
)
