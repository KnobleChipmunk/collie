"""Herdr client and the pane decisions collie makes."""

import json
import os
import signal
import subprocess

LABEL_PREFIX = "collie:"
RIGHT_MIN_WIDTH = 160
SHELLS = {"zsh", "bash", "fish", "sh", "nu", "dash"}
RENDER_PROCS = {"bat", "delta", "git"}
RENDER_MARK = "-m collie render"
POLL_INTERVAL_S = 0.2
HERDR_TIMEOUT_S = 30


def _grace_ms() -> int:
    try:
        return int(os.environ.get("COLLIE_BUSY_GRACE_MS") or 2000)
    except ValueError:
        return 2000


BUSY_GRACE_MS = _grace_ms()


class HerdrError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def label_for(caller: str) -> str:
    return LABEL_PREFIX + caller


def find_code_pane(panes: list[dict], caller: str, tab_id: str) -> str | None:
    label = label_for(caller)
    for pane in panes:
        if pane.get("label") == label and pane.get("tab_id") == tab_id:
            return pane["pane_id"]
    return None


def choose_direction(width: int) -> str:
    return "right" if width >= RIGHT_MIN_WIDTH else "down"


def foreground_names(process_info: dict) -> list[str]:
    return [p.get("name", "") for p in process_info.get("foreground_processes", [])]


def is_idle_shell(process_info: dict) -> bool:
    names = foreground_names(process_info)
    return bool(names) and all(name in SHELLS for name in names)


def is_own_render(process_info: dict) -> bool:
    procs = process_info.get("foreground_processes", [])
    return bool(procs) and all(p.get("name") in RENDER_PROCS or RENDER_MARK in (p.get("cmdline") or "") for p in procs)


def renderer_pids(process_info: dict) -> list[int]:
    return [
        p["pid"]
        for p in process_info.get("foreground_processes", [])
        if RENDER_MARK in (p.get("cmdline") or "") and isinstance(p.get("pid"), int)
    ]


def is_collie_renderer(pid: int) -> bool:
    try:
        done = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and RENDER_MARK in done.stdout


def stop_renderers(process_info: dict) -> int:
    stopped = 0
    for pid in renderer_pids(process_info):
        if not is_collie_renderer(pid):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        stopped += 1
    return stopped


class Herdr:
    """Runs the `herdr` on PATH and returns the parsed `result` object."""

    def call(self, *args: str) -> dict:
        try:
            done = subprocess.run(
                ["herdr", *args], capture_output=True, text=True, check=False, timeout=HERDR_TIMEOUT_S
            )
        except FileNotFoundError as exc:
            raise HerdrError("herdr_not_found", "herdr is not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise HerdrError("timeout", f"herdr {' '.join(args[:2])} took over {HERDR_TIMEOUT_S}s") from exc
        if done.returncode == 0 and not done.stdout.strip():
            return {}  # `pane run` prints nothing on success (observed against herdr 0.8.0)
        try:
            payload = json.loads(done.stdout)
        except json.JSONDecodeError:
            payload = None
        if done.returncode != 0 or not isinstance(payload, dict) or "error" in payload:
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                raise HerdrError(str(error.get("code", "error")), str(error.get("message", "")))
            raise HerdrError("bad_output", f"herdr {' '.join(args[:2])}: " + (done.stderr or done.stdout).strip()[:200])
        return payload.get("result", {})

    def get(self, pane: str) -> dict:
        return self.call("pane", "get", pane)["pane"]

    def list_panes(self, workspace: str | None) -> list[dict]:
        extra = ["--workspace", workspace] if workspace else []
        return self.call("pane", "list", *extra)["panes"]

    def layout(self, pane: str) -> list[dict]:
        return self.call("pane", "layout", "--pane", pane)["layout"]["panes"]

    def process_info(self, pane: str) -> dict:
        return self.call("pane", "process-info", "--pane", pane)["process_info"]

    def split(self, pane: str, direction: str, cwd: str) -> str:
        result = self.call("pane", "split", "--pane", pane, "--direction", direction, "--cwd", cwd, "--no-focus")
        return result["pane"]["pane_id"]

    def rename(self, pane: str, label: str) -> None:
        self.call("pane", "rename", pane, label)

    def run(self, pane: str, command: str) -> None:
        self.call("pane", "run", pane, command)

    def close(self, pane: str) -> None:
        self.call("pane", "close", pane)
