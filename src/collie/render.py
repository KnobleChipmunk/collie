"""Pure helpers that build the bytes and argv the code pane renders."""

import os
from pathlib import Path

DEFAULT_THEME = "Catppuccin Mocha"
NOTE_RGB = (203, 166, 247)
EXCERPT_ROWS = 6
CHROME_ROWS = 8


def theme() -> str:
    return os.environ.get("COLLIE_THEME") or DEFAULT_THEME


def note_line(text: str) -> str:
    r, g, b = NOTE_RGB
    return f"\x1b[1;38;2;{r};{g};{b}m▶ {text}\x1b[0m"


def header_text(subject: str, note: str | None) -> str:
    return subject if note is None else f"{subject} · {note}"


def diff_subject(rev: str | None, paths: list[str]) -> str:
    subject = f"diff {rev}" if rev else "diff working tree"
    if paths:
        subject += " -- " + " ".join(paths)
    return subject


def overflow(content_lines: int, pane_height: int, excerpts: int = 1) -> int:
    """Rows of content that scroll out of view; a floor, since wrapped lines are not counted."""
    return max(0, content_lines + CHROME_ROWS + EXCERPT_ROWS * (excerpts - 1) - pane_height)


def redraw_prefix(rows: int) -> str:
    """Scroll the screen up by its height (output goes to scrollback), then home. Never clears history."""
    return f"\x1b[{rows}S\x1b[H"


def bat_argv(
    path: Path, line_range: tuple[int, int] | None, highlights: list[tuple[int, int]], theme: str
) -> list[str]:
    argv = ["bat", "--paging=never", "--color=always", f"--theme={theme}", "--style=numbers,grid,header"]
    if line_range is not None:
        argv.append(f"--line-range={line_range[0]}:{line_range[1]}")
    argv.extend(f"--highlight-line={a}:{b}" for a, b in highlights)
    argv.append(str(path))
    return argv


def diff_argvs(repo: Path, rev: str | None, paths: list[str], theme: str) -> tuple[list[str], list[str]]:
    git = ["git", "-C", str(repo), "-c", "core.pager=cat", "diff"]
    if rev:
        git.append(rev)
    git.append("--")
    git.extend(paths)
    delta = ["delta", "--no-gitconfig", "--paging=never", "--line-numbers", f"--syntax-theme={theme}"]
    return git, delta
