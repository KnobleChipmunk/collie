"""Argument parsing, exit codes (0/2/3/4/5), and the show/diff orchestration from design.md."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from collie import panes, setup
from collie.panes import (
    Herdr,
    HerdrError,
    choose_direction,
    find_code_pane,
    is_idle_shell,
    is_own_render,
    label_for,
    stop_renderers,
)
from collie.ranges import Excerpt, find_match, parse_excerpt
from collie.render import (
    bat_argv,
    diff_argvs,
    diff_subject,
    header_text,
    note_line,
    overflow,
    redraw_prefix,
    theme,
)
from collie.resident import resident_enabled, resident_terminal, stay_resident

MAX_EXCERPTS = 5
DEFAULT_CONTEXT = 30
MATCH_LEAD = 3


class CollieExit(Exception):
    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Plan:
    """What `show` or `diff` will render, fully validated, before any Herdr call."""

    render_args: list[str]
    subject: str
    excerpts: int
    count_lines: Callable[[], int]
    notes: list[str]


# helpers --------------------------------------------------------------------------------------


def clean_note(note: str | None) -> str | None:
    """One line, no control characters: the note is agent supplied text printed into a terminal."""
    if note is None:
        return None
    cleaned = " ".join("".join(c if c.isprintable() else " " for c in note).split())
    return cleaned or None


def option(name: str, value: str) -> list[str]:
    """`--name value`, or `--name=value` when the value could be read as a flag."""
    return [f"{name}={value}"] if value.startswith("-") else [name, value]


def read_lines(path: Path) -> list[str]:
    """Split on newline only: bat numbers lines by `\\n`, while `str.splitlines` also splits on \\x0c and others."""
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise CollieExit(2, f"collie: {name} is not on PATH; install it first")


def git_output(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


# preflight ------------------------------------------------------------------------------------


def plan_show(args: argparse.Namespace) -> Plan:
    if len(args.excerpts) > MAX_EXCERPTS:
        raise CollieExit(2, f"collie: at most {MAX_EXCERPTS} excerpts per call, got {len(args.excerpts)}")
    excerpts: list[Excerpt] = []
    for text in args.excerpts:
        try:
            parsed = parse_excerpt(text)
        except ValueError as exc:
            raise CollieExit(2, f"collie: {exc}") from exc
        path = parsed.path.expanduser() if str(parsed.path).startswith("~") else parsed.path
        path = (Path.cwd() / path).resolve()
        if not path.is_file():
            raise CollieExit(2, f"collie: no such file: {path}")
        excerpts.append(Excerpt(path, parsed.lines, parsed.highlights))

    notes: list[str] = []
    if args.match is not None:
        if len(excerpts) != 1 or excerpts[0].lines is not None or excerpts[0].highlights:
            raise CollieExit(2, "collie: --match takes exactly one file with no line range or highlight")
        if args.context < 1:
            raise CollieExit(2, "collie: --context must be at least 1")
        lines = read_lines(excerpts[0].path)
        found = find_match(lines, args.match)
        if found is None:
            raise CollieExit(2, f"collie: text not found in {excerpts[0].path}: {args.match!r}")
        first, count = found
        start = max(1, first - MATCH_LEAD)
        end = min(len(lines), first + args.context - 1)
        excerpts[0] = Excerpt(excerpts[0].path, (start, end), ((first, first),))
        if count > 1:
            notes.append(f"matched {count} times; showing the first, at line {first}")

    for ex in excerpts:  # e.g. an `@` in a parent directory: render would misread the path
        try:
            round_trips = parse_excerpt(ex.spec()) == ex
        except ValueError:
            round_trips = False
        if not round_trips:
            raise CollieExit(2, f"collie: cannot pass this path to the code pane unambiguously: {ex.path}")

    require_tool("bat")

    def count_lines() -> int:
        total = 0
        for ex in excerpts:
            length = len(read_lines(ex.path))
            if ex.lines is None:
                total += length
            else:
                total += max(0, min(ex.lines[1], length) - ex.lines[0] + 1)
        return total

    note = clean_note(args.note)
    render_args = ["show", *(ex.spec() for ex in excerpts)]
    if note:
        render_args += option("--note", note)
    return Plan(render_args, ", ".join(ex.subject() for ex in excerpts), len(excerpts), count_lines, notes)


def plan_diff(args: argparse.Namespace) -> Plan:
    require_tool("delta")
    require_tool("git")
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir() or git_output(repo, "rev-parse", "--is-inside-work-tree").returncode != 0:
        raise CollieExit(2, f"collie: not a git work tree: {repo}")
    rev = args.rev
    if rev is not None and (
        rev.startswith("-") or git_output(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").returncode
    ):
        raise CollieExit(2, f"collie: revision does not resolve to a commit: {rev}")

    paths: list[str] = args.path or []
    git_argv, _ = diff_argvs(repo, rev, paths, theme())

    def count_lines() -> int:
        done = subprocess.run(git_argv, capture_output=True, text=True, check=False)
        return len(done.stdout.splitlines())

    render_args = ["diff", *option("--repo", str(repo))]
    for path in paths:
        render_args += option("--path", path)
    note = clean_note(args.note)
    if note:
        render_args += option("--note", note)
    if rev:
        render_args.append(rev)
    return Plan(render_args, diff_subject(rev, paths), 1, count_lines, [])


# talking to Herdr -----------------------------------------------------------------------------


def require_herdr_env() -> str:
    caller = os.environ.get("HERDR_PANE_ID")
    if os.environ.get("HERDR_ENV") != "1" or not caller:
        raise CollieExit(3, "collie: not inside Herdr (HERDR_ENV=1 and HERDR_PANE_ID are required)")
    return caller


def await_idle(herdr: Herdr, pane: str, keep_waiting: Callable[[dict], bool]) -> dict | None:
    """None once `pane` is an idle shell; otherwise its process info when waiting stops or time runs out."""
    deadline = time.monotonic() + panes.BUSY_GRACE_MS / 1000
    while True:
        info = herdr.process_info(pane)
        if is_idle_shell(info):
            return None
        if not keep_waiting(info) or time.monotonic() >= deadline:
            return info
        time.sleep(panes.POLL_INTERVAL_S)


def stop_and_wait(herdr: Herdr, pane: str) -> dict | None:
    """None once the pane is an idle shell; else the process info that kept it busy.

    Collie's own render (resident or not) is waited out, with SIGTERM sent to a confirmed resident
    renderer; anything else in the foreground is the user's and gets no signal.
    """
    info = herdr.process_info(pane)
    if is_idle_shell(info):
        return None
    if not is_own_render(info):
        return info
    stop_renderers(info)
    # herdr briefly reports no foreground process between the renderer exiting and the prompt
    return await_idle(herdr, pane, lambda i: is_own_render(i) or not i.get("foreground_processes"))


def pane_rect(herdr: Herdr, pane: str) -> dict:
    for entry in herdr.layout(pane):
        if entry.get("pane_id") == pane:
            return entry.get("rect", {})
    return {}


def busy_exit(pane: str, info: dict) -> CollieExit:
    names = ", ".join(panes.foreground_names(info)) or "unknown"
    return CollieExit(4, f"collie: code pane {pane} is busy (foreground: {names}); sent it no input")


def create_code_pane(herdr: Herdr, caller: str, cwd: str) -> str:
    width = pane_rect(herdr, caller).get("width")
    direction = choose_direction(width) if isinstance(width, int) else "down"
    new = herdr.split(caller, direction, cwd)
    try:
        herdr.rename(new, label_for(caller))
        stuck = await_idle(herdr, new, lambda _info: True)
    except HerdrError:
        close_quietly(herdr, new)
        raise
    if stuck is not None:
        close_quietly(herdr, new)
        raise CollieExit(4, f"collie: new code pane {new} did not reach a prompt")
    return new


def close_quietly(herdr: Herdr, pane: str) -> None:
    try:
        herdr.close(pane)
    except HerdrError:
        pass


def deliver(plan: Plan) -> int:
    if os.environ.get("COLLIE") == "off":
        print("collie: disabled (COLLIE=off)")
        return 0
    caller = require_herdr_env()
    herdr = Herdr()
    caller_info = herdr.get(caller)
    tab_id = caller_info["tab_id"]
    existing = find_code_pane(herdr.list_panes(os.environ.get("HERDR_WORKSPACE_ID")), caller, tab_id)

    if existing is not None:
        code_pane = existing
        busy = stop_and_wait(herdr, code_pane)
        if busy is not None:
            raise busy_exit(code_pane, busy)
    else:
        code_pane = create_code_pane(herdr, caller, caller_info.get("cwd") or str(Path.cwd()))

    herdr.run(code_pane, shlex.join([sys.executable, "-m", "collie", "render", *plan.render_args]))

    message = f"shown in {code_pane}: {plan.subject}"
    height = pane_rect(herdr, code_pane).get("height")
    if isinstance(height, int):
        total = plan.count_lines()
        hidden = overflow(total, height, plan.excerpts)
        if hidden > 0:
            message += (
                f" (pane fits ~{max(0, total - hidden)} of {total} lines; the first {hidden} scrolled out of view)"
            )
    print(message)
    for line in plan.notes:
        print(line)
    return 0


# commands -------------------------------------------------------------------------------------


def cmd_show(args: argparse.Namespace) -> int:
    return deliver(plan_show(args))


def cmd_diff(args: argparse.Namespace) -> int:
    return deliver(plan_diff(args))


def cmd_close(_args: argparse.Namespace) -> int:
    if os.environ.get("COLLIE") == "off":
        print("collie: disabled (COLLIE=off)")
        return 0
    caller = require_herdr_env()
    herdr = Herdr()
    tab_id = herdr.get(caller)["tab_id"]
    code_pane = find_code_pane(herdr.list_panes(os.environ.get("HERDR_WORKSPACE_ID")), caller, tab_id)
    if code_pane is None:
        print("no code pane to close")
        return 0
    busy = stop_and_wait(herdr, code_pane)
    if busy is not None:
        raise busy_exit(code_pane, busy)
    herdr.close(code_pane)
    print(f"closed {code_pane}")
    return 0


def cmd_rule(_args: argparse.Namespace) -> int:
    if os.environ.get("COLLIE") == "off" or os.environ.get("HERDR_ENV") != "1":
        return 0
    print(resources.files("collie").joinpath("rule.md").read_text(encoding="utf-8").strip())
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    try:
        lines = setup.run_setup(args.dry_run)
    except (ValueError, TypeError, OSError) as exc:
        raise CollieExit(1, f"collie: setup failed: {exc}") from exc
    print("\n".join(lines))
    return 0


def run_render(draw: Callable[[], int]) -> int:
    """First draw, then on a terminal stay resident and redraw on resize (design.md)."""
    out = sys.stdout
    if not resident_enabled():
        out.write(redraw_prefix(shutil.get_terminal_size().lines))
        return draw()
    with resident_terminal() as state:
        out.write(redraw_prefix(shutil.get_terminal_size().lines))
        status = draw()
        if state.stop:
            return status
        return stay_resident(state, draw)


def cmd_render_show(args: argparse.Namespace) -> int:
    out = sys.stdout
    note = clean_note(args.note)
    excerpts: list[Excerpt] = []
    for text in args.excerpts:
        try:
            excerpts.append(parse_excerpt(text))
        except ValueError as exc:
            raise CollieExit(2, f"collie: {exc}") from exc

    def draw() -> int:
        status = 0
        for index, ex in enumerate(excerpts):
            out.write(note_line(header_text(ex.subject(), note if index == 0 else None)) + "\n\n")
            out.flush()
            argv = bat_argv(ex.path, ex.lines, list(ex.highlights), theme())
            status = subprocess.run(argv, check=False).returncode or status
        return status

    return run_render(draw)


def cmd_render_diff(args: argparse.Namespace) -> int:
    out = sys.stdout
    paths: list[str] = args.path or []
    git_argv, delta_argv = diff_argvs(Path(args.repo), args.rev, paths, theme())
    header = note_line(header_text(diff_subject(args.rev, paths), clean_note(args.note))) + "\n\n"

    def draw() -> int:
        out.write(header)
        out.flush()
        done = subprocess.run(git_argv, capture_output=True, check=False)
        if done.returncode != 0:
            sys.stderr.write(done.stderr.decode("utf-8", errors="replace"))
            return done.returncode
        if not done.stdout.strip():
            print("no changes")
            return 0
        return subprocess.run(delta_argv, input=done.stdout, check=False).returncode

    return run_render(draw)


# parser ---------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="collie", description="Show code in a Herdr pane instead of describing it.")
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="render 1 to 5 file excerpts")
    show.add_argument("excerpts", nargs="+", metavar="PATH[:N-M][@H-H,...]")
    show.add_argument("--note")
    show.add_argument("--match", help="find lines by text instead of numbers (one file, no range)")
    show.add_argument("--context", type=int, default=DEFAULT_CONTEXT)
    show.set_defaults(func=cmd_show)

    diff = sub.add_parser("diff", help="render a unified git diff")
    diff.add_argument("rev", nargs="?")
    diff.add_argument("--path", action="append")
    diff.add_argument("--note")
    diff.add_argument("--repo", default=".")
    diff.set_defaults(func=cmd_diff)

    close = sub.add_parser("close", help="close your idle code pane")
    close.set_defaults(func=cmd_close)

    rule = sub.add_parser("rule", help="print the agent rule (SessionStart hook)")
    rule.set_defaults(func=cmd_rule)

    setup_cmd = sub.add_parser("setup", help="link the skill, add the rule and hook for this machine")
    setup_cmd.add_argument("--dry-run", action="store_true")
    setup_cmd.set_defaults(func=cmd_setup)

    render = sub.add_parser("render", help="internal: runs inside the code pane")
    render_sub = render.add_subparsers(dest="kind", required=True)
    render_show = render_sub.add_parser("show")
    render_show.add_argument("excerpts", nargs="+")
    render_show.add_argument("--note")
    render_show.set_defaults(func=cmd_render_show)
    render_diff = render_sub.add_parser("diff")
    render_diff.add_argument("rev", nargs="?")
    render_diff.add_argument("--repo", required=True)
    render_diff.add_argument("--path", action="append")
    render_diff.add_argument("--note")
    render_diff.set_defaults(func=cmd_render_diff)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CollieExit as exc:
        if exc.message:
            print(exc.message, file=sys.stderr)
        return exc.code
    except HerdrError as exc:
        print(f"collie: herdr error {exc.code}: {exc.message}", file=sys.stderr)
        return 5
