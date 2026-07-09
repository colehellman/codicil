"""Cross-process guard: ChromaDB's PersistentClient does not support concurrent
multi-process access to one store. `_live_server_pid`/`refuse_if_server_running`
detect a live `codicil serve` before a separate index/query process touches the
same store, instead of racing it into a crash.
"""

import os
import sys

import pytest

from codicil import cli, server


@pytest.fixture
def pid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PID_FILE", tmp_path / "server.pid")
    return tmp_path / "server.pid"


def test_no_pidfile_means_no_live_server(pid_file):
    assert server._live_server_pid() is None


def test_stale_pidfile_is_cleared(pid_file):
    pid_file.write_text("999999999")  # not a real PID on any real machine
    assert server._live_server_pid() is None
    assert not pid_file.exists()


def test_live_pidfile_is_detected(pid_file):
    pid_file.write_text(str(os.getpid()))
    assert server._live_server_pid() == os.getpid()


def test_refuse_if_server_running_exits_when_live(pid_file):
    pid_file.write_text(str(os.getpid()))
    with pytest.raises(SystemExit):
        server.refuse_if_server_running()


def test_refuse_if_server_running_passes_when_not_live(pid_file):
    assert server.refuse_if_server_running() is None


def test_serve_refuses_when_already_running(pid_file, monkeypatch):
    pid_file.write_text(str(os.getpid()))
    monkeypatch.setattr(server.mcp, "run", lambda: pytest.fail("must not reach mcp.run"))
    with pytest.raises(SystemExit):
        server.serve()


def test_serve_writes_pidfile(pid_file, monkeypatch):
    monkeypatch.setattr(server.mcp, "run", lambda: None)
    server.serve()
    assert pid_file.read_text() == str(os.getpid())


def test_cli_index_refuses_when_server_live(docs_repo, pid_file, monkeypatch):
    pid_file.write_text(str(os.getpid()))
    monkeypatch.setattr(sys, "argv", ["codicil", "index", str(docs_repo)])

    with pytest.raises(SystemExit):
        cli.main()


def test_cli_query_refuses_when_server_live(docs_repo, pid_file, monkeypatch):
    pid_file.write_text(str(os.getpid()))
    monkeypatch.setattr(sys, "argv", ["codicil", "query", "anything", "--repo", str(docs_repo)])

    with pytest.raises(SystemExit):
        cli.main()
