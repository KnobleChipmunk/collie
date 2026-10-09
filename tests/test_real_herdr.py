"""Opt-in check against the real herdr and bat, to catch drift in tests/fakes/herdr.

Runs only when HERDR_ENV=1 and COLLIE_REAL_HERDR=1. Works in a scratch tab it creates without
focus and always closes, so the user's layout is untouched.
"""

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HERDR_ENV") != "1" or os.environ.get("COLLIE_REAL_HERDR") != "1",
    reason="real herdr check: set COLLIE_REAL_HERDR=1 inside Herdr",
)


def herdr(*args: str) -> dict:
    done = subprocess.run(["herdr", *args], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout)


def read_text(pane: str, source: str, lines: int = 400) -> str:
    """`herdr pane read` prints plain text, not JSON."""
    done = subprocess.run(
        ["herdr", "pane", "read", pane, "--source", source, "--lines", str(lines)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def wait_for_shell(pane: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        procs = herdr("pane", "process-info", "--pane", pane)["result"]["process_info"]["foreground_processes"]
        if procs and all(p["name"] in {"zsh", "bash", "fish", "sh", "nu", "dash"} for p in procs):
            return
        time.sleep(0.2)
    pytest.fail(f"{pane} never reached a shell prompt")


@pytest.fixture
def scratch_tab(tmp_path: Path) -> Iterator[tuple[str, str]]:
    created = herdr(
        "tab",
        "create",
        "--workspace",
        os.environ["HERDR_WORKSPACE_ID"],
        "--cwd",
        str(tmp_path),
        "--label",
        "collie-smoke",
        "--no-focus",
    )["result"]
    tab, root = created["tab"]["tab_id"], created["root_pane"]["pane_id"]
    try:
        wait_for_shell(root)
        yield tab, root
    finally:
        subprocess.run(["herdr", "tab", "close", tab], capture_output=True, check=False)


def collie(root: str, tab: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "HERDR_PANE_ID": root, "HERDR_TAB_ID": tab}
    env.pop("COLLIE", None)
    return subprocess.run([sys.executable, "-m", "collie", *args], env=env, capture_output=True, text=True, check=False)


def test_show_reuse_scrollback_close(scratch_tab: tuple[str, str], source_file: Path) -> None:
    tab, root = scratch_tab

    first = collie(root, tab, "show", f"{source_file}:1-10@3", "--note", "smoke one")
    assert first.returncode == 0, first.stderr
    found = re.search(r"shown in (\S+):", first.stdout)
    assert found, first.stdout
    code_pane = found.group(1)
    herdr("pane", "wait-output", code_pane, "--match", "line_10 = 10", "--timeout", "10000")

    second = collie(root, tab, "show", f"{source_file}:20-25")
    assert second.returncode == 0, second.stderr
    assert f"shown in {code_pane}:" in second.stdout
    herdr("pane", "wait-output", code_pane, "--match", "line_25 = 25", "--timeout", "10000")

    panes = [
        p
        for p in herdr("pane", "list", "--workspace", os.environ["HERDR_WORKSPACE_ID"])["result"]["panes"]
        if p["tab_id"] == tab
    ]
    assert len(panes) == 2  # one code pane, reused
    label = next(p for p in panes if p["pane_id"] == code_pane).get("label")
    assert label == f"collie:{root}"

    assert "example.py:20-25" in read_text(code_pane, "visible")
    assert "line_3 = 3" in read_text(code_pane, "recent")  # the first excerpt survives in scrollback

    wait_for_shell(code_pane)  # the render has exited; close does no grace wait
    closed = collie(root, tab, "close")
    assert closed.returncode == 0, closed.stderr
    remaining = [
        p["pane_id"]
        for p in herdr("pane", "list", "--workspace", os.environ["HERDR_WORKSPACE_ID"])["result"]["panes"]
        if p["tab_id"] == tab
    ]
    assert remaining == [root]
