"""Test config: point Codicil at throwaway temp dirs and provide clean-state fixtures.

Tests never touch a real embedding host — embed()/embed_many() are mocked with
deterministic fake vectors so the whole suite runs offline (and in CI).
"""

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

# Configure Codicil BEFORE importing the server module (it reads env at import time).
_TMP = Path(tempfile.mkdtemp(prefix="codicil-test-"))
os.environ["CODICIL_REPO"] = str(_TMP / "repo")
os.environ["CODICIL_STORE"] = str(_TMP / "store")
os.environ.setdefault("CODICIL_EMBED_MODEL", "nomic-embed-text")
(_TMP / "repo").mkdir(parents=True, exist_ok=True)

from codicil import server  # noqa: E402


def fake_vec(text: str, dim: int = 16) -> list[float]:
    """Deterministic pseudo-embedding — same text always yields the same vector."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in h[:dim]]


@pytest.fixture(autouse=True)
def clean_index(tmp_path, monkeypatch):
    """Give each test a fresh state file and an empty collection."""
    monkeypatch.setattr(server, "STATE_FILE", tmp_path / "index_state.json")
    ids = server.collection.get().get("ids", [])
    if ids:
        server.collection.delete(ids=ids)
    yield
    ids = server.collection.get().get("ids", [])
    if ids:
        server.collection.delete(ids=ids)


@pytest.fixture
def docs_repo(tmp_path, monkeypatch):
    """A throwaway repo directory that server functions read from."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(server, "REPO_PATH", repo)
    return repo


@pytest.fixture
def fake_embed(monkeypatch):
    """Replace real embedding calls with offline deterministic vectors."""
    monkeypatch.setattr(server, "embed", lambda text, kind="query": fake_vec(text))
    monkeypatch.setattr(server, "embed_many", lambda texts: [fake_vec(t) for t in texts])
