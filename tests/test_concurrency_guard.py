"""The persistent store may only be owned by one Codicil process."""

import os
import subprocess
import sys


def test_second_process_is_refused(tmp_path):
    env = os.environ | {
        "CODICIL_REPO": str(tmp_path / "repo"),
        "CODICIL_STORE": str(tmp_path / "store"),
    }
    (tmp_path / "repo").mkdir()
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from codicil import server; import time; print('ready', flush=True); time.sleep(30)",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ready"

        contender = subprocess.run(
            [sys.executable, "-c", "from codicil import server"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert contender.returncode != 0
        assert "store is already in use" in contender.stderr
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_cli_refuses_cleanly_when_store_is_locked(tmp_path):
    """The `codicil` CLI entry point (not just a bare `import server`) must turn the
    store-lock RuntimeError into a one-line `codicil: ...` message, not a traceback —
    cli.main() imports server.py without a try/except around it."""
    env = os.environ | {
        "CODICIL_REPO": str(tmp_path / "repo"),
        "CODICIL_STORE": str(tmp_path / "store"),
    }
    (tmp_path / "repo").mkdir()
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from codicil import server; import time; print('ready', flush=True); time.sleep(30)",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ready"

        contender = subprocess.run(
            [sys.executable, "-m", "codicil.cli", "index", str(tmp_path / "repo")],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert contender.returncode != 0
        assert contender.stderr.strip() == (
            f"codicil: Codicil store is already in use: {tmp_path / 'store'}. "
            "Stop the other codicil process before starting another one."
        )
        assert "Traceback" not in contender.stderr
    finally:
        holder.terminate()
        holder.wait(timeout=10)
