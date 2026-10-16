"""The resident renderer: stay in the code pane after the first draw and redraw on resize (design.md)."""

import os
import select
import signal
import sys
import termios
import time
import tty
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

SETTLE_S = 0.15
REDRAW_CLEAR = "\x1b[H\x1b[2J"
POLL_S = 0.05
STOP_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)


@dataclass
class ResidentState:
    last_resize: float | None = None
    stop: bool = False


def resident_enabled() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("COLLIE_RESIDENT") != "off"


@contextmanager
def resident_terminal() -> Iterator[ResidentState]:
    state = ResidentState()
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)

    def on_resize(_signum: int, _frame: object) -> None:
        state.last_resize = time.monotonic()

    def on_stop(_signum: int, _frame: object) -> None:
        state.stop = True

    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGWINCH, *STOP_SIGNALS)}
    try:
        signal.signal(signal.SIGWINCH, on_resize)
        for sig in STOP_SIGNALS:
            signal.signal(sig, on_stop)
        tty.setcbreak(fd)
        yield state
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def stay_resident(state: ResidentState, draw: Callable[[], int]) -> int:
    fd = sys.stdin.fileno()
    while not state.stop:
        if state.last_resize is not None and time.monotonic() - state.last_resize >= SETTLE_S:
            state.last_resize = None  # a resize during this draw schedules the next one
            sys.stdout.write(REDRAW_CLEAR)
            sys.stdout.flush()
            draw()
            continue
        ready, _, _ = select.select([fd], [], [], POLL_S)
        if ready:
            os.read(fd, 1024)  # any key, or EOF, hands the pane back
            return 0
    return 0
