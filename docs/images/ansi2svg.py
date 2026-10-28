"""Render a captured ANSI pane snapshot to an SVG terminal window (Catppuccin Mocha chrome)."""

import sys
from pathlib import Path

from rich.console import Console
from rich.terminal_theme import TerminalTheme
from rich.text import Text

MOCHA = TerminalTheme(
    (30, 30, 46),
    (205, 214, 244),
    [
        (69, 71, 90),
        (243, 139, 168),
        (166, 227, 161),
        (249, 226, 175),
        (137, 180, 250),
        (245, 194, 231),
        (148, 226, 213),
        (186, 194, 222),
    ],
    [
        (88, 91, 112),
        (243, 139, 168),
        (166, 227, 161),
        (249, 226, 175),
        (137, 180, 250),
        (245, 194, 231),
        (148, 226, 213),
        (166, 173, 200),
    ],
)


def main(src: Path, dst: Path, title: str) -> None:
    lines = src.read_text(encoding="utf-8", errors="replace").replace(str(Path.home()), "~").rstrip("\n").split("\n")
    while lines and not Text.from_ansi(lines[-1]).plain.strip():
        lines.pop()
    width = max(len(Text.from_ansi(line).plain.rstrip()) for line in lines) + 2
    with open("/dev/null", "w") as sink:
        console = Console(record=True, width=width, file=sink, color_system="truecolor")
        console.print(Text.from_ansi("\n".join(lines)), soft_wrap=True)
        console.save_svg(str(dst), title=title, theme=MOCHA)
    print(dst, width, "cols", len(lines), "rows")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
