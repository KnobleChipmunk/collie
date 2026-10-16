"""The resident renderer, driven through a real pseudo terminal (proposal.md fact 4)."""

import fcntl
import os
import pty
import select
import signal
import struct
import sys
import termios
import time
from pathlib import Path

import pytest

from conftest import FakeHerdr

SCROLL_PREFIX = b"\x1b[30S\x1b[H"  # redraw_prefix(30): the first draw only
CLEAR = b"\x1b[H\x1b[2J"


def winsize(cols: int, rows: int = 30) -> bytes:
    return struct.pack("HHHH", rows, cols, 0, 0)


class PtyRender:
    """`python -m collie render ...` on a pty that starts at `cols` x 30."""

    def __init__(self, args: list[str], env: dict[str, str], cols: int = 100) -> None:
        env = {k: v for k, v in env.items() if k not in {"COLUMNS", "LINES"}}
        pid, fd = pty.fork()
        if pid == 0:  # child: size the terminal before exec, so no resize races the first draw
            fcntl.ioctl(0, termios.TIOCSWINSZ, winsize(cols))
            os.execve(sys.executable, [sys.executable, "-m", "collie", "render", *args], env)
        self.pid, self.fd, self.buf, self.status = pid, fd, b"", None

    def _pump(self, timeout: float) -> None:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if ready:
            try:
                self.buf += os.read(self.fd, 4096)
            except OSError:
                pass

    def wait_for(self, token: bytes, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while token not in self.buf and time.monotonic() < deadline:
            self._pump(0.05)
        assert token in self.buf, f"{token!r} not seen in {self.buf[-400:]!r}"

    def read_for(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._pump(0.05)

    def resize(self, cols: int) -> None:
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize(cols))

    def exit_code(self, timeout: float = 3.0) -> int | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._pump(0.05)
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.status = status
                return os.waitstatus_to_exitcode(status)
        return None

    def close(self) -> None:
        if self.status is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
        os.close(self.fd)


@pytest.fixture
def spawn(herdr: FakeHerdr):
    started: list[PtyRender] = []

    def start(*args: str, cols: int = 100, extra_env: dict[str, str] | None = None) -> PtyRender:
        r = PtyRender(list(args), {**herdr.env, **(extra_env or {})}, cols)
        started.append(r)
        return r

    yield start
    for r in started:
        r.close()


def test_resize_redraws_at_new_width(spawn, source_file: Path) -> None:
    r = spawn("show", f"{source_file}:1-5")
    r.wait_for(b"BAT_COLS 100")
    mark = len(r.buf)
    r.resize(133)
    r.wait_for(b"BAT_COLS 133")
    after = r.buf[mark:]
    assert CLEAR in after
    assert r.buf.count(SCROLL_PREFIX) == 1  # a resize clears; it never scrolls another copy away
    assert b"\x1b[3J" not in r.buf  # scrollback is never wiped
    assert r.buf.count(b"example.py:1-5") == 2  # the same header, drawn again


def test_burst_of_resizes_redraws_once(spawn, source_file: Path) -> None:
    r = spawn("show", f"{source_file}:1-5")
    r.wait_for(b"BAT_COLS 100")
    for cols in (110, 120, 130, 140, 150):
        r.resize(cols)
        time.sleep(0.01)
    r.wait_for(b"BAT_COLS 150")
    r.read_for(0.6)
    assert r.buf.count(b"BAT_COLS") == 2


def test_diff_redraws_on_resize(spawn, git_repo: Path) -> None:
    r = spawn("diff", "--repo", str(git_repo))
    r.wait_for(b"DELTA_COLS 100")
    r.resize(140)
    r.wait_for(b"DELTA_COLS 140")


def test_any_key_exits_zero(spawn, source_file: Path) -> None:
    r = spawn("show", f"{source_file}:1-5")
    r.wait_for(b"BAT_COLS 100")
    assert r.exit_code(timeout=0.5) is None  # resident first, so the key is what ends it
    os.write(r.fd, b"x")
    assert r.exit_code() == 0


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_signals_exit_zero(spawn, source_file: Path, sig: signal.Signals) -> None:
    r = spawn("show", f"{source_file}:1-5")
    r.wait_for(b"BAT_COLS 100")
    assert r.exit_code(timeout=0.5) is None  # resident first, so the signal is what ends it
    os.kill(r.pid, sig)
    assert r.exit_code() == 0


def test_resident_off_draws_once(spawn, source_file: Path) -> None:
    r = spawn("show", f"{source_file}:1-5", extra_env={"COLLIE_RESIDENT": "off"})
    r.wait_for(b"BAT_COLS 100")
    assert r.exit_code() == 0


def test_stays_resident_without_input(spawn, source_file: Path) -> None:
    r = spawn("show", f"{source_file}:1-5")
    r.wait_for(b"BAT_COLS 100")
    assert r.exit_code(timeout=1.0) is None  # still running, waiting for a resize or a key
